"""Contrôles qualité. Un contrôle « bloquant » en échec empêche toute publication :
la dernière version valide reste en place. Une « alerte » est signalée mais ne bloque pas."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np
import pandas as pd

from .config import Competition

BLOQUANT, ALERTE = "bloquant", "alerte"


@dataclass
class Controle:
    code: str
    niveau: str
    ok: bool
    detail: str = ""


@dataclass
class Rapport:
    controles: list[Controle] = field(default_factory=list)

    def ajouter(self, code: str, niveau: str, ok: bool, detail: str = "") -> None:
        self.controles.append(Controle(code, niveau, bool(ok), detail))

    @property
    def bloquants_en_echec(self) -> list[Controle]:
        return [c for c in self.controles if c.niveau == BLOQUANT and not c.ok]

    @property
    def valide(self) -> bool:
        return not self.bloquants_en_echec

    def en_dict(self) -> dict:
        return {"valide": self.valide, "controles": [asdict(c) for c in self.controles]}

    def resume(self) -> str:
        lignes = []
        for c in self.controles:
            etat = "OK " if c.ok else ("ÉCHEC" if c.niveau == BLOQUANT else "ALERTE")
            lignes.append(f"[{etat:6}] {c.code}" + (f" — {c.detail}" if c.detail and not c.ok else ""))
        return "\n".join(lignes)


class ErreurQualite(RuntimeError):
    def __init__(self, rapport: Rapport):
        self.rapport = rapport
        super().__init__("Contrôles bloquants en échec :\n" + "\n".join(
            f"- {c.code} : {c.detail}" for c in rapport.bloquants_en_echec))


def _exemples(df: pd.DataFrame, n: int = 3) -> str:
    return ", ".join(df["match_id"].head(n).astype(str))


def controler(matchs: pd.DataFrame, comp: Competition, precedent: pd.DataFrame | None = None) -> Rapport:
    r = Rapport()
    joues = matchs[matchs["statut"] == "joue"]

    # Structure
    doublons = matchs[matchs["match_id"].duplicated(keep=False)]
    r.ajouter("identifiants_uniques", BLOQUANT, doublons.empty, f"doublons : {_exemples(doublons)}")
    r.ajouter("equipes_renseignees", BLOQUANT, matchs[["dom", "ext"]].notna().all().all())
    r.ajouter("pas_d_auto_match", BLOQUANT, (matchs["dom"] != matchs["ext"]).all())
    r.ajouter("dates_valides", BLOQUANT, matchs["date"].notna().all(),
              f"{int(matchs['date'].isna().sum())} date(s) manquante(s)")

    # Dates dans la fenêtre de la saison (1er juillet -> 31 juillet suivant)
    debut = pd.to_datetime(matchs["saison"].str[:4] + "-07-01")
    fin = pd.to_datetime((matchs["saison"].str[:4].astype(int) + 1).astype(str) + "-07-31")
    hors = matchs[(matchs["date"] < debut) | (matchs["date"] > fin)]
    r.ajouter("dates_dans_la_saison", BLOQUANT, hors.empty, f"hors fenêtre : {_exemples(hors)}")

    # Scores cohérents
    for c in ("buts_dom", "buts_ext"):
        v = joues[c]
        r.ajouter(f"{c}_entiers_positifs", BLOQUANT, ((v >= 0) & (v == v.round()) & (v < 20)).all())
    mt = joues.dropna(subset=["mt_dom", "mt_ext"])
    incoh = mt[(mt["mt_dom"] > mt["buts_dom"]) | (mt["mt_ext"] > mt["buts_ext"])]
    r.ajouter("mi_temps_inferieure_au_final", BLOQUANT, incoh.empty, f"incohérents : {_exemples(incoh)}")

    # Statistiques de match
    for cote in ("dom", "ext"):
        st = joues.dropna(subset=[f"tirs_{cote}", f"cadres_{cote}"])
        incoh = st[st[f"cadres_{cote}"] > st[f"tirs_{cote}"]]
        r.ajouter(f"cadres_inferieurs_aux_tirs_{cote}", ALERTE, incoh.empty, f"{len(incoh)} cas : {_exemples(incoh)}")
        st = joues.dropna(subset=[f"cadres_{cote}"])
        incoh = st[st[f"buts_{cote}"] > st[f"cadres_{cote}"] + 3]  # CSC possibles, mais pas en masse
        r.ajouter(f"buts_plausibles_vs_cadres_{cote}", ALERTE, len(incoh) <= 5, f"{len(incoh)} cas : {_exemples(incoh)}")
    rouges = joues[["rouges_dom", "rouges_ext"]].max(axis=1)
    r.ajouter("cartons_rouges_plausibles", ALERTE, (rouges.fillna(0) <= 5).all())

    # Cotes
    co = joues.dropna(subset=["cote_dom", "cote_nul", "cote_ext"])
    if len(co):
        marge = 1 / co["cote_dom"] + 1 / co["cote_nul"] + 1 / co["cote_ext"]
        anormal = co[(marge < 0.97) | (marge > 1.35) | (co[["cote_dom", "cote_nul", "cote_ext"]] <= 1).any(axis=1)]
        r.ajouter("cotes_plausibles", ALERTE, len(anormal) <= 0.005 * len(co) + 1,
                  f"{len(anormal)} match(s) à marge anormale : {_exemples(anormal)}")

    # Format de chaque saison
    for saison, g in matchs.groupby("saison"):
        fmt = comp.format_saison(saison)
        equipes = sorted(set(g["dom"]) | set(g["ext"]))
        n = len(equipes)
        attendu = fmt.get("equipes")
        ok_n = (n == attendu) if attendu else n in (18, 20)
        r.ajouter(f"nombre_equipes_{saison}", BLOQUANT if saison == comp.saison_courante else ALERTE,
                  ok_n, f"{n} équipes (attendu {attendu or '18 ou 20'})")
        paires = g.groupby(["dom", "ext"]).size()
        r.ajouter(f"aller_retour_unique_{saison}", BLOQUANT, (paires <= 1).all(), "une affiche apparaît deux fois")
        complet = len(g) == n * (n - 1)
        if saison == comp.saison_courante:
            r.ajouter(f"calendrier_complet_{saison}", ALERTE, complet,
                      f"{len(g)} matchs connus sur {n * (n - 1)} (calendrier incomplet : simulation impossible)")
        elif saison != "2019-20":  # saison arrêtée, connue et documentée
            r.ajouter(f"saison_complete_{saison}", ALERTE, complet, f"{len(g)} matchs sur {n * (n - 1)}")

    # Écart de matchs joués dans la saison en cours (matchs reportés)
    cour = joues[joues["saison"] == comp.saison_courante]
    if len(cour):
        nb = pd.concat([cour["dom"], cour["ext"]]).value_counts()
        r.ajouter("ecart_matchs_joues", ALERTE, nb.max() - nb.min() <= 3,
                  f"de {nb.min()} à {nb.max()} matchs joués selon les équipes")

    # Non-régression par rapport à la dernière version valide
    if precedent is not None and len(precedent):
        p = precedent[precedent["statut"] == "joue"].set_index("match_id")
        n = joues.set_index("match_id")
        disparus = p.index.difference(n.index)
        r.ajouter("aucun_match_joue_disparu", BLOQUANT, len(disparus) == 0,
                  f"{len(disparus)} match(s) disparu(s) : {', '.join(disparus[:3])}")
        communs = p.index.intersection(n.index)
        modifies = [m for m in communs
                    if (p.at[m, "buts_dom"], p.at[m, "buts_ext"]) != (n.at[m, "buts_dom"], n.at[m, "buts_ext"])]
        r.ajouter("scores_inchanges", ALERTE, not modifies,
                  f"{len(modifies)} score(s) corrigé(s) par la source : {', '.join(modifies[:3])}")
    return r


def controle_croise(matchs: pd.DataFrame, calendrier: pd.DataFrame | None, rapport: Rapport) -> None:
    """Compare les scores football-data et openfootball quand les deux existent."""
    if calendrier is None or calendrier.empty:
        rapport.ajouter("croisement_openfootball", ALERTE, False, "calendrier openfootball absent")
        return
    fd = matchs[(matchs["source"] == "football-data.co.uk") & (matchs["statut"] == "joue")]
    m = fd.merge(calendrier.dropna(subset=["buts_dom"]), on=["saison", "dom", "ext"], suffixes=("", "_of"))
    desaccords = m[(m["buts_dom"] != m["buts_dom_of"]) | (m["buts_ext"] != m["buts_ext_of"])]
    rapport.ajouter("croisement_openfootball", ALERTE, desaccords.empty,
                    f"{len(desaccords)} score(s) en désaccord sur {len(m)} comparés : {_exemples(desaccords)}")
    ecart = (m["date"] - m["date_of"]).abs().dt.days if "date_of" in m.columns else pd.Series(dtype=float)
    if len(ecart):
        r = m[ecart > 2]
        rapport.ajouter("dates_coherentes_openfootball", ALERTE, r.empty, f"{len(r)} date(s) divergente(s)")


def matrice_disponibilite(matchs: pd.DataFrame) -> list[dict]:
    """Part des matchs joués disposant de chaque type de donnée, par saison."""
    joues = matchs[matchs["statut"] == "joue"]
    champs = {"mi_temps": "mt_dom", "tirs": "tirs_dom", "tirs_cadres": "cadres_dom", "corners": "corners_dom",
              "fautes": "fautes_dom", "cartons": "jaunes_dom", "cotes": "cote_dom", "cotes_cloture": "cote_clot_dom"}
    res = []
    for saison, g in joues.groupby("saison"):
        ligne = {"saison": saison, "matchs": int(len(g))}
        for nom, col in champs.items():
            ligne[nom] = round(float(g[col].notna().mean()), 3)
        res.append(ligne)
    return res


def controle_croise_org(matchs: pd.DataFrame, org: pd.DataFrame | None, rapport: Rapport) -> None:
    """Compare les scores football-data.co.uk et football-data.org quand les deux existent."""
    if org is None or org.empty:
        return
    fd = matchs[(matchs["source"] == "football-data.co.uk") & (matchs["statut"] == "joue")]
    o = org[org["statut_source"] == "termine"]
    m = fd.merge(o, on=["saison", "dom", "ext"], suffixes=("", "_org"))
    desaccords = m[(m["buts_dom"] != m["buts_dom_org"]) | (m["buts_ext"] != m["buts_ext_org"])]
    rapport.ajouter("croisement_football_data_org", ALERTE, desaccords.empty,
                    f"{len(desaccords)} score(s) en désaccord sur {len(m)} comparés : {_exemples(desaccords)}")
