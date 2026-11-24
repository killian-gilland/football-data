# Ligue 1 en données

Site d'analyse de la Ligue 1 par les données : classement, stats d'équipes, historique depuis 1993-94, probabilités
de chaque match, simulations de fin de saison et historique public des prédictions. Open data uniquement, coût 0 €,
mise à jour automatique.

## Architecture

```
config/                 compétitions, règles de chaque saison, référentiel des clubs
pipeline/               Python : ingestion -> contrôles qualité -> stats -> modèles -> export JSON
  sources/              football-data.co.uk (principale), openfootball (calendrier, CC0)
  modeles/              Elo, Dixon-Coles, indice d'occasions, métriques (RPS, log loss, Brier)
  backtest.py           validation walk-forward (aucune fuite du futur)
  simulation.py         Monte-Carlo de fin de saison
  predictions.py        journal public des prédictions (ajout seul)
donnees/
  brut/                 fichiers sources téléchargés (versionnés)
  canonique/            table des matchs validée + manifeste (dernière version valide)
  predictions/          journal horodaté des prédictions
site/                   Astro (statique), lit site/src/donnees/<competition>/*.json
tests/                  pytest (aucun accès réseau)
.github/workflows/      mise à jour quotidienne + tests à chaque push
```

La compétition est un paramètre partout. Ajouter la Ligue 2 : passer `actif: true` dans
`config/competitions.yaml`, créer `config/formats/fr-ligue2.yaml` (zones de la saison), compléter les alias de clubs
dans `config/equipes/fr.yaml` si le pipeline signale des noms inconnus.

## Commandes

```bash
pip install -r requirements.txt
python -m pytest                    # tests
python -m pipeline                  # télécharge, contrôle, calcule, exporte (≈ 1 à 2 min)
python -m pipeline --hors-ligne     # idem avec les seuls fichiers déjà présents

cd site && npm install && npm run build   # site statique dans site/dist
npm run preview                           # http://localhost:4321
```

Code de sortie 2 = un contrôle bloquant a échoué : rien n'est écrit, la dernière version valide reste en place.

## Mise en ligne (une seule fois)

1. Créer un dépôt GitHub (privé recommandé : les fichiers bruts de football-data.co.uk y sont versionnés) et pousser.
2. Cloudflare : créer un projet Pages en « Direct Upload » (par ex. `ligue1-data`), puis un jeton d'API avec la
   permission *Cloudflare Pages : Edit*.
3. Dans le dépôt GitHub, *Settings > Secrets and variables > Actions* :
   - secrets : `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID` ;
   - variables : `CF_PAGES_PROJET` (nom du projet Pages), `SITE_URL` (ex. `https://ligue1-data.pages.dev`).
4. Lancer une première fois le workflow « Mise à jour » à la main (*Actions > Mise à jour > Run workflow*).

Ensuite tout est automatique : chaque matin et chaque soir de match, le workflow télécharge les données, exécute les
contrôles, recalcule tout, enregistre le journal des prédictions dans le dépôt et redéploie. En cas d'échec, rien
n'est déployé et une issue « Échec de la mise à jour automatique » est ouverte.

## Sources

- [football-data.co.uk](https://www.football-data.co.uk/) : résultats, statistiques de match, cotes. Leurs conditions
  réservent l'usage aux particuliers et à un usage non commercial : à revoir avec eux avant toute monétisation.
  `enrichissements: false` masque déjà tirs, corners, cartons et cotes ; en revanche les scores viennent encore de
  cette source (openfootball a plusieurs semaines de retard). Pour s'en passer entièrement, il faudra brancher une
  autre source de résultats dans `pipeline/sources/`.
- [openfootball](https://github.com/openfootball/football.json) : calendrier, domaine public (CC0).
