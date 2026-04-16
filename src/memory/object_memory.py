#!/usr/bin/env python3

"""Minimal object memory built from Habitat GT semantic objects and agent poses."""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

import habitat_sim
import numpy as np
import quaternion

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.run_minimal_trajectory import build_config


STRUCTURE_CATEGORIES = {
    "unknown",
    "wall",
    "floor",
    "ceiling",
    "door",
    "door frame",
    "door/window",
    "door/window frame",
    "window",
    "window frame",
    "window shutter",
    "recessed wall",
    "compound wall",
    "bar",
    "lamp",
    "picture",
    "art frame",
    "mirror",
    "decoration",
    "blinds",
    "stairs",
    "stairs railing",
    "ceiling dome",
    "shower ceiling",
    "wall panel",
    "glass",
}


def canonicalize_category(name: str) -> str:
    return " ".join(name.strip().lower().split())


@dataclass(frozen=True)
class ObjectMemoryConfig:
    observation_radius_m: float = 2.5
    horizontal_fov_deg: float = 110.0
    max_height_diff_m: float = 2.5
    min_bbox_size_m: float = 1e-4
    ignore_structure: bool = True

    def __post_init__(self) -> None:
        if self.observation_radius_m <= 0.0:
            raise ValueError("observation_radius_m must be positive")
        if not 0.0 < self.horizontal_fov_deg <= 360.0:
            raise ValueError("horizontal_fov_deg must be in (0, 360]")
        if self.max_height_diff_m < 0.0:
            raise ValueError("max_height_diff_m must be non-negative")
        if self.min_bbox_size_m < 0.0:
            raise ValueError("min_bbox_size_m must be non-negative")


@dataclass(frozen=True)
class SemanticObject:
    object_id: str
    category: str
    region_id: str
    center_xyz: List[float]
    size_xyz: List[float]


@dataclass
class ObjectMemoryEntry:
    object_id: str
    category: str
    region_id: str
    center_xyz: List[float]
    size_xyz: List[float]
    first_seen_step: int
    last_seen_step: int
    first_seen_agent_position: List[float]
    last_seen_agent_position: List[float]
    observation_count: int = 0
    observed_step_ids: List[int] = field(default_factory=list)
    min_distance_m: float = math.inf

    def observe(self, step_index: int, agent_position: Sequence[float], distance_m: float) -> None:
        if self.observation_count == 0:
            self.first_seen_step = step_index
            self.first_seen_agent_position = [float(v) for v in agent_position]
        self.last_seen_step = step_index
        self.last_seen_agent_position = [float(v) for v in agent_position]
        self.observation_count += 1
        self.observed_step_ids.append(step_index)
        self.min_distance_m = min(self.min_distance_m, float(distance_m))

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["min_distance_m"] = round(float(self.min_distance_m), 4)
        return payload


