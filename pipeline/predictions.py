"""Journal public des prédictions, en ajout seul.

Chaque exécution enregistre les prédictions des matchs à venir (horodatées). Une ligne n'est jamais
modifiée ni supprimée. Pour évaluer un match, on retient la DERNIÈRE prédiction enregistrée avant
le jour du match (heure de Paris) : impossible de « corriger » une prédiction après coup.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .config import DOSSIER_DONNEES
from .modeles import metriques as mt

VERSION_MODELE = "v1"


def chemin_journal(cid: str, racine: Path = DOSSIER_DONNEES) -> Path:
    return racine / "predictions" / cid / "journal.jsonl"


def lire(cid: str, racine: Path = DOSSIER_DONNEES) -> list[dict]:
    p = chemin_journal(cid, racine)
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def enregistrer(cid: str, previsions: list[dict], maintenant: datetime | None = None,
                horizon_jours: int = 10, racine: Path = DOSSIER_DONNEES) -> int:
    """Ajoute les prédictions des matchs des `horizon_jours` prochains jours. Renvoie le nombre ajouté."""
    maintenant = maintenant or datetime.now(timezone.utc)
    aujourd_hui = pd.Timestamp(maintenant.date())
    existantes = lire(cid, racine)
    derniere = {}
    for e in existantes:
        derniere[e["match_id"]] = e
    nouvelles = []
    for p in previsions:
        d = pd.Timestamp(p["date"])
        if not (aujourd_hui < d <= aujourd_hui + pd.Timedelta(days=horizon_jours)):
            continue  # seulement les matchs des jours suivants : jamais le jour même
        probas = [round(x, 4) for x in p["p"]]
        prec = derniere.get(p["match_id"])
        if prec and prec["p"] == probas:
            continue  # rien de nouveau
        nouvelles.append({"horodatage": maintenant.isoformat(timespec="seconds"), "match_id": p["match_id"],
                          "date_match": p["date"], "modele": p["modele"], "version": VERSION_MODELE,
                          "p": probas, "scores": p.get("scores", [])[:3]})
    if nouvelles:
        chemin = chemin_journal(cid, racine)
        chemin.parent.mkdir(parents=True, exist_ok=True)
        with open(chemin, "a", encoding="utf-8") as f:
            for n in nouvelles:
                f.write(json.dumps(n, ensure_ascii=False) + "\n")
    return len(nouvelles)


def retenues(journal: list[dict]) -> dict[str, dict]:
    """Dernière prédiction enregistrée strictement avant le jour du match, par match."""
    res: dict[str, dict] = {}
    for e in journal:
        h = pd.Timestamp(e["horodatage"]).tz_convert("Europe/Paris").tz_localize(None).normalize()
        if h < pd.Timestamp(e["date_match"]):
            if e["match_id"] not in res or e["horodatage"] >= res[e["match_id"]]["horodatage"]:
                res[e["match_id"]] = e
    return res


def evaluer(journal: list[dict], matchs: pd.DataFrame) -> dict:
    ret = retenues(journal)
    joues = set(matchs.loc[matchs["statut"] == "joue", "match_id"])
    en_attente = sorted([e for m, e in ret.items() if m not in joues], key=lambda e: e["date_match"])
    j = matchs[(matchs["statut"] == "joue") & matchs["match_id"].isin(ret)].copy()
    if j.empty:
        return {"n_predictions": len(journal), "n_evaluees": 0, "liste": [], "en_attente": en_attente,
                "premiere": journal[0]["horodatage"] if journal else None}
    p = np.array([ret[m]["p"] for m in j["match_id"]])
    p = p / p.sum(axis=1, keepdims=True)
    y = mt.issue_index(j["buts_dom"], j["buts_ext"])
    marche = mt.probas_cotes(j["cote_dom"], j["cote_nul"], j["cote_ext"])
    ok = ~np.isnan(marche).any(axis=1)
    rps = mt.rps(p, y)
    liste = [{"match_id": m, "horodatage": ret[m]["horodatage"], "p": ret[m]["p"],
              "issue": ["dom", "nul", "ext"][int(yy)], "rps": float(r)} for m, yy, r in zip(j["match_id"], y, rps)]
    return {"n_predictions": len(journal), "n_evaluees": int(len(j)),
            "modele": mt.resume(p, y), "marche": mt.resume(marche[ok], y[ok]) if ok.any() else None,
            "liste": sorted(liste, key=lambda x: x["horodatage"], reverse=True), "en_attente": en_attente,
            "premiere": journal[0]["horodatage"]}
