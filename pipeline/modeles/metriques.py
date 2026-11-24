"""Métriques de prévision 1N2. Les probabilités sont ordonnées [domicile, nul, extérieur]."""
from __future__ import annotations

import numpy as np

ISSUES = ("dom", "nul", "ext")


def issue_index(buts_dom, buts_ext) -> np.ndarray:
    bd, be = np.asarray(buts_dom), np.asarray(buts_ext)
    return np.where(bd > be, 0, np.where(bd == be, 1, 2))


def _onehot(y: np.ndarray) -> np.ndarray:
    o = np.zeros((len(y), 3))
    o[np.arange(len(y)), y] = 1
    return o


def rps(p: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Ranked Probability Score par match (plus bas = meilleur). Tient compte de l'ordre dom < nul < ext."""
    cp, co = np.cumsum(p, axis=1)[:, :2], np.cumsum(_onehot(y), axis=1)[:, :2]
    return ((cp - co) ** 2).sum(axis=1) / 2


def log_loss(p: np.ndarray, y: np.ndarray) -> np.ndarray:
    return -np.log(np.clip(p[np.arange(len(y)), y], 1e-12, 1))


def brier(p: np.ndarray, y: np.ndarray) -> np.ndarray:
    return ((p - _onehot(y)) ** 2).sum(axis=1)


def resume(p: np.ndarray, y: np.ndarray) -> dict:
    return {"rps": float(rps(p, y).mean()), "log_loss": float(log_loss(p, y).mean()),
            "brier": float(brier(p, y).mean()), "n": int(len(y)),
            "precision": float((p.argmax(axis=1) == y).mean())}


def ic_ecart_bootstrap(a: np.ndarray, b: np.ndarray, n: int = 2000, graine: int = 0) -> tuple[float, float, float]:
    """Écart moyen a - b (par match, appariés) et son intervalle de confiance bootstrap à 95 %."""
    d = np.asarray(a) - np.asarray(b)
    rng = np.random.default_rng(graine)
    idx = rng.integers(0, len(d), size=(n, len(d)))
    moyennes = d[idx].mean(axis=1)
    return float(d.mean()), float(np.percentile(moyennes, 2.5)), float(np.percentile(moyennes, 97.5))


def calibration(p: np.ndarray, y: np.ndarray, tranches: int = 10) -> list[dict]:
    """Probabilité annoncée vs fréquence observée, toutes issues confondues."""
    pf, of = p.ravel(), _onehot(y).ravel()
    bornes = np.linspace(0, 1, tranches + 1)
    res = []
    for lo, hi in zip(bornes[:-1], bornes[1:]):
        m = (pf >= lo) & (pf < hi if hi < 1 else pf <= hi)
        if m.sum() >= 20:
            res.append({"de": round(lo, 2), "a": round(hi, 2), "annonce": float(pf[m].mean()),
                        "observe": float(of[m].mean()), "n": int(m.sum())})
    return res


def probas_cotes(cote_dom, cote_nul, cote_ext) -> np.ndarray:
    """Probabilités implicites des cotes, marge retirée proportionnellement."""
    inv = 1 / np.column_stack([cote_dom, cote_nul, cote_ext]).astype(float)
    return inv / inv.sum(axis=1, keepdims=True)
