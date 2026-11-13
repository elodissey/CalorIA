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

# Chemin complet vers le fichier de base de données (configurable via CALORIA_DB_PATH pour un serveur)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("CALORIA_DB_PATH") or os.path.join(BASE_DIR, "caloria.db")

# Les 4 menus fixes validés pour chaque journée
MENUS_FIXES = ("Petit-déjeuner", "Déjeuner", "Dîner", "Collation")


def get_connection() -> sqlite3.Connection:
    """Ouvre une connexion SQLite configurée pour renvoyer des dictionnaires."""
    conn = sqlite3.connect(DB_PATH)
    # Permet d'accéder aux colonnes par leur nom (ex: row["name"]) au lieu d'un index
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """Crée les tables si elles n'existent pas encore (base vide au démarrage)."""
    # Crée le dossier parent de la base si besoin (utile dans Docker avec /app/data/caloria.db)
    db_dir = os.path.dirname(os.path.abspath(DB_PATH))
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
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
        # Chaque ligne appartient à un utilisateur (`user_id`), mais `foods` reste partagé.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS meal_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER DEFAULT NULL,
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

        # Migration douce : si la base existait déjà avant l'ajout de `user_id`, on ajoute la colonne sans rien effacer
        existing_cols = [r["name"] for r in conn.execute("PRAGMA table_info(meal_entries)").fetchall()]
        if "user_id" not in existing_cols:
            conn.execute("ALTER TABLE meal_entries ADD COLUMN user_id INTEGER DEFAULT NULL")

        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_entries_user_date ON meal_entries(user_id, entry_date)"
        )

        # Table 3 : Référentiel officiel français ANSES Ciqual (hors ligne, partagé)
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

        # Table 4 : Utilisateurs autorisés (gérés via le script users.py, pas d'inscription publique)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                goal_min INTEGER NOT NULL DEFAULT 1650,
                goal_max INTEGER NOT NULL DEFAULT 1750,
                ref_kcal INTEGER NOT NULL DEFAULT 1990,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # Table 5 : Sessions de connexion actives
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                expires_at TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """
        )

        # Table 6 : Aliments favoris par utilisateur (Option A - Étoiles favoris)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS favorites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                food_id INTEGER NOT NULL,
                default_meal TEXT DEFAULT NULL,
                default_qty REAL DEFAULT 100,
                default_unit TEXT DEFAULT 'g',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (food_id) REFERENCES foods(id) ON DELETE CASCADE,
                UNIQUE(user_id, food_id)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_favorites_user ON favorites(user_id)"
        )
        conn.commit()


# ------------------------------------------------------------------
# Gestion des utilisateurs et des sessions
# ------------------------------------------------------------------

def count_users() -> int:
    """Retourne le nombre de comptes créés."""
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS cnt FROM users").fetchone()
    return int(row["cnt"]) if row else 0


def list_users() -> List[Dict[str, Any]]:
    """Liste les utilisateurs sans jamais exposer leurs mots de passe."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, username, goal_min, goal_max, ref_kcal, created_at FROM users ORDER BY id ASC"
        ).fetchall()
    return [dict(row) for row in rows]


def get_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    """Récupère un utilisateur complet (avec password_hash) pour vérifier sa connexion."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE LOWER(username) = LOWER(?) LIMIT 1",
            (username.strip(),),
        ).fetchone()
    return dict(row) if row else None


def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    """Récupère les informations publiques d'un utilisateur."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, username, goal_min, goal_max, ref_kcal FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    return dict(row) if row else None


