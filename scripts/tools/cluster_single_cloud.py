#!/usr/bin/env python3
"""Clusterise directement un .las/.laz sans passer par la pipeline complete."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import laspy  # noqa: E402
import numpy as np  # noqa: E402
from laspy import ExtraBytesParams  # noqa: E402

from tls_leaf_pipeline.clustering import cluster_points  # noqa: E402
from tls_leaf_pipeline.colors import labels_to_rgb16  # noqa: E402
from tls_leaf_pipeline.config import ClusteringConfig  # noqa: E402
from tls_leaf_pipeline.io_utils import las_xyz  # noqa: E402


def make_config(args: argparse.Namespace) -> ClusteringConfig:
    return ClusteringConfig(
        enable_sor=not args.no_sor,
        sor_nb_neighbors=int(args.sor_k),
        sor_std_ratio=float(args.sor_alpha),
        enable_tiling=not args.no_tiling,
        tile_size_xyz_m=(float(args.tile_size), float(args.tile_size), float(args.tile_size)),
        min_points_per_tile=int(args.min_points_per_tile),
        hdbscan_min_cluster_size=int(args.min_cluster_size),
        hdbscan_min_samples=int(args.min_samples),
        hdbscan_cluster_selection_epsilon=float(args.cluster_selection_epsilon),
        hdbscan_cluster_selection_method=str(args.cluster_selection_method),
        export_colored_las=not args.no_color,
    )


def add_cluster_id(las: laspy.LasData, labels: np.ndarray) -> None:
    if "cluster_id" not in set(las.point_format.dimension_names):
        las.add_extra_dim(ExtraBytesParams(name="cluster_id", type=np.int32))
    las["cluster_id"] = labels.astype(np.int32)


def colorize_if_possible(las: laspy.LasData, labels: np.ndarray) -> bool:
    dims = set(las.point_format.dimension_names)
    if not {"red", "green", "blue"}.issubset(dims):
        return False
    rgb = labels_to_rgb16(labels)
    las["red"] = rgb[:, 0]
    las["green"] = rgb[:, 1]
    las["blue"] = rgb[:, 2]
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Clustering HDBSCAN direct d'un fichier LAS/LAZ.")
    parser.add_argument("--input", required=True, type=Path, help="Fichier .las/.laz")
    parser.add_argument("--output", required=True, type=Path, help="LAS/LAZ de sortie avec cluster_id")
    parser.add_argument("--no-sor", action="store_true")
    parser.add_argument("--sor-k", type=int, default=30)
    parser.add_argument("--sor-alpha", type=float, default=1.0)
    parser.add_argument("--no-tiling", action="store_true")
    parser.add_argument("--tile-size", type=float, default=0.5)
    parser.add_argument("--min-points-per-tile", type=int, default=120)
    parser.add_argument("--min-cluster-size", type=int, default=300)
    parser.add_argument("--min-samples", type=int, default=5)
    parser.add_argument("--cluster-selection-epsilon", type=float, default=0.0)
    parser.add_argument("--cluster-selection-method", choices=["eom", "leaf"], default="eom")
    parser.add_argument("--no-color", action="store_true")
    args = parser.parse_args()

    if args.input.suffix.lower() not in {".las", ".laz"}:
        raise SystemExit("Ce script accepte uniquement .las/.laz")

    t0 = perf_counter()
    cfg = make_config(args)
    las = laspy.read(args.input)
    points = las_xyz(las)
    labels, stats = cluster_points(points, cfg)

    out = laspy.LasData(las.header.copy())
    out.points = las.points.copy()
    add_cluster_id(out, labels)
    colored = False
    if cfg.export_colored_las:
        colored = colorize_if_possible(out, labels)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    out.write(args.output)

    print(f"input points : {len(points):,}")
    print(f"clusters     : {stats['n_clusters']:,}")
    print(f"noise points : {stats['n_noise']:,}")
    print(f"colored      : {colored}")
    print(f"output       : {args.output}")
    print(f"elapsed s    : {perf_counter() - t0:.2f}")


if __name__ == "__main__":
    main()

