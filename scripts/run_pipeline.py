#!/usr/bin/env python3
"""Point d'entree simple pour lancer la pipeline."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from tls_leaf_pipeline.config import load_config  # noqa: E402
from tls_leaf_pipeline.pipeline import run_all, run_clustering, run_meshing  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Pipeline TLS feuilles : clustering et meshing.")
    parser.add_argument("--config", type=Path, default=ROOT / "configs" / "default.toml")
    parser.add_argument("--step", choices=["cluster", "mesh", "all"], default="all")
    args = parser.parse_args()

    cfg = load_config(args.config)

    if args.step == "cluster":
        run_clustering(cfg)
    elif args.step == "mesh":
        run_meshing(cfg)
    else:
        run_all(cfg)


if __name__ == "__main__":
    main()

