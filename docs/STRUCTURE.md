# Structure du repo

## Dossiers principaux

`configs/`

Contient les fichiers de configuration. Le fichier `default.toml` centralise les chemins, les parametres de clustering et les parametres de reconstruction de surface.

`scripts/`

Contient les points d'entree executables. Pour l'instant, `run_pipeline.py` permet de lancer uniquement le clustering, uniquement le meshing, ou les deux etapes successivement via deux processus separes.

`scripts/tools/`

Contient des outils plus mobiles pour traiter un fichier ponctuellement : clustering direct d'un LAS/LAZ, ou reconstruction Poisson lissee d'un LAS/LAZ/TXT.

`scripts/experimental/`

Contient des approches non centrales, utiles pour tester des variantes sans alourdir la pipeline principale. Exemple actuel : MLS + BPA adaptatif sur un fichier unique.

`src/tls_leaf_pipeline/`

Contient le code Python reutilisable.

`outputs/`

Contient les sorties de calcul. Ce dossier est ignore par Git pour eviter de versionner les gros fichiers LAS/LAZ/PLY.

## Modules Python

`config.py`

Lit le fichier TOML et transforme les parametres en objets Python explicites.

`clustering.py`

Applique le filtrage SOR si demande, decoupe le nuage en tuiles si demande, lance HDBSCAN, puis exporte un LAS clusterise avec un champ `cluster_id`.

`meshing.py`

Reconstruit une surface par cluster. La methode reprend la pipeline validee : Poisson d6, suppression des vertices trop loin du nuage, lissage Laplacien + Taubin, puis remise en place des bords.

`pipeline.py`

Orchestre les etapes principales.

## Philosophie

Les scripts d'exploration doivent rester separes du code final. Si une nouvelle idee devient stable, elle peut etre ajoutee dans `src/tls_leaf_pipeline/` sous forme de fonction propre, puis exposee par `scripts/run_pipeline.py` ou un nouveau script court.
