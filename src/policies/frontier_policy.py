#!/usr/bin/env python3

"""Frontier-style exploration policy using the minimal occupancy map."""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

import habitat_sim
import numpy as np
import quaternion

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.run_minimal_trajectory import (  # noqa: E402
    DEFAULT_DATASET_CONFIG,
    DEFAULT_SCENE,
    build_config,
)
from src.memory.occupancy_map import OccupancyMap  # noqa: E402
from src.policies.base_policy import (  # noqa: E402
    BaseExplorationPolicy,
    PolicyDecision,
    PolicyInput,
)
from src.policies.rollout_utils import (  # noqa: E402
    DEFAULT_TASKS,
    build_episode_payload,
    build_occupancy_context,
    load_tasks_payload,
    observation_summary,
    select_task,
    state_to_dict,
)


DEFAULT_OUTPUT = Path("outputs/runs/frontier_policy_preview.json")


@dataclass(frozen=True)
class FrontierPolicyConfig:
    seed: int = 11
    turn_threshold_deg: float = 18.0
    frontier_limit: int = 64
    collision_cooldown_steps: int = 2

    def __post_init__(self) -> None:
        if not 0.0 <= self.turn_threshold_deg <= 180.0:
            raise ValueError("turn_threshold_deg must be within [0, 180]")
        if self.frontier_limit <= 0:
            raise ValueError("frontier_limit must be positive")
        if self.collision_cooldown_steps < 0:
            raise ValueError("collision_cooldown_steps must be non-negative")


