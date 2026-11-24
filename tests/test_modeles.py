import numpy as np
import pandas as pd
import pytest

from pipeline.modeles import dixon_coles as dc
from pipeline.modeles import elo
from pipeline.modeles import metriques as mt
from tests.conftest import faire_saison


def test_rps_valeurs_connues():
    y = np.array([0])
    assert mt.rps(np.array([[1.0, 0, 0]]), y)[0] == 0
    # Tout sur l'extérieur alors que le domicile gagne : pire cas = 1
    assert mt.rps(np.array([[0, 0, 1.0]]), y)[0] == pytest.approx(1.0)
    # RPS punit moins une erreur « proche » (nul) qu'une erreur lointaine
    assert mt.rps(np.array([[0, 1.0, 0]]), y)[0] < mt.rps(np.array([[0, 0, 1.0]]), y)[0]


def test_log_loss_et_brier():
    p = np.array([[0.5, 0.3, 0.2]])
    assert mt.log_loss(p, np.array([0]))[0] == pytest.approx(-np.log(0.5))
    assert mt.brier(p, np.array([0]))[0] == pytest.approx(0.25 + 0.09 + 0.04)


def test_probas_cotes_retirent_la_marge():
    p = mt.probas_cotes([2.0], [3.0], [4.0])
    assert p.sum() == pytest.approx(1.0)
    assert p[0, 0] > p[0, 1] > p[0, 2]


def test_matrice_scores_normalisee_et_rho():
    m = dc.matrice_scores(1.4, 1.1, -0.1)
    assert m.sum() == pytest.approx(1.0)
    m0 = dc.matrice_scores(1.4, 1.1, 0.0)
    assert m[0, 0] > m0[0, 0]  # rho négatif : plus de 0-0


def _ligue_simulee(forces, saisons=3, graine=1):
    rng = np.random.default_rng(graine)
    blocs = []
    for k in range(saisons):
        s = f"{2020 + k}-{str(2021 + k)[2:]}"
        m = faire_saison(list(forces), saison=s, graine=graine + k)
        for i, r in m.iterrows():
            m.at[i, "buts_dom"] = rng.poisson(np.exp(0.1 + 0.25 + forces[r["dom"]][0] + forces[r["ext"]][1]))
            m.at[i, "buts_ext"] = rng.poisson(np.exp(0.1 + forces[r["ext"]][0] + forces[r["dom"]][1]))
        blocs.append(m)
    return pd.concat(blocs, ignore_index=True)


def test_dixon_coles_retrouve_l_ordre_des_forces_et_l_avantage_domicile():
    forces = {"fort": (0.5, -0.4), "moyen": (0.0, 0.0), "faible": (-0.5, 0.4), "moyen2": (0.05, 0.05)}
    m = _ligue_simulee(forces, saisons=3)
    mod = dc.ajuster(m, pd.Timestamp("2024-01-01"), list(forces), params=dc.ParamsDC(ridge=0.5))
    a = dict(zip(mod.equipes, mod.attaque))
    assert a["fort"] > a["moyen"] > a["faible"]
    assert 0.05 < mod.gamma < 0.5
    p = mod.predire_1n2(["fort"], ["faible"])[0]
    assert p[0] > 0.6 and p.sum() == pytest.approx(1.0)


def test_dixon_coles_sans_fuite_du_futur():
    """Modifier les matchs postérieurs à la date de référence ne doit rien changer."""
    forces = {"a": (0.3, -0.2), "b": (0.0, 0.0), "c": (-0.3, 0.2)}
    m = _ligue_simulee(forces, saisons=2)
    date_ref = pd.Timestamp("2021-10-01")
    m1 = dc.ajuster(m, date_ref, list(forces))
    m_alt = m.copy()
    futur = m_alt["date"] >= date_ref
    m_alt.loc[futur, "buts_dom"] = 9
    m2 = dc.ajuster(m_alt, date_ref, list(forces))
    np.testing.assert_allclose(m1.attaque, m2.attaque)
    assert m1.rho == m2.rho


def test_elo_somme_nulle_et_avantage_domicile():
    m = faire_saison(["a", "b", "c", "d"], scores={})
    hist, notes = elo.calculer(m)
    assert sum(notes.values()) == pytest.approx(4 * 1500)
    # Notes avant un match = notes après le match précédent de l'équipe (pas de fuite)
    premier = hist.iloc[0]
    assert premier["elo_dom_avant"] == 1500 and premier["elo_ext_avant"] == 1500


def test_elo_promus_recoivent_la_note_des_relegues():
    s1 = faire_saison(["a", "b", "c"], saison="2020-21", graine=3)
    s2 = faire_saison(["a", "b", "x"], saison="2021-22", graine=4)
    m = pd.concat([s1, s2], ignore_index=True)
    hist, _ = elo.calculer(m, elo.ParamsElo(regression=0.0))
    fin_c = hist[hist["saison"] == "2020-21"].apply(
        lambda r: r["elo_dom_apres"] if r["dom"] == "c" else (r["elo_ext_apres"] if r["ext"] == "c" else np.nan), axis=1).dropna().iloc[-1]
    debut_x = hist[(hist["saison"] == "2021-22") & ((hist["dom"] == "x") | (hist["ext"] == "x"))].iloc[0]
    note_x = debut_x["elo_dom_avant"] if debut_x["dom"] == "x" else debut_x["elo_ext_avant"]
    assert note_x == pytest.approx(fin_c)


def test_logit_ordonne_monotone():
    rng = np.random.default_rng(0)
    x = rng.normal(0, 150, 3000)
    lat = 0.006 * x + rng.logistic(size=3000)
    y = np.where(lat > 0.5, 0, np.where(lat > -0.4, 1, 2))
    lo = elo.LogitOrdonne().ajuster(x, y)
    p = lo.predire(np.array([-200, 0, 200]))
    assert np.all(np.diff(p[:, 0]) > 0) and np.all(np.diff(p[:, 2]) < 0)
    np.testing.assert_allclose(p.sum(axis=1), 1)
