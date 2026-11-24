"""Point d'entrée : python -m pipeline [--competition fr-ligue1] [--hors-ligne]

Enchaînement : ingestion -> contrôles qualité -> (si OK) promotion de la version valide
-> calculs -> export JSON -> journal des prédictions.
En cas d'échec d'un contrôle bloquant : code de sortie 2, rien n'est modifié (ni données, ni site).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone

from . import export, predictions, stockage
from .config import DOSSIER_DONNEES, charger_competitions
from .ingestion import ErreurIngestion, ingerer
from .qualite import controle_croise, controle_croise_org, controler, matrice_disponibilite
from .telechargement import ErreurSource


def executer(cid: str, hors_ligne: bool = False) -> int:
    comp = charger_competitions()[cid]
    t0 = time.time()
    print(f"== {comp.nom} {comp.saison_courante} ==")
    try:
        res = ingerer(comp, hors_ligne=hors_ligne)
    except (ErreurIngestion, ErreurSource) as e:
        print(f"ÉCHEC ingestion : {e}\nLa dernière version valide est conservée.")
        return 2
    for a in res.alertes:
        print(f"[alerte] {a}")
    precedent = stockage.charger_matchs(cid)
    rapport = controler(res.matchs, comp, precedent)
    controle_croise(res.matchs, res.calendrier_openfootball, rapport)
    controle_croise_org(res.matchs, res.resultats_org, rapport)
    print(rapport.resume() if not rapport.valide else
          "\n".join(l for l in rapport.resume().splitlines() if not l.startswith("[OK")) or "Contrôles qualité : tout est OK")
    if not rapport.valide:
        rejet = DOSSIER_DONNEES / "rejets" / cid
        rejet.mkdir(parents=True, exist_ok=True)
        res.matchs.to_csv(rejet / f"rejet_{datetime.now():%Y%m%d_%H%M%S}.csv", index=False)
        print("ÉCHEC des contrôles bloquants : rien n'est publié, la dernière version valide reste en ligne.")
        return 2
    rapport_dict = {**rapport.en_dict(), "disponibilite": matrice_disponibilite(res.matchs)}
    manifeste = stockage.promouvoir(cid, res.matchs, res.bruts, rapport_dict)
    print(f"Version validée : {manifeste['matchs_joues']} matchs joués, empreinte {manifeste['empreinte']}")

    maintenant = datetime.now(timezone.utc)
    journal = predictions.lire(cid)
    sortie = export.construire(comp, res.matchs, rapport_dict, res.alertes, maintenant, journal)
    dossier = export.ecrire(cid, sortie.fichiers)
    ajoutees = predictions.enregistrer(cid, sortie.previsions, maintenant)
    print(f"Export : {len(sortie.fichiers)} fichiers dans {dossier}")
    print(f"Journal des prédictions : {ajoutees} nouvelle(s) entrée(s)")
    print(f"Terminé en {time.time() - t0:.0f} s")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Pipeline de données football")
    ap.add_argument("--competition", action="append", help="identifiant (défaut : toutes les compétitions actives)")
    ap.add_argument("--hors-ligne", action="store_true", help="n'utilise que les fichiers bruts déjà présents")
    args = ap.parse_args(argv)
    comps = charger_competitions()
    cids = args.competition or [c for c, v in comps.items() if v.actif]
    codes = [executer(c, args.hors_ligne) for c in cids]
    return max(codes) if codes else 0


if __name__ == "__main__":
    sys.exit(main())
