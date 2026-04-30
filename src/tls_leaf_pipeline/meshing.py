"""Reconstruction Poisson + lissage + reconstruction des bords."""

from __future__ import annotations

from collections import defaultdict
import contextlib
import csv
import os
from pathlib import Path
from time import perf_counter

import laspy
import numpy as np
import open3d as o3d
from scipy.spatial import cKDTree

from .colors import cluster_color_rgb01
from .config import MeshingConfig, PipelineConfig
from .io_utils import las_xyz, make_run_dir, write_json


@contextlib.contextmanager
def suppress_open3d_output():
    """Evite que Poisson remplisse le terminal de logs C++ peu lisibles."""
    old_stdout = os.dup(1)
    old_stderr = os.dup(2)
    devnull = open(os.devnull, "w", encoding="utf-8")
    os.dup2(devnull.fileno(), 1)
    os.dup2(devnull.fileno(), 2)
    try:
        yield
    finally:
        os.dup2(old_stdout, 1)
        os.dup2(old_stderr, 2)
        os.close(old_stdout)
        os.close(old_stderr)
        devnull.close()


def configure_open3d_logging() -> None:
    try:
        o3d.utility.set_verbosity_level(o3d.utility.VerbosityLevel.Error)
    except Exception:
        pass


def boundary_loops(mesh: o3d.geometry.TriangleMesh) -> list[list[int]]:
    triangles = np.asarray(mesh.triangles, dtype=np.int32)
    if len(triangles) == 0:
        return []

    edge_count: dict[tuple[int, int], int] = defaultdict(int)
    for tri in triangles:
        for i in range(3):
            a = int(tri[i])
            b = int(tri[(i + 1) % 3])
            edge_count[(min(a, b), max(a, b))] += 1

    boundary_edges = [edge for edge, count in edge_count.items() if count == 1]
    if not boundary_edges:
        return []

    adjacency: dict[int, list[int]] = defaultdict(list)
    for a, b in boundary_edges:
        adjacency[a].append(b)
        adjacency[b].append(a)

    visited: set[int] = set()
    loops: list[list[int]] = []
    for start in list(adjacency):
        if start in visited:
            continue
        loop = [start]
        current = start
        visited.add(start)
        while True:
            nxt = [v for v in adjacency[current] if v not in visited]
            if not nxt:
                break
            current = nxt[0]
            visited.add(current)
            loop.append(current)
        if len(loop) >= 3:
            loops.append(loop)

    loops.sort(key=len, reverse=True)
    return loops


def loop_area(loop: list[int], vertices: np.ndarray) -> float:
    pts = vertices[np.asarray(loop, dtype=np.int32)]
    center = pts.mean(axis=0)
    area = 0.0
    for i in range(len(pts)):
        v1 = pts[i] - center
        v2 = pts[(i + 1) % len(pts)] - center
        area += 0.5 * float(np.linalg.norm(np.cross(v1, v2)))
    return area


def fill_interior_holes(mesh: o3d.geometry.TriangleMesh, max_area_m2: float) -> o3d.geometry.TriangleMesh:
    loops = boundary_loops(mesh)
    if len(loops) <= 1:
        return mesh

    vertices = list(np.asarray(mesh.vertices, dtype=np.float64))
    triangles = list(np.asarray(mesh.triangles, dtype=np.int32))
    verts_array = np.asarray(vertices, dtype=np.float64)
    filled = 0

    # Le plus grand contour est interprete comme le bord externe de la feuille.
    # Les autres petits contours sont traites comme trous internes a combler.
    for loop in loops[1:]:
        if loop_area(loop, verts_array) > max_area_m2:
            continue
        center_idx = len(vertices)
        vertices.append(verts_array[loop].mean(axis=0))
        for i in range(len(loop)):
            triangles.append([loop[i], loop[(i + 1) % len(loop)], center_idx])
        filled += 1

    if filled == 0:
        return mesh

    out = o3d.geometry.TriangleMesh()
    out.vertices = o3d.utility.Vector3dVector(np.asarray(vertices, dtype=np.float64))
    out.triangles = o3d.utility.Vector3iVector(np.asarray(triangles, dtype=np.int32))
    out.compute_vertex_normals()
    return out


