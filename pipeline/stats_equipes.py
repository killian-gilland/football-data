"""Statistiques d'équipes : attaque, défense, tirs, discipline, mi-temps, forme, séries."""
from __future__ import annotations

import numpy as np
import pandas as pd


def _ratio(a: float, b: float) -> float | None:
    return float(a) / float(b) if b and not np.isnan(b) and not np.isnan(a) else None


def _somme(s: pd.Series) -> float | None:
    """Somme sur les seuls matchs renseignés ; None si la donnée n'existe pas pour cette équipe."""
    return float(s.sum()) if s.notna().any() else None


def _par_match(s: pd.Series) -> float | None:
    s = s.dropna()
    return float(s.mean()) if len(s) else None


def _bloc_resultats(v: pd.DataFrame, bareme: dict) -> dict:
    g, n, p = (v["resultat"] == "V").sum(), (v["resultat"] == "N").sum(), (v["resultat"] == "D").sum()
    return {"j": int(len(v)), "g": int(g), "n": int(n), "p": int(p), "bp": int(v["bp"].sum()),
            "bc": int(v["bc"].sum()), "pts": int(g * bareme["victoire"] + n * bareme["nul"])}


def stats_saison(v: pd.DataFrame, bareme: dict) -> dict:
    """Statistiques détaillées d'une équipe sur une saison (v = ses lignes de vue_equipes)."""
    pts_res = {"V": bareme["victoire"], "N": bareme["nul"], "D": 0}
    s: dict = {
        "general": _bloc_resultats(v, bareme),
        "domicile": _bloc_resultats(v[v["lieu"] == "domicile"], bareme),
        "exterieur": _bloc_resultats(v[v["lieu"] == "exterieur"], bareme),
        "clean_sheets": int((v["bc"] == 0).sum()),
        "sans_marquer": int((v["bp"] == 0).sum()),
    }
    mt = v.dropna(subset=["mt_bp", "mt_bc"])
    if len(mt):
        mene = mt[mt["mt_bp"] < mt["mt_bc"]]
        menant = mt[mt["mt_bp"] > mt["mt_bc"]]
        pts_mene = mene["resultat"].map(pts_res).sum()
        pts_menant = menant["resultat"].map(pts_res).sum()
        s["mi_temps"] = {
            "bp_1": int(mt["mt_bp"].sum()), "bc_1": int(mt["mt_bc"].sum()),
            "bp_2": int((mt["bp"] - mt["mt_bp"]).sum()), "bc_2": int((mt["bc"] - mt["mt_bc"]).sum()),
            "mene_a_la_pause": int(len(mene)), "points_gagnes_apres_avoir_ete_mene": int(pts_mene),
            "menant_a_la_pause": int(len(menant)),
            "points_perdus_en_menant": int(len(menant) * bareme["victoire"] - pts_menant),
        }
    if v["tirs"].notna().any():
        tirs, cadres = _somme(v["tirs"]), _somme(v["cadres"])
        tirs_c, cadres_c = _somme(v["tirs_contre"]), _somme(v["cadres_contre"])
        avec_cadres = v.dropna(subset=["cadres"])
        avec_cadres_c = v.dropna(subset=["cadres_contre"])
        s["tirs"] = {
            "tirs_par_match": _par_match(v["tirs"]), "cadres_par_match": _par_match(v["cadres"]),
            "tirs_concedes_par_match": _par_match(v["tirs_contre"]),
            "cadres_concedes_par_match": _par_match(v["cadres_contre"]),
            "precision": _ratio(cadres, tirs),                       # tirs cadrés / tirs
            "conversion": _ratio(avec_cadres["bp"].sum(), cadres),    # buts / tirs cadrés
            "conversion_adverse": _ratio(avec_cadres_c["bc"].sum(), cadres_c),
            "part_des_tirs": _ratio(tirs, (tirs or 0) + (tirs_c or 0)),
        }
    if v["corners"].notna().any():
        s["corners"] = {"pour_par_match": _par_match(v["corners"]), "contre_par_match": _par_match(v["corners_contre"])}
    if v["jaunes"].notna().any() or v["fautes"].notna().any():
        s["discipline"] = {"fautes_par_match": _par_match(v["fautes"]),
                           "fautes_subies_par_match": _par_match(v["fautes_subies"]),
                           "jaunes": _somme(v["jaunes"]), "rouges": _somme(v["rouges"]),
                           "jaunes_par_match": _par_match(v["jaunes"])}
    return s


def series(resultats: list[str]) -> dict:
    """Séries en cours (à partir du dernier match) et records sur la liste chronologique donnée."""
    def en_cours(pred) -> int:
        n = 0
        for r in reversed(resultats):
            if not pred(r):
                break
            n += 1
        return n

    def record(pred) -> int:
        best = cur = 0
        for r in resultats:
            cur = cur + 1 if pred(r) else 0
            best = max(best, cur)
        return best

    preds = {"victoires": lambda r: r == "V", "invincibilite": lambda r: r != "D",
             "sans_victoire": lambda r: r != "V", "defaites": lambda r: r == "D"}
    return {"en_cours": {k: en_cours(p) for k, p in preds.items()},
            "record": {k: record(p) for k, p in preds.items()}}


def forme(v: pd.DataFrame, bareme: dict, n: int = 5) -> dict:
    """Derniers résultats d'une équipe (v trié chronologiquement)."""
    pts_res = {"V": bareme["victoire"], "N": bareme["nul"], "D": 0}
    der = v.tail(n)
    return {
        "derniers": [{"match_id": m, "resultat": r, "adversaire": a, "lieu": l, "score": f"{int(bp)}-{int(bc)}"}
                     for m, r, a, l, bp, bc in zip(der["match_id"], der["resultat"], der["adversaire"],
                                                   der["lieu"], der["bp"], der["bc"])],
        "points_5_derniers": int(der["resultat"].map(pts_res).sum()),
        "points_10_derniers": int(v.tail(10)["resultat"].map(pts_res).sum()),
    }
