"""Simulation Monte-Carlo de la fin de saison.

Chaque match restant est simulé à partir des buts attendus du modèle Dixon-Coles (tirage de Poisson).
Une incertitude sur la force des équipes est ajoutée à chaque simulation (σ, choisi par backtest).
Le classement simulé applique points, différence de buts, buts marqués, victoires, victoires à
l'extérieur ; les confrontations directes ne sont pas appliquées dans la simulation (approximation).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .classement import classement
from .modeles import dixon_coles as dc


def groupes_de_zones(fmt: dict, n_equipes: int) -> dict[str, list[int]]:
    """Regroupements lisibles des places : titre, Ligue des champions, Europe, zone rouge, relégation."""
    zones = {z["code"]: z["positions"] for z in fmt.get("zones", [])}
    g = {"titre": [1]}
    if "c1" in zones:
        g["c1"] = zones["c1"]
    europe = sorted({p for c in ("c1", "c1q", "c3", "c4") for p in zones.get(c, [])})
    if europe:
        g["europe"] = europe
    danger = sorted({p for c in ("barrage", "relegation") for p in zones.get(c, [])})
    if danger:
        g["danger"] = danger
    if "relegation" in zones:
        g["relegation"] = zones["relegation"]
    return g


def simuler(matchs_saison: pd.DataFrame, modele: dc.ModeleDC, fmt: dict, n_sims: int = 10000,
            sigma: float = 0.0, graine: int = 42, suivis: list[str] | None = None) -> dict:
    """`suivis` : identifiants de matchs à venir dont on calcule « ce qui se joue » (chances selon le résultat)."""
    rng = np.random.default_rng(graine)
    base = classement(matchs_saison, {**fmt, "zones": []})
    equipes = list(base.sort_values("equipe")["equipe"])
    idx = {e: i for i, e in enumerate(equipes)}
    n = len(equipes)
    b = base.set_index("equipe").loc[equipes]
    bareme = fmt.get("points", {"victoire": 3, "nul": 1})

    restants = matchs_saison[matchs_saison["statut"] == "a_venir"]
    pts = np.tile(b["pts"].to_numpy(float), (n_sims, 1))
    diff = np.tile(b["diff"].to_numpy(float), (n_sims, 1))
    bp = np.tile(b["bp"].to_numpy(float), (n_sims, 1))
    vic = np.tile(b["g"].to_numpy(float), (n_sims, 1))
    vic_ext = np.tile(b["victoires_exterieur"].to_numpy(float), (n_sims, 1))

    if len(restants):
        di = restants["dom"].map(idx).to_numpy()
        ei = restants["ext"].map(idx).to_numpy()
        ld, le = modele.lambdas(restants["dom"].to_numpy(), restants["ext"].to_numpy())
        if sigma > 0:
            bruit_a = rng.normal(0, sigma, (n_sims, n))
            bruit_d = rng.normal(0, sigma, (n_sims, n))
            ld = ld * np.exp(bruit_a[:, di] + bruit_d[:, ei])
            le = le * np.exp(bruit_a[:, ei] + bruit_d[:, di])
        else:
            ld, le = np.tile(ld, (n_sims, 1)), np.tile(le, (n_sims, 1))
        gd, ge = rng.poisson(ld), rng.poisson(le)
        H = np.zeros((len(restants), n)); H[np.arange(len(restants)), di] = 1
        A = np.zeros((len(restants), n)); A[np.arange(len(restants)), ei] = 1
        vd, nul, ve = (gd > ge), (gd == ge), (gd < ge)
        pts += (vd * bareme["victoire"] + nul * bareme["nul"]) @ H + (ve * bareme["victoire"] + nul * bareme["nul"]) @ A
        diff += (gd - ge) @ H + (ge - gd) @ A
        bp += gd @ H + ge @ A
        vic += vd @ H + ve @ A
        vic_ext += ve @ A

    # Clé de tri lexicographique encodée dans un seul nombre (+ aléa pour les égalités parfaites)
    cle = (pts * 1e10 + (diff + 500) * 1e7 + bp * 1e4 + vic * 1e2 + vic_ext + rng.random(pts.shape) * 0.5)
    ordre = np.argsort(-cle, axis=1)
    rangs = np.empty_like(ordre)
    rangs[np.arange(n_sims)[:, None], ordre] = np.arange(1, n + 1)

    positions = np.stack([(rangs == r).mean(axis=0) for r in range(1, n + 1)], axis=1)  # équipes x rangs
    res_equipes = []
    for e in equipes:
        i = idx[e]
        z = {}
        for zone in fmt.get("zones", []):
            z[zone["code"]] = float(np.isin(rangs[:, i], zone["positions"]).mean())
        res_equipes.append({
            "equipe": e, "points_actuels": int(b.loc[e, "pts"]),
            "points_attendus": float(pts[:, i].mean()),
            "points_p10": float(np.percentile(pts[:, i], 10)), "points_p90": float(np.percentile(pts[:, i], 90)),
            "rang_moyen": float(rangs[:, i].mean()), "titre": float((rangs[:, i] == 1).mean()),
            "zones": z, "positions": [float(x) for x in positions[i]],
        })
    res_equipes.sort(key=lambda r: r["rang_moyen"])
    enjeux = {}
    if suivis and len(restants):
        groupes = groupes_de_zones(fmt, n)
        colonnes = {m: k for k, m in enumerate(restants["match_id"])}
        for mid in suivis:
            k = colonnes.get(mid)
            if k is None:
                continue
            issue = np.sign(gd[:, k] - ge[:, k])  # 1 : victoire domicile, 0 : nul, -1 : victoire extérieur
            masques = [issue == 1, issue == 0, issue == -1]
            res_m, importance = {}, 0.0
            for cote, eq in (("dom", restants.iloc[k]["dom"]), ("ext", restants.iloc[k]["ext"])):
                r = rangs[:, idx[eq]]
                res_m[cote] = {}
                for nom, pos in groupes.items():
                    dedans = np.isin(r, pos)
                    vals = [float(dedans[mq].mean()) if mq.sum() >= 200 else None for mq in masques]
                    connus = [v for v in vals if v is not None]
                    if connus:
                        importance = max(importance, max(connus) - min(connus))
                    res_m[cote][nom] = vals
                pts_e = pts[:, idx[eq]]
                res_m[cote]["points"] = [float(pts_e[mq].mean()) if mq.sum() >= 200 else None for mq in masques]
            res_m["importance"] = importance
            enjeux[mid] = res_m
    return {"n_simulations": n_sims, "sigma": sigma, "matchs_restants": int(len(restants)), "equipes": res_equipes,
            "enjeux": enjeux}


def evolution_chances(matchs: pd.DataFrame, comp, saison: str, sigma: float = 0.0, n_sims: int = 4000) -> dict:
    """Chances de chaque équipe recalculées après chaque journée (et avant la 1re), sans regarder le futur :
    le modèle est réajusté à la date de la journée, les matchs suivants sont simulés."""
    from .backtest import contexte_saison
    cur = matchs[matchs["saison"] == saison].copy()
    fmt = comp.format_saison(saison)
    joues = cur[cur["statut"] == "joue"]
    journees = [0] + sorted(int(j) for j in joues["journee"].dropna().unique())
    ctx = contexte_saison(matchs, saison)
    groupes = groupes_de_zones(fmt, len(ctx.equipes))
    series: dict[str, dict[str, list]] = {e: {g: [] for g in [*groupes, "points"]} for e in ctx.equipes}
    for j in journees:
        etat = cur.copy()
        hors = ~((etat["statut"] == "joue") & (etat["journee"] <= j))
        etat.loc[hors, ["statut"]] = "a_venir"
        etat.loc[hors, ["buts_dom", "buts_ext"]] = np.nan
        deja = cur[(cur["statut"] == "joue") & (cur["journee"] <= j)]
        date_ref = (deja["date"].max() + pd.Timedelta(days=1)) if len(deja) else cur["date"].min()
        modele = dc.ajuster(matchs, date_ref, ctx.equipes, ctx.promus, ctx.relegues)
        zones = [{"code": g, "positions": p} for g, p in groupes.items()]
        sim = simuler(etat, modele, {**fmt, "zones": zones}, n_sims=n_sims, sigma=sigma, graine=7)
        for e in sim["equipes"]:
            for g in groupes:
                series[e["equipe"]][g].append(round(e["zones"][g], 4))
            series[e["equipe"]]["points"].append(round(e["points_attendus"], 1))
    return {"journees": journees, "groupes": list(groupes), "n_simulations": n_sims,
            "equipes": [{"equipe": e, **v} for e, v in series.items()]}


def backtest_simulation(matchs: pd.DataFrame, comp, saisons: list[str], sigmas=(0.0, 0.1),
                        n_sims: int = 3000) -> dict:
    """Simulation lancée à mi-saison sur des saisons passées. On évalue (Brier) les probabilités de
    titre, de top 3 et de 3 dernières places, contre la référence « classement de mi-saison figé »."""
    from .backtest import contexte_saison
    lignes = []
    for s in saisons:
        g = matchs[matchs["saison"] == s].sort_values("date").copy()
        if g.empty or s == "2019-20":
            continue
        fmt = {**comp.format_saison(s), "zones": []}
        n_eq = len(set(g["dom"]) | set(g["ext"]))
        coupe = g["date"].iloc[len(g) // 2]
        final = classement(g, fmt).set_index("equipe")["rang"]
        a_mi = g.copy()
        a_mi.loc[a_mi["date"] >= coupe, "statut"] = "a_venir"
        mi = classement(a_mi, fmt).set_index("equipe")["rang"]
        ctx = contexte_saison(matchs, s)
        modele = dc.ajuster(matchs, coupe, ctx.equipes, ctx.promus, ctx.relegues)
        zones = [{"code": "titre", "positions": [1]}, {"code": "top3", "positions": [1, 2, 3]},
                 {"code": "bas3", "positions": [n_eq - 2, n_eq - 1, n_eq]}]
        for sigma in sigmas:
            sim = simuler(a_mi, modele, {**fmt, "zones": zones}, n_sims=n_sims, sigma=sigma, graine=1)
            for r in sim["equipes"]:
                e = r["equipe"]
                for z in zones:
                    obs = float(final[e] in z["positions"])
                    lignes.append({"saison": s, "sigma": sigma, "evenement": z["code"], "equipe": e,
                                   "proba": r["zones"][z["code"]], "naif": float(mi[e] in z["positions"]),
                                   "observe": obs})
    df = pd.DataFrame(lignes)
    res = {"saisons": sorted(df["saison"].unique().tolist()), "par_sigma": {}}
    for sigma, g in df.groupby("sigma"):
        res["par_sigma"][str(sigma)] = {
            ev: {"brier_modele": float(((h["proba"] - h["observe"]) ** 2).mean()),
                 "brier_classement_fige": float(((h["naif"] - h["observe"]) ** 2).mean())}
            for ev, h in g.groupby("evenement")}
    moy = {s: np.mean([v["brier_modele"] for v in d.values()]) for s, d in res["par_sigma"].items()}
    res["sigma_retenu"] = float(min(moy, key=moy.get))
    res["valide"] = all(v["brier_modele"] < v["brier_classement_fige"]
                        for v in res["par_sigma"][str(res["sigma_retenu"])].values())
    return res
