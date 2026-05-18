# Exemple minimal

Ce dossier contient un nuage de points d'exemple et un appel pret a lancer sur la pipeline complete.

Depuis la racine du depot :

```bash
conda env create -f environment.yml
conda activate ird_tls
pip install -e .
bash example/run_pipeline_example.sh
```

Le script appelle :

```bash
python scripts/run_pipeline.py --config example/example.toml --step all
```

Le mode `all` lance automatiquement les deux étapes dans deux processus Python
séparés : un processus pour `cluster`, puis un second pour `mesh`.

Si l'on veut lancer explicitement les deux étapes sans passer par `all` :

```bash
bash example/run_pipeline_two_steps.sh
```

Les sorties sont écrites dans :

```text
example/outputs/clustering/run_XX/
example/outputs/meshing/run_XX/
```

Voila ce que j'obtiens :

```
├── box_0_5.laz
├── example.toml
├── outputs
│   ├── clustering
│   │   └── run_01
│   │       ├── sor_filtered.las
│   │       ├── sor_tiled_hdbscan_colored.las
│   │       ├── sor_tiled_hdbscan.las
│   │       └── summary.json
│   └── meshing
│       └── run_01
│           ├── global_clusters_smooth_edge_recon_colored.ply
│           ├── meshes_per_cluster
│           │   ├── cluster_00000_smooth_edge_recon.ply
│           │   ├── cluster_00001_smooth_edge_recon.ply
│           │   ├── cluster_00002_smooth_edge_recon.ply
│           │   ├── cluster_00003_smooth_edge_recon.ply
│           │   ├── ...
│           │   ├── cluster_00052_smooth_edge_recon.ply
│           │   ├── cluster_00053_smooth_edge_recon.ply
│           │   └── cluster_00054_smooth_edge_recon.ply
│           ├── per_cluster_surface_summary.csv
│           └── summary.json
├── README.md
├── run_pipeline_example.sh
└── run_pipeline_two_steps.sh
```



Les fichiers les plus utiles pour illustrer la pipeline sont :

- `sor_tiled_hdbscan_colored.las` apres le clustering ;
- `global_clusters_smooth_edge_recon_colored.ply` apres le meshing ;
- les deux fichiers `summary.json` pour les statistiques de chaque étape.
