"""Indice d'occasions (IO) : buts « mérités » d'après les tirs cadrés et non cadrés.

Ce n'est PAS un xG : on ne connaît ni la position ni le type des tirs. C'est une régression de Poisson
(lien identité, coefficients positifs) des buts sur les tirs cadrés et non cadrés, ajustée uniquement
sur des saisons passées.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import minimize


@dataclass
class ModeleIO:
    coef_cadre: float
    coef_non_cadre: float
    saisons_apprentissage: list[str]

    def io(self, tirs, cadres) -> np.ndarray:
        tirs, cadres = np.asarray(tirs, float), np.asarray(cadres, float)
        return self.coef_cadre * cadres + self.coef_non_cadre * np.clip(tirs - cadres, 0, None)


def ajuster(vue: pd.DataFrame, saisons: list[str]) -> ModeleIO:
    d = vue[vue["saison"].isin(saisons)].dropna(subset=["tirs", "cadres"])
    x1 = d["cadres"].to_numpy(float)
    x2 = np.clip(d["tirs"].to_numpy(float) - x1, 0, None)
    y = d["bp"].to_numpy(float)

    def nll(c):
        lam = c[0] * x1 + c[1] * x2 + 1e-6
        return (lam - y * np.log(lam)).sum()
    sol = minimize(nll, x0=[0.3, 0.02], bounds=[(0, 2), (0, 1)], method="L-BFGS-B")
    return ModeleIO(float(sol.x[0]), float(sol.x[1]), sorted(saisons))


def pouvoir_predictif(vue: pd.DataFrame, modele: ModeleIO, saisons: list[str]) -> dict:
    """Pour chaque équipe-saison : la 1re moitié de saison prédit-elle la 2nde ?
    Compare le R² (différence par match) obtenu avec les buts, les tirs cadrés et l'IO."""
    lignes = []
    for (s, e), g in vue[vue["saison"].isin(saisons)].dropna(subset=["tirs", "cadres"]).groupby(["saison", "equipe"]):
        g = g.sort_values("date")
        if len(g) < 20:
            continue
        m = len(g) // 2
        a, b = g.iloc[:m], g.iloc[m:]
        io_pour = modele.io(a["tirs"], a["cadres"]).mean()
        io_contre = modele.io(a["tirs_contre"], a["cadres_contre"]).mean()
        lignes.append({
            "buts": (a["bp"] - a["bc"]).mean(), "cadres": (a["cadres"] - a["cadres_contre"]).mean(),
            "io": io_pour - io_contre,
            "cible_buts": (b["bp"] - b["bc"]).mean(),
            "cible_points": b["resultat"].map({"V": 3, "N": 1, "D": 0}).mean(),
        })
    df = pd.DataFrame(lignes)
    res = {"equipes_saisons": int(len(df))}
    for cible in ("cible_buts", "cible_points"):
        res[cible] = {k: float(np.corrcoef(df[k], df[cible])[0, 1] ** 2) for k in ("buts", "cadres", "io")}
        # Les occasions apportent-elles une information en plus des buts ? (régression à deux variables)
        X = np.column_stack([np.ones(len(df)), df["buts"], df["io"]])
        coef, *_ = np.linalg.lstsq(X, df[cible], rcond=None)
        resid = df[cible] - X @ coef
        res[cible]["buts_plus_io"] = float(1 - resid.var() / df[cible].var())
    return res
