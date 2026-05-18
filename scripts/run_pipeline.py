#!/usr/bin/env python3
"""Point d'entree simple pour lancer la pipeline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from tls_leaf_pipeline.config import load_config  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Pipeline TLS feuilles : clustering et meshing.")
    parser.add_argument("--config", type=Path, default=ROOT / "configs" / "default.toml")
    parser.add_argument("--step", choices=["cluster", "mesh", "all"], required=True)
    parser.add_argument(
        "--clustered-las",
        type=Path,
        help="LAS clusterise a utiliser pour l'etape mesh. Reserve a l'orchestration interne de --step all.",
    )
    args = parser.parse_args()

    cfg = load_config(args.config)

    if args.step == "cluster":
        from tls_leaf_pipeline.pipeline import run_clustering  # noqa: PLC0415

        run_clustering(cfg)
    elif args.step == "mesh":
        from tls_leaf_pipeline.pipeline import run_meshing  # noqa: PLC0415

        if args.clustered_las is not None:
            cfg.paths.clustered_las = args.clustered_las
        run_meshing_with_cleanup(cfg)
    else:
        run_all_in_separate_processes(args.config)


def latest_clustered_las(output_root: Path) -> Path:
    cluster_root = output_root / "clustering"
    run_dirs = sorted(p for p in cluster_root.glob("run_*") if p.is_dir())
    if not run_dirs:
        raise RuntimeError(f"Aucun run de clustering trouve dans {cluster_root}")

    summary_path = run_dirs[-1] / "summary.json"
    with summary_path.open("r", encoding="utf-8") as f:
        summary = json.load(f)
    return Path(summary["outputs"]["clustered_las"])


def latest_run_dir(root: Path) -> Path | None:
    run_dirs = sorted(p for p in root.glob("run_*") if p.is_dir())
    return run_dirs[-1] if run_dirs else None


def meshing_completed(run_dir: Path | None) -> bool:
    if run_dir is None:
        return False
    return (run_dir / "summary.json").is_file() and (
        run_dir / "global_clusters_smooth_edge_recon_colored.ply"
    ).is_file()


def run_meshing_with_cleanup(cfg) -> None:
    from tls_leaf_pipeline.pipeline import run_meshing  # noqa: PLC0415

    meshing_root = cfg.paths.output_root / "meshing"
    try:
        run_meshing(cfg)
    finally:
        latest_mesh_run = latest_run_dir(meshing_root)
        if latest_mesh_run is not None and not meshing_completed(latest_mesh_run):
            shutil.rmtree(latest_mesh_run)


def run_all_in_separate_processes(config_path: Path) -> None:
    script = Path(__file__).resolve()
    subprocess.run(
        [sys.executable, str(script), "--config", str(config_path), "--step", "cluster"],
        check=True,
    )

    cfg = load_config(config_path)
    clustered_las = latest_clustered_las(cfg.paths.output_root)
    meshing_root = cfg.paths.output_root / "meshing"
    mesh_cmd = [
        sys.executable,
        str(script),
        "--config",
        str(config_path),
        "--step",
        "mesh",
        "--clustered-las",
        str(clustered_las),
    ]
    mesh_result = subprocess.run(mesh_cmd)
    latest_mesh_run = latest_run_dir(meshing_root)
    if mesh_result.returncode == 0 and meshing_completed(latest_mesh_run):
        return

    # Sur macOS, Open3D peut mourir ponctuellement par signal natif pendant le
    # meshing. Une relance dans un nouveau processus repart d'un etat propre.
    if mesh_result.returncode < 0 or not meshing_completed(latest_mesh_run):
        print("meshing incomplet ; nouvelle tentative...")
        if latest_mesh_run is not None and latest_mesh_run.exists():
            shutil.rmtree(latest_mesh_run)
        retry_result = subprocess.run(mesh_cmd)
        retry_mesh_run = latest_run_dir(meshing_root)
        if retry_result.returncode == 0 and meshing_completed(retry_mesh_run):
            return
        retry_result.check_returncode()
        raise RuntimeError("Le meshing s'est termine sans produire les sorties finales attendues.")

    mesh_result.check_returncode()


if __name__ == "__main__":
    main()
