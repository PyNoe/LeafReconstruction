"""Couleurs deterministes pour les exports de debug."""

from __future__ import annotations

import colorsys

import numpy as np


NOISE_GRAY_16BIT = 32000


def cluster_color_rgb01(cluster_id: int) -> np.ndarray:
    # Le nombre d'or donne une bonne dispersion des teintes entre clusters voisins.
    h = float((int(cluster_id) * 0.6180339887498949) % 1.0)
    r, g, b = colorsys.hsv_to_rgb(h, 0.85, 1.0)
    return np.array([r, g, b], dtype=np.float64)


def labels_to_rgb16(labels: np.ndarray) -> np.ndarray:
    rgb = np.full((len(labels), 3), int(NOISE_GRAY_16BIT), dtype=np.uint16)
    for cid in np.unique(labels[labels >= 0]).astype(np.int64):
        col = np.clip(np.round(cluster_color_rgb01(int(cid)) * 65535.0), 0, 65535).astype(np.uint16)
        rgb[labels == cid] = col
    return rgb

