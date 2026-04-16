#!/usr/bin/env python3

"""Render a top-down path figure for the minimal HM3D trajectory."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import habitat_sim
import matplotlib.pyplot as plt
import numpy as np
from habitat.utils.visualizations import maps

from run_minimal_trajectory import build_config


DEFAULT_TRAJECTORY = Path("outputs/runs/minimal_demo_trajectory.json")
DEFAULT_OUTPUT = Path("outputs/figures/minimal_demo.png")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export a top-down path figure for T0.5."
    )
    parser.add_argument("--trajectory", type=Path, default=DEFAULT_TRAJECTORY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--map-resolution", type=int, default=1024)
    parser.add_argument("--path-thickness", type=int, default=3)
    return parser.parse_args()


def load_payload(path: Path) -> dict[str, object]:
    if not path.exists():
        raise FileNotFoundError(f"Missing trajectory file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def world_positions(payload: dict[str, object]) -> list[list[float]]:
    return [
        payload["initial_state"]["position"],
        *[step["state"]["position"] for step in payload["trajectory"]],
    ]


def main() -> None:
    args = parse_args()
    payload = load_payload(args.trajectory)
    positions = world_positions(payload)

    sim_args = argparse.Namespace(
        scene_dataset_config=Path(str(payload["scene_dataset_config"])),
        scene=Path(str(payload["scene"])),
        width=int(payload["initial_observation_summary"]["color_shape"][1]),
        height=int(payload["initial_observation_summary"]["color_shape"][0]),
        sensor_height=1.5,
        hfov=90.0,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    sim = habitat_sim.Simulator(build_config(sim_args))
    try:
        height = float(positions[0][1])
        top_down = maps.get_topdown_map(
            sim.pathfinder,
            height=height,
            map_resolution=args.map_resolution,
            draw_border=True,
        )

        path_points = [
            maps.to_grid(pos[2], pos[0], top_down.shape, pathfinder=sim.pathfinder)
            for pos in positions
        ]
        maps.draw_path(
            top_down,
            path_points,
            color=maps.MAP_SHORTEST_PATH_COLOR,
            thickness=args.path_thickness,
        )
        top_down[path_points[0][0], path_points[0][1]] = maps.MAP_SOURCE_POINT_INDICATOR
        top_down[path_points[-1][0], path_points[-1][1]] = maps.MAP_TARGET_POINT_INDICATOR

        colorized = maps.colorize_topdown_map(top_down)
        marker_radius = max(5, colorized.shape[0] // 120)
        cv2.circle(
            colorized,
            path_points[0][::-1],
            marker_radius,
            tuple(int(v) for v in maps.TOP_DOWN_MAP_COLORS[maps.MAP_SOURCE_POINT_INDICATOR]),
            thickness=-1,
        )
        cv2.circle(
            colorized,
            path_points[-1][::-1],
            marker_radius,
            tuple(int(v) for v in maps.TOP_DOWN_MAP_COLORS[maps.MAP_TARGET_POINT_INDICATOR]),
            thickness=-1,
        )

        fig, ax = plt.subplots(figsize=(8, 8))
        ax.imshow(colorized)
        ax.set_title("Minimal HM3D Random Trajectory")
        ax.set_axis_off()
        fig.tight_layout()
        fig.savefig(args.output, dpi=160, bbox_inches="tight", pad_inches=0.05)
        plt.close(fig)

        print(f"saved: {args.output}")
        print(f"num_points: {len(path_points)}")
        print(f"map_shape: {list(top_down.shape)}")
    finally:
        sim.close()


if __name__ == "__main__":
    main()
