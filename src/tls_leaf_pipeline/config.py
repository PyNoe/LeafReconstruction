"""Lecture et validation legere de la configuration TOML."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib


@dataclass
class PathsConfig:
    input_las: Path
    clustered_las: Path
    output_root: Path


@dataclass
class ClusteringConfig:
    enable_sor: bool
    sor_nb_neighbors: int
    sor_std_ratio: float
    enable_tiling: bool
    tile_size_xyz_m: tuple[float, float, float]
    min_points_per_tile: int
    hdbscan_min_cluster_size: int
    hdbscan_min_samples: int
    hdbscan_cluster_selection_epsilon: float
    hdbscan_cluster_selection_method: str
    export_colored_las: bool


@dataclass
class MeshingConfig:
    cluster_field: str
    noise_label: int
    min_points_cluster: int
    start_cluster_id: int
    end_cluster_id: int
    poisson_depth: int
    normal_radius: float
    normal_max_nn: int
    orient_k: int
    max_dist_factor: float
    fill_poisson_holes: bool
    max_hole_area_cm2: float
    subdiv_iter: int
    laplacian_iter: int
    taubin_iter: int
    taubin_lambda: float
    taubin_mu: float
    fill_after_smooth: bool
    max_hole_area_after_smooth_cm2: float
    voxel_size_per_cluster: float
    max_points_per_cluster: int
    export_per_cluster_meshes: bool
    export_per_cluster_poisson_raw: bool


@dataclass
class PipelineConfig:
    paths: PathsConfig
    clustering: ClusteringConfig
    meshing: MeshingConfig


def _as_path(value: str) -> Path:
    return Path(value).expanduser()


def load_config(path: Path) -> PipelineConfig:
    with path.open("rb") as f:
        raw = tomllib.load(f)

    p = raw["paths"]
    c = raw["clustering"]
    m = raw["meshing"]

    tile = c.get("tile_size_xyz_m", [0.5, 0.5, 0.5])
    if len(tile) != 3:
        raise ValueError("clustering.tile_size_xyz_m doit contenir 3 valeurs")

    return PipelineConfig(
        paths=PathsConfig(
            input_las=_as_path(p["input_las"]),
            clustered_las=_as_path(p["clustered_las"]),
            output_root=_as_path(p["output_root"]),
        ),
        clustering=ClusteringConfig(
            enable_sor=bool(c.get("enable_sor", True)),
            sor_nb_neighbors=int(c["sor_nb_neighbors"]),
            sor_std_ratio=float(c["sor_std_ratio"]),
            enable_tiling=bool(c.get("enable_tiling", True)),
            tile_size_xyz_m=tuple(float(v) for v in tile),  # type: ignore[arg-type]
            min_points_per_tile=int(c["min_points_per_tile"]),
            hdbscan_min_cluster_size=int(c["hdbscan_min_cluster_size"]),
            hdbscan_min_samples=int(c["hdbscan_min_samples"]),
            hdbscan_cluster_selection_epsilon=float(c["hdbscan_cluster_selection_epsilon"]),
            hdbscan_cluster_selection_method=str(c["hdbscan_cluster_selection_method"]),
            export_colored_las=bool(c["export_colored_las"]),
        ),
        meshing=MeshingConfig(
            cluster_field=str(m["cluster_field"]),
            noise_label=int(m["noise_label"]),
            min_points_cluster=int(m["min_points_cluster"]),
            start_cluster_id=int(m["start_cluster_id"]),
            end_cluster_id=int(m["end_cluster_id"]),
            poisson_depth=int(m["poisson_depth"]),
            normal_radius=float(m["normal_radius"]),
            normal_max_nn=int(m["normal_max_nn"]),
            orient_k=int(m["orient_k"]),
            max_dist_factor=float(m["max_dist_factor"]),
            fill_poisson_holes=bool(m["fill_poisson_holes"]),
            max_hole_area_cm2=float(m["max_hole_area_cm2"]),
            subdiv_iter=int(m["subdiv_iter"]),
            laplacian_iter=int(m["laplacian_iter"]),
            taubin_iter=int(m["taubin_iter"]),
            taubin_lambda=float(m["taubin_lambda"]),
            taubin_mu=float(m["taubin_mu"]),
            fill_after_smooth=bool(m["fill_after_smooth"]),
            max_hole_area_after_smooth_cm2=float(m["max_hole_area_after_smooth_cm2"]),
            voxel_size_per_cluster=float(m["voxel_size_per_cluster"]),
            max_points_per_cluster=int(m["max_points_per_cluster"]),
            export_per_cluster_meshes=bool(m["export_per_cluster_meshes"]),
            export_per_cluster_poisson_raw=bool(m["export_per_cluster_poisson_raw"]),
        ),
    )
