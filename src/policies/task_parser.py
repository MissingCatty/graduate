#!/usr/bin/env python3

"""Normalize task records into a policy-friendly representation."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


DEFAULT_TASKS = Path("outputs/tasks/tasks.json")
DEFAULT_OUTPUT = Path("outputs/runs/task_parser_preview.json")

# Mirrored from `scripts/generate_tasks.py` so task parsing stays lightweight and
# does not depend on Habitat-related imports.
ROOM_KEYWORDS = {
    "bathroom": {
        "toilet",
        "toilet brush",
        "toilet paper",
        "bathroom accessory",
        "bathroom cabinet",
        "bathroom shelf",
        "bathroom utensil",
        "bath sink",
        "sink",
        "tap",
        "shower floor",
        "shower wall",
        "showerhead",
        "shower hose/head",
        "shower hose",
        "shower dial",
        "liquid soap",
    },
    "bedroom": {
        "bed",
        "bed stand",
        "wardrobe",
        "dresser",
        "pillow",
        "blanket",
    },
    "kitchen": {
        "kitchen cabinet",
        "kitchen island",
        "oven",
        "refrigerator",
        "refrigerator cabinet",
        "sink",
        "tap",
        "ventilation hood",
        "bowl",
    },
    "living_room": {
        "couch",
        "sofa chair",
        "tv",
        "speaker",
        "pouffe",
        "small table/stand",
        "telephone",
    },
    "office": {
        "desk",
        "desk chair",
        "desk clutter",
        "desk lamp",
        "book rack",
        "book",
        "stack of papers",
        "recycle bin",
    },
    "storage": {
        "storage cabinet",
        "cardboard box",
        "basket of something",
        "case",
        "container",
        "closet area for hanging clothes",
        "hanger",
    },
    "laundry_room": {
        "washing machine",
        "laundry basket",
        "bottle of detergent",
        "ironing board",
        "vacuum cleaner",
        "rack",
    },
    "garage": {
        "car",
        "bicycle",
        "motorcycle",
        "toolbox",
        "tool cabinet",
        "workbench",
        "power tool",
        "garage door",
    },
    "nursery": {
        "crib",
        "stroller",
        "changing table",
        "baby toy",
        "baby chair",
    },
    "pantry": {
        "pantry shelf",
        "canned food",
        "food package",
        "spice rack",
        "wine rack",
    },
    "home_theater": {
        "projector",
        "movie screen",
        "surround speaker",
        "recliner",
        "media console",
    },
    "gym": {
        "exercise bike",
        "treadmill",
        "weights",
        "dumbbell",
        "yoga mat",
    },
}


@dataclass(frozen=True)
class ParsedTask:
    task_id: str
    scene_id: str
    scene_path: Optional[str]
    question: str
    task_type: str
    answer_type: str
    relation: str
    room_label: Optional[str]
    target_category: Optional[str]
    anchor_category: Optional[str]
    semantic_hints: tuple[str, ...]
    room_keywords: tuple[str, ...]
    hint_categories: tuple[str, ...]
    gt_answer: Optional[str]
    gt_answer_bool: Optional[bool]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def canonicalize_category(name: str) -> str:
    return " ".join(name.strip().lower().split())


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


def _normalize_optional_string(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _normalize_room_label(value: Any) -> Optional[str]:
    room_label = _normalize_optional_string(value)
    if room_label is None:
        return None
    return room_label.strip().lower().replace(" ", "_")


def _normalize_relation(task: Mapping[str, Any], task_spec: Mapping[str, Any]) -> str:
    relation = _normalize_optional_string(task_spec.get("relation"))
    if relation is not None:
        return relation

    task_type = _normalize_optional_string(task.get("task_type")) or "unknown"
    if task_type == "near_exist":
        return "near"
    if task_type == "room_exist":
        return "exist_in_scene"
    return task_type


def _normalized_semantic_hints(task_spec: Mapping[str, Any]) -> tuple[str, ...]:
    semantic_hints = task_spec.get("semantic_hints") or []
    normalized: set[str] = set()
    for value in semantic_hints:
        hint = _normalize_optional_string(value)
        if hint is None:
            continue
        normalized.add(canonicalize_category(hint))
    return tuple(sorted(normalized))


def parse_task(task: Mapping[str, Any]) -> ParsedTask:
    task_spec = dict(task.get("task_spec") or {})
    room_label = _normalize_room_label(task_spec.get("room_label"))
    target_category = _normalize_optional_string(task_spec.get("target_category"))
    anchor_category = _normalize_optional_string(task_spec.get("anchor_category"))

    normalized_target = (
        None if target_category is None else canonicalize_category(target_category)
    )
    normalized_anchor = (
        None if anchor_category is None else canonicalize_category(anchor_category)
    )
    semantic_hints = _normalized_semantic_hints(task_spec)
    room_keywords = tuple(sorted(ROOM_KEYWORDS.get(room_label, set())))

    hint_categories: set[str] = set(room_keywords)
    if normalized_target is not None:
        hint_categories.add(normalized_target)
    if normalized_anchor is not None:
        hint_categories.add(normalized_anchor)
    for hint in semantic_hints:
        if hint in ROOM_KEYWORDS:
            continue
        hint_categories.add(hint)

    return ParsedTask(
        task_id=str(task.get("task_id", "")),
        scene_id=str(task.get("scene_id", "")),
        scene_path=_normalize_optional_string(task.get("scene_path")),
        question=str(task.get("question", "")),
        task_type=str(task.get("task_type", "")),
        answer_type=str(task.get("answer_type", "")),
        relation=_normalize_relation(task, task_spec),
        room_label=room_label,
        target_category=normalized_target,
        anchor_category=normalized_anchor,
        semantic_hints=semantic_hints,
        room_keywords=room_keywords,
        hint_categories=tuple(sorted(hint_categories)),
        gt_answer=_normalize_optional_string(task.get("gt_answer")),
        gt_answer_bool=task.get("gt_answer_bool"),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Normalize a task into a policy-friendly parsed representation."
    )
    parser.add_argument("--tasks", type=Path, default=DEFAULT_TASKS)
    parser.add_argument("--task-index", type=int, default=0)
    parser.add_argument("--task-id", type=str, default=None)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    tasks_payload = load_tasks_payload(args.tasks)
    task = select_task(tasks_payload, task_index=args.task_index, task_id=args.task_id)
    parsed = parse_task(task)

    output_payload = {
        "input_task": {
            "task_id": task.get("task_id"),
            "task_type": task.get("task_type"),
            "question": task.get("question"),
            "task_spec": task.get("task_spec"),
        },
        "parsed_task": parsed.to_dict(),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output_payload, indent=2), encoding="utf-8")
    print(f"saved: {args.output}")
    print(f"task_id: {parsed.task_id}")
    print(f"task_type: {parsed.task_type}")
    print(f"hint_categories: {list(parsed.hint_categories)}")


if __name__ == "__main__":
    main()
