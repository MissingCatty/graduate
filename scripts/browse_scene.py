#!/usr/bin/env python3

"""Interactive browser for manually checking HM3D task answers."""

from __future__ import annotations

import argparse
import json
import textwrap
import time
from pathlib import Path
from typing import Optional

import cv2
import habitat_sim
import numpy as np
import quaternion

from export_minimal_observations import depth_to_uint8, semantic_to_rgb
from run_minimal_trajectory import build_config


DEFAULT_TRAJECTORY = Path("outputs/runs/minimal_demo_trajectory.json")
DEFAULT_TASKS = Path("outputs/tasks/tasks.json")
DEFAULT_SNAPSHOT = Path("outputs/figures/scene_browser_preview.png")

DISPLAY_MODES = ("rgb", "depth", "semantic")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Browse the current Habitat HM3D scene and inspect task answers."
    )
    parser.add_argument("--trajectory", type=Path, default=DEFAULT_TRAJECTORY)
    parser.add_argument("--tasks", type=Path, default=DEFAULT_TASKS)
    parser.add_argument("--start-step", type=int, default=0)
    parser.add_argument("--mode", choices=DISPLAY_MODES, default="rgb")
    parser.add_argument("--width", type=int, default=960)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--scale", type=float, default=1.0)
    parser.add_argument("--window-name", default="HM3D Task Browser")
    parser.add_argument(
        "--snapshot-output",
        type=Path,
        default=None,
        help="Save a single annotated frame and exit without opening a window.",
    )
    return parser.parse_args()


