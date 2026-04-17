"""Reusable helpers for lightweight policy rollouts."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

import habitat_sim
import numpy as np
import quaternion

from src.memory.occupancy_map import OccupancyMap
from src.policies.base_policy import BaseExplorationPolicy


DEFAULT_TASKS = Path("outputs/tasks/tasks.json")


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


def build_occupancy_context(
    occupancy_map: OccupancyMap,
    position: Sequence[float],
    *,
    frontier_limit: Optional[int] = None,
) -> dict[str, Any]:
    frontier_cells = occupancy_map.frontier_cells()
    summary = occupancy_map.summary(
        frontier_preview_limit=len(frontier_cells)
        if frontier_limit is None
        else max(frontier_limit, 1)
    )
    if frontier_limit is not None:
        frontier_cells = frontier_cells[:frontier_limit]

    summary["current_cell"] = list(occupancy_map.world_to_cell(position))
    summary["frontier_cells"] = [[cell[0], cell[1]] for cell in frontier_cells]
    return summary


def build_episode_payload(
    *,
    args: Any,
    selected_task: Mapping[str, Any],
    policy: BaseExplorationPolicy,
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
