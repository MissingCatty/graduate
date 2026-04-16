#!/usr/bin/env python3

"""Run a minimal random trajectory in a single HM3D Habitat-Sim scene."""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

import habitat_sim
import habitat_sim.agent
import numpy as np
import quaternion


DEFAULT_DATASET_CONFIG = (
    "data/versioned_data/hm3d-0.2/hm3d/example/"
    "hm3d_annotated_example_basis.scene_dataset_config.json"
)
DEFAULT_SCENE = (
    "data/versioned_data/hm3d-0.2/hm3d/example/"
    "00861-GLAQ4DNUx5U/GLAQ4DNUx5U.basis.glb"
)
DEFAULT_OUTPUT = "outputs/runs/minimal_demo_trajectory.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a 20-30 step random trajectory in an HM3D example scene."
    )
    parser.add_argument("--steps", type=int, default=24)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument(
        "--scene-dataset-config",
        type=Path,
        default=Path(DEFAULT_DATASET_CONFIG),
    )
    parser.add_argument("--scene", type=Path, default=Path(DEFAULT_SCENE))
    parser.add_argument("--output", type=Path, default=Path(DEFAULT_OUTPUT))
    parser.add_argument("--width", type=int, default=320)
    parser.add_argument("--height", type=int, default=240)
    parser.add_argument("--sensor-height", type=float, default=1.5)
    parser.add_argument("--hfov", type=float, default=90.0)
    return parser.parse_args()


def make_sensor_spec(
    uuid: str,
    sensor_type: habitat_sim.SensorType,
    width: int,
    height: int,
    sensor_height: float,
    hfov: float,
) -> habitat_sim.CameraSensorSpec:
    spec = habitat_sim.CameraSensorSpec()
    spec.uuid = uuid
    spec.sensor_type = sensor_type
    spec.sensor_subtype = habitat_sim.SensorSubType.PINHOLE
    spec.resolution = [height, width]
    spec.position = [0.0, sensor_height, 0.0]
    spec.hfov = hfov
    if sensor_type != habitat_sim.SensorType.COLOR:
        spec.channels = 1
    return spec


def build_config(args: argparse.Namespace) -> habitat_sim.Configuration:
    sim_cfg = habitat_sim.SimulatorConfiguration()
    sim_cfg.gpu_device_id = 0
    sim_cfg.scene_dataset_config_file = str(args.scene_dataset_config.resolve())
    sim_cfg.scene_id = str(args.scene.resolve())

    agent_cfg = habitat_sim.agent.AgentConfiguration()
    agent_cfg.sensor_specifications = [
        make_sensor_spec(
            "color_sensor",
            habitat_sim.SensorType.COLOR,
            args.width,
            args.height,
            args.sensor_height,
            args.hfov,
        ),
        make_sensor_spec(
            "depth_sensor",
            habitat_sim.SensorType.DEPTH,
            args.width,
            args.height,
            args.sensor_height,
            args.hfov,
        ),
        make_sensor_spec(
            "semantic_sensor",
            habitat_sim.SensorType.SEMANTIC,
            args.width,
            args.height,
            args.sensor_height,
            args.hfov,
        ),
    ]
    return habitat_sim.Configuration(sim_cfg, [agent_cfg])


def state_to_dict(state: habitat_sim.AgentState) -> dict[str, object]:
    return {
        "position": [float(v) for v in state.position],
        "rotation_wxyz": [float(v) for v in quaternion.as_float_array(state.rotation)],
    }


def observation_summary(observations: dict[str, np.ndarray]) -> dict[str, object]:
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
    }


def main() -> None:
    args = parse_args()
    if not 20 <= args.steps <= 30:
        raise ValueError("--steps must be within [20, 30] for the T0.3 minimal demo")
    if not args.scene_dataset_config.exists():
        raise FileNotFoundError(f"Missing dataset config: {args.scene_dataset_config}")
    if not args.scene.exists():
        raise FileNotFoundError(f"Missing scene file: {args.scene}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    rng = random.Random(args.seed)

    sim = habitat_sim.Simulator(build_config(args))
    try:
        agent = sim.initialize_agent(0)
        start_state = agent.get_state()
        if sim.pathfinder.is_loaded:
            start_state.position = sim.pathfinder.get_random_navigable_point()
            agent.set_state(start_state)

        initial_state = agent.get_state()
        initial_observations = sim.get_sensor_observations()
        actions = list(agent.agent_config.action_space.keys())
        trajectory: list[dict[str, object]] = []

        for step_idx in range(args.steps):
            action = rng.choice(actions)
            observations = sim.step(action)
            state = agent.get_state()
            trajectory.append(
                {
                    "step": step_idx + 1,
                    "action": action,
                    "state": state_to_dict(state),
                    "observation_summary": observation_summary(observations),
                }
            )

        result = {
            "scene_dataset_config": str(args.scene_dataset_config.resolve()),
            "scene": str(args.scene.resolve()),
            "steps": args.steps,
            "seed": args.seed,
            "pathfinder_loaded": bool(sim.pathfinder.is_loaded),
            "action_space": actions,
            "initial_state": state_to_dict(initial_state),
            "final_state": state_to_dict(agent.get_state()),
            "initial_observation_summary": observation_summary(initial_observations),
            "trajectory": trajectory,
        }
        args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"saved: {args.output}")
        print(f"steps: {args.steps}")
        print(f"scene: {args.scene}")
        print(f"sensor_keys: {result['initial_observation_summary']['sensor_keys']}")
    finally:
        sim.close()


if __name__ == "__main__":
    main()