def load_json(path: Path) -> dict[str, object]:
    if not path.exists():
        raise FileNotFoundError(f"Missing JSON file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def scene_id_from_path(scene_path: str) -> str:
    return Path(scene_path).parent.name


def load_tasks(path: Path, scene_id: str) -> list[dict[str, object]]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    tasks = payload["tasks"] if isinstance(payload, dict) and "tasks" in payload else payload
    return [task for task in tasks if task.get("scene_id") == scene_id]


def state_from_trajectory(payload: dict[str, object], start_step: int) -> dict[str, object]:
    max_step = int(payload["steps"])
    if start_step < 0 or start_step > max_step:
        raise ValueError(f"--start-step must be within [0, {max_step}]")
    if start_step == 0:
        return payload["initial_state"]
    return payload["trajectory"][start_step - 1]["state"]


def set_agent_state(agent: habitat_sim.agent.Agent, state_dict: dict[str, object]) -> None:
    state = agent.get_state()
    state.position = np.array(state_dict["position"], dtype=np.float32)
    state.rotation = quaternion.from_float_array(
        np.array(state_dict["rotation_wxyz"], dtype=np.float64)
    )
    agent.set_state(state)


def pose_summary(agent_state: habitat_sim.AgentState) -> str:
    position = np.asarray(agent_state.position, dtype=np.float64)
    rotation = agent_state.rotation
    forward = quaternion.rotate_vectors(rotation, np.array([0.0, 0.0, -1.0], dtype=np.float64))
    yaw_deg = float(np.degrees(np.arctan2(forward[0], -forward[2])))
    return (
        f"pos=({position[0]:.2f}, {position[1]:.2f}, {position[2]:.2f}) "
        f"yaw={yaw_deg:.1f}deg"
    )


def observation_frame(observations: dict[str, np.ndarray], mode: str) -> np.ndarray:
    if mode == "rgb":
        rgb = np.asarray(observations["color_sensor"], dtype=np.uint8)[..., :3]
        return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    if mode == "depth":
        depth = depth_to_uint8(observations["depth_sensor"])
        return cv2.cvtColor(depth, cv2.COLOR_GRAY2BGR)
    if mode == "semantic":
        semantic = semantic_to_rgb(observations["semantic_sensor"])
        return cv2.cvtColor(semantic, cv2.COLOR_RGB2BGR)
    raise ValueError(f"Unsupported display mode: {mode}")


def draw_overlay(
    frame_bgr: np.ndarray,
    *,
    mode: str,
    pose_text: str,
    task: Optional[dict[str, object]],
    task_index: int,
    task_count: int,
    show_hud: bool,
) -> np.ndarray:
    annotated = frame_bgr.copy()
    if not show_hud:
        return annotated

    height, width = annotated.shape[:2]
    overlay = annotated.copy()
    panel_margin = 12
    panel_width = min(440, max(280, int(width * 0.36)))
    panel_x0 = panel_margin
    panel_y0 = panel_margin

    lines = [
        f"Mode: {mode.upper()}",
        pose_text,
    ]
    if task is not None:
        lines.append(
            f"Task {task_index + 1}/{task_count}: {task['task_type']} | GT {task['gt_answer']}"
        )
        wrap_width = max(26, (panel_width - 28) // 9)
        lines.extend(textwrap.wrap(str(task["question"]), width=wrap_width))
    else:
        lines.append("Task: no task loaded for this scene")

    line_height = 18
    panel_height = 18 + (len(lines) * line_height) + 12
    cv2.rectangle(
        overlay,
        (panel_x0, panel_y0),
        (panel_x0 + panel_width, panel_y0 + panel_height),
        (18, 18, 18),
        thickness=-1,
    )
    help_text = "W move | A/D turn | M mode | N/P task | H hide HUD | R reset | C shot | Q quit"
    help_width = min(width - (panel_margin * 2), max(360, int(width * 0.62)))
    help_height = 30
    help_x0 = panel_margin
    help_y0 = height - panel_margin - help_height
    cv2.rectangle(
        overlay,
        (help_x0, help_y0),
        (help_x0 + help_width, help_y0 + help_height),
        (18, 18, 18),
        thickness=-1,
    )
    annotated = cv2.addWeighted(overlay, 0.35, annotated, 0.65, 0.0)

    for line_index, line in enumerate(lines):
        text_y = panel_y0 + 22 + (line_index * line_height)
        color = (255, 255, 255)
        if "GT yes" in line:
            color = (120, 220, 120)
        elif "GT no" in line:
            color = (120, 160, 255)
        cv2.putText(
            annotated,
            line,
            (panel_x0 + 12, text_y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            color,
            1,
            cv2.LINE_AA,
        )

    cv2.putText(
        annotated,
        help_text,
        (help_x0 + 10, help_y0 + 20),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.45,
        (255, 255, 255),
        1,
        cv2.LINE_AA,
    )
    return annotated


def save_frame(path: Path, frame_bgr: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(path), frame_bgr):
        raise RuntimeError(f"Failed to save frame to {path}")


def print_controls() -> None:
    print("Controls:")
    print("  W: move forward")
    print("  A: turn left")
    print("  D: turn right")
    print("  M: cycle RGB/depth/semantic")
    print("  N/P: next/previous task for this scene")
    print("  H: toggle HUD visibility")
    print("  R: reset to the chosen start step")
    print("  C: save current annotated screenshot")
    print("  Q or ESC: quit")


def main() -> None:
    args = parse_args()
    payload = load_json(args.trajectory)
    scene_id = scene_id_from_path(str(payload["scene"]))
    tasks = load_tasks(args.tasks, scene_id)
    start_state_dict = state_from_trajectory(payload, args.start_step)

    sim_args = argparse.Namespace(
        scene_dataset_config=Path(str(payload["scene_dataset_config"])),
        scene=Path(str(payload["scene"])),
        width=args.width,
        height=args.height,
        sensor_height=1.5,
        hfov=90.0,
    )

    task_index = 0
    mode = args.mode
    show_hud = True

    sim = habitat_sim.Simulator(build_config(sim_args))
    try:
        agent = sim.initialize_agent(0)
        set_agent_state(agent, start_state_dict)

        print_controls()
        print(f"scene_id: {scene_id}")
        print(f"num_tasks_for_scene: {len(tasks)}")
        print(f"start_step: {args.start_step}")

        while True:
            observations = sim.get_sensor_observations()
            frame = observation_frame(observations, mode)
            task = tasks[task_index] if tasks else None
            annotated = draw_overlay(
                frame,
                mode=mode,
                pose_text=pose_summary(agent.get_state()),
                task=task,
                task_index=task_index,
                task_count=len(tasks),
                show_hud=show_hud,
            )

            if args.scale != 1.0:
                interpolation = cv2.INTER_NEAREST if mode == "semantic" else cv2.INTER_LINEAR
                annotated = cv2.resize(
                    annotated,
                    dsize=None,
                    fx=args.scale,
                    fy=args.scale,
                    interpolation=interpolation,
                )

            if args.snapshot_output is not None:
                save_frame(args.snapshot_output, annotated)
                print(f"saved: {args.snapshot_output}")
                break

            cv2.imshow(args.window_name, annotated)
            key = cv2.waitKey(30) & 0xFF

            if key in (27, ord("q")):
                break
            if key == ord("w"):
                sim.step("move_forward")
                continue
            if key == ord("a"):
                sim.step("turn_left")
                continue
            if key == ord("d"):
                sim.step("turn_right")
                continue
            if key == ord("m"):
                mode = DISPLAY_MODES[(DISPLAY_MODES.index(mode) + 1) % len(DISPLAY_MODES)]
                continue
            if key == ord("h"):
                show_hud = not show_hud
                continue
            if key == ord("n") and tasks:
                task_index = (task_index + 1) % len(tasks)
                continue
            if key == ord("p") and tasks:
                task_index = (task_index - 1) % len(tasks)
                continue
            if key == ord("r"):
                set_agent_state(agent, start_state_dict)
                continue
            if key == ord("c"):
                capture_path = Path("outputs/figures") / (
                    f"scene_browser_capture_{int(time.time())}.png"
                )
                save_frame(capture_path, annotated)
                print(f"saved: {capture_path}")
                continue
    finally:
        cv2.destroyAllWindows()
        sim.close()


if __name__ == "__main__":
    main()
