"""
auth.py — Gestion simple de l'authentification pour CalorIA.

Utilise uniquement la bibliothèque standard Python (`hashlib`, `hmac`, `secrets`,
`http.cookies`) sans aucune dépendance externe :
- Hachage sécurisé des mots de passe avec PBKDF2-SHA256 + sel aléatoire.
- Création et lecture de cookies de session HttpOnly.
"""

import datetime
import hashlib
import hmac
import http.cookies
import secrets
from typing import Optional

COOKIE_NAME = "caloria_session"
SESSION_DAYS = 30
PBKDF2_ITERATIONS = 200_000


def hash_password(password: str) -> str:
    """
    Transforme un mot de passe en empreinte chiffrée non réversible avec un sel aléatoire.
    Format stocké : pbkdf2_sha256$<iterations>$<salt>$<hash_hex>
    """
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        PBKDF2_ITERATIONS,
    )
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt}${digest.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Vérifie qu'un mot de passe saisi correspond bien au hash stocké en base."""
    try:
        algo, iter_str, salt, expected_hex = stored_hash.split("$", 3)
        if algo != "pbkdf2_sha256":
            return False
        iterations = int(iter_str)
    except ValueError:
        return False

    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        iterations,
    )
    return hmac.compare_digest(digest.hex(), expected_hex)


def generate_session_token() -> str:
    """Génère un jeton de session aléatoire difficile à deviner."""
    return secrets.token_urlsafe(32)


def get_session_expiration_iso(days: int = SESSION_DAYS) -> str:
    """Calcule la date d'expiration UTC d'une session au format ISO."""
    expires = datetime.datetime.utcnow() + datetime.timedelta(days=days)
    return expires.strftime("%Y-%m-%d %H:%M:%S")


def extract_session_token(cookie_header: Optional[str]) -> Optional[str]:
    """Extrait le jeton de session depuis l'en-tête HTTP Cookie."""
    if not cookie_header:
        return None
    cookie = http.cookies.SimpleCookie()
    try:
        cookie.load(cookie_header)
    except http.cookies.CookieError:
        return None
    morsel = cookie.get(COOKIE_NAME)
    return morsel.value if morsel and morsel.value else None


def build_session_cookie(token: str, is_https: bool = False, max_age: int = SESSION_DAYS * 86400) -> str:
    """
    Construit l'en-tête Set-Cookie sécurisé :
    - HttpOnly : empêche JavaScript de lire le cookie.
    - SameSite=Lax : protège contre les requêtes inter-sites (CSRF).
    - Secure : activé automatiquement quand l'appli est derrière HTTPS.
    """
    parts = [
        f"{COOKIE_NAME}={token}",
        "Path=/",
        f"Max-Age={max_age}",
        "HttpOnly",
        "SameSite=Lax",
    ]
    if is_https:
        parts.append("Secure")
    return "; ".join(parts)


def build_logout_cookie(is_https: bool = False) -> str:
    """Construit un Set-Cookie expiré pour déconnecter l'utilisateur."""
    return build_session_cookie("", is_https=is_https, max_age=0)
