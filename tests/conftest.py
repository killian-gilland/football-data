"""Données synthétiques pour les tests (aucun accès réseau)."""
from __future__ import annotations

import itertools

import numpy as np
import pandas as pd
import pytest

from pipeline.config import Competition


def faire_saison(equipes, saison="2024-25", scores=None, graine=0, a_venir=0):
    """Championnat aller-retour complet. `scores` : dict (dom, ext) -> (bd, be) ; sinon tirages aléatoires."""
    rng = np.random.default_rng(graine)
    debut = pd.Timestamp(f"{saison[:4]}-08-10")
    lignes = []
    paires = list(itertools.permutations(equipes, 2))
    for k, (d, e) in enumerate(paires):
        bd, be = (scores or {}).get((d, e), (int(rng.poisson(1.5)), int(rng.poisson(1.1))))
        lignes.append({"match_id": f"{saison[2:4]}{saison[5:]}-{d}-{e}", "competition": "test", "saison": saison,
                       "journee": k // max(len(equipes) // 2, 1) + 1, "date": debut + pd.Timedelta(days=7 * (k // 2)),
                       "heure": "", "dom": d, "ext": e, "statut": "joue", "buts_dom": float(bd), "buts_ext": float(be),
                       "mt_dom": float(min(bd, 1)), "mt_ext": 0.0, "tirs_dom": 12.0, "tirs_ext": 9.0,
                       "cadres_dom": 5.0, "cadres_ext": 3.0, "corners_dom": 5.0, "corners_ext": 4.0,
                       "fautes_dom": 11.0, "fautes_ext": 12.0, "jaunes_dom": 2.0, "jaunes_ext": 2.0,
                       "rouges_dom": 0.0, "rouges_ext": 0.0, "cote_dom": 2.2, "cote_nul": 3.3, "cote_ext": 3.4,
                       "cote_clot_dom": 2.2, "cote_clot_nul": 3.3, "cote_clot_ext": 3.4, "nb_bookmakers": 3,
                       "source": "test"})
    df = pd.DataFrame(lignes)
    if a_venir:
        idx = df.index[-a_venir:]
        df.loc[idx, ["buts_dom", "buts_ext", "mt_dom", "mt_ext"]] = np.nan
        df.loc[idx, "statut"] = "a_venir"
    return df


@pytest.fixture
def comp_test():
    return Competition(
        id="test", nom="Test", pays="France", slug="test", actif=True, saison_courante="2024-25",
        premiere_saison="2023-24", referentiel_equipes="fr", enrichissements=True, sources={},
        formats={"defaut": {"points": {"victoire": 3, "nul": 1, "defaite": 0},
                            "departage": ["diff", "confrontations_points", "confrontations_diff", "buts_pour"],
                            "zones": []},
                 "saisons": {"2024-25": {"equipes": 4}}})
