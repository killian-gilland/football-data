"""Correspondance noms bruts (par source) -> identifiant stable d'équipe."""
from __future__ import annotations

import unicodedata

import pandas as pd


def _cle(nom: str) -> str:
    """Clé de comparaison insensible à la casse, aux accents et aux espaces."""
    s = unicodedata.normalize("NFKD", str(nom)).encode("ascii", "ignore").decode()
    return " ".join(s.lower().replace("-", " ").split())


class Referentiel:
    def __init__(self, equipes: dict[str, dict]):
        self.equipes = equipes
        self._index: dict[str, str] = {}
        for eid, info in equipes.items():
            for nom in [info["nom"], *info.get("alias", [])]:
                cle = _cle(nom)
                if cle in self._index and self._index[cle] != eid:
                    raise ValueError(f"Alias ambigu « {nom} » : {self._index[cle]} et {eid}")
                self._index[cle] = eid

    def identifiant(self, nom: str) -> str | None:
        return self._index.get(_cle(nom))

    def mapper(self, serie: pd.Series) -> tuple[pd.Series, list[str]]:
        """Renvoie (identifiants, noms inconnus)."""
        ids = serie.map(self.identifiant)
        inconnus = sorted(set(serie[ids.isna()].dropna()))
        return ids, inconnus

    def nom(self, eid: str) -> str:
        return self.equipes.get(eid, {}).get("nom", eid)

    def court(self, eid: str) -> str:
        return self.equipes.get(eid, {}).get("court", self.nom(eid))
