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

Le mode `all` lance automatiquement les deux etapes dans deux processus Python
separes : un processus pour `cluster`, puis un second pour `mesh`.

Si l'on veut lancer explicitement les deux etapes sans passer par `all` :

```bash
bash example/run_pipeline_two_steps.sh
```

Les sorties sont ecrites dans :

```text
example/outputs/clustering/run_XX/
example/outputs/meshing/run_XX/
```

Les fichiers les plus utiles pour illustrer la pipeline sont :

- `sor_tiled_hdbscan_colored.las` apres le clustering ;
- `global_clusters_smooth_edge_recon_colored.ply` apres le meshing ;
- les deux fichiers `summary.json` pour les statistiques de chaque etape.
