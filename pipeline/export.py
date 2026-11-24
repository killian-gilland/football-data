"""Calcule tous les contenus du site et les écrit en JSON (contrat lu par le site Astro).

`construire` est pur (aucune écriture) ; `ecrire` remplace le dossier d'export d'un bloc,
pour ne jamais laisser le site avec un mélange d'ancienne et de nouvelle version.
"""
from __future__ import annotations

import json
import math
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import poisson

from . import backtest as bt
from . import cotes as cotes_mod
from . import historique as hist
from . import predictions as journal_mod
from . import simulation as sim_mod
from .classement import classement, evolution_par_journee, vue_equipes
from .config import DOSSIER_EXPORT, Competition, charger_referentiel
from .modeles import dixon_coles as dc
from .modeles import elo as elo_mod
from .modeles import indice_occasions as io_mod
from .modeles import metriques as mt
from .referentiel import Referentiel
from .stats_equipes import forme, series, stats_saison

NB_SAISONS_BACKTEST = 14
SOURCES = [
    {"nom": "football-data.co.uk", "url": "https://www.football-data.co.uk/",
     "usage": "Résultats, statistiques de match et cotes (source principale)"},
    {"nom": "openfootball", "url": "https://github.com/openfootball/football.json",
     "usage": "Calendrier de la saison en cours et contrôle croisé des scores", "licence": "CC0 (domaine public)"},
    {"nom": "football-data.org", "url": "https://www.football-data.org/",
     "usage": "Scores en quasi-direct et résultats du soir (« Football data provided by the Football-Data.org API »)"},
]


def propre(o):
    """Rend un objet sérialisable en JSON (types numpy, NaN -> null, dates -> texte)."""
    if isinstance(o, dict):
        return {str(k): propre(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [propre(v) for v in o]
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating, float)):
        f = float(o)
        return None if math.isnan(f) or math.isinf(f) else round(f, 4)
    if isinstance(o, np.bool_):
        return bool(o)
    if isinstance(o, (pd.Timestamp, datetime)):
        return o.strftime("%Y-%m-%d")
    if o is pd.NaT:
        return None
    return o


def _num(x):
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else x


@dataclass
class Sortie:
    fichiers: dict[str, object]
    previsions: list[dict]


def _points_attendus_poisson(l1: np.ndarray, l2: np.ndarray, bareme: dict) -> tuple[np.ndarray, np.ndarray]:
    k = np.arange(11)
    p1 = poisson.pmf(k[None, :], l1[:, None])
    p2 = poisson.pmf(k[None, :], l2[:, None])
    m = p1[:, :, None] * p2[:, None, :]
    v1 = np.tril(np.ones((11, 11)), -1)[None]
    nul = np.eye(11)[None]
    pv1, pn, pv2 = (m * v1).sum((1, 2)), (m * nul).sum((1, 2)), (m * v1.transpose(0, 2, 1)).sum((1, 2))
    return bareme["victoire"] * pv1 + bareme["nul"] * pn, bareme["victoire"] * pv2 + bareme["nul"] * pn


