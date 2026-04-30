"""Petits utilitaires partages par les pipelines."""

from __future__ import annotations

from pathlib import Path
import json

import laspy
import numpy as np


def make_run_dir(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    ids: list[int] = []
    for p in root.iterdir():
        if not p.is_dir() or not p.name.startswith("run_"):
            continue
        suffix = p.name.replace("run_", "", 1)
        if suffix.isdigit():
            ids.append(int(suffix))
    run_dir = root / f"run_{(max(ids) + 1) if ids else 1:02d}"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def las_xyz(las: laspy.LasData) -> np.ndarray:
    return np.column_stack((np.asarray(las.x), np.asarray(las.y), np.asarray(las.z))).astype(np.float64)


def write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2), encoding="utf-8")

