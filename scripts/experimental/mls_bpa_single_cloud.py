#!/usr/bin/env python3
"""Experimental: MLS puis BPA adaptatif sur un .txt/.las/.laz."""

from __future__ import annotations

import argparse
import json
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
from scipy.spatial import cKDTree  # noqa: E402


def load_points(path: Path) -> np.ndarray:
    suffix = path.suffix.lower()
    if suffix in {".las", ".laz"}:
        las = laspy.read(path)
        return np.column_stack((np.asarray(las.x), np.asarray(las.y), np.asarray(las.z))).astype(np.float64)
    if suffix == ".txt":
        arr = np.loadtxt(path, dtype=np.float64)
        if arr.ndim == 1:
            arr = arr[None, :]
        if arr.shape[1] < 3:
            raise ValueError("Le TXT doit contenir au moins trois colonnes x y z.")
        return arr[:, :3].astype(np.float64)
    raise ValueError(f"Format non supporte: {path.suffix}")


def voxel_downsample(points: np.ndarray, voxel_size: float) -> np.ndarray:
    if voxel_size <= 0:
        return points
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(points)
    pcd = pcd.voxel_down_sample(float(voxel_size))
    return np.asarray(pcd.points, dtype=np.float64)


def cap_points(points: np.ndarray, max_points: int) -> np.ndarray:
    if max_points <= 0 or len(points) <= max_points:
        return points
    rng = np.random.default_rng(42)
    idx = np.sort(rng.choice(len(points), size=int(max_points), replace=False))
    return points[idx]


