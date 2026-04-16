#!/usr/bin/env python3

"""Generate simple room_exist / near_exist tasks from HM3D GT semantics."""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import habitat_sim


DEFAULT_SCENE_ROOT = Path("data/versioned_data/hm3d-0.2/hm3d/example")
DEFAULT_DATASET_CONFIG = DEFAULT_SCENE_ROOT / "hm3d_annotated_example_basis.scene_dataset_config.json"
DEFAULT_OUTPUT = Path("outputs/tasks/tasks.json")

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

ROOM_SCORE_THRESHOLDS = {
    "bathroom": 2,
    "bedroom": 2,
    "kitchen": 2,
    "living_room": 2,
    "office": 2,
    "storage": 2,
    "laundry_room": 3,
    "garage": 2,
    "nursery": 2,
    "pantry": 2,
    "home_theater": 2,
    "gym": 2,
}

NOISE_CATEGORIES = {
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

NEAR_CATEGORY_WHITELIST = {
    "toilet",
    "sink",
    "showerhead",
    "bed",
    "wardrobe",
    "desk",
    "desk chair",
    "book",
    "couch",
    "tv",
    "chair",
    "table",
    "kitchen cabinet",
    "kitchen island",
    "oven",
    "refrigerator",
    "storage cabinet",
    "cardboard box",
    "plant",
    "pillow",
    "bag",
}

SCENE_STRUCT_SUFFIX = ".basis.glb"


@dataclass
class SceneSemanticSummary:
    scene_id: str
    scene_path: str
    region_categories: dict[str, list[str]]
    scene_object_counter: Counter[str]
    inferred_room_regions: dict[str, list[str]]
    inferred_scene_rooms: list[str]


DISPLAY_ALIASES = {
    "living_room": "living room",
    "laundry_room": "laundry room",
    "home_theater": "home theater",
    "tv": "TV",
    "storage": "storage room",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate simple GT yes-no tasks from HM3D semantic annotations."
    )
    parser.add_argument("--scene-root", type=Path, default=DEFAULT_SCENE_ROOT)
    parser.add_argument("--dataset-config", type=Path, default=DEFAULT_DATASET_CONFIG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--target-count", type=int, default=24)
    parser.add_argument("--max-near-per-scene", type=int, default=20)
    parser.add_argument("--max-room-per-scene", type=int, default=8)
    return parser.parse_args()


def canonicalize_category(name: str) -> str:
    return " ".join(name.strip().lower().split())


def display_label(name: str) -> str:
    normalized = name.strip().lower().replace("_", " ")
    return DISPLAY_ALIASES.get(name, DISPLAY_ALIASES.get(normalized, normalized))


def with_indefinite_article(name: str) -> str:
    label = display_label(name)
    article = "an" if label[:1].lower() in {"a", "e", "i", "o", "u"} else "a"
    return f"{article} {label}"


def answer_to_bool(answer: str) -> bool:
    if answer not in {"yes", "no"}:
        raise ValueError(f"Unsupported yes/no answer: {answer}")
    return answer == "yes"


def build_task_spec(
    task_type: str,
    *,
    room_label: str | None = None,
    target_category: str | None = None,
    anchor_category: str | None = None,
) -> dict[str, object]:
    semantic_hints = [
        value
        for value in [room_label, target_category, anchor_category]
        if value is not None
    ]
    relation = "exist_in_scene" if task_type == "room_exist" else "near"
    return {
        "relation": relation,
        "room_label": room_label,
        "target_category": target_category,
        "anchor_category": anchor_category,
        "semantic_hints": semantic_hints,
    }


def iter_semantic_scenes(scene_root: Path) -> Iterable[Path]:
    for scene_path in sorted(scene_root.glob(f"*/*{SCENE_STRUCT_SUFFIX}")):
        semantic_txt = scene_path.parent / f"{scene_path.stem.replace('.basis', '')}.semantic.txt"
        if semantic_txt.exists():
            yield scene_path


def load_scene_summary(dataset_config: Path, scene_path: Path) -> SceneSemanticSummary:
    sim_cfg = habitat_sim.SimulatorConfiguration()
    sim_cfg.scene_dataset_config_file = str(dataset_config.resolve())
    sim_cfg.scene_id = str(scene_path.resolve())
    agent_cfg = habitat_sim.agent.AgentConfiguration()
    sim = habitat_sim.Simulator(habitat_sim.Configuration(sim_cfg, [agent_cfg]))
    try:
        per_region: dict[str, set[str]] = defaultdict(set)
        object_counter: Counter[str] = Counter()
        for obj in sim.semantic_scene.objects:
            category = canonicalize_category(obj.category.name())
            region_id = obj.region.id if obj.region is not None else "_-1"
            per_region[region_id].add(category)
            object_counter[category] += 1

        inferred_room_regions: dict[str, list[str]] = {}
        for room_label, keywords in ROOM_KEYWORDS.items():
            matched_regions: list[str] = []
            threshold = ROOM_SCORE_THRESHOLDS[room_label]
            for region_id, categories in per_region.items():
                score = len(categories & keywords)
                if score >= threshold:
                    matched_regions.append(region_id)
            inferred_room_regions[room_label] = sorted(matched_regions)

        inferred_scene_rooms = sorted(
            room_label
            for room_label, region_ids in inferred_room_regions.items()
            if region_ids
        )

        return SceneSemanticSummary(
            scene_id=scene_path.parent.name,
            scene_path=str(scene_path.resolve()),
            region_categories={
                region_id: sorted(categories) for region_id, categories in sorted(per_region.items())
            },
            scene_object_counter=object_counter,
            inferred_room_regions=inferred_room_regions,
            inferred_scene_rooms=inferred_scene_rooms,
        )
    finally:
        sim.close()


def build_room_tasks(summary: SceneSemanticSummary, max_count: int) -> list[dict[str, object]]:
    tasks: list[dict[str, object]] = []
    for room_label in ROOM_KEYWORDS:
        region_scores: dict[str, int] = {}
        keywords = ROOM_KEYWORDS[room_label]
        threshold = ROOM_SCORE_THRESHOLDS[room_label]
        for region_id, categories in summary.region_categories.items():
            score = len(set(categories) & keywords)
            if score > 0:
                region_scores[region_id] = score

        positive_regions = summary.inferred_room_regions[room_label]
        gt_answer = "yes" if positive_regions else "no"
        tasks.append(
            {
                "task_id": f"{summary.scene_id}__room_exist__{room_label}",
                "scene_id": summary.scene_id,
                "scene_path": summary.scene_path,
                "task_type": "room_exist",
                "question": f"Is there {with_indefinite_article(room_label)} in the scene?",
                "query": room_label,
                "answer_type": "yes_no",
                "gt_answer": gt_answer,
                "gt_answer_bool": answer_to_bool(gt_answer),
                "gt_source": "region_object_keyword_heuristic",
                "task_spec": build_task_spec(
                    "room_exist",
                    room_label=room_label,
                ),
                "evidence": {
                    "positive_region_ids": positive_regions,
                    "room_keywords": sorted(keywords),
                    "region_scores": region_scores,
                    "room_score": max(region_scores.values(), default=0),
                    "score_threshold": threshold,
                },
            }
        )
    return tasks


def usable_near_categories(summary: SceneSemanticSummary) -> list[str]:
    categories = []
    for category, count in summary.scene_object_counter.items():
        if count <= 0:
            continue
        if category in NOISE_CATEGORIES:
            continue
        if category not in NEAR_CATEGORY_WHITELIST:
            continue
        categories.append(category)
    return sorted(categories)


def build_near_tasks(
    summary: SceneSemanticSummary,
    max_count: int,
    rng: random.Random,
) -> list[dict[str, object]]:
    categories = usable_near_categories(summary)
    region_to_categories = {
        region_id: {cat for cat in cats if cat in categories}
        for region_id, cats in summary.region_categories.items()
    }

    positive_pairs: dict[tuple[str, str], list[str]] = {}
    for region_id, cats in region_to_categories.items():
        cats = sorted(cats)
        for anchor in cats:
            for target in cats:
                if anchor == target:
                    continue
                positive_pairs.setdefault((target, anchor), []).append(region_id)

    all_pairs = [
        (target, anchor)
        for target in categories
        for anchor in categories
        if target != anchor
    ]
    negative_pairs = [
        pair for pair in all_pairs if pair not in positive_pairs
    ]

    rng.shuffle(all_pairs)
    rng.shuffle(negative_pairs)

    positives = sorted(positive_pairs.items())
    rng.shuffle(positives)

    tasks: list[dict[str, object]] = []
    near_budget = max_count
    yes_budget = near_budget // 2
    no_budget = near_budget - yes_budget

    for (target, anchor), region_ids in positives[:yes_budget]:
        tasks.append(
            {
                "task_id": f"{summary.scene_id}__near_exist__{target}__{anchor}",
                "scene_id": summary.scene_id,
                "scene_path": summary.scene_path,
                "task_type": "near_exist",
                "question": (
                    f"Is there {with_indefinite_article(target)} near the "
                    f"{display_label(anchor)} in the scene?"
                ),
                "target_category": target,
                "anchor_category": anchor,
                "answer_type": "yes_no",
                "gt_answer": "yes",
                "gt_answer_bool": True,
                "gt_source": "same_region_cooccurrence_heuristic",
                "task_spec": build_task_spec(
                    "near_exist",
                    target_category=target,
                    anchor_category=anchor,
                ),
                "evidence": {
                    "positive_region_ids": sorted(region_ids),
                },
            }
        )

    for target, anchor in negative_pairs[:no_budget]:
        tasks.append(
            {
                "task_id": f"{summary.scene_id}__near_exist__{target}__{anchor}",
                "scene_id": summary.scene_id,
                "scene_path": summary.scene_path,
                "task_type": "near_exist",
                "question": (
                    f"Is there {with_indefinite_article(target)} near the "
                    f"{display_label(anchor)} in the scene?"
                ),
                "target_category": target,
                "anchor_category": anchor,
                "answer_type": "yes_no",
                "gt_answer": "no",
                "gt_answer_bool": False,
                "gt_source": "same_region_cooccurrence_heuristic",
                "task_spec": build_task_spec(
                    "near_exist",
                    target_category=target,
                    anchor_category=anchor,
                ),
                "evidence": {
                    "positive_region_ids": [],
                },
            }
        )

    return tasks[:max_count]


def select_balanced_tasks(
    tasks: list[dict[str, object]],
    target_count: int,
    rng: random.Random,
    *,
    score_field: str | None = None,
) -> list[dict[str, object]]:
    yes_tasks = [task for task in tasks if task["gt_answer"] == "yes"]
    no_tasks = [task for task in tasks if task["gt_answer"] == "no"]

    if score_field is not None:
        yes_tasks = sorted(
            yes_tasks,
            key=lambda task: (-int(task["evidence"].get(score_field, 0)), task["task_id"]),
        )
        no_tasks = sorted(
            no_tasks,
            key=lambda task: (int(task["evidence"].get(score_field, 0)), task["task_id"]),
        )
    else:
        rng.shuffle(yes_tasks)
        rng.shuffle(no_tasks)

    yes_target = min(len(yes_tasks), target_count // 2)
    no_target = min(len(no_tasks), target_count - yes_target)

    selected = yes_tasks[:yes_target] + no_tasks[:no_target]
    if len(selected) < target_count:
        leftovers = yes_tasks[yes_target:] + no_tasks[no_target:]
        if score_field is None:
            rng.shuffle(leftovers)
        selected.extend(leftovers[: target_count - len(selected)])

    return selected[:target_count]


def generate_tasks(args: argparse.Namespace) -> list[dict[str, object]]:
    rng = random.Random(args.seed)
    scene_paths = list(iter_semantic_scenes(args.scene_root))
    summaries = [
        load_scene_summary(args.dataset_config, scene_path) for scene_path in scene_paths
    ]

    room_tasks: list[dict[str, object]] = []
    near_tasks: list[dict[str, object]] = []
    for summary in summaries:
        room_tasks.extend(build_room_tasks(summary, args.max_room_per_scene))
        near_tasks.extend(build_near_tasks(summary, args.max_near_per_scene, rng))

    room_target = min(len(room_tasks), args.max_room_per_scene)
    selected_room_tasks = select_balanced_tasks(
        room_tasks,
        room_target,
        rng,
        score_field="room_score",
    )

    remaining_target = max(0, args.target_count - len(selected_room_tasks))
    global_yes_target = args.target_count // 2
    global_no_target = args.target_count - global_yes_target

    room_yes = sum(task["gt_answer"] == "yes" for task in selected_room_tasks)
    room_no = len(selected_room_tasks) - room_yes
    near_yes_target = max(0, global_yes_target - room_yes)
    near_no_target = max(0, global_no_target - room_no)

    near_yes_tasks = [task for task in near_tasks if task["gt_answer"] == "yes"]
    near_no_tasks = [task for task in near_tasks if task["gt_answer"] == "no"]
    rng.shuffle(near_yes_tasks)
    rng.shuffle(near_no_tasks)

    selected_near_tasks = (
        near_yes_tasks[:near_yes_target] + near_no_tasks[:near_no_target]
    )
    if len(selected_near_tasks) < remaining_target:
        leftovers = near_yes_tasks[near_yes_target:] + near_no_tasks[near_no_target:]
        rng.shuffle(leftovers)
        selected_near_tasks.extend(leftovers[: remaining_target - len(selected_near_tasks)])

    tasks = selected_room_tasks + selected_near_tasks[:remaining_target]
    rng.shuffle(tasks)
    return tasks[: args.target_count]


def main() -> None:
    args = parse_args()
    if not args.dataset_config.exists():
        raise FileNotFoundError(f"Missing dataset config: {args.dataset_config}")
    if not args.scene_root.exists():
        raise FileNotFoundError(f"Missing scene root: {args.scene_root}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    tasks = generate_tasks(args)

    payload = {
        "metadata": {
            "schema_version": 2,
            "task_count": len(tasks),
            "scene_root": str(args.scene_root.resolve()),
            "dataset_config": str(args.dataset_config.resolve()),
            "gt_policy": {
                "room_exist": "region_object_keyword_heuristic",
                "near_exist": "same_region_cooccurrence_heuristic",
            },
            "required_task_fields": [
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
            ],
        },
        "tasks": tasks,
    }
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"saved: {args.output}")
    print(f"task_count: {len(tasks)}")
    print(
        "task_type_counts:",
        dict(Counter(task["task_type"] for task in tasks)),
    )
    print(
        "answer_counts:",
        dict(Counter(task["gt_answer"] for task in tasks)),
    )


if __name__ == "__main__":
    main()
