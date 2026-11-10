"""
app.py — Serveur web local de CalorIA.

Ce script lance un petit serveur web sur votre ordinateur (http://127.0.0.1:8000)
en utilisant uniquement les modules intégrés à Python (`http.server`, `json`, `urllib`).

Pour démarrer l'application :
    python3 app.py
Puis ouvrez http://127.0.0.1:8000 dans votre navigateur.
"""

import datetime
import json
import mimetypes
import os
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Optional

import ciqual
import db
import openfoodfacts

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

HOST = "127.0.0.1"
PORT = 8000


class CalorIAHandler(BaseHTTPRequestHandler):
    """Gère toutes les requêtes HTTP (pages HTML/CSS/JS et routes API JSON)."""

    def _send_json(self, status_code: int, data: Any) -> None:
        """Envoie une réponse au format JSON."""
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, file_path: str) -> None:
        """Envoie un fichier statique (HTML, CSS ou JS) au navigateur."""
        if not os.path.isfile(file_path):
            self._send_json(404, {"error": "Fichier introuvable."})
            return

        content_type, _ = mimetypes.guess_type(file_path)
        if not content_type:
            content_type = "application/octet-stream"
        if content_type.startswith("text/") or content_type == "application/javascript":
            content_type = f"{content_type}; charset=utf-8"

        with open(file_path, "rb") as f:
            content = f.read()

        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _read_json_body(self) -> Optional[Dict[str, Any]]:
        """Lit et décode le corps JSON d'une requête POST."""
        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8")
            return json.loads(raw) if raw else {}
        except Exception:
            return None

    def log_message(self, format: str, *args: Any) -> None:
        """Allège les logs affichés dans le terminal pour rester lisible."""
        print(f"[CalorIA] {self.address_string()} - {format % args}")

    # ------------------------------------------------------------------
    # Routes GET (lecture de la page et des données)
    # ------------------------------------------------------------------
    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        params = urllib.parse.parse_qs(parsed.query)

        # Page d'accueil
        if path == "/":
            self._send_file(os.path.join(STATIC_DIR, "index.html"))
            return

        # Fichiers CSS et JS dans /static/
        if path.startswith("/static/"):
            rel_path = os.path.normpath(path[len("/static/"):]).lstrip(os.sep)
            target = os.path.abspath(os.path.join(STATIC_DIR, rel_path))
            # Sécurité : empêcher de sortir du dossier static/
            if not target.startswith(os.path.abspath(STATIC_DIR)):
                self._send_json(403, {"error": "Accès refusé."})
                return
            self._send_file(target)
            return

        # Résumé d'une journée (par défaut : aujourd'hui)
        if path == "/api/day":
            today = datetime.date.today().isoformat()
            entry_date = params.get("date", [today])[0]
            self._send_json(200, db.get_day_summary(entry_date))
            return

        # Historique des jours enregistrés
        if path == "/api/history":
            self._send_json(200, {"days": db.get_recent_history()})
            return

        # Recherche dans le catalogue local SQLite + table Ciqual hors ligne
        if path == "/api/foods":
            query = params.get("q", [""])[0]
            ciqual_results = db.search_ciqual_foods(query) if query.strip() else []
            self._send_json(
                200,
                {
                    "foods": db.search_local_foods(query),
                    "ciqual": ciqual_results,
                },
            )
            return

        # Recherche en direct sur Open Food Facts
        if path == "/api/openfoodfacts":
            query = params.get("q", [""])[0]
            result = openfoodfacts.search_openfoodfacts(query)
            self._send_json(200, result)
            return

        self._send_json(404, {"error": "Route inconnue."})

    # ------------------------------------------------------------------
    # Routes POST (création d'aliments et ajout aux menus)
    # ------------------------------------------------------------------
    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        data = self._read_json_body()

        if data is None:
            self._send_json(400, {"error": "Corps JSON invalide."})
            return

        # Créer un aliment manuellement dans le catalogue local
        if path == "/api/foods":
            name = str(data.get("name", "")).strip()
            brand = str(data.get("brand", "")).strip()
            portion_name = str(data.get("portion_name", "")).strip()

            try:
                kcal_per_100g = float(data.get("kcal_per_100g"))
                if kcal_per_100g < 0:
                    raise ValueError()
            except (TypeError, ValueError):
                self._send_json(400, {"error": "Veuillez indiquer un nombre valide de kcal pour 100g."})
                return

            if not name:
                self._send_json(400, {"error": "Le nom de l'aliment est obligatoire."})
                return

            portion_grams = None
            raw_pg = data.get("portion_grams")
            if raw_pg not in (None, ""):
                try:
                    portion_grams = float(raw_pg)
                    if portion_grams <= 0:
                        raise ValueError()
                except (TypeError, ValueError):
                    self._send_json(400, {"error": "Le poids d'une portion doit être supérieur à 0."})
                    return

            food = db.save_food(
                name=name,
                brand=brand,
                kcal_per_100g=kcal_per_100g,
                portion_name=portion_name,
                portion_grams=portion_grams,
                source="manuel",
            )
            self._send_json(201, {"food": food})
            return

        # Ajouter un aliment consommé dans un menu d'une journée
        if path == "/api/entries":
            entry_date = str(data.get("entry_date") or datetime.date.today().isoformat()).strip()
            meal_type = str(data.get("meal_type", "")).strip()
            unit = str(data.get("unit", "g")).strip()

            if meal_type not in db.MENUS_FIXES:
                self._send_json(400, {"error": "Menu invalide."})
                return

            if unit not in ("g", "portion"):
                self._send_json(400, {"error": "Unité invalide (utilisez 'g' ou 'portion')."})
                return

            try:
                quantity = float(data.get("quantity"))
                if quantity <= 0:
                    raise ValueError()
            except (TypeError, ValueError):
                self._send_json(400, {"error": "La quantité doit être supérieure à 0."})
                return

            # On récupère l'aliment soit par son ID local, soit en mémorisant le produit Open Food Facts
            food = None
            food_id = data.get("food_id")
            if food_id is not None:
                food = db.get_food_by_id(int(food_id))
                if not food:
                    self._send_json(404, {"error": "Aliment introuvable dans le catalogue local."})
                    return
            elif isinstance(data.get("food"), dict):
                off_food = data["food"]
                try:
                    kcal_100 = float(off_food.get("kcal_per_100g"))
                except (TypeError, ValueError):
                    self._send_json(400, {"error": "Valeur calorique du produit invalide."})
                    return

                food = db.save_food(
                    name=str(off_food.get("name", "")).strip() or "Produit",
                    brand=str(off_food.get("brand", "")).strip(),
                    kcal_per_100g=kcal_100,
                    portion_name=str(off_food.get("portion_name", "")).strip(),
                    portion_grams=off_food.get("portion_grams"),
                    source=str(off_food.get("source", "openfoodfacts")),
                    external_code=off_food.get("external_code"),
                )
            else:
                self._send_json(400, {"error": "Aucun aliment sélectionné."})
                return

            # Calcul de l'équivalent en grammes selon l'unité choisie
            if unit == "g":
                grams_equivalent = quantity
            else:
                # Si l'utilisatrice saisit un poids de portion personnalisé, on l'enregistre sur l'aliment
                custom_pg = data.get("custom_portion_grams")
                if custom_pg not in (None, ""):
                    try:
                        portion_grams = float(custom_pg)
                        if portion_grams <= 0:
                            raise ValueError()
                    except (TypeError, ValueError):
                        self._send_json(400, {"error": "Le poids de la portion doit être supérieur à 0."})
                        return
                    portion_label = food.get("portion_name") or "portion"
                    food = db.update_food_portion(food["id"], portion_label, portion_grams) or food
                else:
                    portion_grams = food.get("portion_grams")

                if not portion_grams or portion_grams <= 0:
                    self._send_json(
                        400,
                        {"error": "Ce produit n'a pas encore de poids de portion. Indiquez le poids d'1 portion en grammes."},
                    )
                    return
                grams_equivalent = quantity * float(portion_grams)

            # Formule finale des calories consommées
            kcal_calculated = (grams_equivalent / 100.0) * float(food["kcal_per_100g"])

            entry = db.add_meal_entry(
                entry_date=entry_date,
                meal_type=meal_type,
                food_id=food["id"],
                food_name=food["name"],
                food_brand=food.get("brand", ""),
                unit=unit,
                quantity=quantity,
                grams_equivalent=grams_equivalent,
                kcal_calculated=kcal_calculated,
            )
            self._send_json(201, {"entry": entry, "food": food})
            return

        self._send_json(404, {"error": "Route inconnue."})

    # ------------------------------------------------------------------
    # Route DELETE (suppression d'une ligne de repas)
    # ------------------------------------------------------------------
    def do_DELETE(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path.startswith("/api/entries/"):
            raw_id = path[len("/api/entries/"):].strip("/")
            try:
                entry_id = int(raw_id)
            except ValueError:
                self._send_json(400, {"error": "Identifiant invalide."})
                return

            deleted = db.delete_meal_entry(entry_id)
            if not deleted:
                self._send_json(404, {"error": "Entrée introuvable."})
                return

            self._send_json(200, {"deleted": True})
            return

        self._send_json(404, {"error": "Route inconnue."})


def main() -> None:
    """Initialise la base SQLite (et importe Ciqual si nécessaire) puis démarre le serveur."""
    db.init_db()
    if db.ciqual_count() == 0 and os.path.isfile(ciqual.DEFAULT_XLSX_PATH):
        print("Import initial de la table Ciqual en cours...")
        items = ciqual.read_ciqual_xlsx()
        count = db.import_ciqual_foods(items)
        print(f"Table Ciqual importée ({count} aliments prêts hors ligne).")

    server = ThreadingHTTPServer((HOST, PORT), CalorIAHandler)
    print(f"CalorIA est lancé sur : http://{HOST}:{PORT}")
    print("Appuyez sur Ctrl+C pour arrêter le serveur.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nArrêt de CalorIA.")
        server.server_close()


if __name__ == "__main__":
    main()
