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

import auth
import ciqual
import db
import openfoodfacts

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

# Configurable par variables d'environnement pour faciliter un futur déploiement sur serveur
HOST = os.environ.get("CALORIA_HOST", "127.0.0.1")
PORT = int(os.environ.get("CALORIA_PORT", "8000"))


class CalorIAHandler(BaseHTTPRequestHandler):
    """Gère toutes les requêtes HTTP (pages HTML/CSS/JS et routes API JSON)."""

    def _is_https(self) -> bool:
        """Détecte si l'appli est derrière un proxy HTTPS (Nginx, Caddy, Render, etc.)."""
        return self.headers.get("X-Forwarded-Proto", "").lower() == "https"

    def _current_user(self) -> Optional[Dict[str, Any]]:
        """Retourne l'utilisateur connecté via son cookie de session, ou None."""
        token = auth.extract_session_token(self.headers.get("Cookie"))
        return db.get_user_by_session(token) if token else None

    def _require_api_user(self) -> Optional[Dict[str, Any]]:
        """Vérifie la session pour une route API ; renvoie 401 sinon."""
        user = self._current_user()
        if not user:
            self._send_json(401, {"error": "Authentification requise."})
            return None
        return user

    def _redirect(self, location: str) -> None:
        """Redirige le navigateur vers une autre URL."""
        self.send_response(302)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _send_json(
        self,
        status_code: int,
        data: Any,
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> None:
        """Envoie une réponse au format JSON."""
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        if extra_headers:
            for k, v in extra_headers.items():
                self.send_header(k, v)
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

        # Page de connexion (publique)
        if path == "/login":
            if self._current_user():
                self._redirect("/")
                return
            self._send_file(os.path.join(STATIC_DIR, "login.html"))
            return

        # Indique uniquement à la page /login si les comptes ont déjà été créés
        if path == "/api/auth/status":
            self._send_json(200, {"has_users": db.count_users() > 0})
            return

        # CSS nécessaire aussi pour la page /login
        if path == "/static/style.css":
            self._send_file(os.path.join(STATIC_DIR, "style.css"))
            return

        # Page d'accueil protégée : redirige vers /login si non connecté
        if path == "/":
            if not self._current_user():
                self._redirect("/login")
                return
            self._send_file(os.path.join(STATIC_DIR, "index.html"))
            return

        # Fichiers JS dans /static/ (protégés)
        if path.startswith("/static/"):
            if not self._require_api_user():
                return
            rel_path = os.path.normpath(path[len("/static/"):]).lstrip(os.sep)
            target = os.path.abspath(os.path.join(STATIC_DIR, rel_path))
            # Sécurité : empêcher de sortir du dossier static/
            if not target.startswith(os.path.abspath(STATIC_DIR)):
                self._send_json(403, {"error": "Accès refusé."})
                return
            self._send_file(target)
            return

        # Toutes les routes API ci-dessous nécessitent d'être authentifié
        user = self._require_api_user()
        if not user:
            return

        # Informations et objectifs de l'utilisateur connecté
        if path == "/api/me":
            self._send_json(200, {"user": user})
            return

        # Résumé d'une journée pour cet utilisateur (+ aperçu du partenaire pour copie item par item)
        if path == "/api/day":
            today = datetime.date.today().isoformat()
            entry_date = params.get("date", [today])[0]
            summary = db.get_day_summary(entry_date, user["id"])
            summary["partner"] = db.get_partner_day_summary(entry_date, user["id"])
            self._send_json(200, summary)
            return

        # Historique des jours enregistrés pour cet utilisateur
        if path == "/api/history":
            self._send_json(200, {"days": db.get_recent_history(user["id"])})
            return

        # Recherche dans le catalogue partagé SQLite + table Ciqual hors ligne
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
    # Routes POST (connexion, déconnexion, création d'aliments et ajout aux menus)
    # ------------------------------------------------------------------
    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        data = self._read_json_body()

        if data is None:
            self._send_json(400, {"error": "Corps JSON invalide."})
            return

        # Connexion (route publique)
        if path == "/api/login":
            username = str(data.get("username", "")).strip()
            password = str(data.get("password", ""))
            user_record = db.get_user_by_username(username) if username else None
            if not user_record or not auth.verify_password(password, user_record["password_hash"]):
                self._send_json(401, {"error": "Identifiant ou mot de passe incorrect."})
                return

            token = auth.generate_session_token()
            db.create_session(token, user_record["id"], auth.get_session_expiration_iso())
            cookie_val = auth.build_session_cookie(token, is_https=self._is_https())
            safe_user = db.get_user_by_id(user_record["id"])
            self._send_json(200, {"user": safe_user}, extra_headers={"Set-Cookie": cookie_val})
            return

        # Déconnexion
        if path == "/api/logout":
            token = auth.extract_session_token(self.headers.get("Cookie"))
            if token:
                db.delete_session(token)
            cookie_val = auth.build_logout_cookie(is_https=self._is_https())
            self._send_json(200, {"ok": True}, extra_headers={"Set-Cookie": cookie_val})
            return

        # Routes protégées ci-dessous
        user = self._require_api_user()
        if not user:
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

        # Copier un aliment précis depuis le menu de l'autre utilisateur vers son propre menu
        if path == "/api/entries/copy":
            try:
                source_entry_id = int(data.get("source_entry_id"))
            except (TypeError, ValueError):
                self._send_json(400, {"error": "Identifiant d'aliment à copier invalide."})
                return

            target_date = str(data.get("entry_date") or datetime.date.today().isoformat()).strip()
            target_meal_type = data.get("meal_type")
            if target_meal_type is not None and target_meal_type not in db.MENUS_FIXES:
                self._send_json(400, {"error": "Menu cible invalide."})
                return

            copied = db.copy_meal_entry(source_entry_id, user["id"], target_date, target_meal_type)
            if not copied:
                self._send_json(404, {"error": "Aliment source introuvable."})
                return

            self._send_json(201, {"entry": copied})
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
                user_id=user["id"],
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
    # Route PUT (modification de la quantité ou du menu d'une ligne)
    # ------------------------------------------------------------------
    def do_PUT(self) -> None:
        user = self._require_api_user()
        if not user:
            return

        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path.startswith("/api/entries/"):
            raw_id = path[len("/api/entries/"):].strip("/")
            try:
                entry_id = int(raw_id)
            except ValueError:
                self._send_json(400, {"error": "Identifiant invalide."})
                return

            data = self._read_json_body()
            if data is None:
                self._send_json(400, {"error": "Corps JSON invalide."})
                return

            meal_type = str(data.get("meal_type", "")).strip()
            if meal_type not in db.MENUS_FIXES:
                self._send_json(400, {"error": "Menu invalide."})
                return

            try:
                quantity = float(data.get("quantity"))
                if quantity <= 0:
                    raise ValueError()
            except (TypeError, ValueError):
                self._send_json(400, {"error": "La quantité doit être supérieure à 0."})
                return

            updated = db.update_meal_entry(entry_id, quantity, meal_type, user["id"])
            if not updated:
                self._send_json(404, {"error": "Entrée introuvable."})
                return

            self._send_json(200, {"entry": updated})
            return

        self._send_json(404, {"error": "Route inconnue."})

    # ------------------------------------------------------------------
    # Route DELETE (suppression d'une ligne de repas)
    # ------------------------------------------------------------------
    def do_DELETE(self) -> None:
        user = self._require_api_user()
        if not user:
            return

        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path.startswith("/api/entries/"):
            raw_id = path[len("/api/entries/"):].strip("/")
            try:
                entry_id = int(raw_id)
            except ValueError:
                self._send_json(400, {"error": "Identifiant invalide."})
                return

            deleted = db.delete_meal_entry(entry_id, user["id"])
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
