# TLS Leaf Surface Pipeline

Ce depot regroupe une version propre et reutilisable de la pipeline developpee pour segmenter des nuages de points TLS de feuilles et reconstruire leurs surfaces.

L'objectif est de garder une structure simple :

- `cluster` : filtrage SOR puis clustering HDBSCAN par tuiles.
- `mesh` : reconstruction de surface par cluster avec Poisson d6, lissage Laplacien + Taubin, puis reconstruction des bords.
- `all` : lance `cluster`, puis `mesh`, dans deux processus Python separes.

Les scripts historiques d'exploration ne sont pas inclus dans cette couche propre. Ils restent utiles pour reproduire les essais, mais ce dossier est pensé comme base de repo GitHub pour la suite.

## Installation

Environnement conseillé :

```bash
conda env create -f environment.yml
conda activate ird_tls
pip install -e .
```

Dépendances principales :

```
numpy, pandas, laspy, lazrs, open3d, hdbscan, scipy
```

## Utilisation

Modifier d'abord le fichier :

```bash
configs/default.toml
```

Puis lancer une étape :

```bash
python scripts/run_pipeline.py --config configs/default.toml --step cluster
python scripts/run_pipeline.py --config configs/default.toml --step mesh
python scripts/run_pipeline.py --config configs/default.toml --step all
```

Le mode `all` orchestre les deux étapes de bout en bout, mais les lance dans
deux processus Python différents. L'étape `mesh` relit alors automatiquement la
sortie produite par l'étape `cluster`.

### Si le meshing s'interrompt

Sur certaines executions, le meshing peut s'arreter brutalement pendant la
reconstruction des clusters, sans exception Python lisible ni fichier final.
Le problème semble venir d'un crash natif intermittent dans les dépendances de
reconstruction de surface, plutot que de la logique Python de la pipeline.

Le mode `all` limite ce risque en lancant `cluster` et `mesh` dans deux processus
séparés, puis en relancant automatiquement le meshing si les sorties finales
attendues ne sont pas produites.

Si l'on veut contourner completement ce mode automatisé, il reste possible de
lancer les deux etapes manuellement :

```bash
python scripts/run_pipeline.py --config configs/default.toml --step cluster
python scripts/run_pipeline.py --config configs/default.toml --step mesh
```

Dans ce cas, `paths.clustered_las` doit pointer vers le LAS clusterisé produit
par l'étape `cluster`.

## Scripts utilitaires mobiles

Des scripts autonomes sont disponibles dans `scripts/tools/` pour lancer une tache simple sans passer par toute la pipeline.

Meshing direct depuis un nuage unique :

```bash
python scripts/tools/mesh_single_cloud.py \
  --input path/to/cloud.laz \
  --output path/to/mesh_smooth.ply
```

Formats acceptés en entrée : `.las`, `.laz`, `.txt`.

Clustering direct depuis un LAS/LAZ :

```bash
python scripts/tools/cluster_single_cloud.py \
  --input path/to/cloud.laz \
  --output path/to/cloud_clustered.laz
```

Options utiles :

```bash
--no-sor
--no-tiling
--tile-size 0.5
--min-cluster-size 300
```

## Scripts experimentaux

Les scripts de `scripts/experimental/` servent a tester des approches parallèles. Ils ne font pas partie de la pipeline principale.

MLS + BPA adaptatif sur un fichier unique :

```bash
python scripts/experimental/mls_bpa_single_cloud.py \
  --input "path/to/cloud.laz" \
  --output-dir "outputs/mls_bpa_test"
```

Ce script exporte :

- `points_raw.ply`
- `points_mls.ply`
- `bpa_mls_adaptive.ply`
- `summary.json`

Les rayons BPA sont calculés automatiquement a partir de la distance mediane aux voisins locaux, puis multipliés par `--radius-factors`.

## Sorties

Pour le clustering :

- `sor_filtered.las` si le SOR est activé.
- `sor_tiled_hdbscan.las`, `tiled_hdbscan.las`, `sor_hdbscan.las` ou `hdbscan.las` selon les options activées.
- la version `_colored.las` si l'export couleur est activé.
- `summary.json`

Pour le meshing :

- `global_clusters_smooth_edge_recon_colored.ply`
- `per_cluster_surface_summary.csv`
- `summary.json`

## Remarques importantes

Le fichier LAS/LAZ d'entrée du meshing doit contenir un champ scalaire `cluster_id`.

Le bruit est defini par `cluster_id = -1` et n'est pas maillé.

Dans `configs/default.toml`, deux options controlent le comportement du clustering :

- `enable_sor = true/false` pour activer ou désactiver le filtrage SOR.
- `enable_tiling = true/false` pour lancer HDBSCAN par tuiles ou sur tout le nuage d'un seul bloc.

La reconstruction de surface reprend la pipeline validée :

1. éstimation des normales locales ;
2. orientation cohérente des normales ;
3. Poisson depth 6 ;
4. élagage des vertices trop loin du nuage initial ;
5. comblement optionnel des petits trous internes ;
6. subdivision Loop ;
7. lissage Laplacien ;
8. lissage Taubin ;
9. remise en place des bords initiaux apres lissage.
