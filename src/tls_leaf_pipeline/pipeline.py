"""Orchestration des etapes principales."""

from __future__ import annotations

from .clustering import run_clustering_stage
from .config import PipelineConfig
from .meshing import run_meshing_stage


def run_clustering(cfg: PipelineConfig):
    return run_clustering_stage(cfg)


def run_meshing(cfg: PipelineConfig):
    return run_meshing_stage(cfg)


def run_all(cfg: PipelineConfig):
    clustered_las = run_clustering_stage(cfg)
    return run_meshing_stage(cfg, clustered_las=clustered_las)

