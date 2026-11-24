"""Ingestion : sources brutes -> table canonique des matchs d'une compétition.

Rien n'est écrit sur disque ici. On renvoie la table et les octets bruts téléchargés ;
`stockage.promouvoir` ne les écrit qu'après passage des contrôles qualité.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from .config import DOSSIER_DONNEES, Competition, charger_referentiel, saison_vers_code
from .referentiel import Referentiel
from .sources import footballdata_couk as fd
from .sources import openfootball as of
from .telechargement import ErreurSource, telecharger

COLONNES_STATS = list(fd.COLONNES_STATS.values())
COLONNES_COTES = ["cote_dom", "cote_nul", "cote_ext", "cote_clot_dom", "cote_clot_nul", "cote_clot_ext"]
COLONNES = (["match_id", "competition", "saison", "journee", "date", "heure", "dom", "ext", "statut",
             "buts_dom", "buts_ext", "mt_dom", "mt_ext"] + COLONNES_STATS + COLONNES_COTES
            + ["nb_bookmakers", "source"])


class ErreurIngestion(RuntimeError):
    pass


@dataclass
class ResultatIngestion:
    matchs: pd.DataFrame
    bruts: dict[Path, bytes] = field(default_factory=dict)  # fichiers bruts à écrire si validé
    alertes: list[str] = field(default_factory=list)
    diagnostics: dict = field(default_factory=dict)
    calendrier_openfootball: pd.DataFrame | None = None


def chemin_brut(comp: Competition, source: str, nom: str, racine: Path = DOSSIER_DONNEES) -> Path:
    return racine / "brut" / comp.id / source / nom


def identifiant_match(competition: str, saison: str, dom: str, ext: str) -> str:
    # Unique dans un championnat aller-retour ; lisible et stable (sert d'URL).
    return f"{saison_vers_code(saison)}-{dom}-{ext}"


def _obtenir(url: str, chemin: Path, toujours_telecharger: bool, hors_ligne: bool,
             res: ResultatIngestion) -> bytes | None:
    if chemin.exists() and (hors_ligne or not toujours_telecharger):
        return chemin.read_bytes()
    if hors_ligne:
        return None
    try:
        contenu = telecharger(url)
        time.sleep(0.3)  # politesse envers la source
        if not chemin.exists() or chemin.read_bytes() != contenu:
            res.bruts[chemin] = contenu
        return contenu
    except ErreurSource as e:
        if chemin.exists():
            res.alertes.append(f"Source indisponible ({e}) : on réutilise la dernière copie valide.")
            return chemin.read_bytes()
        raise


def ingerer(comp: Competition, hors_ligne: bool = False, racine: Path = DOSSIER_DONNEES,
            saisons: list[str] | None = None) -> ResultatIngestion:
    ref = Referentiel(charger_referentiel(comp.referentiel_equipes))
    res = ResultatIngestion(matchs=pd.DataFrame())
    saisons = saisons or comp.saisons
    blocs, inconnus = [], set()
    div = comp.sources["football_data_couk"]["division"]

    # 1) football-data.co.uk : une saison = un fichier. Les saisons passées sont figées.
    for s in saisons:
        chemin = chemin_brut(comp, "football-data-couk", f"{div}_{saison_vers_code(s)}.csv", racine)
        contenu = _obtenir(fd.url_saison(div, s), chemin, s == comp.saison_courante, hors_ligne, res)
        if contenu is None:
            res.alertes.append(f"Saison {s} : aucune donnée football-data disponible.")
            continue
        brut, diag = fd.lire_csv_tolerant(contenu)
        res.diagnostics[s] = {k: v for k, v in diag.items() if k != "colonnes"}
        df = fd.normaliser(brut, comp.id, s)
        df["dom"], i1 = ref.mapper(df["dom_brut"])
        df["ext"], i2 = ref.mapper(df["ext_brut"])
        inconnus |= set(i1) | set(i2)
        df["source"] = "football-data.co.uk"
        blocs.append(df)
    if inconnus:
        raise ErreurIngestion("Équipes inconnues du référentiel (à ajouter dans config/equipes) : "
                              + ", ".join(sorted(inconnus)))
    matchs = pd.concat(blocs, ignore_index=True) if blocs else pd.DataFrame()
    matchs["statut"] = np.where(matchs["buts_dom"].notna() & matchs["buts_ext"].notna(), "joue", "a_venir")
    matchs["journee"] = np.nan
    matchs["heure"] = ""

    # 2) openfootball : calendrier complet de la saison en cours.
    s = comp.saison_courante
    if s in saisons and "openfootball" in comp.sources:
        code = comp.sources["openfootball"]["code"]
        chemin = chemin_brut(comp, "openfootball", f"{code}_{s}.json", racine)
        try:
            contenu = _obtenir(of.url_saison(code, s), chemin, True, hors_ligne, res)
        except ErreurSource as e:
            contenu = None
            res.alertes.append(f"Calendrier openfootball indisponible : {e}")
        if contenu is not None:
            cal = of.normaliser(contenu, comp.id, s)
            cal["dom"], i1 = ref.mapper(cal["dom_brut"])
            cal["ext"], i2 = ref.mapper(cal["ext_brut"])
            if i1 or i2:
                raise ErreurIngestion("Équipes openfootball inconnues : " + ", ".join(sorted(set(i1) | set(i2))))
            res.calendrier_openfootball = cal
            matchs = _fusionner_calendrier(matchs, cal, s, res)

    # 3) Cotes des prochains matchs (fixtures.csv de football-data, quelques jours à l'avance).
    if comp.enrichissements and s in saisons and not hors_ligne:
        try:
            brut, _ = fd.lire_csv_tolerant(telecharger(fd.URL_PROCHAINS))
            brut = brut[brut.get("Div", pd.Series(dtype=str)) == div]
            if len(brut):
                prochains = fd.normaliser(brut.reset_index(drop=True), comp.id, s)
                prochains["dom"], _i1 = ref.mapper(prochains["dom_brut"])
                prochains["ext"], _i2 = ref.mapper(prochains["ext_brut"])
                matchs = _ajouter_cotes_prochains(matchs, prochains.dropna(subset=["dom", "ext"]), s)
        except Exception as e:  # source annexe : jamais bloquante
            res.alertes.append(f"Cotes des prochains matchs indisponibles : {e}")

    matchs["match_id"] = [identifiant_match(comp.id, sa, d, e)
                          for sa, d, e in zip(matchs["saison"], matchs["dom"], matchs["ext"])]
    matchs["date"] = pd.to_datetime(matchs["date"]).dt.normalize()
    for c in COLONNES:
        if c not in matchs.columns:
            matchs[c] = np.nan
    res.matchs = matchs[COLONNES].sort_values(["date", "match_id"]).reset_index(drop=True)
    return res


def _ajouter_cotes_prochains(matchs: pd.DataFrame, prochains: pd.DataFrame, saison: str) -> pd.DataFrame:
    cols = ["cote_dom", "cote_nul", "cote_ext", "nb_bookmakers"]
    cotes = prochains.set_index(["dom", "ext"])[cols]
    cotes = cotes[~cotes.index.duplicated()]
    for i in matchs.index[(matchs["saison"] == saison) & (matchs["statut"] == "a_venir")]:
        cle = (matchs.at[i, "dom"], matchs.at[i, "ext"])
        if cle in cotes.index:
            for c in cols:
                matchs.at[i, c] = cotes.at[cle, c]
    return matchs


def _fusionner_calendrier(matchs: pd.DataFrame, cal: pd.DataFrame, saison: str,
                          res: ResultatIngestion) -> pd.DataFrame:
    """Ajoute journée + heure locale aux matchs joués, et les matchs à venir absents de football-data."""
    cle = ["dom", "ext"]
    courant = matchs["saison"] == saison
    m = matchs[courant].merge(cal[cle + ["journee", "heure_locale", "date"]].rename(
        columns={"date": "date_of"}), on=cle, how="left")
    m["journee"] = m["journee_y"] if "journee_y" in m.columns else m["journee"]
    m["heure"] = m["heure_locale"].fillna("")
    m = m.drop(columns=[c for c in m.columns if c.endswith("_x") or c.endswith("_y")
                        or c in ("heure_locale", "date_of")])
    connus = set(zip(m["dom"], m["ext"]))
    absents = cal[[(d, e) not in connus for d, e in zip(cal["dom"], cal["ext"])]].copy()
    if len(absents):
        joues_of = absents["buts_dom"].notna()
        if joues_of.any():
            res.alertes.append(f"{int(joues_of.sum())} match(s) joué(s) selon openfootball mais absents de "
                               "football-data : score openfootball utilisé.")
        absents["statut"] = np.where(joues_of, "joue", "a_venir")
        absents["source"] = np.where(joues_of, "openfootball", "openfootball (calendrier)")
        absents["heure"] = absents["heure_locale"]
        absents = absents.drop(columns=["heure_locale", "dom_brut", "ext_brut"])
    autres = matchs[~courant]
    return pd.concat([autres, m, absents], ignore_index=True)
