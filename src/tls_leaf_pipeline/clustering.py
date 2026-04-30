"""Filtrage SOR optionnel puis clustering HDBSCAN, global ou par tuiles."""

from __future__ import annotations

from pathlib import Path
from time import perf_counter

import hdbscan
import laspy
import numpy as np
import open3d as o3d
from laspy import ExtraBytesParams

from .colors import labels_to_rgb16
from .config import ClusteringConfig, PipelineConfig
from .io_utils import las_xyz, make_run_dir, write_json


def sor_mask(points_xyz: np.ndarray, nb_neighbors: int, std_ratio: float) -> np.ndarray:
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(points_xyz)
    _, ind = pcd.remove_statistical_outlier(nb_neighbors=int(nb_neighbors), std_ratio=float(std_ratio))
    mask = np.zeros(len(points_xyz), dtype=bool)
    mask[np.asarray(ind, dtype=np.int64)] = True
    return mask


def tile_indices(points_xyz: np.ndarray, tile_size_xyz: tuple[float, float, float]) -> np.ndarray:
    mins = points_xyz.min(axis=0)
    tile_size = np.asarray(tile_size_xyz, dtype=np.float64)
    return np.floor((points_xyz - mins[None, :]) / tile_size[None, :]).astype(np.int32)


def _add_or_replace_cluster_id(las: laspy.LasData, labels: np.ndarray) -> None:
    dims = set(las.point_format.dimension_names)
    if "cluster_id" not in dims:
        las.add_extra_dim(ExtraBytesParams(name="cluster_id", type=np.int32))
    las["cluster_id"] = labels.astype(np.int32)


def _write_colored_las(las: laspy.LasData, labels: np.ndarray, path: Path) -> Path | None:
    dims = set(las.point_format.dimension_names)
    if not {"red", "green", "blue"}.issubset(dims):
        return None
    out = laspy.LasData(las.header.copy())
    out.points = las.points.copy()
    rgb = labels_to_rgb16(labels)
    out["red"] = rgb[:, 0]
    out["green"] = rgb[:, 1]
    out["blue"] = rgb[:, 2]
    path.parent.mkdir(parents=True, exist_ok=True)
    out.write(path)
    return path


def _hdbscan_model(cfg: ClusteringConfig) -> hdbscan.HDBSCAN:
    return hdbscan.HDBSCAN(
        min_cluster_size=cfg.hdbscan_min_cluster_size,
        min_samples=cfg.hdbscan_min_samples,
        cluster_selection_epsilon=cfg.hdbscan_cluster_selection_epsilon,
        cluster_selection_method=cfg.hdbscan_cluster_selection_method,
        core_dist_n_jobs=1,
    )


def _cluster_global(points_xyz: np.ndarray, cfg: ClusteringConfig) -> tuple[np.ndarray, int, int, int]:
    labels = _hdbscan_model(cfg).fit_predict(points_xyz).astype(np.int32)
    n_clusters = int(np.count_nonzero(np.unique(labels) >= 0))
    return labels, n_clusters, 1, 0


def _cluster_by_tiles(points_xyz: np.ndarray, cfg: ClusteringConfig) -> tuple[np.ndarray, int, int, int]:
    tiles = tile_indices(points_xyz, cfg.tile_size_xyz_m)
    _, inv = np.unique(tiles, axis=0, return_inverse=True)
    n_tiles = int(inv.max() + 1) if len(inv) else 0

    labels = np.full(len(points_xyz), -1, dtype=np.int32)
    next_cluster = 0
    n_tiles_clustered = 0
    n_tiles_small = 0

    for tile_id in range(n_tiles):
        idx = np.where(inv == tile_id)[0]
        if len(idx) < cfg.min_points_per_tile:
            n_tiles_small += 1
            continue

        local = _hdbscan_model(cfg).fit_predict(points_xyz[idx]).astype(np.int32)
        for local_id in np.unique(local[local >= 0]).astype(np.int32):
            labels[idx[local == local_id]] = next_cluster
            next_cluster += 1
        n_tiles_clustered += 1

    return labels, int(next_cluster), int(n_tiles_clustered), int(n_tiles_small)


