"""Génère worker/src/alias.json (nom normalisé -> identifiant de club) depuis config/equipes/fr.yaml.
À relancer après toute modification du référentiel (le workflow de déploiement le fait)."""
import json
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from pipeline.config import charger_referentiel  # noqa: E402
from pipeline.referentiel import Referentiel  # noqa: E402

ref = Referentiel(charger_referentiel("fr"))
cible = RACINE / "worker" / "src" / "alias.json"
cible.write_text(json.dumps(dict(sorted(ref._index.items())), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
print(f"{len(ref._index)} alias écrits dans {cible.relative_to(RACINE)}")
