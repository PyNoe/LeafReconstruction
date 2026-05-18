#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

python scripts/run_pipeline.py \
  --config example/example.toml \
  --step cluster

latest_cluster_run="$(find example/outputs/clustering -maxdepth 1 -type d -name 'run_*' | sort | tail -n 1)"
latest_clustered_las="$latest_cluster_run/sor_tiled_hdbscan.las"

run_mesh() {
  python scripts/run_pipeline.py \
    --config example/example.toml \
    --step mesh \
    --clustered-las "$latest_clustered_las"
}

run_mesh || true

latest_mesh_run="$(find example/outputs/meshing -maxdepth 1 -type d -name 'run_*' | sort | tail -n 1)"
if [[ ! -f "$latest_mesh_run/global_clusters_smooth_edge_recon_colored.ply" || ! -f "$latest_mesh_run/summary.json" ]]; then
  echo "meshing incomplet ; nouvelle tentative..."
  run_mesh
fi
