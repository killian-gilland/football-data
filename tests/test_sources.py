import json

import numpy as np

from pipeline.referentiel import Referentiel
from pipeline.sources import footballdata_couk as fd
from pipeline.sources import openfootball as of

CSV_ANCIEN = b"""Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR,,,
F1,23/07/93,Toulouse,Le Havre,1,0,H,,,
F1,24/07/93,Paris SG,Lyon,2,2,D,,,

"""

CSV_RECENT = b"""Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,FTR,HTHG,HTAG,HTR,HS,AS,HST,AST,B365H,B365D,B365A,PSH,PSD,PSA,MaxH,MaxD,MaxA,AvgH,AvgD,AvgA,B365CH,B365CD,B365CA
F1,21/08/2026,19:45,Marseille,Strasbourg,4,0,H,0,0,D,14,5,8,2,2.0,3.5,4.0,2.0,3.5,4.0,9.0,9.0,9.0,1.0,1.0,1.0,1.8,3.6,4.5
"""


def test_csv_ancien_format_date_court_et_colonnes_vides():
    df, diag = fd.lire_csv_tolerant(CSV_ANCIEN)
    assert diag["lignes"] == 2 and diag["lignes_vides_ignorees"] == 1
    n = fd.normaliser(df, "fr-ligue1", "1993-94")
    assert str(n["date"].iloc[0].date()) == "1993-07-23"
    # Colonnes absentes -> manquantes, jamais 0
    assert np.isnan(n["tirs_dom"]).all() and np.isnan(n["cote_dom"]).all()
    assert n["buts_dom"].tolist() == [1, 2]


def test_csv_recent_date_longue_et_cote_moyenne_sans_max_ni_avg():
    df, _ = fd.lire_csv_tolerant(CSV_RECENT)
    n = fd.normaliser(df, "fr-ligue1", "2026-27")
    assert str(n["date"].iloc[0].date()) == "2026-08-21"
    # Moyenne de B365 et PS uniquement (Max et Avg exclus) : cotes identiques -> 2.0
    assert abs(n["cote_dom"].iloc[0] - 2.0) < 1e-9
    assert n["nb_bookmakers"].iloc[0] == 2
    # La cote de clôture est séparée de l'avant-match
    assert abs(n["cote_clot_dom"].iloc[0] - 1.8) < 1e-9
    assert n["cadres_dom"].iloc[0] == 8


def test_ligne_plus_longue_que_l_entete_est_signalee():
    df, diag = fd.lire_csv_tolerant(b"Div,Date,HomeTeam,AwayTeam,FTHG,FTAG\nF1,01/09/20,A,B,1,0,EXTRA\n")
    assert diag["lignes_debordantes"] == 1 and len(df) == 1


def test_openfootball_deux_formats_de_score():
    data = {"matches": [
        {"round": "Matchday 1", "date": "2026-08-21", "team1": "A", "team2": "B", "score": {"ht": [0, 0], "ft": [2, 1]}},
        {"round": "Matchday 1", "date": "2026-08-22", "team1": "C", "team2": "D", "score": [0, 0]},
        {"round": "Matchday 34", "date": "2027-05-29", "team1": "B", "team2": "A"},
    ]}
    df = of.normaliser(json.dumps(data).encode(), "x", "2026-27")
    assert df["buts_dom"].tolist()[:2] == [2, 0]
    assert np.isnan(df["mt_dom"].iloc[1]) and np.isnan(df["buts_dom"].iloc[2])
    assert df["journee"].tolist() == [1, 1, 34]


def test_referentiel_insensible_casse_accents():
    ref = Referentiel({"saint-etienne": {"nom": "AS Saint-Étienne", "alias": ["St Etienne"]}})
    assert ref.identifiant("st etienne") == "saint-etienne"
    assert ref.identifiant("AS SAINT-ETIENNE") == "saint-etienne"
    assert ref.identifiant("Inconnu") is None


def test_referentiel_alias_ambigu_refuse():
    import pytest
    with pytest.raises(ValueError):
        Referentiel({"a": {"nom": "X", "alias": ["Paris"]}, "b": {"nom": "Y", "alias": ["Paris"]}})


def test_referentiel_reel_couvre_les_noms_connus():
    from pipeline.config import charger_referentiel
    ref = Referentiel(charger_referentiel("fr"))
    for nom in ["Paris SG", "Paris Saint-Germain FC", "Ajaccio GFCO", "Ajaccio", "ES Troyes AC", "Stade Rennais FC 1901"]:
        assert ref.identifiant(nom) is not None, nom
    assert ref.identifiant("Ajaccio") != ref.identifiant("Ajaccio GFCO")
