import pandas as pd

from pipeline.classement import classement
from pipeline.qualite import controler
from tests.conftest import faire_saison

FMT = {"points": {"victoire": 3, "nul": 1, "defaite": 0},
       "departage": ["diff", "confrontations_points", "confrontations_diff", "buts_pour"], "zones": []}


def test_points_et_ordre_simple():
    sc = {("a", "b"): (2, 0), ("b", "a"): (0, 1), ("a", "c"): (1, 1), ("c", "a"): (0, 0),
          ("b", "c"): (1, 0), ("c", "b"): (0, 3)}
    t = classement(faire_saison(["a", "b", "c"], scores=sc), FMT)
    assert t["equipe"].tolist() == ["a", "b", "c"]
    assert t.set_index("equipe").loc["a", "pts"] == 3 + 3 + 1 + 1
    assert t.set_index("equipe").loc["c", "pts"] == 2


def test_departage_confrontations_directes_apres_difference_de_buts():
    # a et b : 11 points et +2 chacun ; b a pris 4 points sur 6 dans la confrontation directe.
    sc = {("a", "b"): (0, 1), ("b", "a"): (1, 1), ("a", "c"): (1, 0), ("c", "a"): (0, 1),
          ("a", "d"): (1, 0), ("d", "a"): (0, 0), ("b", "c"): (1, 0), ("c", "b"): (0, 1),
          ("b", "d"): (0, 0), ("d", "b"): (1, 0), ("c", "d"): (0, 0), ("d", "c"): (0, 0)}
    t = classement(faire_saison(["a", "b", "c", "d"], scores=sc), FMT).set_index("equipe")
    assert (t.loc["a", "pts"], t.loc["a", "diff"]) == (11, 2)
    assert (t.loc["b", "pts"], t.loc["b", "diff"]) == (11, 2)
    assert t.loc["b", "rang"] == 1 and t.loc["a", "rang"] == 2


def test_confrontations_ignorees_si_le_retour_n_est_pas_joue():
    sc = {("a", "b"): (0, 1), ("b", "a"): (1, 1), ("a", "c"): (1, 0), ("c", "a"): (0, 1),
          ("a", "d"): (1, 0), ("d", "a"): (0, 0), ("b", "c"): (1, 0), ("c", "b"): (0, 1),
          ("b", "d"): (0, 0), ("d", "b"): (1, 0), ("c", "d"): (0, 0), ("d", "c"): (0, 0)}
    m = faire_saison(["a", "b", "c", "d"], scores=sc)
    m.loc[(m["dom"] == "b") & (m["ext"] == "a"), ["statut", "buts_dom", "buts_ext"]] = ["a_venir", None, None]
    t = classement(m, FMT)
    assert t["equipe"].iloc[0] in ("a", "b")  # pas d'erreur, critère suivant utilisé


def test_bareme_a_2_points_et_penalite():
    sc = {("a", "b"): (1, 0), ("b", "a"): (1, 1)}
    t = classement(faire_saison(["a", "b"], scores=sc), {**FMT, "points": {"victoire": 2, "nul": 1},
                                                          "penalites": {"a": 1}}).set_index("equipe")
    assert t.loc["a", "pts"] == 2 + 1 - 1 and t.loc["a", "penalite"] == 1


def test_classement_au_quotient_points_par_match():
    m = faire_saison(["a", "b", "c"], scores={("a", "b"): (1, 0), ("b", "a"): (1, 0), ("a", "c"): (1, 0),
                                              ("c", "a"): (0, 1), ("b", "c"): (3, 0), ("c", "b"): (0, 1)})
    # b a joué un match de moins (non joué) mais a un meilleur ratio
    m = m[~((m["dom"] == "a") & (m["ext"] == "c"))]
    t = classement(m, {**FMT, "classement_par": "points_par_match"})
    assert t.iloc[0]["equipe"] == "b"


def test_zones():
    t = classement(faire_saison(["a", "b", "c", "d"]), {**FMT, "zones": [{"code": "rel", "positions": [4]}]})
    assert t["zone"].tolist()[-1] == "rel" and t["zone"].isna().sum() == 3


def test_qualite_saison_propre_est_valide(comp_test):
    r = controler(faire_saison(["a", "b", "c", "d"]), comp_test)
    assert r.valide, r.resume()


def test_qualite_doublon_bloquant(comp_test):
    m = faire_saison(["a", "b", "c", "d"])
    r = controler(pd.concat([m, m.iloc[[0]]]), comp_test)
    assert not r.valide
    assert any(c.code == "identifiants_uniques" for c in r.bloquants_en_echec)


def test_qualite_mi_temps_superieure_au_final_bloquante(comp_test):
    m = faire_saison(["a", "b", "c", "d"])
    m.loc[0, ["buts_dom", "mt_dom"]] = [1.0, 3.0]
    assert not controler(m, comp_test).valide


def test_qualite_date_hors_saison_bloquante(comp_test):
    m = faire_saison(["a", "b", "c", "d"])
    m.loc[0, "date"] = pd.Timestamp("2030-01-01")
    assert not controler(m, comp_test).valide


def test_qualite_nombre_equipes_saison_courante(comp_test):
    m = faire_saison(["a", "b", "c"])
    assert not controler(m, comp_test).valide  # format : 4 équipes attendues


def test_non_regression_match_disparu_bloquant(comp_test):
    m = faire_saison(["a", "b", "c", "d"])
    r = controler(m.iloc[1:], comp_test, precedent=m)
    assert any(c.code == "aucun_match_joue_disparu" for c in r.bloquants_en_echec)


def test_score_corrige_est_une_alerte_pas_un_blocage(comp_test):
    m = faire_saison(["a", "b", "c", "d"])
    m2 = m.copy()
    m2.loc[0, "buts_dom"] = m.loc[0, "buts_dom"] + 1
    m2.loc[0, "mt_dom"] = 0.0
    r = controler(m2, comp_test, precedent=m)
    assert r.valide
    assert any(c.code == "scores_inchanges" and not c.ok for c in r.controles)


def test_evolution_par_journee_coherente_avec_le_classement_final():
    from pipeline.classement import evolution_par_journee
    m = faire_saison(["a", "b", "c", "d"], graine=3)
    evo = evolution_par_journee(m, FMT)
    final = classement(m, FMT).set_index("equipe")
    assert evo["journees"] == sorted(m["journee"].unique().astype(int).tolist())
    for e in evo["equipes"]:
        assert e["rangs"][-1] == final.loc[e["equipe"], "rang"]
        assert e["points"][-1] == final.loc[e["equipe"], "pts"]
        assert all(a <= b for a, b in zip(e["points"], e["points"][1:]))  # les points ne baissent jamais
