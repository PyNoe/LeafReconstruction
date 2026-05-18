"""Orchestration des etapes principales."""

from __future__ import annotations

from .clustering import run_clustering_stage
from .config import PipelineConfig
from .meshing import run_meshing_stage


def run_clustering(cfg: PipelineConfig):
    return run_clustering_stage(cfg)


def run_meshing(cfg: PipelineConfig):
    return run_meshing_stage(cfg)
