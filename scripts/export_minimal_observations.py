#!/usr/bin/env python3

"""Export RGB, depth, and semantic example images from the minimal HM3D demo."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import habitat_sim
import habitat_sim.agent
import numpy as np
import quaternion
from PIL import Image

from run_minimal_trajectory import build_config


DEFAULT_TRAJECTORY = Path("outputs/runs/minimal_demo_trajectory.json")
DEFAULT_RGB = Path("outputs/figures/minimal_demo_rgb.png")
DEFAULT_DEPTH = Path("outputs/figures/minimal_demo_depth.png")
DEFAULT_SEMANTIC = Path("outputs/figures/minimal_demo_semantic.png")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export RGB/depth/semantic example images for T0.4."
    )
    parser.add_argument("--trajectory", type=Path, default=DEFAULT_TRAJECTORY)
    parser.add_argument("--rgb-output", type=Path, default=DEFAULT_RGB)
    parser.add_argument("--depth-output", type=Path, default=DEFAULT_DEPTH)
    parser.add_argument("--semantic-output", type=Path, default=DEFAULT_SEMANTIC)
    return parser.parse_args()


def load_trajectory(path: Path) -> dict[str, object]:
    if not path.exists():
        raise FileNotFoundError(f"Missing trajectory file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def palette_color(label: int) -> tuple[int, int, int]:
    # Deterministic pseudo-palette so repeated runs color the same labels consistently.
    if label == 0:
        return (0, 0, 0)
    return (
        (label * 37) % 256,
        (label * 67) % 256,
        (label * 97) % 256,
    )


def semantic_to_rgb(semantic: np.ndarray) -> np.ndarray:
    semantic = np.asarray(semantic, dtype=np.uint32)
    rgb = np.zeros((*semantic.shape, 3), dtype=np.uint8)
    for label in np.unique(semantic):
        rgb[semantic == label] = palette_color(int(label))
    return rgb


def depth_to_uint8(depth: np.ndarray) -> np.ndarray:
    depth = np.asarray(depth, dtype=np.float32)
    finite_mask = np.isfinite(depth)
    if not finite_mask.any():
        return np.zeros(depth.shape, dtype=np.uint8)

    depth_min = float(depth[finite_mask].min())
    depth_max = float(depth[finite_mask].max())
    if depth_max <= depth_min:
        return np.zeros(depth.shape, dtype=np.uint8)

    normalized = (depth - depth_min) / (depth_max - depth_min)
    normalized = np.clip(normalized, 0.0, 1.0)
    return (normalized * 255.0).astype(np.uint8)


def main() -> None:
    args = parse_args()
    payload = load_trajectory(args.trajectory)

    scene_dataset_config = Path(str(payload["scene_dataset_config"]))
    scene = Path(str(payload["scene"]))
    summary = payload["initial_observation_summary"]
    initial_state = payload["initial_state"]

    sim_args = argparse.Namespace(
        scene_dataset_config=scene_dataset_config,
        scene=scene,
        width=int(summary["color_shape"][1]),
        height=int(summary["color_shape"][0]),
        sensor_height=1.5,
        hfov=90.0,
    )

    for output in (args.rgb_output, args.depth_output, args.semantic_output):
        output.parent.mkdir(parents=True, exist_ok=True)

    sim = habitat_sim.Simulator(build_config(sim_args))
    try:
        agent = sim.initialize_agent(0)
        state = agent.get_state()
        state.position = np.array(initial_state["position"], dtype=np.float32)
        state.rotation = quaternion.from_float_array(
            np.array(initial_state["rotation_wxyz"], dtype=np.float64)
        )
        agent.set_state(state)

        observations = sim.get_sensor_observations()
        color = np.asarray(observations["color_sensor"], dtype=np.uint8)[..., :3]
        depth = depth_to_uint8(observations["depth_sensor"])
        semantic = semantic_to_rgb(observations["semantic_sensor"])

        Image.fromarray(color, mode="RGB").save(args.rgb_output)
        Image.fromarray(depth, mode="L").save(args.depth_output)
        Image.fromarray(semantic, mode="RGB").save(args.semantic_output)

        print(f"saved: {args.rgb_output}")
        print(f"saved: {args.depth_output}")
        print(f"saved: {args.semantic_output}")
        print(
            "semantic_labels:",
            len(np.unique(np.asarray(observations["semantic_sensor"], dtype=np.uint32))),
        )
    finally:
        sim.close()


if __name__ == "__main__":
    main()