def poisson_envelope(points: np.ndarray, cfg: MeshingConfig) -> o3d.geometry.TriangleMesh:
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(points.astype(np.float64))
    pcd.estimate_normals(
        search_param=o3d.geometry.KDTreeSearchParamHybrid(
            radius=float(cfg.normal_radius),
            max_nn=int(cfg.normal_max_nn),
        )
    )
    try:
        pcd.orient_normals_consistent_tangent_plane(int(cfg.orient_k))
    except RuntimeError:
        pass

    with suppress_open3d_output():
        mesh, _ = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(
            pcd,
            depth=int(cfg.poisson_depth),
        )

    if len(np.asarray(mesh.triangles)) == 0:
        raise ValueError("Poisson vide")

    dists, _ = cKDTree(points).query(points, k=2)
    median_nn = float(np.median(dists[:, 1]))
    verts = np.asarray(mesh.vertices, dtype=np.float64)
    nn_dist, _ = cKDTree(points).query(verts, k=1)
    mesh.remove_vertices_by_mask(nn_dist > float(cfg.max_dist_factor) * median_nn)

    if len(np.asarray(mesh.triangles)) == 0:
        raise ValueError("Mesh vide apres elagage")

    if cfg.fill_poisson_holes and cfg.max_hole_area_cm2 > 0:
        mesh = fill_interior_holes(mesh, float(cfg.max_hole_area_cm2) * 1e-4)
    mesh.compute_vertex_normals()
    return mesh


def smooth_with_edge_reconstruction(
    mesh_env: o3d.geometry.TriangleMesh,
    cfg: MeshingConfig,
) -> o3d.geometry.TriangleMesh:
    with suppress_open3d_output():
        mesh_sub = mesh_env.subdivide_loop(number_of_iterations=int(cfg.subdiv_iter))

    loops = boundary_loops(mesh_sub)
    boundary_vertices = np.unique(np.concatenate(loops)) if loops else np.array([], dtype=np.int32)
    verts_sub = np.asarray(mesh_sub.vertices, dtype=np.float64).copy()

    with suppress_open3d_output():
        mesh_lap = mesh_sub.filter_smooth_simple(number_of_iterations=int(cfg.laplacian_iter))
        mesh_out = mesh_lap.filter_smooth_taubin(
            number_of_iterations=int(cfg.taubin_iter),
            lambda_filter=float(cfg.taubin_lambda),
            mu=float(cfg.taubin_mu),
        )

    # Le lissage deplace les bords. On remet donc les vertices de bord a leur
    # position avant lissage pour limiter la perte d'aire en bordure.
    verts_out = np.asarray(mesh_out.vertices, dtype=np.float64).copy()
    if len(boundary_vertices):
        verts_out[boundary_vertices] = verts_sub[boundary_vertices]
    mesh_out.vertices = o3d.utility.Vector3dVector(verts_out)
    mesh_out.compute_vertex_normals()

    if cfg.fill_after_smooth and cfg.max_hole_area_after_smooth_cm2 > 0:
        mesh_out = fill_interior_holes(mesh_out, float(cfg.max_hole_area_after_smooth_cm2) * 1e-4)
    return mesh_out


def voxel_downsample_points(points: np.ndarray, voxel_size: float) -> np.ndarray:
    if voxel_size <= 0:
        return points
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(points)
    pcd = pcd.voxel_down_sample(float(voxel_size))
    return np.asarray(pcd.points, dtype=np.float64)


