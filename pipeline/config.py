"""Chargement de la configuration (compétitions, formats de saison, référentiel d'équipes)."""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

RACINE = Path(__file__).resolve().parent.parent
DOSSIER_CONFIG = RACINE / "config"
DOSSIER_DONNEES = RACINE / "donnees"
DOSSIER_EXPORT = RACINE / "site" / "src" / "donnees"


def _lire_yaml(chemin: Path) -> dict:
    with open(chemin, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def saison_vers_code(saison: str) -> str:
    """'2026-27' -> '2627' (format des URL football-data.co.uk)."""
    debut, fin = saison.split("-")
    return debut[2:] + fin[-2:]


def saison_suivante(saison: str) -> str:
    debut = int(saison[:4]) + 1
    return f"{debut}-{str(debut + 1)[2:]}"


def saison_precedente(saison: str) -> str:
    debut = int(saison[:4]) - 1
    return f"{debut}-{str(debut + 1)[2:]}"


def liste_saisons(premiere: str, derniere: str) -> list[str]:
    saisons, s = [], premiere
    while int(s[:4]) <= int(derniere[:4]):
        saisons.append(s)
        s = saison_suivante(s)
    return saisons


def _fusion(base: dict, surcharge: dict) -> dict:
    res = copy.deepcopy(base)
    for k, v in surcharge.items():
        if isinstance(v, dict) and isinstance(res.get(k), dict):
            res[k] = _fusion(res[k], v)
        else:
            res[k] = copy.deepcopy(v)
    return res


@dataclass
class Competition:
    id: str
    nom: str
    pays: str
    slug: str
    actif: bool
    saison_courante: str
    premiere_saison: str
    referentiel_equipes: str
    enrichissements: bool
    sources: dict[str, Any]
    formats: dict[str, Any] = field(default_factory=dict)
    logos: bool = False  # interrupteur des logos de clubs (voir pipeline/logos.py)

    @property
    def saisons(self) -> list[str]:
        return liste_saisons(self.premiere_saison, self.saison_courante)

    def format_saison(self, saison: str) -> dict:
        """Règles effectives d'une saison (défaut + surcharge éventuelle)."""
        return _fusion(self.formats.get("defaut", {}), self.formats.get("saisons", {}).get(saison, {}))


def charger_competitions(dossier: Path = DOSSIER_CONFIG) -> dict[str, Competition]:
    brut = _lire_yaml(dossier / "competitions.yaml")["competitions"]
    res = {}
    for cid, c in brut.items():
        chemin_format = dossier / "formats" / f"{cid}.yaml"
        formats = _lire_yaml(chemin_format) if chemin_format.exists() else {}
        res[cid] = Competition(id=cid, formats=formats, **c)
    return res


def charger_competition(cid: str, dossier: Path = DOSSIER_CONFIG) -> Competition:
    comps = charger_competitions(dossier)
    if cid not in comps:
        raise KeyError(f"Compétition inconnue : {cid} (connues : {', '.join(comps)})")
    return comps[cid]


def charger_referentiel(nom: str, dossier: Path = DOSSIER_CONFIG) -> dict[str, dict]:
    return _lire_yaml(dossier / "equipes" / f"{nom}.yaml").get("equipes", {})
