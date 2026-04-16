#!/usr/bin/env python3

"""Probe Habitat-related Python packages and local scene data availability.

This script is designed for T0 environment validation. It inspects:
1. Python/runtime information for the active environment
2. Habitat-Lab / Habitat-Sim related Python modules
3. Common local dataset roots for HM3D or Habitat demo/test scenes

By default it prints a Markdown report to stdout. Use --output to save it.
"""

from __future__ import annotations

import argparse
import importlib
import importlib.metadata
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable


@dataclass
class ModuleProbe:
    label: str
    module_name: str
    dist_names: tuple[str, ...]
    installed: bool
    version: str
    module_path: str
    note: str


@dataclass
class SceneCandidate:
    kind: str
    path: str
    evidence: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check Habitat package and scene-data availability for T0."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path to save the Markdown report.",
    )
    parser.add_argument(
        "--search-root",
        action="append",
        default=[],
        help="Additional root directory to scan for scene datasets.",
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=4,
        help="Maximum directory depth used when scanning candidate roots.",
    )
    return parser.parse_args()


def probe_module(label: str, module_name: str, dist_names: Iterable[str]) -> ModuleProbe:
    dist_names = tuple(dist_names)
    try:
        module = importlib.import_module(module_name)
        module_version = getattr(module, "__version__", "") or ""
        if module_name == "cv2":
            module_version = module_version or getattr(module, "version", {}).get("opencv", "")
        dist_version = ""
        for dist_name in dist_names:
            try:
                dist_version = importlib.metadata.version(dist_name)
                break
            except importlib.metadata.PackageNotFoundError:
                continue
        version = module_version or dist_version or "unknown"
        module_path = getattr(module, "__file__", "<builtin>")
        note = "import succeeded"
        return ModuleProbe(label, module_name, dist_names, True, version, module_path, note)
    except Exception as exc:  # noqa: BLE001
        return ModuleProbe(
            label=label,
            module_name=module_name,
            dist_names=dist_names,
            installed=False,
            version="",
            module_path="",
            note=f"{type(exc).__name__}: {exc}",
        )


def candidate_roots(extra_roots: Iterable[str]) -> list[Path]:
    cwd = Path.cwd()
    home = Path.home()

    env_roots = [
        os.environ.get("HM3D_DIR"),
        os.environ.get("HABITAT_DATA_PATH"),
        os.environ.get("HABITAT_SCENE_DATASETS_DIR"),
        os.environ.get("HABITAT_SIM_DATA_PATH"),
    ]
    common_roots = [
        cwd / "data",
        cwd / "datasets",
        cwd / "scene_datasets",
        cwd / "assets",
        home / "data",
        home / "datasets",
        home / "hm3d",
        home / "habitat-lab" / "data",
        Path("/data"),
        Path("/datasets"),
        Path("/mnt/data"),
    ]

    ordered: list[Path] = []
    seen: set[str] = set()
    for raw in [*env_roots, *extra_roots, *map(str, common_roots)]:
        if not raw:
            continue
        path = Path(raw).expanduser()
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        ordered.append(path)
    return ordered


def scan_scene_candidates(roots: Iterable[Path], max_depth: int) -> tuple[list[SceneCandidate], list[str]]:
    findings: dict[tuple[str, str], SceneCandidate] = {}
    searched: list[str] = []

    for root in roots:
        if not root.exists():
            continue
        searched.append(str(root))
        for current_dir, dirnames, filenames in os.walk(root):
            current = Path(current_dir)
            try:
                relative = current.relative_to(root)
                depth = len(relative.parts)
            except ValueError:
                depth = 0

            if depth > max_depth:
                dirnames[:] = []
                continue

            lower_path = str(current).lower()
            lower_files = [name.lower() for name in filenames]

            def add(kind: str, evidence: str) -> None:
                key = (kind, str(current))
                findings[key] = SceneCandidate(kind=kind, path=str(current), evidence=evidence)

            if "hm3d" in lower_path:
                add("hm3d", "path contains 'hm3d'")

            if "habitat-test-scenes" in lower_path or (
                "habitat" in lower_path and "test" in lower_path and "scene" in lower_path
            ):
                add("habitat_demo", "path suggests Habitat demo/test scenes")

            has_mesh = any(
                name.endswith((".glb", ".basis.glb", ".scene_instance.json")) for name in lower_files
            )
            has_navmesh = any(name.endswith(".navmesh") for name in lower_files)

            if has_mesh and has_navmesh:
                add("generic_scene_dataset", "contains scene mesh/json and navmesh files")
            elif any(name.endswith(".scene_instance.json") for name in lower_files):
                add("generic_scene_dataset", "contains scene_instance.json")

    ordered = sorted(findings.values(), key=lambda item: (item.kind, item.path))
    return ordered, searched


