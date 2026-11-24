"""Backtest walk-forward des modèles 1N2.

Pour chaque semaine de chaque saison testée, les modèles sont ajustés uniquement sur les matchs
joués AVANT cette semaine, puis prédisent les matchs de la semaine. Comparaison avec :
- une référence naïve (fréquences domicile/nul/extérieur des 5 saisons précédentes) ;
- les probabilités implicites des bookmakers (cotes moyennes avant-match, et à la clôture).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .config import Competition, saison_precedente
from .modeles import dixon_coles as dc
from .modeles import elo as elo_mod
from .modeles import metriques as mt

MODELES = ("elo", "dixon_coles", "ensemble")


@dataclass
class ContexteSaison:
    equipes: list[str]
    promus: set[str]
    relegues: set[str]


def contexte_saison(matchs: pd.DataFrame, saison: str) -> ContexteSaison:
    eq = set(matchs.loc[matchs["saison"] == saison, "dom"]) | set(matchs.loc[matchs["saison"] == saison, "ext"])
    prec = saison_precedente(saison)
    eq_prec = set(matchs.loc[matchs["saison"] == prec, "dom"]) | set(matchs.loc[matchs["saison"] == prec, "ext"])
    if not eq_prec:
        return ContexteSaison(sorted(eq), set(), set())
    return ContexteSaison(sorted(eq), eq - eq_prec, eq_prec - eq)


def frequences_naives(matchs: pd.DataFrame, avant: pd.Timestamp, saisons: int = 5) -> np.ndarray:
    j = matchs[(matchs["statut"] == "joue") & (matchs["date"] < avant)]
    j = j[j["saison"].isin(sorted(j["saison"].unique())[-saisons:])]
    y = mt.issue_index(j["buts_dom"], j["buts_ext"])
    return np.bincount(y, minlength=3) / len(y)


def logit_elo(hist_elo: pd.DataFrame, avant: pd.Timestamp, params: elo_mod.ParamsElo,
              saisons_echauffement: int = 2) -> elo_mod.LogitOrdonne:
    h = hist_elo[hist_elo["date"] < avant]
    h = h[h["saison"].isin(sorted(h["saison"].unique())[saisons_echauffement:])]
    ecart = h["elo_dom_avant"] + params.avantage_domicile - h["elo_ext_avant"]
    return elo_mod.LogitOrdonne().ajuster(ecart.to_numpy(), h["y"].to_numpy())


def walk_forward(matchs: pd.DataFrame, saisons_test: list[str], params_elo=elo_mod.ParamsElo(),
                 params_dc=dc.ParamsDC()) -> pd.DataFrame:
    hist_elo, _ = elo_mod.calculer(matchs, params_elo)
    joues = matchs[matchs["statut"] == "joue"].copy()
    joues["y"] = mt.issue_index(joues["buts_dom"], joues["buts_ext"])
    hist_elo = hist_elo.merge(joues[["match_id", "y"]], on="match_id")
    blocs = []
    for s in saisons_test:
        js = joues[joues["saison"] == s].sort_values("date")
        if js.empty:
            continue
        debut = js["date"].min()
        logit = logit_elo(hist_elo, debut, params_elo)
        naif = frequences_naives(matchs, debut)
        ctx = contexte_saison(matchs, s)
        he = hist_elo.set_index("match_id")
        semaines = js["date"].dt.to_period("W-MON")  # semaines du mardi au lundi : une journée = un bloc
        for _, g in js.groupby(semaines):
            date_ref = g["date"].min()
            modele = dc.ajuster(matchs, date_ref, ctx.equipes, ctx.promus, ctx.relegues, params_dc)
            p_dc = modele.predire_1n2(g["dom"].to_numpy(), g["ext"].to_numpy())
            ld, le = modele.lambdas(g["dom"].to_numpy(), g["ext"].to_numpy())
            e = he.loc[g["match_id"]]
            ecart = (e["elo_dom_avant"] + params_elo.avantage_domicile - e["elo_ext_avant"]).to_numpy()
            p_elo = logit.predire(ecart)
            b = g[["match_id", "saison", "date", "dom", "ext", "buts_dom", "buts_ext", "y"]].copy()
            for nom, p in (("elo", p_elo), ("dixon_coles", p_dc), ("ensemble", (p_elo + p_dc) / 2),
                           ("naif", np.tile(naif, (len(g), 1))),
                           ("marche", mt.probas_cotes(g["cote_dom"], g["cote_nul"], g["cote_ext"])),
                           ("cloture", mt.probas_cotes(g["cote_clot_dom"], g["cote_clot_nul"], g["cote_clot_ext"]))):
                for k, issue in enumerate(mt.ISSUES):
                    b[f"p_{nom}_{issue}"] = p[:, k]
            b["lambda_dom"], b["lambda_ext"] = ld, le
            b["elo_dom"], b["elo_ext"] = e["elo_dom_avant"].to_numpy(), e["elo_ext_avant"].to_numpy()
            blocs.append(b)
    return pd.concat(blocs, ignore_index=True)


def probas(df: pd.DataFrame, nom: str) -> np.ndarray:
    return df[[f"p_{nom}_{i}" for i in mt.ISSUES]].to_numpy()


def evaluer(pred: pd.DataFrame) -> dict:
    """Métriques globales et par saison + règle de validation de chaque modèle."""
    y = pred["y"].to_numpy()
    res: dict = {"global": {}, "par_saison": [], "validation": {}, "calibration": {}}
    references = ["naif", "marche", "cloture"]
    for nom in (*MODELES, *references):
        p = probas(pred, nom)
        ok = ~np.isnan(p).any(axis=1)
        res["global"][nom] = mt.resume(p[ok], y[ok])
    for s, g in pred.groupby("saison"):
        ligne = {"saison": s}
        for nom in (*MODELES, *references):
            p = probas(g, nom)
            ok = ~np.isnan(p).any(axis=1)
            ligne[nom] = float(mt.rps(p[ok], g["y"].to_numpy()[ok]).mean()) if ok.any() else None
        res["par_saison"].append(ligne)
    rps_naif = mt.rps(probas(pred, "naif"), y)
    marche = probas(pred, "marche")
    ok_m = ~np.isnan(marche).any(axis=1)
    rps_marche = mt.rps(marche[ok_m], y[ok_m])
    for nom in MODELES:
        r = mt.rps(probas(pred, nom), y)
        ecart, lo, hi = mt.ic_ecart_bootstrap(r, rps_naif)
        ecart_m, lo_m, hi_m = mt.ic_ecart_bootstrap(r[ok_m], rps_marche)
        res["validation"][nom] = {
            "ecart_rps_vs_naif": ecart, "ic95_vs_naif": [lo, hi],
            "ecart_rps_vs_marche": ecart_m, "ic95_vs_marche": [lo_m, hi_m],
            # Règle d'affichage : significativement meilleur que la référence naïve.
            "valide": bool(hi < 0),
        }
        res["calibration"][nom] = mt.calibration(probas(pred, nom), y)
    res["calibration"]["marche"] = mt.calibration(marche[ok_m], y[ok_m])
    valides = [m for m in MODELES if res["validation"][m]["valide"]]
    res["modele_principal"] = min(valides, key=lambda m: res["global"][m]["rps"]) if valides else None
    return res
