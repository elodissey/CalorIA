"""
db.py — Gestion de la base de données SQLite locale pour CalorIA.

Ce fichier contient toutes les fonctions qui lisent et écrivent dans le fichier
`caloria.db` (créé automatiquement dans le dossier CalorIA).
Aucune bibliothèque externe n'est nécessaire : `sqlite3` est inclus dans Python.
"""

import os
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

import ciqual

# Chemin complet vers le fichier de base de données, dans le même dossier que ce script
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "caloria.db")

# Les 4 menus fixes validés pour chaque journée
MENUS_FIXES = ("Petit-déjeuner", "Déjeuner", "Dîner", "Collation")


def get_connection() -> sqlite3.Connection:
    """Ouvre une connexion SQLite configurée pour renvoyer des dictionnaires."""
    conn = sqlite3.connect(DB_PATH)
    # Permet d'accéder aux colonnes par leur nom (ex: row["name"]) au lieu d'un index
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Crée les tables si elles n'existent pas encore (base vide au démarrage)."""
    with get_connection() as conn:
        # Table 1 : Catalogue des aliments enregistrés localement
        # (soit créés manuellement, soit mémorisés depuis Open Food Facts)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS foods (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                brand TEXT DEFAULT '',
                kcal_per_100g REAL NOT NULL,
                portion_name TEXT DEFAULT '',
                portion_grams REAL DEFAULT NULL,
                source TEXT NOT NULL DEFAULT 'manuel',
                external_code TEXT DEFAULT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # Table 2 : Journal des aliments consommés par jour et par menu
        # On stocke un "instantané" (nom, marque, calories calculées) pour que
        # l'historique passé reste exact même si on modifie un aliment plus tard.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS meal_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entry_date TEXT NOT NULL,
                meal_type TEXT NOT NULL,
                food_id INTEGER DEFAULT NULL,
                food_name TEXT NOT NULL,
                food_brand TEXT DEFAULT '',
                unit TEXT NOT NULL,
                quantity REAL NOT NULL,
                grams_equivalent REAL NOT NULL,
                kcal_calculated REAL NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # Table 3 : Référentiel officiel français ANSES Ciqual (hors ligne)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ciqual_foods (
                alim_code TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                group_name TEXT DEFAULT '',
                kcal_per_100g REAL NOT NULL,
                search_text TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_ciqual_search ON ciqual_foods(search_text)"
        )
        conn.commit()


def ciqual_count() -> int:
    """Retourne le nombre d'aliments Ciqual déjà importés en base."""
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS cnt FROM ciqual_foods").fetchone()
    return int(row["cnt"]) if row else 0


def import_ciqual_foods(items: List[Tuple[str, str, str, float, str]]) -> int:
    """Insère ou met à jour en masse les aliments de la table Ciqual."""
    if not items:
        return 0
    with get_connection() as conn:
        conn.executemany(
            """
            INSERT OR REPLACE INTO ciqual_foods (alim_code, name, group_name, kcal_per_100g, search_text)
            VALUES (?, ?, ?, ?, ?)
            """,
            items,
        )
        conn.commit()
    return len(items)


def search_ciqual_foods(query: str, limit: int = 25) -> List[Dict[str, Any]]:
    """
    Recherche dans la table Ciqual hors ligne (sans tenir compte des accents).
    Si la recherche contient plusieurs mots (ex: 'pain campagne'), tous les mots
    doivent apparaître dans le nom ou le groupe.
    """
    norm = ciqual.normalize_text(query)
    words = norm.split()
    if not words:
        return []

    where_clauses = " AND ".join("search_text LIKE ?" for _ in words)
    params: List[Any] = [f"%{w}%" for w in words]
    # Astuce pour classer les résultats qui commencent par le premier mot en premier
    params.append(f"{words[0]}%")
    params.append(limit)

    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT alim_code, name, group_name, kcal_per_100g
            FROM ciqual_foods
            WHERE {where_clauses}
            ORDER BY CASE WHEN search_text LIKE ? THEN 0 ELSE 1 END, LENGTH(name) ASC
            LIMIT ?
            """,
            params,
        ).fetchall()

    results: List[Dict[str, Any]] = []
    for row in rows:
        grp = row["group_name"] or "Ciqual"
        results.append(
            {
                "id": None,
                "name": row["name"],
                "brand": f"Ciqual · {grp}",
                "kcal_per_100g": row["kcal_per_100g"],
                "portion_name": "",
                "portion_grams": None,
                "source": "ciqual",
                "external_code": row["alim_code"],
            }
        )
    return results


def search_local_foods(query: str = "") -> List[Dict[str, Any]]:
    """Recherche des aliments dans le catalogue local (tous si query est vide)."""
    with get_connection() as conn:
        if query.strip():
            motif = f"%{query.strip()}%"
            rows = conn.execute(
                """
                SELECT id, name, brand, kcal_per_100g, portion_name, portion_grams, source, external_code
                FROM foods
                WHERE name LIKE ? OR brand LIKE ?
                ORDER BY id DESC
                LIMIT 50
                """,
                (motif, motif),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id, name, brand, kcal_per_100g, portion_name, portion_grams, source, external_code
                FROM foods
                ORDER BY id DESC
                LIMIT 50
                """
            ).fetchall()
    return [dict(row) for row in rows]