def summarize_plan(probes: list[ModuleProbe], scenes: list[SceneCandidate]) -> tuple[str, list[str]]:
    has_habitat_core = any(p.module_name == "habitat" and p.installed for p in probes) and any(
        p.module_name == "habitat_sim" and p.installed for p in probes
    )
    has_hm3d = any(scene.kind == "hm3d" for scene in scenes)
    has_demo = any(scene.kind in {"habitat_demo", "generic_scene_dataset"} for scene in scenes)

    if has_habitat_core and has_hm3d:
        return "PLAN_A_READY", [
            "Habitat-Lab and Habitat-Sim imports are available",
            "At least one HM3D-related local dataset candidate was found",
        ]
    if has_habitat_core and has_demo:
        return "PLAN_A_DEGRADED_READY", [
            "Habitat-Lab and Habitat-Sim imports are available",
            "No HM3D candidate found, but a Habitat demo/test or generic scene dataset candidate exists",
        ]
    if has_habitat_core:
        return "BLOCKED_ON_SCENE_DATA", [
            "Habitat-Lab and Habitat-Sim imports are available",
            "No HM3D or Habitat demo/test scene candidate was found in the searched roots",
        ]
    return "BLOCKED_ON_HABITAT_PACKAGES", [
        "Habitat-Lab and/or Habitat-Sim imports are not available in the current environment",
        "Scene data search can still be rerun later after Habitat packages are installed",
    ]


def render_markdown(
    probes: list[ModuleProbe],
    scenes: list[SceneCandidate],
    searched_roots: list[str],
    plan_status: str,
    assessment_notes: list[str],
) -> str:
    timestamp = datetime.now().astimezone().isoformat()
    python_executable = sys.executable
    python_version = sys.version.splitlines()[0]
    conda_env = os.environ.get("CONDA_DEFAULT_ENV", "")

    lines = [
        "# Habitat Environment Check",
        "",
        f"- Timestamp: `{timestamp}`",
        f"- Workspace: `{Path.cwd()}`",
        f"- Python executable: `{python_executable}`",
        f"- Python version: `{python_version}`",
        f"- Conda environment: `{conda_env or 'not set'}`",
        f"- Assessment: `{plan_status}`",
        "",
        "## Package Probes",
    ]

    for probe in probes:
        status = "OK" if probe.installed else "MISSING"
        lines.extend(
            [
                f"- `{probe.label}`: `{status}`",
                f"  module: `{probe.module_name}`",
                f"  version: `{probe.version or 'n/a'}`",
                f"  path: `{probe.module_path or 'n/a'}`",
                f"  note: `{probe.note}`",
            ]
        )

    lines.extend(["", "## Searched Roots"])
    if searched_roots:
        lines.extend([f"- `{root}`" for root in searched_roots])
    else:
        lines.append("- No existing candidate roots were found to scan")

    lines.extend(["", "## Scene Candidates"])
    if scenes:
        for scene in scenes:
            lines.extend(
                [
                    f"- `{scene.kind}`: `{scene.path}`",
                    f"  evidence: `{scene.evidence}`",
                ]
            )
    else:
        lines.append("- No HM3D, Habitat demo/test scene, or generic scene dataset candidates were found")

    lines.extend(["", "## Assessment Notes"])
    lines.extend([f"- {note}" for note in assessment_notes])

    lines.extend(["", "## Recommended Next Action"])
    if plan_status == "PLAN_A_READY":
        lines.append("- Proceed with HM3D-first Habitat validation in T0.2/T0.3")
    elif plan_status == "PLAN_A_DEGRADED_READY":
        lines.append("- Proceed with Habitat validation using the detected demo/test or generic scene candidate")
    elif plan_status == "BLOCKED_ON_SCENE_DATA":
        lines.append("- Record missing-scene-data status in env_report and prepare Plan A degraded path or Plan B if data cannot be provided")
    else:
        lines.append("- Record Habitat package blockage in env_report before attempting installation or fallback planning")

    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()

    probes = [
        probe_module("Habitat-Lab", "habitat", ("habitat-lab", "habitat")),
        probe_module(
            "Habitat-Sim",
            "habitat_sim",
            (
                "habitat-sim",
                "habitat-sim-cu128",
                "habitat-sim-cu126",
                "habitat-sim-cu124",
                "habitat-sim-cu121",
                "habitat-sim-headless",
            ),
        ),
        probe_module("Habitat-Baselines", "habitat_baselines", ("habitat-baselines",)),
        probe_module("Magnum", "magnum", ("magnum-bindings", "magnum")),
        probe_module("Corrade", "corrade", ("corrade",)),
    ]

    roots = candidate_roots(args.search_root)
    scenes, searched_roots = scan_scene_candidates(roots, max_depth=args.max_depth)
    plan_status, assessment_notes = summarize_plan(probes, scenes)
    report = render_markdown(probes, scenes, searched_roots, plan_status, assessment_notes)

    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")

    sys.stdout.write(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
