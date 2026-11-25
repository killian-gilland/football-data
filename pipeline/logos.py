"""Logos des clubs (interrupteur `logos` dans config/competitions.yaml).

Les logos sont la propriété des clubs. Ils servent uniquement à identifier les équipes.
Source : adresses fournies par l'API football-data.org (/v4/competitions/{code}/teams).
Les images sont téléchargées dans site/public/logos/ (ignoré par Git) au moment de la mise à jour :
elles sont servies par le site lui-même, aucun visiteur ne se connecte à un serveur tiers.
Interrupteur sur false : le dossier est vidé et plus aucun logo n'apparaît au déploiement suivant.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import requests

from .config import DOSSIER_DONNEES, RACINE, Competition
from .referentiel import Referentiel
from .sources import footballdata_org as fdo

DOSSIER_LOGOS = RACINE / "site" / "public" / "logos"
URL_EQUIPES = "https://api.football-data.org/v4/competitions/{code}/teams?season={annee}"
EXTENSIONS = {"image/svg+xml": "svg", "image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}


def correspondances(contenu: bytes, ref: Referentiel) -> tuple[dict[str, str], list[str]]:
    """Réponse /teams -> {identifiant de club: adresse du logo}, plus les équipes non reconnues."""
    data = json.loads(contenu.decode("utf-8"))
    res, inconnus = {}, []
    for t in data.get("teams", []):
        eid = next((ref.identifiant(n) for n in (t.get("name"), t.get("shortName"), t.get("tla")) if n and ref.identifiant(n)), None)
        if eid and t.get("crest"):
            res[eid] = t["crest"]
        elif not eid:
            inconnus.append(t.get("name") or "?")
    return res, inconnus


def mettre_a_jour(comp: Competition, ref: Referentiel, hors_ligne: bool = False,
                  dossier: Path = DOSSIER_LOGOS, racine: Path = DOSSIER_DONNEES) -> tuple[dict[str, str], list[str]]:
    """Renvoie ({identifiant: chemin public du logo}, alertes). Ne bloque jamais le pipeline."""
    alertes: list[str] = []
    if not getattr(comp, "logos", False):
        if dossier.exists():
            shutil.rmtree(dossier)  # interrupteur coupé : on retire tous les logos
        return {}, alertes
    cfg = comp.sources.get("football_data_org")
    if not cfg:
        return {}, ["Logos activés mais aucune source football_data_org configurée."]
    cache = racine / "brut" / comp.id / "football-data-org" / f"{cfg['code']}_equipes_{comp.saison_courante}.json"
    contenu = None
    cle = fdo.jeton()
    if cle and not hors_ligne:
        try:
            r = requests.get(URL_EQUIPES.format(code=cfg["code"], annee=comp.saison_courante[:4]),
                             headers={"X-Auth-Token": cle}, timeout=30)
            r.raise_for_status()
            contenu = r.content
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_bytes(contenu)
        except Exception as e:
            alertes.append(f"Liste des équipes football-data.org indisponible ({e}) : logos de la dernière version.")
    if contenu is None and cache.exists():
        contenu = cache.read_bytes()
    if contenu is None:
        alertes.append("Logos activés mais aucune liste d'équipes disponible (clé FOOTBALL_DATA_ORG_TOKEN absente ?).")
        contenu = b'{"teams": []}'
    adresses, inconnus = correspondances(contenu, ref)
    if inconnus:
        alertes.append("Logos : équipes non reconnues (alias à ajouter) : " + ", ".join(inconnus))

    dossier.mkdir(parents=True, exist_ok=True)
    chemins = {}
    for eid, url in adresses.items():
        existant = next(dossier.glob(f"{eid}.*"), None)
        if existant and existant.stat().st_size > 0:
            chemins[eid] = f"/logos/{existant.name}"
            continue
        if hors_ligne:
            continue
        try:
            r = requests.get(url, timeout=30)
            r.raise_for_status()
            ext = EXTENSIONS.get(r.headers.get("Content-Type", "").split(";")[0].strip()) or url.rsplit(".", 1)[-1].lower()
            if ext not in EXTENSIONS.values() or len(r.content) > 500_000:
                alertes.append(f"Logo ignoré pour {eid} (format ou taille inattendus).")
                continue
            (dossier / f"{eid}.{ext}").write_bytes(r.content)
            chemins[eid] = f"/logos/{eid}.{ext}"
        except Exception as e:
            alertes.append(f"Logo indisponible pour {eid} : {e}")
    return chemins, alertes
