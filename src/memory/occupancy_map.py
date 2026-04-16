#!/usr/bin/env python3

"""Minimal 2D occupancy/exploration memory for trajectory-driven exploration."""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, List, Optional, Sequence, Tuple

import numpy as np


UNKNOWN = 0
FREE = 1
OCCUPIED = 2

GridCell = Tuple[int, int]


@dataclass(frozen=True)
class OccupancyMapConfig:
    cell_size: float = 0.25
    explored_radius: float = 0.75
    padding_cells: int = 4

    def __post_init__(self) -> None:
        if self.cell_size <= 0.0:
            raise ValueError("cell_size must be positive")
        if self.explored_radius < 0.0:
            raise ValueError("explored_radius must be non-negative")
        if self.padding_cells < 0:
            raise ValueError("padding_cells must be non-negative")


class OccupancyMap:
    """Sparse occupancy map that can be updated from world positions."""

    def __init__(self, config: Optional[OccupancyMapConfig] = None) -> None:
        self.config = config or OccupancyMapConfig()
        self.explored_cells: set[GridCell] = set()
        self.free_cells: set[GridCell] = set()
        self.occupied_cells: set[GridCell] = set()
        self.visit_counts: Counter[GridCell] = Counter()

    def world_to_cell(self, position: Sequence[float]) -> GridCell:
        if len(position) >= 3:
            x_coord = float(position[0])
            z_coord = float(position[2])
        elif len(position) == 2:
            x_coord = float(position[0])
            z_coord = float(position[1])
        else:
            raise ValueError("position must have length 2 or 3")

        return (
            int(math.floor(x_coord / self.config.cell_size)),
            int(math.floor(z_coord / self.config.cell_size)),
        )

    def cell_to_world(self, cell: GridCell, y_coord: float = 0.0) -> List[float]:
        x_index, z_index = cell
        half = self.config.cell_size * 0.5
        return [
            (x_index * self.config.cell_size) + half,
            float(y_coord),
            (z_index * self.config.cell_size) + half,
        ]

    def _cells_in_disk(self, center: GridCell, radius_m: float) -> Iterator[GridCell]:
        if radius_m <= 0.0:
            yield center
            return

        radius_cells = max(1, int(math.ceil(radius_m / self.config.cell_size)))
        x_center, z_center = center
        for x_offset in range(-radius_cells, radius_cells + 1):
            for z_offset in range(-radius_cells, radius_cells + 1):
                if (x_offset * x_offset) + (z_offset * z_offset) > (radius_cells * radius_cells):
                    continue
                yield (x_center + x_offset, z_center + z_offset)

    def mark_free(self, position: Sequence[float], radius_m: Optional[float] = None) -> GridCell:
        radius_m = self.config.explored_radius if radius_m is None else radius_m
        center_cell = self.world_to_cell(position)
        for cell in self._cells_in_disk(center_cell, radius_m):
            self.explored_cells.add(cell)
            self.free_cells.add(cell)
            self.occupied_cells.discard(cell)
        return center_cell

    def mark_occupied(self, position: Sequence[float], radius_m: float = 0.0) -> GridCell:
        center_cell = self.world_to_cell(position)
        for cell in self._cells_in_disk(center_cell, radius_m):
            self.explored_cells.add(cell)
            self.occupied_cells.add(cell)
            self.free_cells.discard(cell)
        return center_cell

    def mark_path(self, start: Sequence[float], end: Sequence[float]) -> None:
        start_xyz = np.asarray(start, dtype=np.float32)
        end_xyz = np.asarray(end, dtype=np.float32)
        distance = float(np.linalg.norm(end_xyz[[0, 2]] - start_xyz[[0, 2]]))
        if distance == 0.0:
            self.mark_free(start, radius_m=0.0)
            return

        step_distance = max(self.config.cell_size * 0.5, 1e-6)
        num_samples = max(2, int(math.ceil(distance / step_distance)) + 1)
        for alpha in np.linspace(0.0, 1.0, num_samples):
            sample = start_xyz + ((end_xyz - start_xyz) * float(alpha))
            self.mark_free(sample.tolist(), radius_m=0.0)

    def add_observation(self, position: Sequence[float], previous_position: Optional[Sequence[float]] = None) -> GridCell:
        if previous_position is not None:
            self.mark_path(previous_position, position)

        center_cell = self.mark_free(position)
        self.visit_counts[center_cell] += 1
        return center_cell

    def update_from_world_positions(self, positions: Iterable[Sequence[float]]) -> int:
        previous_position: Optional[Sequence[float]] = None
        num_positions = 0
        for position in positions:
            self.add_observation(position, previous_position=previous_position)
            previous_position = position
            num_positions += 1
        return num_positions

    def update_from_trajectory_payload(self, payload: dict[str, object]) -> int:
        positions: List[Sequence[float]] = [payload["initial_state"]["position"]]
        positions.extend(step["state"]["position"] for step in payload["trajectory"])
        return self.update_from_world_positions(positions)

    def _neighbor_cells(self, cell: GridCell) -> Tuple[GridCell, GridCell, GridCell, GridCell]:
        x_index, z_index = cell
        return (
            (x_index + 1, z_index),
            (x_index - 1, z_index),
            (x_index, z_index + 1),
            (x_index, z_index - 1),
        )

    def frontier_cells(self) -> List[GridCell]:
        frontier: List[GridCell] = []
        for cell in sorted(self.free_cells):
            if any(neighbor not in self.explored_cells for neighbor in self._neighbor_cells(cell)):
                frontier.append(cell)
        return frontier

    def bounds(self, padding_cells: Optional[int] = None) -> Optional[Tuple[int, int, int, int]]:
        known_cells = self.explored_cells | self.occupied_cells
        if not known_cells:
            return None

        padding_cells = self.config.padding_cells if padding_cells is None else padding_cells
        x_indices = [cell[0] for cell in known_cells]
        z_indices = [cell[1] for cell in known_cells]
        return (
            min(x_indices) - padding_cells,
            max(x_indices) + padding_cells,
            min(z_indices) - padding_cells,
            max(z_indices) + padding_cells,
        )

    def to_dense(self, padding_cells: Optional[int] = None) -> Tuple[np.ndarray, dict[str, object]]:
        bounds = self.bounds(padding_cells=padding_cells)
        if bounds is None:
            empty = np.zeros((0, 0), dtype=np.uint8)
            return empty, {"origin_cell": [0, 0], "shape": [0, 0]}

        min_x, max_x, min_z, max_z = bounds
        width = (max_x - min_x) + 1
        height = (max_z - min_z) + 1
        grid = np.full((height, width), UNKNOWN, dtype=np.uint8)

        for x_index, z_index in self.free_cells:
            grid[max_z - z_index, x_index - min_x] = FREE
        for x_index, z_index in self.occupied_cells:
            grid[max_z - z_index, x_index - min_x] = OCCUPIED

        return grid, {
            "origin_cell": [min_x, min_z],
            "shape": [int(height), int(width)],
            "max_cell": [max_x, max_z],
        }

    def summary(self, frontier_preview_limit: int = 12) -> dict[str, object]:
        dense, dense_meta = self.to_dense()
        frontier = self.frontier_cells()
        bounds = self.bounds(padding_cells=0)

        if bounds is None:
            bounds_payload = None
        else:
            min_x, max_x, min_z, max_z = bounds
            bounds_payload = {
                "min_cell": [min_x, min_z],
                "max_cell": [max_x, max_z],
                "min_world_xz": [min_x * self.config.cell_size, min_z * self.config.cell_size],
                "max_world_xz": [
                    (max_x + 1) * self.config.cell_size,
                    (max_z + 1) * self.config.cell_size,
                ],
            }

        top_visits = [
            {"cell": [cell[0], cell[1]], "visits": int(visits)}
            for cell, visits in self.visit_counts.most_common(8)
        ]

        return {
            "cell_size": self.config.cell_size,
            "explored_radius": self.config.explored_radius,
            "num_explored_cells": len(self.explored_cells),
            "num_free_cells": len(self.free_cells),
            "num_occupied_cells": len(self.occupied_cells),
            "num_frontier_cells": len(frontier),
            "dense_shape": dense_meta["shape"],
            "bounds": bounds_payload,
            "frontier_preview_cells": [
                [cell[0], cell[1]] for cell in frontier[:frontier_preview_limit]
            ],
            "most_visited_cells": top_visits,
            "grid_value_encoding": {
                "unknown": UNKNOWN,
                "free": FREE,
                "occupied": OCCUPIED,
            },
            "dense_nonzero_count": int(np.count_nonzero(dense)),
        }


