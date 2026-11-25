import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from pipeline import export, predictions
from pipeline.modeles import dixon_coles as dc
from pipeline.simulation import simuler
from tests.conftest import faire_saison

FMT = {"points": {"victoire": 3, "nul": 1}, "departage": ["diff", "buts_pour"],
       "zones": [{"code": "titre", "positions": [1]}, {"code": "rel", "positions": [4]}]}


def _modele(equipes, attaque=None):
    n = len(equipes)
    return dc.ModeleDC(equipes=equipes, attaque=np.array(attaque or [0.0] * n), defense=np.zeros(n),
                       mu=0.2, gamma=0.2, rho=0.0)


def test_simulation_probabilites_coherentes():
    eq = ["a", "b", "c", "d"]
    m = faire_saison(eq, a_venir=6)
    res = simuler(m, _modele(eq, [0.6, 0.0, 0.0, -0.6]), FMT, n_sims=4000)
    pos = np.array([e["positions"] for e in res["equipes"]])
    np.testing.assert_allclose(pos.sum(axis=0), 1, atol=1e-9)  # chaque rang occupé une fois
    np.testing.assert_allclose(pos.sum(axis=1), 1, atol=1e-9)  # chaque équipe a un rang
    assert sum(e["titre"] for e in res["equipes"]) == pytest.approx(1)
    for e in res["equipes"]:
        assert e["points_attendus"] >= e["points_actuels"]


def test_simulation_saison_terminee_est_deterministe():
    eq = ["a", "b", "c", "d"]
    m = faire_saison(eq)
    res = simuler(m, _modele(eq), FMT, n_sims=500)
    assert res["matchs_restants"] == 0
    for e in res["equipes"]:
        assert max(e["positions"]) == pytest.approx(1.0)


def test_journal_ajout_seul_et_pas_de_prediction_le_jour_meme(tmp_path):
    t1 = datetime(2026, 11, 24, 6, 0, tzinfo=timezone.utc)
    prev = [{"match_id": "m1", "date": "2026-11-27", "modele": "x", "p": [0.5, 0.3, 0.2]},
            {"match_id": "m2", "date": "2026-11-24", "modele": "x", "p": [0.4, 0.3, 0.3]}]
    assert predictions.enregistrer("t", prev, t1, racine=tmp_path) == 1  # m2 est le jour même : refusé
    # Même prédiction : rien n'est ajouté
    assert predictions.enregistrer("t", prev, t1, racine=tmp_path) == 0
    # Nouvelle prédiction : ajoutée, l'ancienne reste
    prev[0]["p"] = [0.45, 0.3, 0.25]
    t2 = datetime(2026, 11, 25, 6, 0, tzinfo=timezone.utc)
    assert predictions.enregistrer("t", prev, t2, racine=tmp_path) == 1
    j = predictions.lire("t", racine=tmp_path)
    assert len(j) == 2 and j[0]["p"] == [0.5, 0.3, 0.2]
    assert predictions.retenues(j)["m1"]["p"] == [0.45, 0.3, 0.25]


def test_journal_ignore_une_prediction_horodatee_le_jour_du_match():
    j = [{"match_id": "m", "horodatage": "2026-11-26T06:00:00+00:00", "date_match": "2026-11-27", "p": [1, 0, 0]},
         {"match_id": "m", "horodatage": "2026-11-27T05:00:00+00:00", "date_match": "2026-11-27", "p": [0, 0, 1]}]
    assert predictions.retenues(j)["m"]["p"] == [1, 0, 0]


def test_export_propre_et_ecriture_atomique(tmp_path):
    data = {"x": np.float64(np.nan), "y": np.int64(3), "z": [np.float32(0.123456)], "d": pd.Timestamp("2026-01-02")}
    p = export.propre(data)
    assert p == {"x": None, "y": 3, "z": [0.1235], "d": "2026-01-02"}
    export.ecrire("c", {"a.json": {"v": 1}}, dossier=tmp_path)
    export.ecrire("c", {"b.json": {"v": 2}}, dossier=tmp_path)
    fichiers = sorted(f.name for f in (tmp_path / "c").iterdir())
    assert fichiers == ["b.json"]  # remplacement complet, pas de mélange
    assert json.loads((tmp_path / "c" / "b.json").read_text()) == {"v": 2}


def test_enjeux_coherents_avec_le_resultat():
    eq = ["a", "b", "c", "d"]
    m = faire_saison(eq, a_venir=4)
    suivi = m[m["statut"] == "a_venir"]["match_id"].iloc[0]
    res = simuler(m, _modele(eq, [0.2, 0.0, 0.0, -0.2]), FMT, n_sims=6000, suivis=[suivi])
    e = res["enjeux"][suivi]
    titre_dom = e["dom"]["titre"]          # [si victoire dom, si nul, si victoire ext]
    assert titre_dom[0] >= titre_dom[2]     # gagner ne peut pas faire baisser ses chances de titre
    assert e["dom"]["points"][0] > e["dom"]["points"][2]
    assert 0 <= e["importance"] <= 1


def test_evolution_des_chances_une_valeur_par_journee(comp_test):
    from pipeline.simulation import evolution_chances
    s1 = faire_saison(["a", "b", "c", "d"], saison="2023-24", graine=1)
    s2 = faire_saison(["a", "b", "c", "d"], saison="2024-25", graine=2, a_venir=4)
    m = pd.concat([s1, s2], ignore_index=True)
    evo = evolution_chances(m, comp_test, "2024-25", n_sims=500)
    assert evo["journees"][0] == 0                     # pronostic d'avant-saison
    for e in evo["equipes"]:
        assert len(e["titre"]) == len(evo["journees"])
    total = [sum(e["titre"][k] for e in evo["equipes"]) for k in range(len(evo["journees"]))]
    np.testing.assert_allclose(total, 1, atol=1e-9)    # un seul champion par saison simulée
