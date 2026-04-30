#!/usr/bin/env python3
"""Reconstruit directement une mesh Poisson lissee depuis un .las/.laz/.txt."""

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
import open3d as o3d  # noqa: E402

from tls_leaf_pipeline.config import MeshingConfig  # noqa: E402
from tls_leaf_pipeline.meshing import (  # noqa: E402
    configure_open3d_logging,
    poisson_envelope,
    smooth_with_edge_reconstruction,
    voxel_downsample_points,
    write_mesh,
)


def default_meshing_config(args: argparse.Namespace) -> MeshingConfig:
    return MeshingConfig(
        cluster_field="cluster_id",
        noise_label=-1,
        min_points_cluster=int(args.min_points),
        start_cluster_id=0,
        end_cluster_id=10_000_000,
        poisson_depth=int(args.poisson_depth),
        normal_radius=float(args.normal_radius),
        normal_max_nn=int(args.normal_max_nn),
        orient_k=int(args.orient_k),
        max_dist_factor=float(args.max_dist_factor),
        fill_poisson_holes=not args.no_fill_poisson_holes,
        max_hole_area_cm2=float(args.max_hole_area_cm2),
        subdiv_iter=int(args.subdiv_iter),
        laplacian_iter=int(args.laplacian_iter),
        taubin_iter=int(args.taubin_iter),
        taubin_lambda=float(args.taubin_lambda),
        taubin_mu=float(args.taubin_mu),
        fill_after_smooth=not args.no_fill_after_smooth,
        max_hole_area_after_smooth_cm2=float(args.max_hole_area_after_smooth_cm2),
        voxel_size_per_cluster=float(args.voxel_size),
        max_points_per_cluster=int(args.max_points),
        export_per_cluster_meshes=False,
        export_per_cluster_poisson_raw=False,
    )


def load_points(path: Path) -> np.ndarray:
    suffix = path.suffix.lower()
    if suffix in {".las", ".laz"}:
        las = laspy.read(path)
        pts = np.column_stack((np.asarray(las.x), np.asarray(las.y), np.asarray(las.z)))
        return pts.astype(np.float64)
    if suffix == ".txt":
        arr = np.loadtxt(path, dtype=np.float64)
        if arr.ndim == 1:
            arr = arr[None, :]
        if arr.shape[1] < 3:
            raise ValueError("Le fichier TXT doit contenir au moins trois colonnes x y z.")
        return arr[:, :3].astype(np.float64)
    raise ValueError(f"Format non supporte: {path.suffix}")


def cap_points(points: np.ndarray, max_points: int) -> np.ndarray:
    if max_points <= 0 or len(points) <= max_points:
        return points
    rng = np.random.default_rng(42)
    idx = np.sort(rng.choice(len(points), size=max_points, replace=False))
    return points[idx]


def main() -> None:
    parser = argparse.ArgumentParser(description="Mesh Poisson lissee depuis un nuage unique.")
    parser.add_argument("--input", required=True, type=Path, help="Fichier .las/.laz/.txt")
    parser.add_argument("--output", required=True, type=Path, help="Mesh .ply de sortie")
    parser.add_argument("--export-raw-poisson", type=Path, default=None)
    parser.add_argument("--voxel-size", type=float, default=0.0)
    parser.add_argument("--max-points", type=int, default=0)
    parser.add_argument("--min-points", type=int, default=30)
    parser.add_argument("--poisson-depth", type=int, default=6)
    parser.add_argument("--normal-radius", type=float, default=0.02)
    parser.add_argument("--normal-max-nn", type=int, default=100)
    parser.add_argument("--orient-k", type=int, default=10)
    parser.add_argument("--max-dist-factor", type=float, default=2.0)
    parser.add_argument("--no-fill-poisson-holes", action="store_true")
    parser.add_argument("--max-hole-area-cm2", type=float, default=15.0)
    parser.add_argument("--subdiv-iter", type=int, default=2)
    parser.add_argument("--laplacian-iter", type=int, default=100)
    parser.add_argument("--taubin-iter", type=int, default=40)
    parser.add_argument("--taubin-lambda", type=float, default=0.5)
    parser.add_argument("--taubin-mu", type=float, default=-0.55)
    parser.add_argument("--no-fill-after-smooth", action="store_true")
    parser.add_argument("--max-hole-area-after-smooth-cm2", type=float, default=15.0)
    args = parser.parse_args()

    t0 = perf_counter()
    configure_open3d_logging()
    cfg = default_meshing_config(args)

    points = load_points(args.input)
    points = voxel_downsample_points(points, cfg.voxel_size_per_cluster)
    points = cap_points(points, cfg.max_points_per_cluster)
    if len(points) < cfg.min_points_cluster:
        raise SystemExit(f"Pas assez de points: {len(points)} < {cfg.min_points_cluster}")

    # Poisson est plus stable numeriquement autour de l'origine.
    center = points.mean(axis=0)
    points_local = points - center[None, :]

    print(f"points       : {len(points):,}")
    print("poisson      : start")
    mesh_poisson = poisson_envelope(points_local, cfg)
    print("smooth       : start")
    mesh_smooth = smooth_with_edge_reconstruction(mesh_poisson, cfg)

    for mesh in (mesh_poisson, mesh_smooth):
        verts = np.asarray(mesh.vertices, dtype=np.float64)
        mesh.vertices = o3d.utility.Vector3dVector(verts + center[None, :])
        mesh.compute_vertex_normals()

    write_mesh(args.output, mesh_smooth)
    if args.export_raw_poisson is not None:
        write_mesh(args.export_raw_poisson, mesh_poisson)

    print(f"output       : {args.output}")
    print(f"area cm2     : {mesh_smooth.get_surface_area() * 1e4:.3f}")
    print(f"elapsed s    : {perf_counter() - t0:.2f}")


if __name__ == "__main__":
    main()