def sanitize_mesh(mesh: o3d.geometry.TriangleMesh) -> o3d.geometry.TriangleMesh:
    verts = np.asarray(mesh.vertices, dtype=np.float64)
    tris = np.asarray(mesh.triangles, dtype=np.int64)
    out = o3d.geometry.TriangleMesh()
    if len(verts) == 0 or len(tris) == 0:
        out.vertices = o3d.utility.Vector3dVector(np.empty((0, 3), dtype=np.float64))
        out.triangles = o3d.utility.Vector3iVector(np.empty((0, 3), dtype=np.int32))
        return out

    finite = np.isfinite(verts).all(axis=1)
    if not np.all(finite):
        old_to_new = -np.ones(len(verts), dtype=np.int64)
        keep_idx = np.where(finite)[0]
        old_to_new[keep_idx] = np.arange(len(keep_idx))
        keep_tri = finite[tris].all(axis=1)
        tris = old_to_new[tris[keep_tri]]
        verts = verts[keep_idx]

    valid = (tris >= 0).all(axis=1) & (tris < len(verts)).all(axis=1)
    tris = tris[valid]
    non_degenerate = (tris[:, 0] != tris[:, 1]) & (tris[:, 1] != tris[:, 2]) & (tris[:, 0] != tris[:, 2])
    tris = tris[non_degenerate]

    out.vertices = o3d.utility.Vector3dVector(np.ascontiguousarray(verts, dtype=np.float64))
    out.triangles = o3d.utility.Vector3iVector(np.ascontiguousarray(tris, dtype=np.int32))
    colors = np.asarray(mesh.vertex_colors, dtype=np.float64)
    if colors.shape == (len(verts), 3):
        out.vertex_colors = o3d.utility.Vector3dVector(colors)
    if len(tris):
        out.compute_vertex_normals()
    return out


def write_mesh(path: Path, mesh: o3d.geometry.TriangleMesh) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mesh = sanitize_mesh(mesh)
    ok = o3d.io.write_triangle_mesh(str(path), mesh, write_ascii=False)
    if not ok:
        ok = o3d.io.write_triangle_mesh(str(path), mesh, write_ascii=True)
    if not ok:
        raise RuntimeError(f"Echec ecriture mesh: {path}")


def merge_meshes(meshes: list[o3d.geometry.TriangleMesh]) -> o3d.geometry.TriangleMesh:
    out = o3d.geometry.TriangleMesh()
    for mesh in meshes:
        out += sanitize_mesh(mesh)
    if len(np.asarray(out.triangles)):
        out.compute_vertex_normals()
    return out


