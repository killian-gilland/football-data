"""Classement Elo maison + conversion en probabilités 1N2 (logit ordonné).

- Avantage du terrain en points Elo, multiplicateur selon l'écart de buts.
- Entre deux saisons : régression partielle vers la moyenne.
- Promus : ils reçoivent la note moyenne des équipes reléguées la saison précédente.
Les notes avant chaque match n'utilisent que les matchs antérieurs : aucune fuite du futur.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import expit


@dataclass
class ParamsElo:
    k: float = 20.0
    avantage_domicile: float = 65.0
    regression: float = 0.20
    note_initiale: float = 1500.0


def _multiplicateur(ecart: int) -> float:
    ecart = abs(ecart)
    return 1.0 if ecart <= 1 else (1.5 if ecart == 2 else (11 + ecart) / 8)


def calculer(matchs: pd.DataFrame, params: ParamsElo = ParamsElo()) -> tuple[pd.DataFrame, dict[str, float]]:
    """Parcourt les matchs joués dans l'ordre chronologique.
    Renvoie (une ligne par match avec notes avant/après, notes courantes par équipe)."""
    j = matchs[matchs["statut"] == "joue"].sort_values(["date", "match_id"])
    notes: dict[str, float] = {}
    saison_prec, equipes_prec = None, set()
    lignes = []
    for saison, g in j.groupby("saison", sort=True):
        equipes = set(g["dom"]) | set(g["ext"])
        if saison_prec is not None:
            moyenne = np.mean([notes[e] for e in equipes_prec])
            for e in equipes_prec:
                notes[e] = moyenne + (1 - params.regression) * (notes[e] - moyenne)
            relegues = equipes_prec - equipes
            note_promu = np.mean([notes[e] for e in relegues]) if relegues else params.note_initiale - 50
            for e in equipes - equipes_prec:
                notes[e] = note_promu
        else:
            for e in equipes:
                notes[e] = params.note_initiale
        for r in g.itertuples():
            nd, ne = notes[r.dom], notes[r.ext]
            attendu = 1 / (1 + 10 ** (-(nd + params.avantage_domicile - ne) / 400))
            score = 1.0 if r.buts_dom > r.buts_ext else (0.5 if r.buts_dom == r.buts_ext else 0.0)
            delta = params.k * _multiplicateur(int(r.buts_dom - r.buts_ext)) * (score - attendu)
            notes[r.dom], notes[r.ext] = nd + delta, ne - delta
            lignes.append((r.match_id, saison, r.date, r.dom, r.ext, nd, ne, notes[r.dom], notes[r.ext]))
        saison_prec, equipes_prec = saison, equipes
    hist = pd.DataFrame(lignes, columns=["match_id", "saison", "date", "dom", "ext",
                                         "elo_dom_avant", "elo_ext_avant", "elo_dom_apres", "elo_ext_apres"])
    return hist, notes


def notes_debut_saison(notes_fin: dict[str, float], equipes_prec: set[str], equipes: set[str],
                       params: ParamsElo = ParamsElo()) -> dict[str, float]:
    """Applique le passage de saison (régression + promus) quand une nouvelle saison n'a encore aucun match."""
    moyenne = np.mean([notes_fin[e] for e in equipes_prec])
    res = {e: moyenne + (1 - params.regression) * (notes_fin[e] - moyenne) for e in equipes_prec}
    relegues = equipes_prec - equipes
    note_promu = np.mean([res[e] for e in relegues]) if relegues else params.note_initiale - 50
    for e in equipes - equipes_prec:
        res[e] = note_promu
    return {e: res[e] for e in equipes}


class LogitOrdonne:
    """P(issue) à partir de l'écart Elo (domicile + avantage - extérieur).
    y : 0 = victoire domicile, 1 = nul, 2 = victoire extérieur."""

    def __init__(self):
        self.beta, self.seuils = 0.005, np.array([-0.3, 0.3])

    def ajuster(self, ecart: np.ndarray, y: np.ndarray) -> "LogitOrdonne":
        x = np.asarray(ecart, float)
        # Latent = beta * x ; issue « extérieur » si latent < c1, « nul » si c1 <= latent < c2, sinon « domicile »
        def nll(theta):
            b, c1, dc = theta
            c2 = c1 + np.exp(dc)
            p_ext = expit(c1 - b * x)
            p_ext_ou_nul = expit(c2 - b * x)
            p = np.select([y == 2, y == 1], [p_ext, p_ext_ou_nul - p_ext], 1 - p_ext_ou_nul)
            return -np.log(np.clip(p, 1e-12, 1)).sum()
        sol = minimize(nll, x0=[0.005, -1.0, np.log(0.6)], method="Nelder-Mead",
                       options={"xatol": 1e-7, "fatol": 1e-6, "maxiter": 4000})
        b, c1, dc = sol.x
        self.beta, self.seuils = b, np.array([c1, c1 + np.exp(dc)])
        return self

    def predire(self, ecart: np.ndarray) -> np.ndarray:
        x = np.asarray(ecart, float)
        p_ext = expit(self.seuils[0] - self.beta * x)
        p_ext_ou_nul = expit(self.seuils[1] - self.beta * x)
        return np.column_stack([1 - p_ext_ou_nul, p_ext_ou_nul - p_ext, p_ext])
