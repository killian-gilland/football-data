"""Source principale : football-data.co.uk (un CSV par saison et par division).

Les colonnes varient selon les saisons : on lit le CSV de façon tolérante (lignes plus longues
que l'en-tête, colonnes vides, deux formats de date) puis on mappe vers des noms canoniques.
Les colonnes absentes deviennent des valeurs manquantes, jamais des zéros.
"""
from __future__ import annotations

import csv
import io

import numpy as np
import pandas as pd

from ..config import saison_vers_code

URL = "https://www.football-data.co.uk/mmz4281/{code}/{division}.csv"
URL_PROCHAINS = "https://www.football-data.co.uk/fixtures.csv"  # matchs des prochains jours, avec cotes

# Colonne football-data -> colonne canonique
COLONNES_SCORES = {
    "FTHG": "buts_dom", "FTAG": "buts_ext",
    "HTHG": "mt_dom", "HTAG": "mt_ext",
}
COLONNES_STATS = {
    "HS": "tirs_dom", "AS": "tirs_ext",
    "HST": "cadres_dom", "AST": "cadres_ext",
    "HC": "corners_dom", "AC": "corners_ext",
    "HF": "fautes_dom", "AF": "fautes_ext",
    "HY": "jaunes_dom", "AY": "jaunes_ext",
    "HR": "rouges_dom", "AR": "rouges_ext",
}
# Préfixes à exclure du calcul de la cote moyenne (ce ne sont pas des bookmakers).
PREFIXES_NON_BOOKMAKERS = ("Max", "Avg", "BbMx", "BbAv", "Bb")


def url_saison(division: str, saison: str) -> str:
    return URL.format(code=saison_vers_code(saison), division=division)


def lire_csv_tolerant(contenu: bytes) -> tuple[pd.DataFrame, dict]:
    """Lit un CSV football-data. Renvoie (dataframe brut en texte, diagnostic de lecture)."""
    for enc in ("utf-8-sig", "latin-1"):
        try:
            texte = contenu.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    lignes = list(csv.reader(io.StringIO(texte)))
    if not lignes:
        raise ValueError("CSV vide")
    entete = [c.strip() for c in lignes[0]]
    # On retire les colonnes d'en-tête vides en fin de ligne
    while entete and entete[-1] == "":
        entete.pop()
    n = len(entete)
    lignes_ok, debordements, vides = [], 0, 0
    for brut in lignes[1:]:
        if not any(c.strip() for c in brut):
            vides += 1
            continue
        if len(brut) > n and any(c.strip() for c in brut[n:]):
            debordements += 1
        ligne = (brut + [""] * n)[:n]
        lignes_ok.append([c.strip() for c in ligne])
    df = pd.DataFrame(lignes_ok, columns=entete)
    # Colonnes en double ou sans nom : on garde la première occurrence
    df = df.loc[:, [c != "" for c in df.columns]]
    df = df.loc[:, ~df.columns.duplicated()]
    diag = {"lignes": len(df), "lignes_vides_ignorees": vides, "lignes_debordantes": debordements,
            "colonnes": list(df.columns)}
    return df, diag


def _date(valeurs: pd.Series) -> pd.Series:
    """Gère dd/mm/yy et dd/mm/yyyy."""
    v = valeurs.str.strip()
    longue = pd.to_datetime(v, format="%d/%m/%Y", errors="coerce")
    courte = pd.to_datetime(v, format="%d/%m/%y", errors="coerce")
    return longue.where(v.str.len() > 8, courte)


def _num(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df.columns:
        return pd.Series(np.nan, index=df.index)
    return pd.to_numeric(df[col].replace("", np.nan), errors="coerce")


def _triplets_bookmakers(colonnes: list[str], cloture: bool) -> list[tuple[str, str, str]]:
    """Trouve les triplets (H, D, A) de cotes 1N2 par bookmaker."""
    triplets = []
    for c in colonnes:
        if not c.endswith("H") or len(c) < 2:
            continue
        prefixe = c[:-1]
        if prefixe.startswith(PREFIXES_NON_BOOKMAKERS) or prefixe in ("", "AH", "FTH", "HT", "H"):
            continue
        if not prefixe.isalnum():
            continue
        est_cloture = prefixe.endswith("C") and len(prefixe) > 1 and (prefixe[:-1] + "H") in colonnes
        if est_cloture != cloture:
            continue
        d, a = prefixe + "D", prefixe + "A"
        if d in colonnes and a in colonnes:
            triplets.append((c, d, a))
    return triplets


def _cotes_moyennes(df: pd.DataFrame, cloture: bool) -> pd.DataFrame:
    """Cote moyenne du marché (moyenne des probabilités implicites des bookmakers présents,
    reconvertie en cote). Plus robuste que de dépendre d'une colonne Avg qui n'existe pas partout."""
    triplets = _triplets_bookmakers(list(df.columns), cloture)
    if not triplets:
        return pd.DataFrame({k: np.nan for k in ("dom", "nul", "ext")}, index=df.index)
    probas = {k: [] for k in ("dom", "nul", "ext")}
    for h, d, a in triplets:
        for k, col in zip(("dom", "nul", "ext"), (h, d, a)):
            cote = _num(df, col)
            cote = cote.where(cote > 1.0)
            probas[k].append(1.0 / cote)
    res = {}
    for k in probas:
        p = pd.concat(probas[k], axis=1).mean(axis=1, skipna=True)
        res[k] = 1.0 / p
    return pd.DataFrame(res, index=df.index)


def normaliser(df: pd.DataFrame, competition: str, saison: str) -> pd.DataFrame:
    """CSV brut -> lignes de matchs au schéma canonique (noms d'équipes encore bruts)."""
    out = pd.DataFrame(index=df.index)
    out["competition"] = competition
    out["saison"] = saison
    out["date"] = _date(df["Date"]) if "Date" in df.columns else pd.NaT
    out["heure_source"] = df["Time"] if "Time" in df.columns else ""
    out["dom_brut"] = df["HomeTeam"].str.strip()
    out["ext_brut"] = df["AwayTeam"].str.strip()
    for src, dst in {**COLONNES_SCORES, **COLONNES_STATS}.items():
        out[dst] = _num(df, src)
    avant = _cotes_moyennes(df, cloture=False)
    clot = _cotes_moyennes(df, cloture=True)
    out["cote_dom"], out["cote_nul"], out["cote_ext"] = avant["dom"], avant["nul"], avant["ext"]
    out["cote_clot_dom"], out["cote_clot_nul"], out["cote_clot_ext"] = clot["dom"], clot["nul"], clot["ext"]
    out["nb_bookmakers"] = len(_triplets_bookmakers(list(df.columns), cloture=False))
    out = out[out["dom_brut"].fillna("") != ""]
    return out.reset_index(drop=True)