class ObjectMemory:
    """Accumulate semantic objects observed across agent poses."""

    def __init__(
        self,
        objects: Iterable[SemanticObject],
        config: Optional[ObjectMemoryConfig] = None,
    ) -> None:
        self.config = config or ObjectMemoryConfig()
        self.objects: List[SemanticObject] = list(objects)
        self.entries: Dict[str, ObjectMemoryEntry] = {}
        self.total_pose_updates = 0

    @classmethod
    def from_scene(
        cls,
        scene_dataset_config: Path,
        scene_path: Path,
        *,
        width: int = 320,
        height: int = 240,
        sensor_height: float = 1.5,
        hfov: float = 90.0,
        config: Optional[ObjectMemoryConfig] = None,
    ) -> "ObjectMemory":
        config = config or ObjectMemoryConfig()
        sim_args = argparse.Namespace(
            scene_dataset_config=scene_dataset_config,
            scene=scene_path,
            width=width,
            height=height,
            sensor_height=sensor_height,
            hfov=hfov,
        )
        sim = habitat_sim.Simulator(build_config(sim_args))
        try:
            semantic_objects: List[SemanticObject] = []
            for obj in sim.semantic_scene.objects:
                category = canonicalize_category(obj.category.name())
                if config.ignore_structure and category in STRUCTURE_CATEGORIES:
                    continue

                size = np.asarray(obj.aabb.size(), dtype=np.float32)
                center = np.asarray(obj.aabb.center(), dtype=np.float32)
                if not np.isfinite(size).all() or not np.isfinite(center).all():
                    continue
                if float(np.linalg.norm(size)) <= config.min_bbox_size_m:
                    continue

                semantic_objects.append(
                    SemanticObject(
                        object_id=str(obj.id),
                        category=category,
                        region_id=obj.region.id if obj.region is not None else "_-1",
                        center_xyz=[float(v) for v in center.tolist()],
                        size_xyz=[float(v) for v in size.tolist()],
                    )
                )
        finally:
            sim.close()

        return cls(semantic_objects, config=config)

    def _forward_vector(self, rotation_wxyz: Sequence[float]) -> np.ndarray:
        quat = quaternion.from_float_array(np.asarray(rotation_wxyz, dtype=np.float64))
        forward = quaternion.rotate_vectors(quat, np.array([0.0, 0.0, -1.0], dtype=np.float64))
        norm = float(np.linalg.norm(forward))
        if norm == 0.0:
            raise ValueError("Forward vector norm is zero; invalid rotation")
        return forward / norm

    def _is_observed(
        self,
        obj: SemanticObject,
        agent_position: np.ndarray,
        forward_vector: np.ndarray,
    ) -> tuple[bool, float, float]:
        center = np.asarray(obj.center_xyz, dtype=np.float64)
        offset = center - agent_position
        height_diff = abs(float(offset[1]))
        planar_offset = np.array([offset[0], 0.0, offset[2]], dtype=np.float64)
        planar_distance = float(np.linalg.norm(planar_offset))

        if planar_distance <= 1e-6:
            return True, 0.0, 0.0
        if planar_distance > self.config.observation_radius_m:
            return False, planar_distance, 180.0
        if height_diff > self.config.max_height_diff_m:
            return False, planar_distance, 180.0

        direction = planar_offset / planar_distance
        cosine = float(np.clip(np.dot(forward_vector, direction), -1.0, 1.0))
        angle_deg = math.degrees(math.acos(cosine))
        is_visible = angle_deg <= (self.config.horizontal_fov_deg * 0.5)
        return is_visible, planar_distance, angle_deg

    def observe_pose(
        self,
        *,
        step_index: int,
        agent_position: Sequence[float],
        rotation_wxyz: Sequence[float],
    ) -> int:
        self.total_pose_updates += 1
        agent_position_array = np.asarray(agent_position, dtype=np.float64)
        forward_vector = self._forward_vector(rotation_wxyz)

        observed_count = 0
        for obj in self.objects:
            is_visible, planar_distance, _ = self._is_observed(
                obj,
                agent_position_array,
                forward_vector,
            )
            if not is_visible:
                continue

            entry = self.entries.get(obj.object_id)
            if entry is None:
                entry = ObjectMemoryEntry(
                    object_id=obj.object_id,
                    category=obj.category,
                    region_id=obj.region_id,
                    center_xyz=list(obj.center_xyz),
                    size_xyz=list(obj.size_xyz),
                    first_seen_step=step_index,
                    last_seen_step=step_index,
                    first_seen_agent_position=[float(v) for v in agent_position],
                    last_seen_agent_position=[float(v) for v in agent_position],
                )
                self.entries[obj.object_id] = entry

            entry.observe(step_index, agent_position, planar_distance)
            observed_count += 1

        return observed_count

    def update_from_trajectory_payload(self, payload: dict[str, object]) -> dict[str, int]:
        observed_per_step: List[int] = []

        initial_state = payload["initial_state"]
        observed_per_step.append(
            self.observe_pose(
                step_index=0,
                agent_position=initial_state["position"],
                rotation_wxyz=initial_state["rotation_wxyz"],
            )
        )
        for step in payload["trajectory"]:
            observed_per_step.append(
                self.observe_pose(
                    step_index=int(step["step"]),
                    agent_position=step["state"]["position"],
                    rotation_wxyz=step["state"]["rotation_wxyz"],
                )
            )

        return {
            "num_pose_updates": len(observed_per_step),
            "num_steps_with_any_observation": sum(count > 0 for count in observed_per_step),
            "max_objects_seen_in_single_step": max(observed_per_step, default=0),
        }

    def summary(self, preview_limit: int = 10) -> dict[str, object]:
        entries = sorted(
            self.entries.values(),
            key=lambda entry: (-entry.observation_count, entry.category, entry.object_id),
        )
        category_counts = Counter(entry.category for entry in entries)
        region_counts = Counter(entry.region_id for entry in entries)

        return {
            "num_candidate_objects": len(self.objects),
            "num_observed_objects": len(entries),
            "num_observed_categories": len(category_counts),
            "num_observed_regions": len(region_counts),
            "category_counts": dict(category_counts.most_common(20)),
            "region_counts": dict(region_counts.most_common(20)),
            "preview_entries": [entry.to_dict() for entry in entries[:preview_limit]],
        }

    def to_dict(self) -> dict[str, object]:
        entries = sorted(
            self.entries.values(),
            key=lambda entry: (entry.first_seen_step, entry.category, entry.object_id),
        )
        return {
            "config": asdict(self.config),
            "summary": self.summary(),
            "entries": [entry.to_dict() for entry in entries],
        }


def load_trajectory_payload(path: Path) -> dict[str, object]:
    if not path.exists():
        raise FileNotFoundError(f"Missing trajectory file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a preview object memory from a Habitat trajectory payload."
    )
    parser.add_argument(
        "--trajectory",
        type=Path,
        default=Path("outputs/runs/minimal_demo_trajectory.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("outputs/runs/object_memory_preview.json"),
    )
    parser.add_argument("--observation-radius", type=float, default=2.5)
    parser.add_argument("--horizontal-fov-deg", type=float, default=110.0)
    parser.add_argument("--max-height-diff", type=float, default=2.5)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = load_trajectory_payload(args.trajectory)

    memory = ObjectMemory.from_scene(
        scene_dataset_config=Path(str(payload["scene_dataset_config"])),
        scene_path=Path(str(payload["scene"])),
        config=ObjectMemoryConfig(
            observation_radius_m=args.observation_radius,
            horizontal_fov_deg=args.horizontal_fov_deg,
            max_height_diff_m=args.max_height_diff,
        ),
    )
    trajectory_stats = memory.update_from_trajectory_payload(payload)
    memory_payload = memory.to_dict()
    memory_payload["trajectory"] = {
        "input_path": str(args.trajectory.resolve()),
        "scene": str(payload["scene"]),
        "scene_dataset_config": str(payload["scene_dataset_config"]),
        **trajectory_stats,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(memory_payload, indent=2), encoding="utf-8")
    print(f"saved: {args.output}")
    print(f"num_candidate_objects: {memory_payload['summary']['num_candidate_objects']}")
    print(f"num_observed_objects: {memory_payload['summary']['num_observed_objects']}")
    print(f"num_observed_categories: {memory_payload['summary']['num_observed_categories']}")


if __name__ == "__main__":
    main()
