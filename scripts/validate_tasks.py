#!/usr/bin/env python3

"""Validate generated task files and emit a concise markdown report."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


DEFAULT_INPUT = Path("outputs/tasks/tasks.json")
DEFAULT_OUTPUT = Path("outputs/logs/task_validation.md")

YES_NO_VALUES = {"yes", "no"}
REQUIRED_TASK_FIELDS = {
    "task_id",
    "scene_id",
    "scene_path",
    "task_type",
    "question",
    "answer_type",
    "gt_answer",
    "gt_answer_bool",
    "gt_source",
    "task_spec",
    "evidence",
}
REQUIRED_TASK_SPEC_FIELDS = {
    "relation",
    "room_label",
    "target_category",
    "anchor_category",
    "semantic_hints",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate task payload schema.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def append_failure(failures: list[str], message: str) -> None:
    failures.append(message)


def validate_task(task: dict[str, object], failures: list[str]) -> None:
    task_id = task.get("task_id", "<missing_task_id>")
    missing_fields = sorted(REQUIRED_TASK_FIELDS - task.keys())
    if missing_fields:
        append_failure(failures, f"{task_id}: missing required fields {missing_fields}")
        return

    if task["answer_type"] != "yes_no":
        append_failure(failures, f"{task_id}: answer_type must be yes_no")

    gt_answer = task["gt_answer"]
    gt_answer_bool = task["gt_answer_bool"]
    if gt_answer not in YES_NO_VALUES:
        append_failure(failures, f"{task_id}: gt_answer must be yes or no")
    if not isinstance(gt_answer_bool, bool):
        append_failure(failures, f"{task_id}: gt_answer_bool must be bool")
    elif gt_answer_bool != (gt_answer == "yes"):
        append_failure(failures, f"{task_id}: gt_answer_bool inconsistent with gt_answer")

    task_spec = task["task_spec"]
    if not isinstance(task_spec, dict):
        append_failure(failures, f"{task_id}: task_spec must be an object")
        return

    missing_spec = sorted(REQUIRED_TASK_SPEC_FIELDS - task_spec.keys())
    if missing_spec:
        append_failure(failures, f"{task_id}: missing task_spec fields {missing_spec}")
        return

    semantic_hints = task_spec["semantic_hints"]
    if not isinstance(semantic_hints, list) or not semantic_hints:
        append_failure(failures, f"{task_id}: semantic_hints must be a non-empty list")

    task_type = task["task_type"]
    if task_type == "room_exist":
        if "query" not in task:
            append_failure(failures, f"{task_id}: room_exist task missing query")
        if task_spec["relation"] != "exist_in_scene":
            append_failure(failures, f"{task_id}: room_exist relation must be exist_in_scene")
        if task_spec["room_label"] != task.get("query"):
            append_failure(failures, f"{task_id}: room_label must match query")
        if task_spec["target_category"] is not None or task_spec["anchor_category"] is not None:
            append_failure(failures, f"{task_id}: room_exist target/anchor should be null")
    elif task_type == "near_exist":
        if "target_category" not in task or "anchor_category" not in task:
            append_failure(failures, f"{task_id}: near_exist task missing target/anchor category")
        if task_spec["relation"] != "near":
            append_failure(failures, f"{task_id}: near_exist relation must be near")
        if task_spec["room_label"] is not None:
            append_failure(failures, f"{task_id}: near_exist room_label should be null")
        if task_spec["target_category"] != task.get("target_category"):
            append_failure(failures, f"{task_id}: task_spec target_category mismatch")
        if task_spec["anchor_category"] != task.get("anchor_category"):
            append_failure(failures, f"{task_id}: task_spec anchor_category mismatch")
    else:
        append_failure(failures, f"{task_id}: unsupported task_type {task_type}")


def render_report(
    input_path: Path,
    task_count: int,
    task_type_counts: Counter[str],
    answer_counts: Counter[str],
    duplicate_count: int,
    failures: list[str],
) -> str:
    status = "PASS" if not failures else "FAIL"
    lines = [
        "# Task Validation Report",
        "",
        f"- input: `{input_path}`",
        f"- status: `{status}`",
        f"- task_count: `{task_count}`",
        f"- task_type_counts: `{dict(task_type_counts)}`",
        f"- answer_counts: `{dict(answer_counts)}`",
        f"- duplicate_task_ids: `{duplicate_count}`",
        f"- validation_failures: `{len(failures)}`",
        "",
    ]
    if failures:
        lines.append("## Failures")
        lines.append("")
        for failure in failures[:20]:
            lines.append(f"- {failure}")
    else:
        lines.append("## Summary")
        lines.append("")
        lines.append("- All tasks carry explicit `gt_answer` and consistent `gt_answer_bool`.")
        lines.append("- All tasks expose a unified `task_spec` block for downstream policies/answerers.")
        lines.append("- `room_exist` and `near_exist` task-specific fields are internally consistent.")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    tasks = payload["tasks"]

    task_type_counts = Counter()
    answer_counts = Counter()
    task_ids = []
    failures: list[str] = []

    for task in tasks:
        task_ids.append(task.get("task_id"))
        task_type_counts.update([task.get("task_type", "<missing>")])
        answer_counts.update([task.get("gt_answer", "<missing>")])
        validate_task(task, failures)

    duplicate_count = len(task_ids) - len(set(task_ids))
    if duplicate_count:
        append_failure(failures, f"duplicate task_id count: {duplicate_count}")

    metadata_task_count = payload.get("metadata", {}).get("task_count")
    if metadata_task_count != len(tasks):
        append_failure(
            failures,
            f"metadata.task_count mismatch: metadata={metadata_task_count}, actual={len(tasks)}",
        )

    report = render_report(
        args.input,
        len(tasks),
        task_type_counts,
        answer_counts,
        duplicate_count,
        failures,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report, encoding="utf-8")
    print(f"saved: {args.output}")
    print(f"status: {'PASS' if not failures else 'FAIL'}")
    print(f"task_count: {len(tasks)}")
    print(f"task_type_counts: {dict(task_type_counts)}")
    print(f"answer_counts: {dict(answer_counts)}")
    print(f"validation_failures: {len(failures)}")

    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
