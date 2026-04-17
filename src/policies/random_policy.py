#!/usr/bin/env python3

"""Random exploration policy plus a runnable Habitat smoke-rollout entrypoint."""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter
from dataclasses import dataclass, field
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


DEFAULT_TASKS = Path("outputs/tasks/tasks.json")
DEFAULT_OUTPUT = Path("outputs/runs/random_policy_preview.json")


@dataclass(frozen=True)
class RandomPolicyConfig:
    seed: int = 7
    action_weights: dict[str, float] = field(
        default_factory=lambda: {
            "move_forward": 1.0,
            "turn_left": 1.0,
            "turn_right": 1.0,
        }
    )

    def __post_init__(self) -> None:
        if not self.action_weights:
            raise ValueError("action_weights must not be empty")
        for action, weight in self.action_weights.items():
            if weight < 0.0:
                raise ValueError(f"Action weight must be non-negative: {action}={weight}")


class RandomPolicy(BaseExplorationPolicy):
    """Uniform-or-weighted random baseline for exploration."""

    name = "random"

    def __init__(self, config: Optional[RandomPolicyConfig] = None) -> None:
        self.config = config or RandomPolicyConfig()
        self.rng = random.Random(self.config.seed)
        self._action_space: list[str] = []
        self._task: Optional[Mapping[str, Any]] = None

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

    def act(self, policy_input: PolicyInput) -> PolicyDecision:
        actions = list(policy_input.action_space or self._action_space)
        if not actions:
            raise RuntimeError("RandomPolicy.act() called before reset()")

        weights = [float(self.config.action_weights.get(action, 1.0)) for action in actions]
        if not any(weight > 0.0 for weight in weights):
            raise ValueError("All candidate action weights are zero")

        chosen_index = self.rng.choices(range(len(actions)), weights=weights, k=1)[0]
        chosen_action = actions[chosen_index]
        return PolicyDecision(
            action=chosen_action,
            reason="weighted_random_baseline",
            metadata={
                "sampled_index": chosen_index,
                "sampled_weight": weights[chosen_index],
                "policy_seed": self.config.seed,
                "task_id": None if self._task is None else self._task.get("task_id"),
            },
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a minimal random exploration rollout with a unified policy interface."
    )
    parser.add_argument("--steps", type=int, default=24)
    parser.add_argument("--seed", type=int, default=7)
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
    return parser.parse_args()


def load_tasks_payload(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Missing tasks file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def select_task(
    payload: Mapping[str, Any],
    *,
    task_index: int = 0,
    task_id: Optional[str] = None,
) -> Mapping[str, Any]:
    tasks = payload.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("Task payload must contain a non-empty 'tasks' list")

    if task_id is not None:
        for task in tasks:
            if task.get("task_id") == task_id:
                return task
        raise KeyError(f"Task id not found: {task_id}")

    if not 0 <= task_index < len(tasks):
        raise IndexError(f"task_index out of range: {task_index}")
    return tasks[task_index]


def state_to_dict(state: habitat_sim.AgentState) -> dict[str, Any]:
    return {
        "position": [float(v) for v in state.position],
        "rotation_wxyz": [float(v) for v in quaternion.as_float_array(state.rotation)],
    }


def observation_summary(observations: Mapping[str, Any]) -> dict[str, Any]:
    semantic = np.asarray(observations["semantic_sensor"])
    depth = np.asarray(observations["depth_sensor"])
    color = np.asarray(observations["color_sensor"])
    return {
        "sensor_keys": sorted(observations.keys()),
        "color_shape": list(color.shape),
        "depth_shape": list(depth.shape),
        "semantic_shape": list(semantic.shape),
        "depth_min": float(depth.min()),
        "depth_max": float(depth.max()),
        "semantic_unique_count": int(np.unique(semantic).size),
        "semantic_min": int(semantic.min()),
        "semantic_max": int(semantic.max()),
        "collided": bool(observations.get("collided", False)),
    }


def compact_task_view(task: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "task_id": task.get("task_id"),
        "task_type": task.get("task_type"),
        "question": task.get("question"),
        "gt_answer": task.get("gt_answer"),
        "task_spec": task.get("task_spec"),
    }


def build_episode_payload(
    *,
    args: argparse.Namespace,
    selected_task: Mapping[str, Any],
    policy: RandomPolicy,
    initial_state: habitat_sim.AgentState,
    initial_observations: Mapping[str, Any],
    final_state: habitat_sim.AgentState,
    action_space: Sequence[str],
    trajectory: list[dict[str, Any]],
    occupancy_map: OccupancyMap,
    scene_path: Path,
) -> dict[str, Any]:
    action_counts = Counter(step["decision"]["action"] for step in trajectory)
    collision_count = sum(1 for step in trajectory if step["observation_summary"]["collided"])

    return {
        "policy_name": policy.name,
        "policy_config": policy.config_dict(),
        "seed": args.seed,
        "steps_requested": args.steps,
        "steps_executed": len(trajectory),
        "task": compact_task_view(selected_task),
        "scene_dataset_config": str(args.scene_dataset_config.resolve()),
        "scene": str(scene_path.resolve()),
        "action_space": list(action_space),
        "action_counts": dict(action_counts),
        "collision_count": collision_count,
        "initial_state": state_to_dict(initial_state),
        "final_state": state_to_dict(final_state),
        "initial_observation_summary": observation_summary(initial_observations),
        "occupancy_summary": occupancy_map.summary(),
        "trajectory": trajectory,
    }


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
        raise FileNotFoundError(
            f"Missing dataset config: {args.scene_dataset_config}"
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)

    sim_args = argparse.Namespace(
        scene_dataset_config=args.scene_dataset_config,
        scene=scene_path,
        width=args.width,
        height=args.height,
        sensor_height=args.sensor_height,
        hfov=args.hfov,
    )

    policy = RandomPolicy(RandomPolicyConfig(seed=args.seed))
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
                occupancy_summary=occupancy_map.summary(frontier_preview_limit=6),
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
