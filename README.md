# CalorIA

Application web locale et légère en Python pour suivre simplement les calories consommées par jour et par menu, sans aucune dépendance externe à installer.

## Fonctionnalités

- **Suivi par journée et par menu fixe** : Petit-déjeuner, Déjeuner, Dîner, Collation.
- **Repères visuels** : total du jour, barre de progression, objectif quotidien (`1 650 – 1 750 kcal/jour`) et repère d'activité modérée (`1 990 kcal/jour`).
- **3 sources d'aliments complémentaires** :
  - **Table officielle ANSES Ciqual 2025** (~3 340 aliments courants et plats français, utilisable hors ligne).
  - **Open Food Facts** (recherche en ligne gratuite pour les produits du commerce, sans clé API).
  - **Catalogue personnel & création manuelle** (mémorisation automatique des produits utilisés et du poids de vos portions).
- **Calcul flexible** : saisie en grammes (`g`) ou en portions (`portion(s)` avec poids personnalisable, ex. `0.5` tranche).
- **Historique persistant** : toutes les données sont sauvegardées localement dans une base SQLite (`caloria.db`, ignorée par Git).

## Prérequis

- **Python 3.9+** (bibliothèque standard uniquement, aucun `pip install` requis).

## Lancement

### En local (Python)

```bash
git clone https://github.com/elodissey/CalorIA.git
cd CalorIA
python3 users.py   # crée les 2 comptes autorisés
python3 app.py
```

Ouvrez ensuite [http://127.0.0.1:8000](http://127.0.0.1:8000) dans votre navigateur.

### Avec Docker (pour déployer facilement sur un serveur)

```bash
docker compose up -d --build
docker exec -it caloria python3 users.py   # crée les 2 comptes dans ./data/caloria.db
```

La base SQLite est conservée durablement dans le dossier `./data` (monté sur `/app/data` dans le conteneur).

Au premier démarrage, la base locale `caloria.db` est créée automatiquement.

### Ajouter la table Ciqual hors ligne (optionnel)

Le fichier `ciqual_2025.xlsx` n'est pas inclus dans ce dépôt Git. Pour activer les ~3 340 aliments français hors ligne :

1. Téléchargez le fichier `.xlsx` de la **Table de composition nutritionnelle des aliments Ciqual 2025** sur [Recherche Data Gouv (DOI : 10.57745/RDMHWY)](https://entrepot.recherche.data.gouv.fr/dataset.xhtml?persistentId=doi:10.57745/RDMHWY).
2. Placez-le dans le dossier `CalorIA/` en le renommant `ciqual_2025.xlsx`.
3. Lancez `python3 ciqual.py` (ou démarrez directement `python3 app.py`) : l'import dans `caloria.db` se fait automatiquement.

## Structure du projet

- `app.py` : serveur HTTP local et API JSON.
- `db.py` : gestion de la base SQLite (`foods`, `meal_entries`, `ciqual_foods`).
- `ciqual.py` : lecture du fichier `ciqual_2025.xlsx` et recherche sans accents.
- `openfoodfacts.py` : recherche en ligne via `search.openfoodfacts.org`.
- `static/` : interface web (`index.html`, `style.css`, `app.js`).

## Sources de données & Licence

- **Code** : sous licence [MIT](LICENSE) (`© 2026 elodissey`).
- **Données nutritionnelles hors ligne** : Table de composition nutritionnelle des aliments Ciqual 2025 — ANSES (Licence Ouverte / Etalab, DOI : `10.57745/RDMHWY`).
- **Recherche produits en ligne** : [Open Food Facts](https://world.openfoodfacts.org/) (Open Database License — ODbL).
