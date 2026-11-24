"""Téléchargement HTTP avec reprises. Aucune donnée n'est écrite ici : on renvoie des octets,
c'est l'appelant qui décide de les conserver une fois les contrôles qualité passés."""
from __future__ import annotations

import time

import requests

ENTETES = {"User-Agent": "ligue1-data-pipeline/1.0 (projet open data)"}


class ErreurSource(RuntimeError):
    """Une source n'a pas répondu correctement."""


def telecharger(url: str, tentatives: int = 3, delai: float = 2.0, timeout: float = 30.0) -> bytes:
    derniere_erreur: Exception | None = None
    for i in range(tentatives):
        try:
            r = requests.get(url, headers=ENTETES, timeout=timeout)
            if r.status_code == 404:
                raise ErreurSource(f"404 sur {url}")
            r.raise_for_status()
            if not r.content:
                raise ErreurSource(f"Réponse vide sur {url}")
            return r.content
        except ErreurSource:
            raise
        except Exception as e:  # réseau, 5xx…
            derniere_erreur = e
            time.sleep(delai * (i + 1))
    raise ErreurSource(f"Échec du téléchargement de {url} : {derniere_erreur}")
