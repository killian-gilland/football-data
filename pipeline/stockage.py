"""Persistance : table canonique, fichiers bruts, manifeste de la dernière version valide.
On n'écrit qu'après validation (écriture dans un fichier temporaire puis remplacement atomique)."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .config import DOSSIER_DONNEES


def dossier_canonique(cid: str, racine: Path = DOSSIER_DONNEES) -> Path:
    return racine / "canonique" / cid


def charger_matchs(cid: str, racine: Path = DOSSIER_DONNEES) -> pd.DataFrame | None:
    # CSV plutôt que parquet : versionné dans Git, les mises à jour quotidiennes restent de petits diffs texte.
    chemin = dossier_canonique(cid, racine) / "matchs.csv"
    if not chemin.exists():
        return None
    return pd.read_csv(chemin, parse_dates=["date"], dtype={"match_id": str, "heure": str, "saison": str})


def _ecrire_atomique(chemin: Path, contenu: bytes) -> None:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    tmp = chemin.with_suffix(chemin.suffix + ".tmp")
    tmp.write_bytes(contenu)
    os.replace(tmp, chemin)


def empreinte(df: pd.DataFrame) -> str:
    return hashlib.sha256(pd.util.hash_pandas_object(df, index=False).values.tobytes()).hexdigest()[:16]


def promouvoir(cid: str, matchs: pd.DataFrame, bruts: dict[Path, bytes], rapport: dict,
               racine: Path = DOSSIER_DONNEES) -> dict:
    """Enregistre une version validée comme « dernière version valide »."""
    for chemin, contenu in bruts.items():
        _ecrire_atomique(chemin, contenu)
    dossier = dossier_canonique(cid, racine)
    dossier.mkdir(parents=True, exist_ok=True)
    tmp = dossier / "matchs.csv.tmp"
    matchs.to_csv(tmp, index=False, date_format="%Y-%m-%d", float_format="%.6g", lineterminator="\n")
    os.replace(tmp, dossier / "matchs.csv")
    ancien = dossier / "matchs.parquet"
    if ancien.exists():
        ancien.unlink()
    manifeste = {
        "competition": cid,
        "valide_le": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "empreinte": empreinte(matchs),
        "matchs": int(len(matchs)),
        "matchs_joues": int((matchs["statut"] == "joue").sum()),
        "rapport_qualite": rapport,
    }
    _ecrire_atomique(dossier / "manifeste.json",
                     json.dumps(manifeste, ensure_ascii=False, indent=2).encode("utf-8"))
    return manifeste