class FrontierPolicy(BaseExplorationPolicy):
    """Minimal frontier-driven policy that expands toward unexplored boundaries."""

    name = "frontier"

    def __init__(self, config: Optional[FrontierPolicyConfig] = None) -> None:
        self.config = config or FrontierPolicyConfig()
        self.rng = random.Random(self.config.seed)
        self._action_space: list[str] = []
        self._task: Optional[Mapping[str, Any]] = None
        self._target_frontier: Optional[tuple[int, int]] = None
        self._collision_cooldown: int = 0
        self._fallback_turn: str = "turn_left"

    def reset(
        self,
        *,
        action_space: Sequence[str],
        task: Optional[Mapping[str, Any]] = None,
    ) -> None:
        if not action_space:
            raise ValueError("action_space must not be empty")
        self.rng = random.Random(self.config.seed)
        self._action_space = list(action_space)
        self._task = task
        self._target_frontier = None
        self._collision_cooldown = 0
        self._fallback_turn = self.rng.choice(["turn_left", "turn_right"])

    def _forward_vector(self, rotation_wxyz: Sequence[float]) -> np.ndarray:
        quat = quaternion.from_float_array(np.asarray(rotation_wxyz, dtype=np.float64))
        forward = quaternion.rotate_vectors(quat, np.array([0.0, 0.0, -1.0], dtype=np.float64))
        norm = float(np.linalg.norm(forward))
        if norm == 0.0:
            raise ValueError("Forward vector norm is zero; invalid rotation")
        return forward / norm

    def _world_to_cell(self, position: Sequence[float], cell_size: float) -> tuple[int, int]:
        return (
            int(math.floor(float(position[0]) / cell_size)),
            int(math.floor(float(position[2]) / cell_size)),
        )

    def _cell_center_world(self, cell: Sequence[int], cell_size: float) -> np.ndarray:
        half = cell_size * 0.5
        return np.asarray(
            [
                (float(cell[0]) * cell_size) + half,
                0.0,
                (float(cell[1]) * cell_size) + half,
            ],
            dtype=np.float64,
        )

    def _signed_angle_deg(
        self,
        forward_vector: np.ndarray,
        target_vector: np.ndarray,
    ) -> float:
        forward = np.asarray([forward_vector[0], 0.0, forward_vector[2]], dtype=np.float64)
        target = np.asarray([target_vector[0], 0.0, target_vector[2]], dtype=np.float64)
        forward_norm = float(np.linalg.norm(forward))
        target_norm = float(np.linalg.norm(target))
        if forward_norm == 0.0 or target_norm == 0.0:
            return 0.0
        forward = forward / forward_norm
        target = target / target_norm
        dot = float(np.clip(np.dot(forward, target), -1.0, 1.0))
        det = float((forward[2] * target[0]) - (forward[0] * target[2]))
        return math.degrees(math.atan2(det, dot))

    def _choose_target_frontier(
        self,
        current_cell: tuple[int, int],
        frontier_cells: list[tuple[int, int]],
    ) -> Optional[tuple[int, int]]:
        candidates = [cell for cell in frontier_cells if cell != current_cell]
        if not candidates:
            return None

        if self._target_frontier in candidates:
            return self._target_frontier

        def score(cell: tuple[int, int]) -> tuple[float, int, int]:
            dx = cell[0] - current_cell[0]
            dz = cell[1] - current_cell[1]
            return (math.hypot(dx, dz), cell[0], cell[1])

        return min(candidates, key=score)

    def _collision_recovery_action(self, signed_angle_deg: float) -> str:
        if signed_angle_deg > 1.0:
            action = "turn_left"
        elif signed_angle_deg < -1.0:
            action = "turn_right"
        else:
            action = self._fallback_turn

        self._fallback_turn = "turn_right" if action == "turn_left" else "turn_left"
        self._collision_cooldown = self.config.collision_cooldown_steps
        return action

    def act(self, policy_input: PolicyInput) -> PolicyDecision:
        actions = list(policy_input.action_space or self._action_space)
        if not actions:
            raise RuntimeError("FrontierPolicy.act() called before reset()")

        occupancy_summary = dict(policy_input.occupancy_summary or {})
        cell_size = float(occupancy_summary.get("cell_size", 0.25))
        current_cell = occupancy_summary.get("current_cell")
        if current_cell is None:
            current_cell = list(self._world_to_cell(policy_input.position, cell_size))
        current_cell_tuple = (int(current_cell[0]), int(current_cell[1]))

        frontier_cells_raw = occupancy_summary.get("frontier_cells") or occupancy_summary.get(
            "frontier_preview_cells"
        ) or []
        frontier_cells = [
            (int(cell[0]), int(cell[1]))
            for cell in frontier_cells_raw
            if isinstance(cell, (list, tuple)) and len(cell) == 2
        ]

        target_frontier = self._choose_target_frontier(current_cell_tuple, frontier_cells)
        if target_frontier is None:
            fallback_action = "move_forward" if "move_forward" in actions else actions[0]
            return PolicyDecision(
                action=fallback_action,
                reason="frontier_unavailable_fallback",
                metadata={
                    "frontier_count": len(frontier_cells),
                    "current_cell": list(current_cell_tuple),
                    "task_id": None if self._task is None else self._task.get("task_id"),
                },
            )

        self._target_frontier = target_frontier
        current_world = np.asarray(
            [float(policy_input.position[0]), 0.0, float(policy_input.position[2])],
            dtype=np.float64,
        )
        target_world = self._cell_center_world(target_frontier, cell_size)
        target_offset = target_world - current_world
        target_distance_m = float(np.linalg.norm(target_offset[[0, 2]]))
        signed_angle_deg = self._signed_angle_deg(
            self._forward_vector(policy_input.rotation_wxyz),
            target_offset,
        )

        if policy_input.last_action_collided and policy_input.last_action == "move_forward":
            chosen_action = self._collision_recovery_action(signed_angle_deg)
            reason = "frontier_collision_recovery"
        elif self._collision_cooldown > 0:
            self._collision_cooldown -= 1
            chosen_action = self._fallback_turn if abs(signed_angle_deg) <= 5.0 else (
                "turn_left" if signed_angle_deg > 0.0 else "turn_right"
            )
            reason = "frontier_collision_cooldown"
        elif abs(signed_angle_deg) > self.config.turn_threshold_deg:
            chosen_action = "turn_left" if signed_angle_deg > 0.0 else "turn_right"
            reason = "frontier_heading_alignment"
        else:
            chosen_action = "move_forward" if "move_forward" in actions else actions[0]
            reason = "frontier_advance"

        if chosen_action not in actions:
            chosen_action = actions[0]

        return PolicyDecision(
            action=chosen_action,
            reason=reason,
            metadata={
                "task_id": None if self._task is None else self._task.get("task_id"),
                "frontier_count": len(frontier_cells),
                "current_cell": list(current_cell_tuple),
                "target_frontier_cell": list(target_frontier),
                "target_distance_m": round(target_distance_m, 4),
                "signed_angle_deg": round(signed_angle_deg, 4),
                "collision_cooldown_remaining": self._collision_cooldown,
            },
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a minimal frontier exploration rollout with the shared policy interface."
    )
    parser.add_argument("--steps", type=int, default=24)
    parser.add_argument("--seed", type=int, default=11)
    parser.add_argument("--task-index", type=int, default=0)
    parser.add_argument("--task-id", type=str, default=None)
    parser.add_argument("--tasks", type=Path, default=DEFAULT_TASKS)
    parser.add_argument(
        "--scene-dataset-config",
        type=Path,
        default=Path(DEFAULT_DATASET_CONFIG),
    )
    parser.add_argument("--scene", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--width", type=int, default=320)
    parser.add_argument("--height", type=int, default=240)
    parser.add_argument("--sensor-height", type=float, default=1.5)
    parser.add_argument("--hfov", type=float, default=90.0)
    parser.add_argument("--turn-threshold-deg", type=float, default=18.0)
    parser.add_argument("--frontier-limit", type=int, default=64)
    parser.add_argument("--collision-cooldown-steps", type=int, default=2)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.steps <= 0:
        raise ValueError("--steps must be positive")

    tasks_payload = load_tasks_payload(args.tasks)
    selected_task = select_task(tasks_payload, task_index=args.task_index, task_id=args.task_id)

    scene_path = Path(args.scene) if args.scene is not None else Path(
        selected_task.get("scene_path") or DEFAULT_SCENE
    )
    if not scene_path.exists():
        raise FileNotFoundError(f"Missing scene file: {scene_path}")
    if not args.scene_dataset_config.exists():
        raise FileNotFoundError(f"Missing dataset config: {args.scene_dataset_config}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    sim_args = argparse.Namespace(
        scene_dataset_config=args.scene_dataset_config,
        scene=scene_path,
        width=args.width,
        height=args.height,
        sensor_height=args.sensor_height,
        hfov=args.hfov,
    )

    policy = FrontierPolicy(
        FrontierPolicyConfig(
            seed=args.seed,
            turn_threshold_deg=args.turn_threshold_deg,
            frontier_limit=args.frontier_limit,
            collision_cooldown_steps=args.collision_cooldown_steps,
        )
    )
    occupancy_map = OccupancyMap()

    sim = habitat_sim.Simulator(build_config(sim_args))
    try:
        agent = sim.initialize_agent(0)
        start_state = agent.get_state()
        if sim.pathfinder.is_loaded:
            start_state.position = sim.pathfinder.get_random_navigable_point()
            agent.set_state(start_state)

        initial_state = agent.get_state()
        initial_observations = sim.get_sensor_observations()
        occupancy_map.add_observation(initial_state.position.tolist())

        action_space = list(agent.agent_config.action_space.keys())
        policy.reset(action_space=action_space, task=selected_task)

        trajectory: list[dict[str, Any]] = []
        previous_position = initial_state.position.tolist()
        last_action: Optional[str] = None
        last_action_collided = False

        for step_idx in range(args.steps):
            current_state = agent.get_state()
            occupancy_context = build_occupancy_context(
                occupancy_map,
                current_state.position,
                frontier_limit=args.frontier_limit,
            )
            policy_input = PolicyInput(
                step_index=step_idx + 1,
                max_steps=args.steps,
                action_space=action_space,
                position=[float(v) for v in current_state.position],
                rotation_wxyz=[
                    float(v) for v in quaternion.as_float_array(current_state.rotation)
                ],
                last_action=last_action,
                last_action_collided=last_action_collided,
                task=selected_task,
                occupancy_summary=occupancy_context,
                object_memory_summary=None,
            )
            decision = policy.act(policy_input)
            observations = sim.step(decision.action)
            next_state = agent.get_state()

            current_position = next_state.position.tolist()
            occupancy_map.add_observation(
                current_position,
                previous_position=previous_position,
            )
            previous_position = current_position

            step_summary = observation_summary(observations)
            last_action = decision.action
            last_action_collided = bool(step_summary["collided"])

            trajectory.append(
                {
                    "step": step_idx + 1,
                    "decision": decision.to_dict(),
                    "state": state_to_dict(next_state),
                    "observation_summary": step_summary,
                }
            )

        payload = build_episode_payload(
            args=args,
            selected_task=selected_task,
            policy=policy,
            initial_state=initial_state,
            initial_observations=initial_observations,
            final_state=agent.get_state(),
            action_space=action_space,
            trajectory=trajectory,
            occupancy_map=occupancy_map,
            scene_path=scene_path,
        )
        args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"saved: {args.output}")
        print(f"task_id: {payload['task']['task_id']}")
        print(f"steps_executed: {payload['steps_executed']}")
        print(f"collision_count: {payload['collision_count']}")
    finally:
        sim.close()


if __name__ == "__main__":
    main()
