"""Lecture des cotes : surprises, équipes sous- ou surestimées par le marché."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .modeles import metriques as mt


def _avec_probas(matchs: pd.DataFrame) -> pd.DataFrame:
    j = matchs[(matchs["statut"] == "joue")].dropna(subset=["cote_dom", "cote_nul", "cote_ext"]).copy()
    p = mt.probas_cotes(j["cote_dom"], j["cote_nul"], j["cote_ext"])
    j["pm_dom"], j["pm_nul"], j["pm_ext"] = p[:, 0], p[:, 1], p[:, 2]
    y = mt.issue_index(j["buts_dom"], j["buts_ext"])
    j["p_resultat"] = p[np.arange(len(j)), y]
    j["issue"] = np.array(["dom", "nul", "ext"])[y]
    return j


def surprises(matchs: pd.DataFrame, n: int = 15) -> list[dict]:
    j = _avec_probas(matchs).sort_values("p_resultat").head(n)
    return [{"match_id": r.match_id, "saison": r.saison, "date": r.date.strftime("%Y-%m-%d"), "dom": r.dom,
             "ext": r.ext, "score": f"{int(r.buts_dom)}-{int(r.buts_ext)}", "issue": r.issue,
             "proba_marche": float(r.p_resultat)} for r in j.itertuples()]


def equipes_vs_marche(matchs_saison: pd.DataFrame, bareme: dict) -> list[dict]:
    """Points réels vs points attendus d'après les cotes avant-match."""
    j = _avec_probas(matchs_saison)
    v, nul = bareme["victoire"], bareme["nul"]
    lignes = []
    for e in sorted(set(j["dom"]) | set(j["ext"])):
        d, x = j[j["dom"] == e], j[j["ext"] == e]
        attendus = (v * d["pm_dom"] + nul * d["pm_nul"]).sum() + (v * x["pm_ext"] + nul * x["pm_nul"]).sum()
        reels = (v * (d["buts_dom"] > d["buts_ext"]) + nul * (d["buts_dom"] == d["buts_ext"])).sum() + \
                (v * (x["buts_ext"] > x["buts_dom"]) + nul * (x["buts_dom"] == x["buts_ext"])).sum()
        favori = pd.concat([d["pm_dom"] > d["pm_ext"], x["pm_ext"] > x["pm_dom"]])
        lignes.append({"equipe": e, "matchs": int(len(d) + len(x)), "points": int(reels),
                       "points_attendus_marche": float(attendus), "ecart": float(reels - attendus),
                       "favori": int(favori.sum())})
    return sorted(lignes, key=lambda r: -r["ecart"])


def bilan_favoris(matchs: pd.DataFrame) -> list[dict]:
    """Par saison : part des matchs gagnés par le favori du marché."""
    j = _avec_probas(matchs)
    fav = np.where(j["pm_dom"] >= j["pm_ext"], "dom", "ext")
    j["favori_gagne"] = j["issue"].to_numpy() == fav
    return [{"saison": s, "matchs": int(len(g)), "favori_gagne": float(g["favori_gagne"].mean()),
             "nuls": float((g["issue"] == "nul").mean())} for s, g in j.groupby("saison")]
