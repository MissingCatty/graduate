#!/usr/bin/env python3

"""Task-aware exploration policy using task hints plus minimal object-memory cues."""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from dataclasses import asdict, dataclass
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
from src.memory.object_memory import (  # noqa: E402
    ObjectMemory,
    SemanticObject,
    canonicalize_category,
)
from src.memory.occupancy_map import OccupancyMap  # noqa: E402
from src.policies.base_policy import PolicyDecision, PolicyInput  # noqa: E402
from src.policies.frontier_policy import (  # noqa: E402
    FrontierPolicy,
    FrontierPolicyConfig,
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
from src.policies.task_parser import ParsedTask, parse_task  # noqa: E402


DEFAULT_OUTPUT = Path("outputs/runs/task_aware_policy_preview.json")


@dataclass(frozen=True)
class TaskAwarePolicyConfig:
    seed: int = 13
    turn_threshold_deg: float = 18.0
    frontier_limit: int = 64
    collision_cooldown_steps: int = 2
    observed_object_weight: float = 2.5
    scene_prior_weight: float = 1.15
    frontier_distance_penalty: float = 0.22
    relevance_distance_offset: float = 0.65

    def to_frontier_config(self) -> FrontierPolicyConfig:
        return FrontierPolicyConfig(
            seed=self.seed,
            turn_threshold_deg=self.turn_threshold_deg,
            frontier_limit=self.frontier_limit,
            collision_cooldown_steps=self.collision_cooldown_steps,
        )

def build_object_memory_context(
    memory: ObjectMemory,
    relevant_categories: set[str],
    *,
    preview_limit: int = 8,
) -> dict[str, Any]:
    entries = sorted(
        memory.entries.values(),
        key=lambda entry: (-entry.observation_count, entry.category, entry.object_id),
    )
    relevant_entries = [entry for entry in entries if entry.category in relevant_categories]
    observed_categories = sorted({entry.category for entry in entries})

    return {
        "num_observed_objects": len(entries),
        "num_observed_categories": len(observed_categories),
        "observed_categories": observed_categories,
        "relevant_hint_categories": sorted(relevant_categories),
        "relevant_entry_count": len(relevant_entries),
        "relevant_observed_categories": sorted({entry.category for entry in relevant_entries}),
        "relevant_entries": [
            {
                "object_id": entry.object_id,
                "category": entry.category,
                "region_id": entry.region_id,
                "center_xyz": list(entry.center_xyz),
                "observation_count": int(entry.observation_count),
                "last_seen_step": int(entry.last_seen_step),
                "min_distance_m": round(float(entry.min_distance_m), 4),
            }
            for entry in relevant_entries[:preview_limit]
        ],
    }


class TaskAwarePolicy(FrontierPolicy):
    """Frontier policy augmented with task-hint and object-memory relevance scoring."""

    name = "task_aware"

    def __init__(
        self,
        scene_objects: Sequence[SemanticObject],
        config: Optional[TaskAwarePolicyConfig] = None,
    ) -> None:
        self.task_config = config or TaskAwarePolicyConfig()
        super().__init__(self.task_config.to_frontier_config())
        self._scene_objects = list(scene_objects)
        self._parsed_task: Optional[ParsedTask] = None
        self._hint_categories: set[str] = set()
        self._relevant_scene_objects: list[SemanticObject] = []
        self._last_target_metadata: dict[str, Any] = {}

    def config_dict(self) -> dict[str, Any]:
        return asdict(self.task_config)

    def reset(
        self,
        *,
        action_space: Sequence[str],
        task: Optional[Mapping[str, Any]] = None,
    ) -> None:
        super().reset(action_space=action_space, task=task)
        task = task or {}
        self._parsed_task = parse_task(task)
        self._hint_categories = set(self._parsed_task.hint_categories)
        self._relevant_scene_objects = [
            obj for obj in self._scene_objects if obj.category in self._hint_categories
        ]
        self._last_target_metadata = {}

    def _candidate_centers_from_memory(
        self,
        object_memory_summary: Optional[Mapping[str, Any]],
    ) -> list[list[float]]:
        if not object_memory_summary:
            return []
        relevant_entries = object_memory_summary.get("relevant_entries") or []
        centers: list[list[float]] = []
        for entry in relevant_entries:
            center = entry.get("center_xyz")
            if isinstance(center, list) and len(center) >= 3:
                centers.append([float(center[0]), float(center[1]), float(center[2])])
        return centers

    def _score_frontier(
        self,
        frontier_cell: tuple[int, int],
        *,
        current_world: np.ndarray,
        cell_size: float,
        observed_centers: Sequence[Sequence[float]],
    ) -> tuple[float, dict[str, Any]]:
        frontier_world = self._cell_center_world(frontier_cell, cell_size)
        frontier_distance = float(np.linalg.norm(frontier_world[[0, 2]] - current_world[[0, 2]]))

        best_observed = 0.0
        for center_xyz in observed_centers:
            center = np.asarray([float(center_xyz[0]), 0.0, float(center_xyz[2])], dtype=np.float64)
            distance = float(np.linalg.norm(frontier_world[[0, 2]] - center[[0, 2]]))
            best_observed = max(
                best_observed,
                self.task_config.observed_object_weight
                / (distance + self.task_config.relevance_distance_offset),
            )

        best_prior = 0.0
        for obj in self._relevant_scene_objects:
            center = np.asarray([obj.center_xyz[0], 0.0, obj.center_xyz[2]], dtype=np.float64)
            distance = float(np.linalg.norm(frontier_world[[0, 2]] - center[[0, 2]]))
            best_prior = max(
                best_prior,
                self.task_config.scene_prior_weight
                / (distance + self.task_config.relevance_distance_offset),
            )

        score = best_observed + best_prior - (
            self.task_config.frontier_distance_penalty * frontier_distance
        )
        return score, {
            "frontier_distance_m": round(frontier_distance, 4),
            "observed_relevance_score": round(best_observed, 4),
            "scene_prior_score": round(best_prior, 4),
            "combined_score": round(score, 4),
        }

    def _choose_task_aware_frontier(
        self,
        *,
        current_cell: tuple[int, int],
        frontier_cells: Sequence[tuple[int, int]],
        current_world: np.ndarray,
        cell_size: float,
        object_memory_summary: Optional[Mapping[str, Any]],
    ) -> tuple[Optional[tuple[int, int]], dict[str, Any]]:
        candidates = [cell for cell in frontier_cells if cell != current_cell]
        if not candidates:
            return None, {
                "selection_source": "no_frontier",
                "hint_categories": sorted(self._hint_categories),
            }

        observed_centers = self._candidate_centers_from_memory(object_memory_summary)
        if not observed_centers and not self._relevant_scene_objects:
            target = super()._choose_target_frontier(current_cell, list(candidates))
            return target, {
                "selection_source": "frontier_fallback",
                "hint_categories": sorted(self._hint_categories),
            }

        ranked: list[tuple[float, tuple[int, int], dict[str, Any]]] = []
        for cell in candidates:
            score, metadata = self._score_frontier(
                cell,
                current_world=current_world,
                cell_size=cell_size,
                observed_centers=observed_centers,
            )
            ranked.append((score, cell, metadata))

        ranked.sort(
            key=lambda item: (
                -item[0],
                item[2]["frontier_distance_m"],
                item[1][0],
                item[1][1],
            )
        )
        best_score, best_cell, best_meta = ranked[0]
        best_meta.update(
            {
                "selection_source": (
                    "observed_memory_guided" if observed_centers else "scene_prior_guided"
                ),
                "hint_categories": sorted(self._hint_categories),
                "relevant_scene_object_count": len(self._relevant_scene_objects),
                "relevant_observed_entry_count": 0 if object_memory_summary is None else int(
                    object_memory_summary.get("relevant_entry_count", 0)
                ),
                "selected_frontier_score": round(best_score, 4),
            }
        )
        return best_cell, best_meta

    def act(self, policy_input: PolicyInput) -> PolicyDecision:
        actions = list(policy_input.action_space or self._action_space)
        if not actions:
            raise RuntimeError("TaskAwarePolicy.act() called before reset()")

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

        current_world = np.asarray(
            [float(policy_input.position[0]), 0.0, float(policy_input.position[2])],
            dtype=np.float64,
        )
        target_frontier, selection_meta = self._choose_task_aware_frontier(
            current_cell=current_cell_tuple,
            frontier_cells=frontier_cells,
            current_world=current_world,
            cell_size=cell_size,
            object_memory_summary=policy_input.object_memory_summary,
        )
        self._last_target_metadata = dict(selection_meta)

        if target_frontier is None:
            fallback_action = "move_forward" if "move_forward" in actions else actions[0]
            return PolicyDecision(
                action=fallback_action,
                reason="task_aware_frontier_unavailable_fallback",
                metadata={
                    "frontier_count": len(frontier_cells),
                    "current_cell": list(current_cell_tuple),
                    **selection_meta,
                    "task_id": None if self._task is None else self._task.get("task_id"),
                },
            )

        self._target_frontier = target_frontier
        target_world = self._cell_center_world(target_frontier, cell_size)
        target_offset = target_world - current_world
        target_distance_m = float(np.linalg.norm(target_offset[[0, 2]]))
        signed_angle_deg = self._signed_angle_deg(
            self._forward_vector(policy_input.rotation_wxyz),
            target_offset,
        )

        if policy_input.last_action_collided and policy_input.last_action == "move_forward":
            chosen_action = self._collision_recovery_action(signed_angle_deg)
            reason = "task_aware_collision_recovery"
        elif self._collision_cooldown > 0:
            self._collision_cooldown -= 1
            chosen_action = self._fallback_turn if abs(signed_angle_deg) <= 5.0 else (
                "turn_left" if signed_angle_deg > 0.0 else "turn_right"
            )
            reason = "task_aware_collision_cooldown"
        elif abs(signed_angle_deg) > self.config.turn_threshold_deg:
            chosen_action = "turn_left" if signed_angle_deg > 0.0 else "turn_right"
            reason = "task_aware_heading_alignment"
        else:
            chosen_action = "move_forward" if "move_forward" in actions else actions[0]
            reason = "task_aware_advance"

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
                **selection_meta,
            },
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a minimal task-aware exploration rollout with shared policy interfaces."
    )
    parser.add_argument("--steps", type=int, default=24)
    parser.add_argument("--seed", type=int, default=13)
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
    parsed_task = parse_task(selected_task)

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

    object_memory = ObjectMemory.from_scene(
        scene_dataset_config=args.scene_dataset_config,
        scene_path=scene_path,
        width=args.width,
        height=args.height,
        sensor_height=args.sensor_height,
        hfov=args.hfov,
    )
    hint_categories = set(parsed_task.hint_categories)

    policy = TaskAwarePolicy(
        scene_objects=object_memory.objects,
        config=TaskAwarePolicyConfig(
            seed=args.seed,
            turn_threshold_deg=args.turn_threshold_deg,
            frontier_limit=args.frontier_limit,
            collision_cooldown_steps=args.collision_cooldown_steps,
        ),
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
        object_memory.observe_pose(
            step_index=0,
            agent_position=initial_state.position.tolist(),
            rotation_wxyz=[
                float(v) for v in quaternion.as_float_array(initial_state.rotation)
            ],
        )

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
            object_memory_context = build_object_memory_context(
                object_memory,
                hint_categories,
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
                object_memory_summary=object_memory_context,
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

            object_memory.observe_pose(
                step_index=step_idx + 1,
                agent_position=current_position,
                rotation_wxyz=[
                    float(v) for v in quaternion.as_float_array(next_state.rotation)
                ],
            )

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
        payload["object_memory_summary"] = build_object_memory_context(
            object_memory,
            hint_categories,
            preview_limit=12,
        )
        payload["task_aware_summary"] = {
            "parsed_task": parsed_task.to_dict(),
            "hint_categories": sorted(hint_categories),
            "relevant_scene_object_count": len(policy._relevant_scene_objects),
            "relevant_scene_category_counts": dict(
                Counter(obj.category for obj in policy._relevant_scene_objects).most_common(12)
            ),
        }

        args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"saved: {args.output}")
        print(f"task_id: {payload['task']['task_id']}")
        print(f"steps_executed: {payload['steps_executed']}")
        print(f"collision_count: {payload['collision_count']}")
    finally:
        sim.close()


if __name__ == "__main__":
    main()
