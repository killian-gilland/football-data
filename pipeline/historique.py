"""Historique et records : classements de chaque saison, all-time, confrontations, records."""
from __future__ import annotations

import pandas as pd

from .classement import classement, vue_equipes
from .config import Competition
from .stats_equipes import series


def classements_saisons(matchs: pd.DataFrame, comp: Competition) -> dict[str, pd.DataFrame]:
    return {s: classement(g, comp.format_saison(s)) for s, g in matchs.groupby("saison")}


def all_time(matchs: pd.DataFrame) -> pd.DataFrame:
    """Classement cumulé. Barème uniforme à 3 points pour comparer les époques."""
    v = vue_equipes(matchs)
    g = v.groupby("equipe")
    t = pd.DataFrame({
        "saisons": g["saison"].nunique(), "j": g.size(),
        "g": g["resultat"].apply(lambda s: (s == "V").sum()),
        "n": g["resultat"].apply(lambda s: (s == "N").sum()),
        "p": g["resultat"].apply(lambda s: (s == "D").sum()),
        "bp": g["bp"].sum(), "bc": g["bc"].sum(),
    })
    t["diff"] = t["bp"] - t["bc"]
    t["pts"] = 3 * t["g"] + t["n"]
    t["ppm"] = t["pts"] / t["j"]
    t = t.sort_values(["pts", "diff"], ascending=False).reset_index()
    t.insert(0, "rang", range(1, len(t) + 1))
    return t


def palmares(classements: dict[str, pd.DataFrame], saison_courante: str) -> list[dict]:
    res = []
    for s, t in sorted(classements.items()):
        if s == saison_courante:
            continue
        top = t.iloc[0]
        res.append({"saison": s, "champion": top["equipe"], "pts": int(top["pts"]),
                    "deuxieme": t.iloc[1]["equipe"], "ecart": int(top["pts"] - t.iloc[1]["pts"])})
    return res


def evolution_par_equipe(classements: dict[str, pd.DataFrame]) -> dict[str, list[dict]]:
    res: dict[str, list[dict]] = {}
    for s, t in sorted(classements.items()):
        for _, r in t.iterrows():
            res.setdefault(r["equipe"], []).append({
                "saison": s, "rang": int(r["rang"]), "equipes": int(len(t)), "pts": int(r["pts"]),
                "j": int(r["j"]), "bp": int(r["bp"]), "bc": int(r["bc"])})
    return res


def confrontations(matchs: pd.DataFrame, equipe: str, derniers: int = 5) -> list[dict]:
    """Bilan de `equipe` face à chacun de ses adversaires en championnat."""
    v = vue_equipes(matchs)
    v = v[v["equipe"] == equipe]
    res = []
    for adv, g in v.groupby("adversaire"):
        g = g.sort_values("date")
        res.append({
            "adversaire": adv, "j": int(len(g)), "v": int((g["resultat"] == "V").sum()),
            "n": int((g["resultat"] == "N").sum()), "d": int((g["resultat"] == "D").sum()),
            "bp": int(g["bp"].sum()), "bc": int(g["bc"].sum()),
            "derniers": [{"match_id": m, "saison": s, "date": d.strftime("%Y-%m-%d"), "lieu": l,
                          "score": f"{int(bp)}-{int(bc)}", "resultat": r}
                         for m, s, d, l, bp, bc, r in zip(g["match_id"], g["saison"], g["date"], g["lieu"],
                                                          g["bp"], g["bc"], g["resultat"])][-derniers:][::-1],
        })
    return sorted(res, key=lambda x: -x["j"])


def plus_gros_scores(matchs: pd.DataFrame, n: int = 20) -> dict:
    j = matchs[matchs["statut"] == "joue"].copy()
    j["ecart"] = (j["buts_dom"] - j["buts_ext"]).abs()
    j["total"] = j["buts_dom"] + j["buts_ext"]

    def fmt(df):
        return [{"match_id": r.match_id, "saison": r.saison, "date": r.date.strftime("%Y-%m-%d"),
                 "dom": r.dom, "ext": r.ext, "score": f"{int(r.buts_dom)}-{int(r.buts_ext)}"}
                for r in df.itertuples()]
    return {"plus_larges_victoires": fmt(j.sort_values(["ecart", "total", "date"], ascending=[False, False, True]).head(n)),
            "matchs_les_plus_prolifiques": fmt(j.sort_values(["total", "ecart", "date"], ascending=[False, False, True]).head(n))}


def series_records(matchs: pd.DataFrame, n: int = 10) -> dict:
    """Plus longues séries en matchs de championnat consécutifs (toutes saisons confondues)."""
    v = vue_equipes(matchs)
    lignes = []
    for eq, g in v.groupby("equipe"):
        rec = series(list(g.sort_values("date")["resultat"]))["record"]
        lignes.append({"equipe": eq, **rec})
    df = pd.DataFrame(lignes)
    return {k: df.sort_values(k, ascending=False).head(n)[["equipe", k]].rename(columns={k: "longueur"}).to_dict("records")
            for k in ("victoires", "invincibilite", "sans_victoire", "defaites")}


def records_saison(classements: dict[str, pd.DataFrame], saison_courante: str, n: int = 10) -> dict:
    lignes = []
    for s, t in classements.items():
        if s == saison_courante:
            continue
        for r in t.itertuples():
            lignes.append({"saison": s, "equipe": r.equipe, "pts": int(r.pts), "ppm": round(float(r.ppm), 3),
                           "bp": int(r.bp), "bc": int(r.bc), "j": int(r.j),
                           "bp_pm": round(r.bp / r.j, 3), "bc_pm": round(r.bc / r.j, 3)})
    df = pd.DataFrame(lignes)
    return {
        "meilleur_ratio_points": df.sort_values("ppm", ascending=False).head(n).to_dict("records"),
        "pire_ratio_points": df.sort_values("ppm").head(n).to_dict("records"),
        "meilleure_attaque": df.sort_values("bp_pm", ascending=False).head(n).to_dict("records"),
        "meilleure_defense": df.sort_values("bc_pm").head(n).to_dict("records"),
    }