def load_trajectory_payload(path: Path) -> dict[str, object]:
    if not path.exists():
        raise FileNotFoundError(f"Missing trajectory file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a minimal occupancy map summary from a trajectory payload."
    )
    parser.add_argument(
        "--trajectory",
        type=Path,
        default=Path("outputs/runs/minimal_demo_trajectory.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("outputs/runs/occupancy_map_summary.json"),
    )
    parser.add_argument("--cell-size", type=float, default=0.25)
    parser.add_argument("--explored-radius", type=float, default=0.75)
    parser.add_argument("--padding-cells", type=int, default=4)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = load_trajectory_payload(args.trajectory)
    occupancy_map = OccupancyMap(
        OccupancyMapConfig(
            cell_size=args.cell_size,
            explored_radius=args.explored_radius,
            padding_cells=args.padding_cells,
        )
    )
    num_positions = occupancy_map.update_from_trajectory_payload(payload)
    summary = occupancy_map.summary()
    summary["trajectory"] = {
        "input_path": str(args.trajectory.resolve()),
        "scene": str(payload["scene"]),
        "scene_dataset_config": str(payload["scene_dataset_config"]),
        "num_positions_ingested": num_positions,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"saved: {args.output}")
    print(f"num_positions_ingested: {num_positions}")
    print(f"num_free_cells: {summary['num_free_cells']}")
    print(f"num_frontier_cells: {summary['num_frontier_cells']}")


if __name__ == "__main__":
    main()
