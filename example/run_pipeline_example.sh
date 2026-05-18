#!/usr/bin/env bash
set -euo pipefail
# En gros -e pour que le script s'arrête à la première erreur, 
# -u pour que les variables non définies soient considérées comme des erreurs,
# et -o pipefail pour que les erreurs dans les pipelines soient correctement propagées.

cd "$(dirname "$0")/.."
# On se place dans le répertoire parent du script

# Si `--step all` plante malgre tout, utiliser :
# bash example/run_pipeline_two_steps.sh

python scripts/run_pipeline.py \
  --config example/example.toml \
  --step all