def construire(comp: Competition, matchs: pd.DataFrame, rapport: dict, alertes: list[str],
               maintenant: datetime | None = None, journal: list[dict] | None = None) -> Sortie:
    maintenant = maintenant or datetime.now(timezone.utc)
    ref = Referentiel(charger_referentiel(comp.referentiel_equipes))
    s = comp.saison_courante
    fmt = comp.format_saison(s)
    bareme = fmt["points"]
    cur = matchs[matchs["saison"] == s].copy()
    joues_cur = cur[cur["statut"] == "joue"]
    a_venir = cur[cur["statut"] == "a_venir"].sort_values(["date", "match_id"])
    v_all = vue_equipes(matchs)
    v_cur = v_all[v_all["saison"] == s]
    table = classement(cur, fmt)
    equipes_cur = list(table["equipe"])
    enrichi = comp.enrichissements

    # ---------- Modèles : backtest walk-forward (saisons passées + saison en cours jouée) ----------
    saisons_dispo = sorted(matchs["saison"].unique())
    saisons_test = saisons_dispo[-(NB_SAISONS_BACKTEST + 1):]
    pred = bt.walk_forward(matchs, saisons_test)
    evaluation = bt.evaluer(pred[pred["saison"] != s])
    principal = evaluation["modele_principal"]
    pred_cur = pred[pred["saison"] == s].set_index("match_id")

    # ---------- Prévisions des matchs à venir ----------
    hist_elo, notes = elo_mod.calculer(matchs)
    if joues_cur.empty:  # nouvelle saison sans match joué : passage de saison appliqué à la main
        prec = saisons_dispo[-2]
        eq_prec = set(matchs.loc[matchs["saison"] == prec, "dom"])
        notes = elo_mod.notes_debut_saison(notes, eq_prec, set(equipes_cur))
    derniere_date = joues_cur["date"].max() if len(joues_cur) else cur["date"].min()
    date_ref = max(pd.Timestamp(maintenant.date()), derniere_date + pd.Timedelta(days=1))
    ctx = bt.contexte_saison(matchs, s)
    modele_dc = dc.ajuster(matchs, date_ref, ctx.equipes, ctx.promus, ctx.relegues)
    joues_tous = matchs[matchs["statut"] == "joue"]
    hist_elo["y"] = mt.issue_index(*joues_tous.set_index("match_id").loc[hist_elo["match_id"], ["buts_dom", "buts_ext"]].T.to_numpy())
    logit = bt.logit_elo(hist_elo, date_ref, elo_mod.ParamsElo())
    previsions = []
    if len(a_venir):
        p_dc = modele_dc.predire_1n2(a_venir["dom"].to_numpy(), a_venir["ext"].to_numpy())
        ecart = np.array([notes[d] + elo_mod.ParamsElo().avantage_domicile - notes[e]
                          for d, e in zip(a_venir["dom"], a_venir["ext"])])
        p_elo = logit.predire(ecart)
        p_sel = {"elo": p_elo, "dixon_coles": p_dc, "ensemble": (p_elo + p_dc) / 2}.get(principal, p_dc)
        ld, le = modele_dc.lambdas(a_venir["dom"].to_numpy(), a_venir["ext"].to_numpy())
        for i, r in enumerate(a_venir.itertuples()):
            m = dc.matrice_scores(ld[i], le[i], modele_dc.rho)
            previsions.append({"match_id": r.match_id, "date": r.date.strftime("%Y-%m-%d"),
                               "modele": principal or "dixon_coles", "p": [float(x) for x in p_sel[i]],
                               "p_elo": p_elo[i].tolist(), "p_dixon_coles": p_dc[i].tolist(),
                               "scores": dc.scores_probables(m, 5), "lambda": [float(ld[i]), float(le[i])]})
    prev_par_id = {p["match_id"]: p for p in previsions}

    # ---------- Simulation Monte-Carlo ----------
    bt_sim = sim_mod.backtest_simulation(matchs, comp, [x for x in saisons_test if x != s])
    simulation = sim_mod.simuler(cur, modele_dc, fmt, n_sims=10000, sigma=bt_sim["sigma_retenu"])
    sim_par_eq = {e["equipe"]: e for e in simulation["equipes"]}

    # ---------- Indice d'occasions ----------
    saisons_stats = sorted(v_all.loc[v_all["tirs"].notna(), "saison"].unique())
    saisons_app = [x for x in saisons_stats if x != s]
    modele_io = io_mod.ajuster(v_all, saisons_app) if enrichi and saisons_app else None
    io_validation = io_mod.pouvoir_predictif(v_all, modele_io, saisons_app) if modele_io else None

    # ---------- Classement attendu ----------
    attendu = {e: {"equipe": e, "points": 0.0, "points_io": None, "points_marche": None, "points_modele": 0.0}
               for e in equipes_cur}
    for e in equipes_cur:
        attendu[e]["points"] = int(table.set_index("equipe").loc[e, "pts"])
    if modele_io is not None:
        st = joues_cur.dropna(subset=["tirs_dom", "cadres_dom", "tirs_ext", "cadres_ext"])
        if len(st):
            io_d = modele_io.io(st["tirs_dom"], st["cadres_dom"])
            io_e = modele_io.io(st["tirs_ext"], st["cadres_ext"])
            xd, xe = _points_attendus_poisson(io_d, io_e, bareme)
            for e in equipes_cur:
                attendu[e]["points_io"] = float(xd[(st["dom"] == e).to_numpy()].sum() + xe[(st["ext"] == e).to_numpy()].sum())
    if enrichi:
        for r in cotes_mod.equipes_vs_marche(cur, bareme):
            attendu[r["equipe"]]["points_marche"] = r["points_attendus_marche"]
    if principal and len(pred_cur):
        p = bt.probas(pred_cur.reset_index(), principal)
        pc = pred_cur.reset_index()
        xd = bareme["victoire"] * p[:, 0] + bareme["nul"] * p[:, 1]
        xe = bareme["victoire"] * p[:, 2] + bareme["nul"] * p[:, 1]
        for e in equipes_cur:
            attendu[e]["points_modele"] = float(xd[(pc["dom"] == e).to_numpy()].sum() + xe[(pc["ext"] == e).to_numpy()].sum())
    for a in attendu.values():
        a["ecart_io"] = a["points"] - a["points_io"] if a["points_io"] is not None else None
        a["ecart_marche"] = a["points"] - a["points_marche"] if a["points_marche"] is not None else None
        a["ecart_modele"] = a["points"] - a["points_modele"]

    # ---------- Calendrier restant ----------
    H = elo_mod.ParamsElo().avantage_domicile
    difficulte = {}
    for e in equipes_cur:
        lignes = []
        for r in a_venir[(a_venir["dom"] == e) | (a_venir["ext"] == e)].itertuples():
            dom = r.dom == e
            adv = r.ext if dom else r.dom
            pr = prev_par_id.get(r.match_id)
            pts_att = None
            if pr:
                pts_att = bareme["victoire"] * pr["p"][0 if dom else 2] + bareme["nul"] * pr["p"][1]
            lignes.append({"match_id": r.match_id, "date": r.date, "journee": _num(r.journee), "adversaire": adv,
                           "lieu": "domicile" if dom else "exterieur",
                           "elo_adversaire_ajuste": notes[adv] + (-H / 2 if dom else H / 2),
                           "points_attendus": pts_att, "p": pr["p"] if pr else None})
        difficulte[e] = {"matchs": lignes,
                         "indice": float(np.mean([l["elo_adversaire_ajuste"] for l in lignes])) if lignes else None,
                         "points_attendus": float(sum(l["points_attendus"] or 0 for l in lignes))}
    avec = sorted([e for e in equipes_cur if difficulte[e]["indice"] is not None],
                  key=lambda e: -difficulte[e]["indice"])
    for rang, e in enumerate(avec, 1):
        difficulte[e]["rang"] = rang  # 1 = calendrier le plus difficile

    # ---------- Journal (prédictions « en direct ») ----------
    journal = journal or []
    retenues = journal_mod.retenues(journal)

    # ---------- Matchs de la saison ----------
    def prediction_match(mid: str):
        # Match à venir : prévision du jour. Match joué : prédiction du journal si elle existe, sinon rétro-prédiction.
        if mid in retenues and mid not in prev_par_id:
            e = retenues[mid]
            return {"type": "direct", "horodatage": e["horodatage"], "modele": e["modele"], "p": e["p"],
                    "scores": e.get("scores", [])}
        if mid in prev_par_id:
            p = prev_par_id[mid]
            return {"type": "prevision", "modele": p["modele"], "p": p["p"], "scores": p["scores"],
                    "lambda": p["lambda"], "p_elo": p["p_elo"], "p_dixon_coles": p["p_dixon_coles"]}
        if mid in pred_cur.index and principal:
            r = pred_cur.loc[mid]
            m = dc.matrice_scores(r["lambda_dom"], r["lambda_ext"], modele_dc.rho)
            return {"type": "retro", "modele": principal,
                    "p": [float(r[f"p_{principal}_{i}"]) for i in mt.ISSUES],
                    "scores": dc.scores_probables(m, 3)}
        return None

    def h2h(dom: str, ext: str) -> dict:
        x = v_all[(v_all["equipe"] == dom) & (v_all["adversaire"] == ext)].sort_values("date")
        x = x[x["date"] < cur["date"].min()] if len(cur) else x
        return {"j": int(len(x)), "v_dom": int((x["resultat"] == "V").sum()), "n": int((x["resultat"] == "N").sum()),
                "v_ext": int((x["resultat"] == "D").sum()),
                "derniers": [{"match_id": m, "saison": sa, "date": d, "dom": dom if l == "domicile" else ext,
                              "ext": ext if l == "domicile" else dom,
                              "score": f"{int(bp)}-{int(bc)}" if l == "domicile" else f"{int(bc)}-{int(bp)}"}
                             for m, sa, d, l, bp, bc in zip(x["match_id"], x["saison"], x["date"], x["lieu"],
                                                            x["bp"], x["bc"])][-6:][::-1]}

    liste_matchs = []
    for r in cur.sort_values(["date", "match_id"]).itertuples():
        stats = None
        if enrichi and r.statut == "joue" and not pd.isna(r.tirs_dom):
            stats = {k: [_num(getattr(r, f"{k}_dom")), _num(getattr(r, f"{k}_ext"))]
                     for k in ("tirs", "cadres", "corners", "fautes", "jaunes", "rouges")}
            if modele_io is not None:
                stats["io"] = [float(modele_io.io([r.tirs_dom], [r.cadres_dom])[0]),
                               float(modele_io.io([r.tirs_ext], [r.cadres_ext])[0])]
        cote = None
        if enrichi and not pd.isna(r.cote_dom):
            cote = {"cotes": [r.cote_dom, r.cote_nul, r.cote_ext],
                    "p": mt.probas_cotes([r.cote_dom], [r.cote_nul], [r.cote_ext])[0].tolist()}
        liste_matchs.append({
            "id": r.match_id, "journee": _num(r.journee), "date": r.date, "heure": r.heure or None,
            "dom": r.dom, "ext": r.ext, "statut": r.statut,
            "score": [int(r.buts_dom), int(r.buts_ext)] if r.statut == "joue" else None,
            "mi_temps": [int(r.mt_dom), int(r.mt_ext)] if r.statut == "joue" and not pd.isna(r.mt_dom) else None,
            "stats": stats, "marche": cote, "prediction": prediction_match(r.match_id),
            "confrontations": h2h(r.dom, r.ext), "source": r.source,
        })

    # ---------- Journée courante et accueil ----------
    journee_courante = int(a_venir["journee"].min()) if len(a_venir) and a_venir["journee"].notna().any() else None
    derniere_journee = int(joues_cur["journee"].max()) if len(joues_cur) and joues_cur["journee"].notna().any() else None
    temps_forts = _temps_forts(table, v_cur, simulation, attendu, cur, ref, bareme, enrichi)

    # ---------- Équipes ----------
    classements = hist.classements_saisons(matchs, comp)
    evolution = hist.evolution_par_equipe(classements)
    long_elo = pd.concat([
        hist_elo[["saison", "dom", "elo_dom_apres", "date"]].set_axis(["saison", "equipe", "elo", "date"], axis=1),
        hist_elo[["saison", "ext", "elo_ext_apres", "date"]].set_axis(["saison", "equipe", "elo", "date"], axis=1)])
    elo_fin_saison = long_elo.sort_values("date").groupby(["saison", "equipe"])["elo"].last()
    fichiers_equipes = {}
    toutes = sorted(set(matchs["dom"]) | set(matchs["ext"]))
    for e in toutes:
        ve = v_all[v_all["equipe"] == e].sort_values("date")
        par_saison = []
        for sa, g in ve.groupby("saison"):
            st = stats_saison(g, comp.format_saison(sa)["points"])
            rang = next((x["rang"] for x in evolution.get(e, []) if x["saison"] == sa), None)
            par_saison.append({"saison": sa, "rang": rang, **st})
        d = {
            "id": e, "nom": ref.nom(e), "court": ref.court(e), "en_cours": e in equipes_cur,
            "evolution": evolution.get(e, []),
            "elo_fin_saison": [{"saison": sa, "elo": float(v)} for sa, v in elo_fin_saison.xs(e, level=1).items()]
            if e in elo_fin_saison.index.get_level_values(1) else [],
            "stats_par_saison": par_saison,
            "series_toutes_saisons": series(list(ve["resultat"]))["record"],
            "confrontations": hist.confrontations(matchs, e),
            "titres": [p["saison"] for p in hist.palmares(classements, s) if p["champion"] == e],
        }
        if e in equipes_cur:
            vc = v_cur[v_cur["equipe"] == e].sort_values("date")
            ligne = table.set_index("equipe").loc[e]
            elo_saison = hist_elo[(hist_elo["saison"] == s) & ((hist_elo["dom"] == e) | (hist_elo["ext"] == e))]
            d["saison_courante"] = {
                "saison": s, "rang": int(ligne["rang"]), "zone": ligne["zone"],
                "stats": stats_saison(vc, bareme) if len(vc) else None,
                "forme": forme(vc, bareme), "series": series(list(vc["resultat"])),
                "elo": float(notes[e]),
                "elo_rang": int(sorted(equipes_cur, key=lambda x: -notes[x]).index(e) + 1),
                "elo_historique": [{"date": r.date, "elo": float(r.elo_dom_apres if r.dom == e else r.elo_ext_apres)}
                                   for r in elo_saison.itertuples()],
                "calendrier_restant": difficulte[e],
                "simulation": sim_par_eq.get(e),
                "attendu": attendu[e],
                "matchs": [m["id"] for m in liste_matchs if e in (m["dom"], m["ext"])],
            }
            if modele_io is not None and len(vc.dropna(subset=["tirs"])):
                x = vc.dropna(subset=["tirs", "cadres", "tirs_contre", "cadres_contre"])
                d["saison_courante"]["io"] = {
                    "pour_par_match": float(modele_io.io(x["tirs"], x["cadres"]).mean()),
                    "contre_par_match": float(modele_io.io(x["tirs_contre"], x["cadres_contre"]).mean())}
        fichiers_equipes[f"equipes/{e}.json"] = d

    # ---------- Classement (avec forme, Elo, IO, simulation) ----------
    lignes = []
    for r in table.itertuples():
        eq = fichiers_equipes[f"equipes/{r.equipe}.json"]["saison_courante"]
        lignes.append({"rang": r.rang, "equipe": r.equipe, "j": r.j, "g": r.g, "n": r.n, "p": r.p, "bp": r.bp,
                       "bc": r.bc, "diff": r.diff, "pts": r.pts, "penalite": r.penalite, "zone": r.zone,
                       "forme": [x["resultat"] for x in eq["forme"]["derniers"]], "elo": eq["elo"],
                       "io": eq.get("io"), "points_attendus_fin": sim_par_eq[r.equipe]["points_attendus"]})

    # ---------- Comparateur (vecteur compact par équipe) ----------
    comparateur = []
    for e in equipes_cur:
        sc = fichiers_equipes[f"equipes/{e}.json"]["saison_courante"]
        st = sc["stats"] or {}
        g = st.get("general", {})
        j = max(g.get("j", 0), 1)
        comparateur.append({
            "equipe": e, "rang": sc["rang"], "pts": g.get("pts"), "ppm": (g.get("pts") or 0) / j,
            "bp_pm": (g.get("bp") or 0) / j, "bc_pm": (g.get("bc") or 0) / j,
            "dom": st.get("domicile"), "ext": st.get("exterieur"),
            "tirs": st.get("tirs"), "corners": st.get("corners"), "discipline": st.get("discipline"),
            "mi_temps": st.get("mi_temps"), "io": sc.get("io"), "elo": sc["elo"],
            "forme5": sc["forme"]["points_5_derniers"], "clean_sheets": st.get("clean_sheets"),
            "titre": sc["simulation"]["titre"] if sc["simulation"] else None,
        })

    # ---------- Historique ----------
    historique = {
        "saisons": [{"saison": sa, "equipes": int(len(t)), "terminee": sa != s,
                     "note": comp.format_saison(sa).get("note"),
                     "bareme_victoire": comp.format_saison(sa)["points"]["victoire"],
                     "classement": t[["rang", "equipe", "j", "g", "n", "p", "bp", "bc", "diff", "pts"]].to_dict("records")}
                    for sa, t in sorted(classements.items())],
        "all_time": hist.all_time(matchs).to_dict("records"),
        "palmares": hist.palmares(classements, s),
        "records": {**hist.plus_gros_scores(matchs), "series": hist.series_records(matchs),
                    "saison": hist.records_saison(classements, s)},
    }

    # ---------- Cotes ----------
    cotes = None
    if enrichi:
        cotes = {"surprises_saison": cotes_mod.surprises(cur, 10),
                 "surprises_historiques": cotes_mod.surprises(matchs, 20),
                 "equipes": cotes_mod.equipes_vs_marche(cur, bareme),
                 "favoris_par_saison": cotes_mod.bilan_favoris(matchs)}

    # ---------- Backtest / méthodologie ----------
    eval_cur = bt.evaluer(pred[pred["saison"] == s]) if (pred["saison"] == s).sum() > 20 else None
    backtest = {
        "periode": [saisons_test[0], [x for x in saisons_test if x != s][-1]],
        "global": evaluation["global"], "par_saison": evaluation["par_saison"],
        "validation": evaluation["validation"], "calibration": evaluation["calibration"],
        "modele_principal": principal, "saison_en_cours": eval_cur["global"] if eval_cur else None,
        "simulation": bt_sim,
        "indice_occasions": {"coef_cadre": modele_io.coef_cadre, "coef_non_cadre": modele_io.coef_non_cadre,
                             "saisons": [saisons_app[0], saisons_app[-1]], "validation": io_validation}
        if modele_io else None,
        "parametres": {"elo": vars(elo_mod.ParamsElo()), "dixon_coles": vars(dc.ParamsDC()),
                       "dixon_coles_courant": {"domicile": modele_dc.gamma, "rho": modele_dc.rho, "mu": modele_dc.mu}},
    }

    # ---------- Méta ----------
    equipes_meta = {e: {"nom": ref.nom(e), "court": ref.court(e)} for e in toutes}
    meta = {
        "competition": {"id": comp.id, "nom": comp.nom, "slug": comp.slug, "pays": comp.pays},
        "saison": s, "mis_a_jour": maintenant.isoformat(timespec="minutes"),
        "derniere_date_match": derniere_date, "journee_courante": journee_courante,
        "derniere_journee": derniere_journee, "enrichissements": enrichi,
        "zones": fmt.get("zones", []), "note_format": fmt.get("note"), "bareme": bareme,
        "sources": SOURCES, "equipes": equipes_meta, "equipes_saison": equipes_cur,
        "modele_principal": principal,
        "qualite": {**rapport, "alertes_ingestion": alertes},
    }
    accueil = {"journee_courante": journee_courante, "derniere_journee": derniere_journee,
               "matchs_journee": [m["id"] for m in liste_matchs if journee_courante and m["journee"] == journee_courante],
               "derniers_resultats": [m["id"] for m in liste_matchs
                                      if derniere_journee and m["journee"] == derniere_journee and m["statut"] == "joue"],
               "temps_forts": temps_forts}

    fichiers = {"meta.json": meta, "classement.json": {"saison": s, "lignes": lignes, "attendu": sorted(
        attendu.values(), key=lambda a: -a["points"])}, "simulation.json": simulation, "matchs.json": liste_matchs,
        "accueil.json": accueil, "historique.json": historique, "backtest.json": backtest,
        "comparateur.json": comparateur, "evolution.json": evolution_par_journee(cur, fmt), "predictions.json": journal_mod.evaluer(journal, matchs),
        **fichiers_equipes}
    if cotes is not None:
        fichiers["cotes.json"] = cotes
    return Sortie(fichiers={k: propre(v) for k, v in fichiers.items()}, previsions=previsions)


