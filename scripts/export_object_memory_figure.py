#!/usr/bin/env python3

"""Render a lightweight overview figure for the accumulated object memory."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Iterable, List

import matplotlib.pyplot as plt
import numpy as np


DEFAULT_MEMORY_PATH = Path("outputs/runs/object_memory_dump.json")
DEFAULT_OUTPUT_PATH = Path("outputs/figures/object_memory_overview.png")


def load_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Missing file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def extract_trajectory_positions(payload: dict) -> np.ndarray:
    positions: List[List[float]] = []
    initial_state = payload["initial_state"]
    positions.append(initial_state["position"])
    for step in payload["trajectory"]:
        positions.append(step["state"]["position"])
    return np.asarray(positions, dtype=np.float32)


def resolve_trajectory_path(memory_payload: dict, cli_value: Path | None) -> Path:
    if cli_value is not None:
        return cli_value

    trajectory_meta = memory_payload.get("trajectory", {})
    input_path = trajectory_meta.get("input_path")
    if input_path:
        return Path(str(input_path))
    return Path("outputs/runs/minimal_demo_trajectory.json")


def stable_color_map(labels: Iterable[str]) -> dict[str, tuple[float, float, float, float]]:
    unique_labels = sorted(set(labels))
    cmap = plt.cm.get_cmap("tab20", max(len(unique_labels), 1))
    return {
        label: cmap(index % cmap.N)
        for index, label in enumerate(unique_labels)
    }


def plot_topdown_memory(ax: plt.Axes, entries: list[dict], trajectory_xyz: np.ndarray) -> None:
    categories = [str(entry["category"]) for entry in entries]
    color_map = stable_color_map(categories)

    if trajectory_xyz.size > 0:
        ax.plot(
            trajectory_xyz[:, 0],
            trajectory_xyz[:, 2],
            color="#a6a6a6",
            linewidth=2.0,
            alpha=0.9,
            label="agent trajectory",
            zorder=1,
        )
        ax.scatter(
            trajectory_xyz[0, 0],
            trajectory_xyz[0, 2],
            s=80,
            color="#2e8b57",
            marker="o",
            edgecolors="black",
            linewidths=0.6,
            label="start",
            zorder=3,
        )
        ax.scatter(
            trajectory_xyz[-1, 0],
            trajectory_xyz[-1, 2],
            s=90,
            color="#d95f02",
            marker="X",
            edgecolors="black",
            linewidths=0.6,
            label="end",
            zorder=3,
        )

    for entry in entries:
        center = entry["center_xyz"]
        marker_size = 40 + (entry["observation_count"] * 28)
        ax.scatter(
            center[0],
            center[2],
            s=marker_size,
            color=color_map[str(entry["category"])],
            alpha=0.78,
            edgecolors="black",
            linewidths=0.4,
            zorder=2,
        )

    ax.set_title("Object Memory Top-Down View", fontsize=13, pad=10)
    ax.set_xlabel("x (meters)")
    ax.set_ylabel("z (meters)")
    ax.grid(True, linestyle="--", alpha=0.25)
    ax.set_aspect("equal", adjustable="datalim")

    legend_labels = []
    legend_handles = []
    category_counter = Counter(categories)
    for category, _ in category_counter.most_common(6):
        if category in legend_labels:
            continue
        handle = ax.scatter([], [], s=90, color=color_map[category], alpha=0.78)
        legend_handles.append(handle)
        legend_labels.append(category)
    if legend_handles:
        ax.legend(
            legend_handles,
            legend_labels,
            title="Top categories",
            loc="upper left",
            frameon=True,
            fontsize=9,
            title_fontsize=9,
        )


def plot_category_counts(ax: plt.Axes, entries: list[dict], limit: int) -> None:
    category_counts = Counter(str(entry["category"]) for entry in entries)
    top_items = category_counts.most_common(limit)
    categories = [item[0] for item in top_items][::-1]
    counts = [item[1] for item in top_items][::-1]

    ax.barh(categories, counts, color="#4c78a8", alpha=0.85)
    ax.set_title("Observed Category Counts", fontsize=13, pad=10)
    ax.set_xlabel("num objects")
    ax.grid(True, axis="x", linestyle="--", alpha=0.25)

    for index, count in enumerate(counts):
        ax.text(count + 0.1, index, str(count), va="center", fontsize=9)


def format_timeline_label(entry: dict) -> str:
    category = str(entry["category"])
    object_id = str(entry["object_id"]).split("_")[-1]
    return f"{category}#{object_id}"


def plot_seen_timeline(ax: plt.Axes, entries: list[dict], limit: int) -> None:
    ranked_entries = sorted(
        entries,
        key=lambda entry: (
            -int(entry["observation_count"]),
            int(entry["first_seen_step"]),
            str(entry["category"]),
        ),
    )[:limit]
    ranked_entries = list(reversed(ranked_entries))

    region_colors = stable_color_map(str(entry["region_id"]) for entry in ranked_entries)
    y_positions = np.arange(len(ranked_entries))
    labels = [format_timeline_label(entry) for entry in ranked_entries]

    for y_value, entry in zip(y_positions, ranked_entries):
        start = int(entry["first_seen_step"])
        end = int(entry["last_seen_step"])
        region_id = str(entry["region_id"])
        color = region_colors[region_id]
        ax.hlines(y_value, start, end, color=color, linewidth=3.4, alpha=0.9)
        ax.scatter(start, y_value, color=color, s=36, marker="o", edgecolors="black", linewidths=0.4)
        ax.scatter(end, y_value, color=color, s=52, marker="s", edgecolors="black", linewidths=0.4)
        ax.text(
            end + 0.25,
            y_value,
            f"{entry['observation_count']} obs / {entry['min_distance_m']:.2f} m",
            va="center",
            fontsize=8,
        )

    ax.set_yticks(y_positions)
    ax.set_yticklabels(labels, fontsize=8)
    ax.set_title("First/Last Seen Timeline", fontsize=13, pad=10)
    ax.set_xlabel("trajectory step")
    ax.grid(True, axis="x", linestyle="--", alpha=0.25)


def add_summary_text(ax: plt.Axes, memory_payload: dict, entries: list[dict]) -> None:
    summary = memory_payload.get("summary", {})
    trajectory = memory_payload.get("trajectory", {})
    region_counts = Counter(str(entry["region_id"]) for entry in entries)
    category_counts = Counter(str(entry["category"]) for entry in entries)
    observation_counts = [int(entry["observation_count"]) for entry in entries]

    lines = [
        f"scene: {Path(str(trajectory.get('scene', 'unknown'))).name}",
        f"pose updates: {trajectory.get('num_pose_updates', 'n/a')}",
        f"observed objects: {summary.get('num_observed_objects', len(entries))}",
        f"observed categories: {summary.get('num_observed_categories', len(category_counts))}",
        f"observed regions: {summary.get('num_observed_regions', len(region_counts))}",
        f"max obs / object: {max(observation_counts) if observation_counts else 0}",
        f"top region: {region_counts.most_common(1)[0][0] if region_counts else 'n/a'}",
        f"top category: {category_counts.most_common(1)[0][0] if category_counts else 'n/a'}",
    ]

    ax.axis("off")
    ax.text(
        0.0,
        1.0,
        "\n".join(lines),
        va="top",
        ha="left",
        fontsize=10,
        family="monospace",
        bbox={
            "boxstyle": "round,pad=0.45",
            "facecolor": "#f5f5f5",
            "edgecolor": "#c7c7c7",
        },
    )


def render_figure(memory_payload: dict, trajectory_payload: dict, output_path: Path) -> None:
    entries = list(memory_payload.get("entries", []))
    if not entries:
        raise ValueError("No object-memory entries found in payload")

    trajectory_xyz = extract_trajectory_positions(trajectory_payload)

    fig = plt.figure(figsize=(15, 10))
    grid = fig.add_gridspec(2, 2, width_ratios=[1.45, 1.0], height_ratios=[1.0, 1.0])

    ax_topdown = fig.add_subplot(grid[0, 0])
    ax_counts = fig.add_subplot(grid[0, 1])
    ax_timeline = fig.add_subplot(grid[1, 0])
    ax_summary = fig.add_subplot(grid[1, 1])

    plot_topdown_memory(ax_topdown, entries, trajectory_xyz)
    plot_category_counts(ax_counts, entries, limit=10)
    plot_seen_timeline(ax_timeline, entries, limit=12)
    add_summary_text(ax_summary, memory_payload, entries)

    fig.suptitle("Accumulated Object Memory Overview", fontsize=16, y=0.98)
    fig.tight_layout(rect=[0.0, 0.0, 1.0, 0.965])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render a lightweight visualization for the accumulated object memory."
    )
    parser.add_argument("--memory", type=Path, default=DEFAULT_MEMORY_PATH)
    parser.add_argument("--trajectory", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    memory_payload = load_json(args.memory)
    trajectory_path = resolve_trajectory_path(memory_payload, args.trajectory)
    trajectory_payload = load_json(trajectory_path)
    render_figure(memory_payload, trajectory_payload, args.output)
    print(f"saved: {args.output}")


if __name__ == "__main__":
    main()