def save_points_ply(path: Path, points: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(points)
    ok = o3d.io.write_point_cloud(str(path), pcd, write_ascii=False)
    if not ok:
        raise RuntimeError(f"Echec ecriture points: {path}")


def median_knn_distance(points: np.ndarray, k: int) -> float:
    if len(points) < 2:
        return 0.0
    kk = min(max(2, int(k)), len(points))
    dists, _ = cKDTree(points).query(points, k=kk)
    if dists.ndim == 1:
        vals = dists
    else:
        vals = dists[:, 1:].reshape(-1)
    vals = vals[np.isfinite(vals) & (vals > 0)]
    return float(np.median(vals)) if len(vals) else 0.0


def mls_project(points: np.ndarray, k: int, n_iters: int, max_disp: float) -> np.ndarray:
    if len(points) < max(5, int(k)):
        return points.copy()

    pts = points.copy()
    for _ in range(int(max(1, n_iters))):
        tree = cKDTree(pts)
        _, nn_idx = tree.query(pts, k=min(int(k), len(pts)))
        if nn_idx.ndim == 1:
            nn_idx = nn_idx[:, None]

        out = pts.copy()
        for i in range(len(pts)):
            neigh = pts[nn_idx[i]]
            center = neigh.mean(axis=0)
            centered = neigh - center[None, :]
            cov = (centered.T @ centered) / max(len(neigh), 1)
            eigvals, eigvecs = np.linalg.eigh(cov)
            normal = eigvecs[:, int(np.argmin(eigvals))]
            normal = normal / max(np.linalg.norm(normal), 1e-12)

            # Projection orthogonale sur le plan local, bornee pour eviter
            # de faire glisser un point vers une feuille voisine.
            dist = float(np.dot(pts[i] - center, normal))
            dist = float(np.clip(dist, -float(max_disp), float(max_disp)))
            out[i] = pts[i] - dist * normal
        pts = out
    return pts


def adaptive_bpa_radii(points: np.ndarray, knn: int, factors: list[float]) -> list[float]:
    base = median_knn_distance(points, k=knn)
    if base <= 0:
        return []
    radii = sorted({float(base * f) for f in factors if f > 0})
    return radii


def bpa_mesh_adaptive(
    points: np.ndarray,
    normal_k: int,
    orient_k: int,
    radius_knn: int,
    radius_factors: list[float],
) -> o3d.geometry.TriangleMesh:
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(points)
    pcd.estimate_normals(search_param=o3d.geometry.KDTreeSearchParamKNN(knn=int(normal_k)))
    try:
        pcd.orient_normals_consistent_tangent_plane(int(orient_k))
    except RuntimeError:
        pass

    radii = adaptive_bpa_radii(points, knn=radius_knn, factors=radius_factors)
    if not radii:
        raise RuntimeError("Impossible de calculer des rayons BPA adaptatifs.")

    mesh = o3d.geometry.TriangleMesh.create_from_point_cloud_ball_pivoting(
        pcd,
        o3d.utility.DoubleVector(radii),
    )
    if len(np.asarray(mesh.triangles)) == 0:
        raise RuntimeError("BPA a produit une mesh vide.")
    mesh.compute_vertex_normals()
    return mesh


def write_mesh(path: Path, mesh: o3d.geometry.TriangleMesh) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ok = o3d.io.write_triangle_mesh(str(path), mesh, write_ascii=False)
    if not ok:
        ok = o3d.io.write_triangle_mesh(str(path), mesh, write_ascii=True)
    if not ok:
        raise RuntimeError(f"Echec ecriture mesh: {path}")


def parse_factors(text: str) -> list[float]:
    vals = [float(v.strip()) for v in text.split(",") if v.strip()]
    if not vals:
        raise ValueError("La liste de facteurs BPA est vide.")
    return vals


def main() -> None:
    parser = argparse.ArgumentParser(description="Experimental MLS + BPA adaptatif.")
    parser.add_argument("--input", required=True, type=Path, help="Fichier .txt/.las/.laz")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--voxel-size", type=float, default=0.0)
    parser.add_argument("--max-points", type=int, default=0)
    parser.add_argument("--recenter", action="store_true", help="Recentre les exports autour de 0.")
    parser.add_argument("--mls-k", type=int, default=30)
    parser.add_argument("--mls-iters", type=int, default=5)
    parser.add_argument("--mls-max-displacement", type=float, default=0.02)
    parser.add_argument("--normal-k", type=int, default=30)
    parser.add_argument("--orient-k", type=int, default=20)
    parser.add_argument("--radius-knn", type=int, default=8)
    parser.add_argument("--radius-factors", type=str, default="0.75,1.0,1.5,2.0,3.0,4.0")
    args = parser.parse_args()

    t0 = perf_counter()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    points = load_points(args.input)
    points = voxel_downsample(points, args.voxel_size)
    points = cap_points(points, args.max_points)
    if len(points) < 30:
        raise SystemExit(f"Pas assez de points pour MLS+BPA: {len(points)}")

    offset = points.mean(axis=0) if args.recenter else np.zeros(3, dtype=np.float64)
    points_raw = points - offset[None, :]
    points_mls = mls_project(
        points_raw,
        k=int(args.mls_k),
        n_iters=int(args.mls_iters),
        max_disp=float(args.mls_max_displacement),
    )

    radius_factors = parse_factors(args.radius_factors)
    mesh = bpa_mesh_adaptive(
        points_mls,
        normal_k=int(args.normal_k),
        orient_k=int(args.orient_k),
        radius_knn=int(args.radius_knn),
        radius_factors=radius_factors,
    )

    raw_path = args.output_dir / "points_raw.ply"
    mls_path = args.output_dir / "points_mls.ply"
    mesh_path = args.output_dir / "bpa_mls_adaptive.ply"
    save_points_ply(raw_path, points_raw)
    save_points_ply(mls_path, points_mls)
    write_mesh(mesh_path, mesh)

    radii = adaptive_bpa_radii(points_mls, knn=int(args.radius_knn), factors=radius_factors)
    summary = {
        "input": str(args.input),
        "output_dir": str(args.output_dir),
        "n_points": int(len(points_raw)),
        "area_bpa_cm2": float(mesh.get_surface_area() * 1e4),
        "offset_applied": [float(v) for v in offset],
        "params": {
            "voxel_size": float(args.voxel_size),
            "max_points": int(args.max_points),
            "recenter": bool(args.recenter),
            "mls_k": int(args.mls_k),
            "mls_iters": int(args.mls_iters),
            "mls_max_displacement": float(args.mls_max_displacement),
            "normal_k": int(args.normal_k),
            "orient_k": int(args.orient_k),
            "radius_knn": int(args.radius_knn),
            "radius_factors": [float(v) for v in radius_factors],
            "adaptive_radii_m": [float(v) for v in radii],
        },
        "outputs": {
            "points_raw_ply": str(raw_path),
            "points_mls_ply": str(mls_path),
            "bpa_mesh_ply": str(mesh_path),
        },
        "elapsed_s": float(perf_counter() - t0),
    }
    (args.output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"points       : {len(points_raw):,}")
    print(f"radii        : {', '.join(f'{r:.5f}' for r in radii)}")
    print(f"area cm2     : {summary['area_bpa_cm2']:.3f}")
    print(f"points raw   : {raw_path}")
    print(f"points MLS   : {mls_path}")
    print(f"mesh BPA     : {mesh_path}")
    print(f"elapsed s    : {summary['elapsed_s']:.2f}")


if __name__ == "__main__":
    main()