def run_meshing_stage(cfg: PipelineConfig, clustered_las: Path | None = None, output_root: Path | None = None) -> Path:
    configure_open3d_logging()
    t0 = perf_counter()
    m = cfg.meshing
    input_las = clustered_las if clustered_las is not None else cfg.paths.clustered_las
    root = output_root if output_root is not None else cfg.paths.output_root / "meshing"
    run_dir = make_run_dir(root)
    mesh_dir = run_dir / "meshes_per_cluster"
    mesh_dir.mkdir(parents=True, exist_ok=True)

    print(f"run dir               : {run_dir}")
    print("step 1/4: chargement LAS clusterise...")
    las = laspy.read(input_las)
    dims = set(las.point_format.dimension_names)
    if m.cluster_field not in dims:
        raise ValueError(f"Champ '{m.cluster_field}' absent du LAS. Champs disponibles: {sorted(dims)}")

    xyz = las_xyz(las)
    labels = np.asarray(las[m.cluster_field], dtype=np.int64)
    cluster_ids = sorted(int(v) for v in np.unique(labels) if v >= 0 and v != m.noise_label)
    cluster_ids = [v for v in cluster_ids if m.start_cluster_id <= v <= m.end_cluster_id]
    print(f"points entree         : {len(xyz):,}")
    print(f"clusters candidats    : {len(cluster_ids):,}")

    print("step 2/4: reconstruction par cluster...")
    rows: list[dict[str, object]] = []
    meshes: list[o3d.geometry.TriangleMesh] = []
    n_fail = 0

    for cid in cluster_ids:
        t_cluster = perf_counter()
        pts = xyz[labels == cid]
        if len(pts) < m.min_points_cluster:
            continue

        pts_work = voxel_downsample_points(pts, m.voxel_size_per_cluster)
        if len(pts_work) < m.min_points_cluster:
            continue
        if m.max_points_per_cluster > 0 and len(pts_work) > m.max_points_per_cluster:
            rng = np.random.default_rng(cid)
            keep = np.sort(rng.choice(len(pts_work), size=m.max_points_per_cluster, replace=False))
            pts_work = pts_work[keep]

        center = pts_work.mean(axis=0)
        pts_local = pts_work - center[None, :]

        try:
            mesh_poisson_local = poisson_envelope(pts_local, m)
            mesh_smooth_local = smooth_with_edge_reconstruction(mesh_poisson_local, m)
        except Exception as exc:
            n_fail += 1
            rows.append(
                {
                    "cluster_id": cid,
                    "n_points": int(len(pts)),
                    "n_points_work": int(len(pts_work)),
                    "status": f"failed:{exc}",
                    "area_poisson_cm2": np.nan,
                    "area_smooth_edge_cm2": np.nan,
                    "mesh_path": "",
                    "time_s": float(perf_counter() - t_cluster),
                }
            )
            print(f"cluster_{cid:05d}     FAILED ({exc})")
            continue

        for mesh in (mesh_poisson_local, mesh_smooth_local):
            verts = np.asarray(mesh.vertices, dtype=np.float64)
            mesh.vertices = o3d.utility.Vector3dVector(verts + center[None, :])
            mesh.compute_vertex_normals()

        color = cluster_color_rgb01(cid)
        n_vertices = len(np.asarray(mesh_smooth_local.vertices))
        mesh_smooth_local.vertex_colors = o3d.utility.Vector3dVector(np.tile(color[None, :], (n_vertices, 1)))
        meshes.append(mesh_smooth_local)

        mesh_path = mesh_dir / f"cluster_{cid:05d}_smooth_edge_recon.ply"
        if m.export_per_cluster_meshes:
            write_mesh(mesh_path, mesh_smooth_local)
            if m.export_per_cluster_poisson_raw:
                write_mesh(mesh_dir / f"cluster_{cid:05d}_poisson_raw.ply", mesh_poisson_local)

        area_poisson = float(mesh_poisson_local.get_surface_area() * 1e4)
        area_smooth = float(mesh_smooth_local.get_surface_area() * 1e4)
        rows.append(
            {
                "cluster_id": cid,
                "n_points": int(len(pts)),
                "n_points_work": int(len(pts_work)),
                "status": "ok",
                "area_poisson_cm2": area_poisson,
                "area_smooth_edge_cm2": area_smooth,
                "mesh_path": str(mesh_path) if m.export_per_cluster_meshes else "",
                "time_s": float(perf_counter() - t_cluster),
            }
        )
        print(
            f"cluster_{cid:05d}     {len(pts):6d} pts -> OK "
            f"A_smooth={area_smooth:8.1f} cm2 t={perf_counter() - t_cluster:5.1f}s"
        )

    print("step 3/4: fusion mesh globale...")
    global_mesh = merge_meshes(meshes)
    global_path = run_dir / "global_clusters_smooth_edge_recon_colored.ply"
    write_mesh(global_path, global_mesh)

    print("step 4/4: resume...")
    csv_path = run_dir / "per_cluster_surface_summary.csv"
    if rows:
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    ok_rows = [r for r in rows if r.get("status") == "ok"]
    summary = {
        "input_clustered_las": str(input_las),
        "run_dir": str(run_dir),
        "params": m.__dict__,
        "stats": {
            "n_input_points": int(len(xyz)),
            "n_input_clusters": int(len(cluster_ids)),
            "n_clusters_ok": int(len(ok_rows)),
            "n_clusters_failed": int(n_fail),
            "total_area_smooth_edge_cm2": float(np.nansum([r["area_smooth_edge_cm2"] for r in ok_rows])) if ok_rows else 0.0,
            "elapsed_s": float(perf_counter() - t0),
        },
        "outputs": {
            "global_colored_ply": str(global_path),
            "per_cluster_csv": str(csv_path),
            "mesh_dir": str(mesh_dir),
        },
    }
    write_json(run_dir / "summary.json", summary)
    print(f"mesh globale          : {global_path}")
    print(f"summary               : {run_dir / 'summary.json'}")
    return global_path