def _fr(x: float, signe: bool = False) -> str:
    """Nombre à une décimale au format français (virgule, vrai signe moins)."""
    s = f"{x:+.1f}" if signe else f"{x:.1f}"
    return s.replace(".", ",").replace("-", "−")


def _temps_forts(table, v_cur, simulation, attendu, cur, ref, bareme, enrichi) -> list[dict]:
    tf = []
    sim = sorted(simulation["equipes"], key=lambda e: -e["titre"])
    if sim and sim[0]["titre"] > 0:
        tf.append({"type": "titre", "equipe": sim[0]["equipe"],
                   "texte": f"{ref.court(sim[0]['equipe'])} : {sim[0]['titre'] * 100:.0f} % de chances de titre selon nos simulations."})
    risque = sorted(simulation["equipes"], key=lambda e: -e["zones"].get("relegation", 0))
    if risque and risque[0]["zones"].get("relegation", 0) > 0:
        e = risque[0]
        tf.append({"type": "relegation", "equipe": e["equipe"],
                   "texte": f"{ref.court(e['equipe'])} : {e['zones']['relegation'] * 100:.0f} % de risque de relégation directe."})
    meilleure = None
    for e, g in v_cur.sort_values("date").groupby("equipe"):
        s = series(list(g["resultat"]))["en_cours"]
        for k, lib in (("invincibilite", "sans défaite"), ("victoires", "victoires de suite"), ("sans_victoire", "sans victoire")):
            if s[k] >= 4 and (meilleure is None or s[k] > meilleure[1]):
                meilleure = (e, s[k], lib)
    if meilleure:
        tf.append({"type": "serie", "equipe": meilleure[0],
                   "texte": f"{ref.court(meilleure[0])} : {meilleure[1]} matchs {meilleure[2]} en championnat."})
    io = [a for a in attendu.values() if a.get("ecart_io") is not None]
    if io:
        sur = max(io, key=lambda a: a["ecart_io"])
        sous = min(io, key=lambda a: a["ecart_io"])
    if io and sur["ecart_io"] > 0 and sous["ecart_io"] < 0:
        tf.append({"type": "surperformance", "equipe": sur["equipe"],
                   "texte": f"{ref.court(sur['equipe'])} compte {_fr(sur['ecart_io'])} points de plus que ce que valent ses occasions."})
        tf.append({"type": "sousperformance", "equipe": sous["equipe"],
                   "texte": f"{ref.court(sous['equipe'])} compte {_fr(-sous['ecart_io'])} points de moins que ce que valent ses occasions."})
    if enrichi:
        sp = cotes_mod.surprises(cur, 1)
        if sp:
            x = sp[0]
            tf.append({"type": "surprise", "match_id": x["match_id"],
                       "texte": f"Plus grosse surprise de la saison : {ref.court(x['dom'])} {x['score']} {ref.court(x['ext'])} "
                                f"(résultat donné à {x['proba_marche'] * 100:.0f} % par les bookmakers)."})
    return tf


def ecrire(cid: str, fichiers: dict[str, object], dossier: Path = DOSSIER_EXPORT) -> Path:
    """Écrit dans un dossier temporaire puis remplace l'export de la compétition d'un bloc."""
    cible = dossier / cid
    tmp = dossier / f".tmp-{cid}"
    if tmp.exists():
        shutil.rmtree(tmp)
    for nom, contenu in fichiers.items():
        p = tmp / nom
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(contenu, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    ancien = dossier / f".ancien-{cid}"
    if ancien.exists():
        shutil.rmtree(ancien)
    if cible.exists():
        cible.rename(ancien)
    tmp.rename(cible)
    if ancien.exists():
        shutil.rmtree(ancien)
    return cible
