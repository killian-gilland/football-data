import json

from pipeline import logos
from pipeline.config import charger_referentiel
from pipeline.referentiel import Referentiel

REPONSE = {"teams": [
    {"name": "Paris Saint-Germain FC", "shortName": "PSG", "tla": "PSG", "crest": "https://crests.example/524.png"},
    {"name": "Racing Club de Lens", "shortName": "RC Lens", "tla": "RCL", "crest": "https://crests.example/546.svg"},
    {"name": "Club Inconnu", "shortName": "Inconnu", "tla": "INC", "crest": "https://crests.example/1.png"},
]}


class FauxComp:
    id = "fr-ligue1"
    saison_courante = "2026-27"
    sources = {"football_data_org": {"code": "FL1"}}

    def __init__(self, actif):
        self.logos = actif


def test_correspondance_des_equipes():
    adresses, inconnus = logos.correspondances(json.dumps(REPONSE).encode(), Referentiel(charger_referentiel("fr")))
    assert adresses == {"psg": "https://crests.example/524.png", "lens": "https://crests.example/546.svg"}
    assert inconnus == ["Club Inconnu"]


def test_interrupteur_coupe_retire_les_logos(tmp_path):
    dossier = tmp_path / "logos"
    dossier.mkdir()
    (dossier / "psg.png").write_bytes(b"x")
    chemins, _ = logos.mettre_a_jour(FauxComp(False), None, dossier=dossier, racine=tmp_path)
    assert chemins == {} and not dossier.exists()


def test_hors_ligne_reutilise_les_fichiers_deja_presents(tmp_path):
    cache = tmp_path / "brut" / "fr-ligue1" / "football-data-org" / "FL1_equipes_2026-27.json"
    cache.parent.mkdir(parents=True)
    cache.write_text(json.dumps(REPONSE), encoding="utf-8")
    dossier = tmp_path / "logos"
    dossier.mkdir()
    (dossier / "psg.png").write_bytes(b"image")
    chemins, alertes = logos.mettre_a_jour(FauxComp(True), Referentiel(charger_referentiel("fr")), hors_ligne=True,
                                           dossier=dossier, racine=tmp_path)
    assert chemins == {"psg": "/logos/psg.png"}  # Lens pas encore téléchargé : pas de logo, pas d'erreur
    assert any("non reconnues" in a for a in alertes)