def get_food_by_id(food_id: int) -> Optional[Dict[str, Any]]:
    """Récupère un aliment local à partir de son identifiant."""
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT id, name, brand, kcal_per_100g, portion_name, portion_grams, source, external_code
            FROM foods
            WHERE id = ?
            """,
            (food_id,),
        ).fetchone()
    return dict(row) if row else None


def find_existing_external_food(
    source: str, external_code: Optional[str], name: str, brand: str
) -> Optional[Dict[str, Any]]:
    """Vérifie si un produit externe (Open Food Facts ou Ciqual) est déjà mémorisé localement."""
    with get_connection() as conn:
        if external_code:
            row = conn.execute(
                "SELECT * FROM foods WHERE source = ? AND external_code = ? LIMIT 1",
                (source, external_code),
            ).fetchone()
            if row:
                return dict(row)

        row = conn.execute(
            "SELECT * FROM foods WHERE name = ? AND brand = ? AND source = ? LIMIT 1",
            (name, brand, source),
        ).fetchone()
        return dict(row) if row else None


def save_food(
    name: str,
    kcal_per_100g: float,
    brand: str = "",
    portion_name: str = "",
    portion_grams: Optional[float] = None,
    source: str = "manuel",
    external_code: Optional[str] = None,
) -> Dict[str, Any]:
    """Enregistre un nouvel aliment dans le catalogue local (ou le retrouve s'il existe déjà)."""
    # Si ça vient d'Open Food Facts ou Ciqual, on évite de créer un doublon
    if source in ("openfoodfacts", "ciqual"):
        existant = find_existing_external_food(source, external_code, name, brand)
        if existant:
            return existant

    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO foods (name, brand, kcal_per_100g, portion_name, portion_grams, source, external_code)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name.strip(),
                brand.strip(),
                round(float(kcal_per_100g), 2),
                portion_name.strip(),
                round(float(portion_grams), 2) if portion_grams else None,
                source,
                external_code,
            ),
        )
        conn.commit()
        new_id = cursor.lastrowid

    return get_food_by_id(new_id)  # type: ignore[return-value]


def update_food_portion(food_id: int, portion_name: str, portion_grams: float) -> Optional[Dict[str, Any]]:
    """Met à jour le poids d'une portion sur un aliment déjà enregistré."""
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE foods
            SET portion_name = ?, portion_grams = ?
            WHERE id = ?
            """,
            (portion_name.strip(), round(float(portion_grams), 2), food_id),
        )
        conn.commit()
    return get_food_by_id(food_id)


def add_meal_entry(
    entry_date: str,
    meal_type: str,
    food_id: Optional[int],
    food_name: str,
    food_brand: str,
    unit: str,
    quantity: float,
    grams_equivalent: float,
    kcal_calculated: float,
) -> Dict[str, Any]:
    """Ajoute un aliment consommé dans un menu d'une journée donnée."""
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO meal_entries (
                entry_date, meal_type, food_id, food_name, food_brand,
                unit, quantity, grams_equivalent, kcal_calculated
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry_date,
                meal_type,
                food_id,
                food_name,
                food_brand,
                unit,
                round(float(quantity), 2),
                round(float(grams_equivalent), 2),
                round(float(kcal_calculated), 1),
            ),
        )
        conn.commit()
        entry_id = cursor.lastrowid
        row = conn.execute("SELECT * FROM meal_entries WHERE id = ?", (entry_id,)).fetchone()
    return dict(row)


def get_day_summary(entry_date: str) -> Dict[str, Any]:
    """
    Récupère toutes les entrées d'une journée, regroupées par les 4 menus fixes,
    ainsi que les sous-totaux par menu et le total global de la journée.
    """
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, entry_date, meal_type, food_id, food_name, food_brand,
                   unit, quantity, grams_equivalent, kcal_calculated, created_at
            FROM meal_entries
            WHERE entry_date = ?
            ORDER BY id ASC
            """,
            (entry_date,),
        ).fetchall()

    # On prépare la structure avec les 4 menus fixes même s'ils sont vides
    menus: Dict[str, Dict[str, Any]] = {
        menu: {"name": menu, "total_kcal": 0.0, "entries": []}
        for menu in MENUS_FIXES
    }

    total_day_kcal = 0.0
    for row in rows:
        item = dict(row)
        meal = item["meal_type"]
        if meal not in menus:
            menus[meal] = {"name": meal, "total_kcal": 0.0, "entries": []}
        menus[meal]["entries"].append(item)
        menus[meal]["total_kcal"] = round(menus[meal]["total_kcal"] + item["kcal_calculated"], 1)
        total_day_kcal += item["kcal_calculated"]

    return {
        "date": entry_date,
        "total_kcal": round(total_day_kcal, 1),
        "menus": [menus[menu] for menu in MENUS_FIXES],
    }


def delete_meal_entry(entry_id: int) -> bool:
    """Supprime une ligne de repas par son identifiant."""
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM meal_entries WHERE id = ?", (entry_id,))
        conn.commit()
        return cursor.rowcount > 0


def get_recent_history(limit: int = 30) -> List[Dict[str, Any]]:
    """Retourne les jours enregistrés les plus récents avec leur total de calories."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT entry_date, ROUND(SUM(kcal_calculated), 1) AS total_kcal, COUNT(*) AS items_count
            FROM meal_entries
            GROUP BY entry_date
            ORDER BY entry_date DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]
