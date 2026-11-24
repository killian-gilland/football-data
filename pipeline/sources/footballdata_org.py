"""Source « quasi-direct » : API football-data.org (offre gratuite, clé personnelle).

Sert à intégrer les résultats le soir même, sans attendre la mise à jour bihebdomadaire de
football-data.co.uk (« Sunday nights and Wednesday nights »). Source annexe : si la clé est absente
ou si l'API échoue, le pipeline continue sans elle. Les scores de l'offre gratuite sont « delayed »
(retard non précisé par le fournisseur).

Format v4 : GET /v4/competitions/{code}/matches?season={année de début}
-> {"matches": [{"utcDate", "status", "matchday", "homeTeam": {"name", "shortName", "tla"},
                 "awayTeam": {...}, "score": {"fullTime": {"home", "away"}, "halfTime": {...}}}]}
"""
from __future__ import annotations

import json
import os

import pandas as pd
import requests

URL = "https://api.football-data.org/v4/competitions/{code}/matches?season={annee}"
VARIABLE_JETON = "FOOTBALL_DATA_ORG_TOKEN"

# Statuts de l'API -> statuts du site
STATUTS = {
    "SCHEDULED": "a_venir", "TIMED": "a_venir",
    "IN_PLAY": "en_cours", "PAUSED": "mi_temps",
    "FINISHED": "termine", "AWARDED": "termine",
    "POSTPONED": "reporte", "SUSPENDED": "reporte", "CANCELLED": "annule",
}


def jeton() -> str | None:
    return os.environ.get(VARIABLE_JETON) or None


def telecharger(code: str, saison: str, cle: str, timeout: float = 30.0) -> bytes:
    r = requests.get(URL.format(code=code, annee=saison[:4]), headers={"X-Auth-Token": cle}, timeout=timeout)
    r.raise_for_status()
    return r.content


def _noms(equipe: dict) -> list[str]:
    """Toutes les graphies utilisables pour retrouver l'équipe dans le référentiel."""
    return [n for n in (equipe.get("name"), equipe.get("shortName"), equipe.get("tla")) if n]


def normaliser(contenu: bytes, competition: str, saison: str) -> pd.DataFrame:
    data = json.loads(contenu.decode("utf-8"))
    lignes = []
    for m in data.get("matches", []):
        utc = pd.Timestamp(m["utcDate"])
        if utc.tzinfo is None:
            utc = utc.tz_localize("UTC")
        local = utc.tz_convert("Europe/Paris")
        score = m.get("score") or {}
        ft = score.get("fullTime") or {}
        ht = score.get("halfTime") or {}
        lignes.append({
            "competition": competition, "saison": saison,
            "journee": float(m["matchday"]) if m.get("matchday") is not None else float("nan"),
            "date": pd.Timestamp(local.date()), "heure_locale": local.strftime("%H:%M"),
            "noms_dom": _noms(m.get("homeTeam") or {}), "noms_ext": _noms(m.get("awayTeam") or {}),
            "statut_source": STATUTS.get(m.get("status"), "inconnu"),
            "buts_dom": ft.get("home"), "buts_ext": ft.get("away"),
            "mt_dom": ht.get("home"), "mt_ext": ht.get("away"),
        })
    df = pd.DataFrame(lignes)
    for c in ("buts_dom", "buts_ext", "mt_dom", "mt_ext"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def identifier(df: pd.DataFrame, ref) -> tuple[pd.DataFrame, list[str]]:
    """Ajoute dom / ext (identifiants du référentiel). Renvoie aussi les équipes non reconnues."""
    inconnus = set()

    def trouver(noms: list[str]):
        for n in noms:
            eid = ref.identifiant(n)
            if eid:
                return eid
        if noms:
            inconnus.add(noms[0])
        return None

    df = df.copy()
    df["dom"] = [trouver(n) for n in df["noms_dom"]]
    df["ext"] = [trouver(n) for n in df["noms_ext"]]
    return df, sorted(inconnus)
