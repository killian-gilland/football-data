"""Modèle de buts Dixon-Coles (1997) avec pondération temporelle.

log λ_dom = μ + γ + attaque[dom] + defense[ext]
log λ_ext = μ +     attaque[ext] + defense[dom]
- Pondération exponentielle des matchs passés : poids = exp(-ξ · ancienneté en jours).
- Pénalité ridge sur attaque/défense ; les promus sont tirés vers le niveau moyen des relégués
  (sans cela, un promu sans historique serait supposé « moyen »).
- ρ corrige les petits scores (0-0, 1-0, 0-1, 1-1).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy.optimize import minimize, minimize_scalar
from scipy.stats import poisson

MAX_BUTS = 10


@dataclass
class ParamsDC:
    xi: float = 0.0019            # demi-vie ≈ 1 an
    fenetre_jours: int = 3 * 365
    ridge: float = 2.0            # force de la pénalité (en « matchs pondérés »)


@dataclass
class ModeleDC:
    equipes: list[str]
    attaque: np.ndarray
    defense: np.ndarray
    mu: float
    gamma: float
    rho: float = 0.0
    index: dict[str, int] = field(default_factory=dict)

    def __post_init__(self):
        self.index = {e: i for i, e in enumerate(self.equipes)}

    def lambdas(self, dom, ext) -> tuple[np.ndarray, np.ndarray]:
        i = np.array([self.index[e] for e in np.atleast_1d(dom)])
        j = np.array([self.index[e] for e in np.atleast_1d(ext)])
        ld = np.exp(self.mu + self.gamma + self.attaque[i] + self.defense[j])
        le = np.exp(self.mu + self.attaque[j] + self.defense[i])
        return ld, le

    def matrice_scores(self, dom: str, ext: str) -> np.ndarray:
        ld, le = self.lambdas([dom], [ext])
        return matrice_scores(float(ld[0]), float(le[0]), self.rho)

    def predire_1n2(self, dom, ext) -> np.ndarray:
        ld, le = self.lambdas(dom, ext)
        return np.array([probas_1n2(matrice_scores(a, b, self.rho)) for a, b in zip(ld, le)])


def tau(x, y, ld, le, rho):
    """Facteur de correction Dixon-Coles (vectorisé)."""
    t = np.ones_like(ld, dtype=float)
    t = np.where((x == 0) & (y == 0), 1 - ld * le * rho, t)
    t = np.where((x == 0) & (y == 1), 1 + ld * rho, t)
    t = np.where((x == 1) & (y == 0), 1 + le * rho, t)
    t = np.where((x == 1) & (y == 1), 1 - rho, t)
    return t


def matrice_scores(ld: float, le: float, rho: float) -> np.ndarray:
    k = np.arange(MAX_BUTS + 1)
    m = np.outer(poisson.pmf(k, ld), poisson.pmf(k, le))
    m[0, 0] *= 1 - ld * le * rho
    m[0, 1] *= 1 + ld * rho
    m[1, 0] *= 1 + le * rho
    m[1, 1] *= 1 - rho
    m = np.clip(m, 0, None)
    return m / m.sum()


def probas_1n2(m: np.ndarray) -> np.ndarray:
    return np.array([np.tril(m, -1).sum(), np.trace(m), np.triu(m, 1).sum()])


def scores_probables(m: np.ndarray, n: int = 5) -> list[dict]:
    idx = np.dstack(np.unravel_index(np.argsort(-m.ravel()), m.shape))[0][:n]
    return [{"score": f"{i}-{j}", "proba": float(m[i, j])} for i, j in idx]


def _nll_poisson(theta, n, hi, ai, yh, ya, w, ridge, cibles_a, cibles_d, poids_ridge):
    a, d, mu, g = theta[:n], theta[n:2 * n], theta[2 * n], theta[2 * n + 1]
    eta_h = mu + g + a[hi] + d[ai]
    eta_a = mu + a[ai] + d[hi]
    lh, la = np.exp(eta_h), np.exp(eta_a)
    nll = (w * (lh - yh * eta_h)).sum() + (w * (la - ya * eta_a)).sum()
    ra, rd = a - cibles_a, d - cibles_d
    nll += 0.5 * ridge * (poids_ridge * (ra ** 2 + rd ** 2)).sum()
    rh, rA = w * (lh - yh), w * (la - ya)
    ga = np.bincount(hi, rh, n) + np.bincount(ai, rA, n) + ridge * poids_ridge * ra
    gd = np.bincount(ai, rh, n) + np.bincount(hi, rA, n) + ridge * poids_ridge * rd
    grad = np.concatenate([ga, gd, [rh.sum() + rA.sum(), rh.sum()]])
    return nll, grad


def ajuster(historique: pd.DataFrame, date_ref: pd.Timestamp, equipes_saison: list[str],
            promus: set[str] | None = None, relegues: set[str] | None = None,
            params: ParamsDC = ParamsDC()) -> ModeleDC:
    """Ajuste le modèle sur les matchs joués STRICTEMENT avant `date_ref`."""
    h = historique[(historique["statut"] == "joue") & (historique["date"] < date_ref)
                   & (historique["date"] >= date_ref - pd.Timedelta(days=params.fenetre_jours))]
    equipes = sorted(set(h["dom"]) | set(h["ext"]) | set(equipes_saison))
    idx = {e: i for i, e in enumerate(equipes)}
    n = len(equipes)
    hi = h["dom"].map(idx).to_numpy()
    ai = h["ext"].map(idx).to_numpy()
    yh, ya = h["buts_dom"].to_numpy(float), h["buts_ext"].to_numpy(float)
    age = (date_ref - h["date"]).dt.days.to_numpy(float)
    w = np.exp(-params.xi * age)

    cibles_a, cibles_d = np.zeros(n), np.zeros(n)
    poids_ridge = np.ones(n)
    theta0 = np.concatenate([np.zeros(2 * n), [np.log(max(h[["buts_dom", "buts_ext"]].mean().mean(), 0.5)), 0.25]])

    def resoudre(theta_init):
        sol = minimize(_nll_poisson, theta_init, jac=True, method="L-BFGS-B",
                       args=(n, hi, ai, yh, ya, w, params.ridge, cibles_a, cibles_d, poids_ridge),
                       options={"maxiter": 500})
        return sol.x

    theta = resoudre(theta0)
    promus = (promus or set()) & set(equipes)
    relegues = (relegues or set()) & set(equipes)
    if promus and relegues:
        # 2e passe : les promus sont tirés vers le niveau moyen des relégués, avec une pénalité plus forte
        ri = [idx[e] for e in relegues]
        for e in promus:
            cibles_a[idx[e]] = theta[:n][ri].mean()
            cibles_d[idx[e]] = theta[n:2 * n][ri].mean()
            poids_ridge[idx[e]] = 3.0
        theta = resoudre(theta)

    a, d, mu, g = theta[:n], theta[n:2 * n], theta[2 * n], theta[2 * n + 1]
    lh = np.exp(mu + g + a[hi] + d[ai])
    la = np.exp(mu + a[ai] + d[hi])
    petits = (yh <= 1) & (ya <= 1)

    def nll_rho(rho):
        t = tau(yh[petits], ya[petits], lh[petits], la[petits], rho)
        return -(w[petits] * np.log(np.clip(t, 1e-10, None))).sum()
    rho = float(minimize_scalar(nll_rho, bounds=(-0.2, 0.2), method="bounded").x) if petits.any() else 0.0
    return ModeleDC(equipes=equipes, attaque=a, defense=d, mu=float(mu), gamma=float(g), rho=rho)
