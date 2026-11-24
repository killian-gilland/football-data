import json

import numpy as np
import pandas as pd

from pipeline.config import charger_referentiel
from pipeline.ingestion import ResultatIngestion, _completer_avec_org
from pipeline.referentiel import Referentiel
from pipeline.sources import footballdata_org as fdo

REPONSE = {"matches": [
    {"utcDate": "2026-11-27T19:45:00Z", "status": "FINISHED", "matchday": 12,
     "homeTeam": {"name": "Stade Brestois 29", "shortName": "Brest", "tla": "SB2"},
     "awayTeam": {"name": "Paris FC", "shortName": "Paris FC", "tla": "PFC"},
     "score": {"fullTime": {"home": 2, "away": 1}, "halfTime": {"home": 1, "away": 0}}},
    {"utcDate": "2026-11-28T16:15:00Z", "status": "IN_PLAY", "matchday": 12,
     "homeTeam": {"name": "Angers SCO", "shortName": "Angers", "tla": "ANG"},
     "awayTeam": {"name": "Racing Club de Lens", "shortName": "RC Lens", "tla": "RCL"},
     "score": {"fullTime": {"home": 0, "away": 0}, "halfTime": {"home": None, "away": None}}},
    {"utcDate": "2027-04-04T13:00:00Z", "status": "TIMED", "matchday": 28,
     "homeTeam": {"name": "Équipe Inconnue FC", "shortName": "Inconnue", "tla": "INC"},
     "awayTeam": {"name": "Paris Saint-Germain FC", "shortName": "PSG", "tla": "PSG"},
     "score": {"fullTime": {"home": None, "away": None}, "halfTime": {"home": None, "away": None}}},
]}


def _org():
    ref = Referentiel(charger_referentiel("fr"))
    df = fdo.normaliser(json.dumps(REPONSE).encode(), "fr-ligue1", "2026-27")
    return fdo.identifier(df, ref)


def test_normalisation_heure_de_paris_et_statuts():
    df, _ = _org()
    assert df.loc[0, "heure_locale"] == "20:45"           # UTC+1 en novembre
    assert df.loc[2, "heure_locale"] == "15:00"           # UTC+2 en avril (heure d'été)
    assert str(df.loc[0, "date"].date()) == "2026-11-27"
    assert df["statut_source"].tolist() == ["termine", "en_cours", "a_venir"]
    assert df.loc[0, "mt_dom"] == 1 and np.isnan(df.loc[1, "mt_dom"])


def test_identification_par_nom_court_et_signalement_des_inconnus():
    df, inconnus = _org()
    assert df.loc[0, ["dom", "ext"]].tolist() == ["brest", "paris-fc"]
    assert df.loc[1, "ext"] == "lens"
    assert df.loc[2, "dom"] is None and df.loc[2, "ext"] == "psg"
    assert inconnus == ["Équipe Inconnue FC"]


def _table():
    base = {"competition": "fr-ligue1", "saison": "2026-27", "heure": "", "mt_dom": np.nan, "mt_ext": np.nan}
    return pd.DataFrame([
        {**base, "dom": "brest", "ext": "paris-fc", "journee": 12.0, "date": pd.Timestamp("2026-11-27"),
         "statut": "a_venir", "buts_dom": np.nan, "buts_ext": np.nan, "source": "openfootball (calendrier)"},
        {**base, "dom": "angers", "ext": "lens", "journee": 12.0, "date": pd.Timestamp("2026-11-29"),
         "statut": "a_venir", "buts_dom": np.nan, "buts_ext": np.nan, "source": "openfootball (calendrier)"},
        {**base, "dom": "lens", "ext": "angers", "journee": 30.0, "date": pd.Timestamp("2027-04-10"),
         "statut": "joue", "buts_dom": 3.0, "buts_ext": 0.0, "source": "football-data.co.uk"},
    ])


def test_resultat_du_soir_integre_et_horaire_mis_a_jour():
    org, _ = _org()
    res = ResultatIngestion(matchs=pd.DataFrame())
    m = _completer_avec_org(_table(), org.dropna(subset=["dom", "ext"]), "2026-27", res)
    brest = m[(m["dom"] == "brest")].iloc[0]
    assert brest["statut"] == "joue" and (brest["buts_dom"], brest["buts_ext"]) == (2, 1)
    assert brest["source"] == "football-data.org"
    angers = m[(m["dom"] == "angers")].iloc[0]
    assert angers["statut"] == "a_venir"                    # match en cours : pas encore un résultat
    assert str(angers["date"].date()) == "2026-11-28"       # reprogrammé : la date de l'API l'emporte
    assert any("1 résultat" in a for a in res.alertes)


def test_football_data_co_uk_reste_prioritaire():
    org, _ = _org()
    org = org.dropna(subset=["dom", "ext"]).copy()
    org.loc[0, ["dom", "ext"]] = ["lens", "angers"]           # même affiche qu'un match déjà publié
    m = _completer_avec_org(_table(), org, "2026-27", ResultatIngestion(matchs=pd.DataFrame()))
    lens = m[(m["dom"] == "lens")].iloc[0]
    assert (lens["buts_dom"], lens["buts_ext"]) == (3, 0) and lens["source"] == "football-data.co.uk"


def test_sans_jeton_la_source_est_ignoree(monkeypatch):
    monkeypatch.delenv(fdo.VARIABLE_JETON, raising=False)
    assert fdo.jeton() is None