def cluster_points(points_xyz: np.ndarray, cfg: ClusteringConfig) -> tuple[np.ndarray, dict[str, int]]:
    """Clusterise des points deja charges, avec SOR et tuiles optionnels."""
    if c_enable_sor := cfg.enable_sor:
        keep = sor_mask(points_xyz, cfg.sor_nb_neighbors, cfg.sor_std_ratio)
        if not np.any(keep):
            raise RuntimeError("Le SOR a supprime tous les points.")
        work_points = points_xyz[keep]
    else:
        keep = np.ones(len(points_xyz), dtype=bool)
        work_points = points_xyz

    if cfg.enable_tiling:
        labels_work, n_clusters, n_tiles_clustered, n_tiles_small = _cluster_by_tiles(work_points, cfg)
        n_tiles = int(len(np.unique(tile_indices(work_points, cfg.tile_size_xyz_m), axis=0)))
    else:
        labels_work, n_clusters, n_tiles_clustered, n_tiles_small = _cluster_global(work_points, cfg)
        n_tiles = 1

    labels = np.full(len(points_xyz), -1, dtype=np.int32)
    labels[keep] = labels_work
    stats = {
        "enable_sor": int(c_enable_sor),
        "enable_tiling": int(cfg.enable_tiling),
        "n_input_points": int(len(points_xyz)),
        "n_work_points": int(len(work_points)),
        "n_tiles": int(n_tiles),
        "n_tiles_clustered": int(n_tiles_clustered),
        "n_tiles_small": int(n_tiles_small),
        "n_clusters": int(n_clusters),
        "n_noise": int(np.count_nonzero(labels < 0)),
    }
    return labels, stats


def run_clustering_stage(cfg: PipelineConfig, output_root: Path | None = None) -> Path:
    t0 = perf_counter()
    c = cfg.clustering
    root = output_root if output_root is not None else cfg.paths.output_root / "clustering"
    run_dir = make_run_dir(root)

    print(f"run dir               : {run_dir}")
    print("step 1/5: chargement LAS/LAZ...")
    las_in = laspy.read(cfg.paths.input_las)
    xyz = las_xyz(las_in)
    print(f"points entree         : {len(xyz):,}")

    print("step 2/5: filtrage SOR...")
    sor_path = None
    if c.enable_sor:
        t_sor = perf_counter()
        keep = sor_mask(xyz, c.sor_nb_neighbors, c.sor_std_ratio)
        print(f"points SOR gardes     : {int(keep.sum()):,} / {len(keep):,}")
        print(f"temps SOR             : {perf_counter() - t_sor:.1f}s")
        if not np.any(keep):
            raise RuntimeError("Le SOR a supprime tous les points.")
    else:
        keep = np.ones(len(xyz), dtype=bool)
        print("SOR                   : desactive")

    las_work = laspy.LasData(las_in.header.copy())
    las_work.points = las_in.points[keep]
    if c.enable_sor:
        sor_path = run_dir / "sor_filtered.las"
        las_work.write(sor_path)

    xyz_work = las_xyz(las_work)

    print("step 3/5: preparation clustering...")
    if c.enable_tiling:
        n_tiles = int(len(np.unique(tile_indices(xyz_work, c.tile_size_xyz_m), axis=0)))
        print(f"mode clustering       : par tuiles")
        print(f"tuiles                : {n_tiles:,}")
    else:
        n_tiles = 1
        print("mode clustering       : global, sans tuiles")

    print("step 4/5: HDBSCAN...")
    t_cluster = perf_counter()
    if c.enable_tiling:
        labels, n_clusters, n_tiles_clustered, n_tiles_small = _cluster_by_tiles(xyz_work, c)
    else:
        labels, n_clusters, n_tiles_clustered, n_tiles_small = _cluster_global(xyz_work, c)

    print(f"clusters globaux      : {n_clusters:,}")
    print(f"points bruit          : {int(np.count_nonzero(labels < 0)):,}")
    print(f"temps clustering      : {perf_counter() - t_cluster:.1f}s")

    print("step 5/5: exports...")
    las_out = laspy.LasData(las_work.header.copy())
    las_out.points = las_work.points.copy()
    _add_or_replace_cluster_id(las_out, labels)
    prefix = ("sor_" if c.enable_sor else "") + ("tiled_" if c.enable_tiling else "")
    clustered_path = run_dir / f"{prefix}hdbscan.las"
    las_out.write(clustered_path)

    colored_path = None
    if c.export_colored_las:
        colored_path = _write_colored_las(las_out, labels, run_dir / f"{prefix}hdbscan_colored.las")

    summary = {
        "input_las": str(cfg.paths.input_las),
        "run_dir": str(run_dir),
        "params": c.__dict__,
        "stats": {
            "n_input_points": int(len(xyz)),
            "n_work_points": int(len(xyz_work)),
            "n_tiles": int(n_tiles),
            "n_tiles_clustered": int(n_tiles_clustered),
            "n_tiles_small": int(n_tiles_small),
            "n_clusters": int(n_clusters),
            "n_noise": int(np.count_nonzero(labels < 0)),
            "elapsed_s": float(perf_counter() - t0),
        },
        "outputs": {
            "sor_filtered_las": str(sor_path) if sor_path is not None else None,
            "clustered_las": str(clustered_path),
            "clustered_colored_las": str(colored_path) if colored_path else None,
        },
    }
    write_json(run_dir / "summary.json", summary)
    return clustered_path