def create_user(
    username: str,
    password_hash: str,
    goal_min: int = 1650,
    goal_max: int = 1750,
    ref_kcal: int = 1990,
) -> Tuple[Dict[str, Any], int]:
    """
    Crée un utilisateur et lui rattache automatiquement d'éventuelles anciennes entrées
    (`user_id IS NULL`) pour ne jamais perdre de données déjà saisies avant le multi-utilisateurs.
    Retourne (user_dict, nombre_entrees_rattachees).
    """
    clean_name = username.strip()
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO users (username, password_hash, goal_min, goal_max, ref_kcal)
            VALUES (?, ?, ?, ?, ?)
            """,
            (clean_name, password_hash, int(goal_min), int(goal_max), int(ref_kcal)),
        )
        user_id = cursor.lastrowid
        # S'il reste des repas enregistrés avant l'activation des comptes, on les attribue à ce compte
        adopted = conn.execute(
            "UPDATE meal_entries SET user_id = ? WHERE user_id IS NULL",
            (user_id,),
        ).rowcount
        conn.commit()

    user = get_user_by_id(user_id)  # type: ignore[arg-type]
    return user, int(adopted or 0)  # type: ignore[return-value]


def update_user_password(username: str, password_hash: str) -> bool:
    """Met à jour le mot de passe d'un utilisateur existant."""
    with get_connection() as conn:
        cursor = conn.execute(
            "UPDATE users SET password_hash = ? WHERE LOWER(username) = LOWER(?)",
            (password_hash, username.strip()),
        )
        conn.commit()
        return cursor.rowcount > 0


def update_user_goals(username: str, goal_min: int, goal_max: int, ref_kcal: int) -> bool:
    """Met à jour les objectifs et le repère calorique d'un utilisateur."""
    with get_connection() as conn:
        cursor = conn.execute(
            """
            UPDATE users
            SET goal_min = ?, goal_max = ?, ref_kcal = ?
            WHERE LOWER(username) = LOWER(?)
            """,
            (int(goal_min), int(goal_max), int(ref_kcal), username.strip()),
        )
        conn.commit()
        return cursor.rowcount > 0


def create_session(token: str, user_id: int, expires_at: str) -> None:
    """Enregistre une session de connexion en base."""
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
            (token, user_id, expires_at),
        )
        conn.commit()


def get_user_by_session(token: str) -> Optional[Dict[str, Any]]:
    """Retourne l'utilisateur lié au jeton s'il est valide et non expiré."""
    if not token:
        return None
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT u.id, u.username, u.goal_min, u.goal_max, u.ref_kcal, s.expires_at
            FROM sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.token = ?
            """,
            (token,),
        ).fetchone()
        if not row:
            return None

        # Vérifie si la session n'a pas expiré (comparaison ISO UTC)
        import datetime

        now_iso = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        if row["expires_at"] <= now_iso:
            conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
            conn.commit()
            return None

        return {
            "id": row["id"],
            "username": row["username"],
            "goal_min": row["goal_min"],
            "goal_max": row["goal_max"],
            "ref_kcal": row["ref_kcal"],
        }


def delete_session(token: str) -> None:
    """Supprime une session lors de la déconnexion."""
    if not token:
        return
    with get_connection() as conn:
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
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


def _word_variants(word: str) -> List[str]:
    """Renvoie le mot et son singulier simple si le mot finit par 's' ou 'x'."""
    variants = [word]
    if len(word) > 3 and word.endswith("s"):
        variants.append(word[:-1])
    elif len(word) > 4 and word.endswith("x"):
        variants.append(word[:-1])
    return variants


def search_ciqual_foods(query: str, limit: int = 40) -> List[Dict[str, Any]]:
    """
    Recherche dans la table Ciqual hors ligne (sans accents et tolérante aux pluriels).
    Si la recherche contient plusieurs mots (ex: 'fruits pommes cuites'), tous les mots
    doivent apparaître dans le nom ou le groupe, et les aliments dont le nom commence par
    un mot recherché (ex: 'Pomme, ...') sont classés en premier.
    """
    norm = ciqual.normalize_text(query)
    words = norm.split()
    if not words:
        return []

    clauses: List[str] = []
    params: List[Any] = []
    word_variants_list = [_word_variants(w) for w in words]

    for variants in word_variants_list:
        or_parts = " OR ".join("search_text LIKE ?" for _ in variants)
        clauses.append(f"({or_parts})")
        params.extend(f"%{v}%" for v in variants)

    where_sql = " AND ".join(clauses)

    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT alim_code, name, group_name, kcal_per_100g
            FROM ciqual_foods
            WHERE {where_sql}
            ORDER BY LENGTH(name) ASC
            LIMIT 100
            """,
            params,
        ).fetchall()

    # Classement simple : privilégie les noms qui commencent exactement par un des mots tapés
    all_variants = [v for variants in word_variants_list for v in variants]

    def _rank(row: sqlite3.Row) -> tuple:
        nom_norm = ciqual.normalize_text(row["name"])
        starts_exact = any(
            nom_norm == v or nom_norm.startswith(f"{v},") or nom_norm.startswith(f"{v} ")
            for v in all_variants
        )
        starts_prefix = any(nom_norm.startswith(v) for v in all_variants)
        # Priorité 0 : commence par "mot," (ex: "Pomme, ...") ; 1 : commence par le mot ; 2 : ailleurs
        starts_comma = any(nom_norm == v or nom_norm.startswith(f"{v},") for v in all_variants)
        if starts_comma:
            prio = 0
        elif starts_exact:
            prio = 1
        elif starts_prefix:
            prio = 2
        else:
            prio = 3
        return (prio, len(row["name"]))

    sorted_rows = sorted(rows, key=_rank)[:limit]

    results: List[Dict[str, Any]] = []
    for row in sorted_rows:
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


