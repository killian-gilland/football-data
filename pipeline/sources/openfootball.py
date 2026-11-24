"""Source secondaire : openfootball (domaine public, CC0).

Utilisée pour le calendrier complet de la saison en cours (matchs à venir, numéros de journée)
et comme contrôle croisé des scores.
"""
from __future__ import annotations

import json
import re

import pandas as pd

URL = "https://raw.githubusercontent.com/openfootball/football.json/master/{saison}/{code}.json"


def url_saison(code: str, saison: str) -> str:
    return URL.format(saison=saison, code=code)


def _journee(libelle: str) -> float:
    m = re.search(r"(\d+)", libelle or "")
    return float(m.group(1)) if m else float("nan")


def normaliser(contenu: bytes, competition: str, saison: str) -> pd.DataFrame:
    data = json.loads(contenu.decode("utf-8"))
    lignes = []
    for m in data.get("matches", []):
        score = m.get("score") or {}
        if isinstance(score, list):  # format court : [buts_dom, buts_ext], sans mi-temps
            ft, ht = score, [None, None]
        else:
            ft = score.get("ft") or [None, None]
            ht = score.get("ht") or [None, None]
        lignes.append({
            "competition": competition,
            "saison": saison,
            "journee": _journee(m.get("round", "")),
            "date": pd.to_datetime(m.get("date"), errors="coerce"),
            "heure_locale": m.get("time") or "",
            "dom_brut": (m.get("team1") or "").strip(),
            "ext_brut": (m.get("team2") or "").strip(),
            "buts_dom": ft[0], "buts_ext": ft[1],
            "mt_dom": ht[0], "mt_ext": ht[1],
        })
    df = pd.DataFrame(lignes)
    for c in ("buts_dom", "buts_ext", "mt_dom", "mt_ext"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df
