"""Classement d'une saison selon ses règles (points par victoire, pénalités, départages, points/match)."""
from __future__ import annotations

import numpy as np
import pandas as pd


def vue_equipes(matchs: pd.DataFrame) -> pd.DataFrame:
    """Une ligne par (match, équipe) avec colonnes « pour » / « contre ». Base de toutes les stats."""
    j = matchs[matchs["statut"] == "joue"]
    paires = [("dom", "ext", "domicile"), ("ext", "dom", "exterieur")]
    blocs = []
    for moi, lui, lieu in paires:
        b = pd.DataFrame({
            "match_id": j["match_id"], "saison": j["saison"], "date": j["date"], "journee": j["journee"],
            "equipe": j[moi], "adversaire": j[lui], "lieu": lieu,
            "bp": j[f"buts_{moi}"], "bc": j[f"buts_{lui}"],
            "mt_bp": j[f"mt_{moi}"], "mt_bc": j[f"mt_{lui}"],
            "tirs": j[f"tirs_{moi}"], "tirs_contre": j[f"tirs_{lui}"],
            "cadres": j[f"cadres_{moi}"], "cadres_contre": j[f"cadres_{lui}"],
            "corners": j[f"corners_{moi}"], "corners_contre": j[f"corners_{lui}"],
            "fautes": j[f"fautes_{moi}"], "fautes_subies": j[f"fautes_{lui}"],
            "jaunes": j[f"jaunes_{moi}"], "rouges": j[f"rouges_{moi}"],
        })
        blocs.append(b)
    v = pd.concat(blocs, ignore_index=True)
    v["resultat"] = np.select([v["bp"] > v["bc"], v["bp"] == v["bc"]], ["V", "N"], "D")
    return v.sort_values(["date", "match_id", "lieu"]).reset_index(drop=True)


def _agreger(v: pd.DataFrame, bareme: dict) -> pd.DataFrame:
    g = v.groupby("equipe")
    t = pd.DataFrame({
        "j": g.size(),
        "g": g["resultat"].apply(lambda s: (s == "V").sum()),
        "n": g["resultat"].apply(lambda s: (s == "N").sum()),
        "p": g["resultat"].apply(lambda s: (s == "D").sum()),
        "bp": g["bp"].sum(), "bc": g["bc"].sum(),
        "victoires_exterieur": v[v["lieu"] == "exterieur"].groupby("equipe")["resultat"].apply(lambda s: (s == "V").sum()),
    }).fillna(0)
    t["diff"] = t["bp"] - t["bc"]
    t["pts"] = t["g"] * bareme["victoire"] + t["n"] * bareme["nul"] + t["p"] * bareme.get("defaite", 0)
    return t.astype(int)


def _mini_championnat(v: pd.DataFrame, groupe: list[str], bareme: dict) -> pd.DataFrame | None:
    """Classement restreint aux matchs entre équipes du groupe ; None si tous les matchs ne sont pas joués."""
    sous = v[v["equipe"].isin(groupe) & v["adversaire"].isin(groupe)]
    attendu = len(groupe) * (len(groupe) - 1)  # aller + retour, vu de chaque côté / 2 * 2
    if len(sous) < attendu:
        return None
    return _agreger(sous, bareme)


def _ordonner(groupe: list[str], table: pd.DataFrame, criteres: list[str], v: pd.DataFrame, bareme: dict) -> list[str]:
    if len(groupe) <= 1:
        return groupe
    if not criteres:
        return sorted(groupe)  # dernier recours (tirage au sort dans le règlement) : ordre alphabétique
    critere, reste = criteres[0], criteres[1:]
    if critere.startswith("confrontations_"):
        mini = _mini_championnat(v, groupe, bareme)
        if mini is None:
            return _ordonner(groupe, table, reste, v, bareme)
        valeurs = mini.reindex(groupe)["pts" if critere == "confrontations_points" else "diff"].fillna(0)
    else:
        col = {"diff": "diff", "buts_pour": "bp", "victoires": "g", "victoires_exterieur": "victoires_exterieur"}[critere]
        valeurs = table.loc[groupe, col]
    ordre = []
    for val in sorted(valeurs.unique(), reverse=True):
        sous_groupe = list(valeurs[valeurs == val].index)
        ordre += _ordonner(sous_groupe, table, reste, v, bareme)
    return ordre


def classement(matchs: pd.DataFrame, fmt: dict, equipes: list[str] | None = None) -> pd.DataFrame:
    """Classement d'une saison. `matchs` = matchs de la saison (joués et à venir)."""
    v = vue_equipes(matchs)
    bareme = fmt.get("points", {"victoire": 3, "nul": 1, "defaite": 0})
    equipes = equipes or sorted(set(matchs["dom"]) | set(matchs["ext"]))
    table = _agreger(v, bareme).reindex(equipes).fillna(0).astype(int)
    penalites = fmt.get("penalites") or {}
    table["penalite"] = [int(penalites.get(e, 0)) for e in table.index]
    table["pts"] = table["pts"] - table["penalite"]
    table["ppm"] = np.where(table["j"] > 0, table["pts"] / table["j"].clip(lower=1), 0.0)
    cle = "ppm" if fmt.get("classement_par") == "points_par_match" else "pts"
    criteres = fmt.get("departage", ["diff", "buts_pour"])
    ordre = []
    for val in sorted(table[cle].unique(), reverse=True):
        groupe = list(table.index[table[cle] == val])
        ordre += _ordonner(groupe, table, criteres, v, bareme)
    table = table.loc[ordre].reset_index().rename(columns={"index": "equipe"})
    table.insert(0, "rang", np.arange(1, len(table) + 1))
    table["zone"] = None
    for z in fmt.get("zones", []):
        for pos in z["positions"]:
            if pos <= len(table):
                table.loc[pos - 1, "zone"] = z["code"]
    return table