def search_local_foods(query: str = "", user_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Recherche des aliments dans le catalogue local (tous si query est vide).
    Si un user_id est fourni, indique si l'aliment est dans ses favoris (is_favorite)
    et remonte les favoris en tête de liste.
    """
    with get_connection() as conn:
        if user_id:
            join_clause = "LEFT JOIN favorites f ON f.food_id = foods.id AND f.user_id = ?"
            select_extra = ", CASE WHEN f.id IS NOT NULL THEN 1 ELSE 0 END AS is_favorite"
            user_param: tuple = (user_id,)
        else:
            join_clause = ""
            select_extra = ", 0 AS is_favorite"
            user_param = ()

        if query.strip():
            motif = f"%{query.strip()}%"
            rows = conn.execute(
                f"""
                SELECT foods.id, foods.name, foods.brand, foods.kcal_per_100g, foods.portion_name,
                       foods.portion_grams, foods.source, foods.external_code{select_extra}
                FROM foods
                {join_clause}
                WHERE foods.name LIKE ? OR foods.brand LIKE ?
                ORDER BY is_favorite DESC, foods.id DESC
                LIMIT 50
                """,
                user_param + (motif, motif),
            ).fetchall()
        else:
            rows = conn.execute(
                f"""
                SELECT foods.id, foods.name, foods.brand, foods.kcal_per_100g, foods.portion_name,
                       foods.portion_grams, foods.source, foods.external_code{select_extra}
                FROM foods
                {join_clause}
                ORDER BY is_favorite DESC, foods.id DESC
                LIMIT 50
                """,
                user_param,
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
    user_id: int,
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
    """Ajoute un aliment consommé dans un menu d'une journée donnée pour cet utilisateur."""
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO meal_entries (
                user_id, entry_date, meal_type, food_id, food_name, food_brand,
                unit, quantity, grams_equivalent, kcal_calculated
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
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


def get_day_summary(entry_date: str, user_id: int) -> Dict[str, Any]:
    """
    Récupère toutes les entrées d'une journée pour un utilisateur, regroupées par les 4 menus fixes,
    ainsi que les sous-totaux par menu et le total global de la journée.
    Indique aussi pour chaque entrée si l'aliment est dans les favoris de l'utilisateur (is_favorite).
    """
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT me.id, me.user_id, me.entry_date, me.meal_type, me.food_id, me.food_name, me.food_brand,
                   me.unit, me.quantity, me.grams_equivalent, me.kcal_calculated, me.created_at,
                   CASE WHEN f.id IS NOT NULL THEN 1 ELSE 0 END AS is_favorite
            FROM meal_entries me
            LEFT JOIN favorites f ON f.food_id = me.food_id AND f.user_id = me.user_id
            WHERE me.entry_date = ? AND me.user_id = ?
            ORDER BY me.id ASC
            """,
            (entry_date, user_id),
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


def update_meal_entry(
    entry_id: int, new_quantity: float, new_meal_type: str, user_id: int
) -> Optional[Dict[str, Any]]:
    """
    Met à jour la quantité et/ou le menu d'une ligne de repas appartenant à l'utilisateur connecté,
    et recalcule automatiquement les grammes équivalents et les calories.
    """
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM meal_entries WHERE id = ? AND user_id = ?",
            (entry_id, user_id),
        ).fetchone()
        if not row:
            return None
        entry = dict(row)

    new_quantity = float(new_quantity)
    old_quantity = float(entry["quantity"])

    # Recalcul des grammes et des calories à partir de la fiche aliment liée (ou proportionnellement)
    food = get_food_by_id(entry["food_id"]) if entry.get("food_id") else None
    if entry["unit"] == "g":
        grams_equivalent = new_quantity
    elif food and food.get("portion_grams"):
        grams_equivalent = new_quantity * float(food["portion_grams"])
    elif old_quantity > 0:
        grams_equivalent = (new_quantity / old_quantity) * float(entry["grams_equivalent"])
    else:
        grams_equivalent = float(entry["grams_equivalent"])

    if food:
        kcal_calculated = (grams_equivalent / 100.0) * float(food["kcal_per_100g"])
    elif old_quantity > 0:
        kcal_calculated = (new_quantity / old_quantity) * float(entry["kcal_calculated"])
    else:
        kcal_calculated = float(entry["kcal_calculated"])

    with get_connection() as conn:
        conn.execute(
            """
            UPDATE meal_entries
            SET meal_type = ?, quantity = ?, grams_equivalent = ?, kcal_calculated = ?
            WHERE id = ? AND user_id = ?
            """,
            (
                new_meal_type,
                round(new_quantity, 2),
                round(grams_equivalent, 2),
                round(kcal_calculated, 1),
                entry_id,
                user_id,
            ),
        )
        conn.commit()
        updated = conn.execute(
            "SELECT * FROM meal_entries WHERE id = ? AND user_id = ?",
            (entry_id, user_id),
        ).fetchone()
    return dict(updated) if updated else None


def delete_meal_entry(entry_id: int, user_id: int) -> bool:
    """Supprime une ligne de repas uniquement si elle appartient à l'utilisateur connecté."""
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM meal_entries WHERE id = ? AND user_id = ?",
            (entry_id, user_id),
        )
        conn.commit()
        return cursor.rowcount > 0


def get_recent_history(user_id: int, limit: int = 30) -> List[Dict[str, Any]]:
    """Retourne les jours enregistrés les plus récents pour cet utilisateur."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT entry_date, ROUND(SUM(kcal_calculated), 1) AS total_kcal, COUNT(*) AS items_count
            FROM meal_entries
            WHERE user_id = ?
            GROUP BY entry_date
            ORDER BY entry_date DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
    return [dict(row) for row in rows]


def get_partner_day_summary(entry_date: str, current_user_id: int) -> Optional[Dict[str, Any]]:
    """
    Récupère les aliments enregistrés par l'autre utilisateur pour cette journée,
    regroupés par menu, afin de pouvoir en copier un par un dans sa propre journée.
    """
    with get_connection() as conn:
        partner = conn.execute(
            "SELECT id, username FROM users WHERE id != ? ORDER BY id ASC LIMIT 1",
            (current_user_id,),
        ).fetchone()
        if not partner:
            return None

        rows = conn.execute(
            """
            SELECT id, meal_type, food_name, food_brand, unit, quantity, grams_equivalent, kcal_calculated
            FROM meal_entries
            WHERE entry_date = ? AND user_id = ?
            ORDER BY id ASC
            """,
            (entry_date, partner["id"]),
        ).fetchall()

    by_menu: Dict[str, List[Dict[str, Any]]] = {m: [] for m in MENUS_FIXES}
    for row in rows:
        item = dict(row)
        meal = item["meal_type"]
        if meal in by_menu:
            by_menu[meal].append(item)

    return {
        "username": partner["username"],
        "by_menu": by_menu,
    }


def copy_meal_entry(
    source_entry_id: int,
    target_user_id: int,
    target_date: str,
    target_meal_type: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Copie un aliment précis depuis le journal de l'autre utilisateur vers le menu
    de l'utilisateur connecté (ajout à la suite, sans modifier la ligne d'origine).
    """
    with get_connection() as conn:
        src = conn.execute(
            "SELECT * FROM meal_entries WHERE id = ?",
            (source_entry_id,),
        ).fetchone()
        if not src:
            return None
        source = dict(src)

        meal_type = target_meal_type if target_meal_type in MENUS_FIXES else source["meal_type"]
        cursor = conn.execute(
            """
            INSERT INTO meal_entries (
                user_id, entry_date, meal_type, food_id, food_name, food_brand,
                unit, quantity, grams_equivalent, kcal_calculated
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                target_user_id,
                target_date,
                meal_type,
                source["food_id"],
                source["food_name"],
                source["food_brand"],
                source["unit"],
                source["quantity"],
                source["grams_equivalent"],
                source["kcal_calculated"],
            ),
        )
        conn.commit()
        new_id = cursor.lastrowid
        row = conn.execute("SELECT * FROM meal_entries WHERE id = ?", (new_id,)).fetchone()
    return dict(row) if row else None


# ------------------------------------------------------------------
# Gestion des favoris personnels (Option A - Étoiles favoris)
# ------------------------------------------------------------------

def list_favorites(user_id: int) -> List[Dict[str, Any]]:
    """
    Retourne la liste des aliments favoris d'un utilisateur, ordonnée par date d'ajout décroissante.
    Inclut les informations complètes de l'aliment (nom, marque, kcal, portions).
    """
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT f.id AS fav_id, f.user_id, f.food_id, f.default_meal, f.default_qty, f.default_unit,
                   f.created_at AS fav_created_at,
                   fd.name, fd.brand, fd.kcal_per_100g, fd.portion_name, fd.portion_grams,
                   fd.source, fd.external_code
            FROM favorites f
            JOIN foods fd ON fd.id = f.food_id
            WHERE f.user_id = ?
            ORDER BY f.id DESC
            """,
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_user_favorite_food_ids(user_id: int) -> List[int]:
    """Retourne la liste des identifiants d'aliments (food_id) mis en favoris par l'utilisateur."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT food_id FROM favorites WHERE user_id = ?",
            (user_id,),
        ).fetchall()
    return [int(r["food_id"]) for r in rows]


def toggle_favorite(
    user_id: int,
    food_id: int,
    default_meal: Optional[str] = None,
    default_qty: float = 100.0,
    default_unit: str = "g",
) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """
    Bascule l'état d'un aliment en favori pour un utilisateur :
    - Si l'aliment est déjà dans ses favoris : le retire et renvoie (False, None).
    - S'il n'y est pas : l'ajoute avec ses valeurs de portion/menu par défaut et renvoie (True, favori).
    """
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT * FROM favorites WHERE user_id = ? AND food_id = ? LIMIT 1",
            (user_id, food_id),
        ).fetchone()

        if existing:
            conn.execute(
                "DELETE FROM favorites WHERE id = ?",
                (existing["id"],),
            )
            conn.commit()
            return False, None

        # Nettoyage et sécurisation des valeurs par défaut
        safe_meal = default_meal if default_meal in MENUS_FIXES else None
        safe_unit = "portion" if default_unit == "portion" else "g"
        safe_qty = max(0.01, float(default_qty or 100.0))

        cursor = conn.execute(
            """
            INSERT INTO favorites (user_id, food_id, default_meal, default_qty, default_unit)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, food_id, safe_meal, safe_qty, safe_unit),
        )
        conn.commit()
        fav_id = cursor.lastrowid
        row = conn.execute("SELECT * FROM favorites WHERE id = ?", (fav_id,)).fetchone()
        return True, dict(row) if row else None


def remove_favorite(fav_id: int, user_id: int) -> bool:
    """Supprime un favori précis appartenant à l'utilisateur connecté."""
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM favorites WHERE id = ? AND user_id = ?",
            (int(fav_id), int(user_id)),
        )
        conn.commit()
        return cursor.rowcount > 0

