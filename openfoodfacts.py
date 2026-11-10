"""
openfoodfacts.py — Recherche gratuite de produits sur Open Food Facts.

Utilise uniquement la bibliothèque standard Python (`urllib.request`, `json`)
sans aucun module externe ni clé API.
"""

import json
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional


# Nouveau moteur de recherche rapide Open Food Facts (Search-a-licious)
# Remplace l'ancien cgi/search.pl qui renvoyait souvent des erreurs 503.
OFF_SEARCH_URL = "https://search.openfoodfacts.org/search"

# En-tête recommandé par Open Food Facts pour identifier poliment l'application
USER_AGENT = "CalorIA/1.0 (application web locale Python)"


def _to_float(value: Any) -> Optional[float]:
    """Convertit prudemment une valeur en nombre flottant, ou renvoie None."""
    if value is None or value == "":
        return None
    try:
        num = float(str(value).replace(",", "."))
        return num if num >= 0 else None
    except (ValueError, TypeError):
        return None


def _extract_kcal_per_100g(nutriments: Dict[str, Any]) -> Optional[float]:
    """
    Extrait les calories pour 100g depuis le bloc `nutriments` d'Open Food Facts.
    Si seules les kilojoules (kJ) sont fournies, convertit en kcal (1 kcal ≈ 4,184 kJ).
    """
    kcal = _to_float(nutriments.get("energy-kcal_100g"))
    if kcal is not None and kcal > 0:
        return round(kcal, 1)

    kj = _to_float(nutriments.get("energy-kj_100g"))
    if kj is not None and kj > 0:
        return round(kj / 4.184, 1)

    energy = _to_float(nutriments.get("energy_100g"))
    if energy is not None and energy > 0:
        unit = str(nutriments.get("energy_unit", "kJ")).lower()
        if unit == "kcal":
            return round(energy, 1)
        return round(energy / 4.184, 1)

    return None


def _extract_portion(product: Dict[str, Any]) -> tuple:
    """
    Tente de lire le nom et le poids en grammes d'une portion si Open Food Facts l'indique.
    Renvoie (portion_name, portion_grams).
    """
    serving_size = str(product.get("serving_size") or "").strip()
    serving_qty = _to_float(product.get("serving_quantity"))

    if serving_qty and serving_qty > 0:
        label = serving_size if serving_size else "portion"
        return label, round(serving_qty, 1)

    # Si `serving_size` contient par exemple "1 tranche (30 g)" ou "30g"
    if serving_size:
        match = re.search(r"(\d+(?:[.,]\d+)?)\s*(g|ml)\b", serving_size.lower())
        if match:
            grams = _to_float(match.group(1))
            if grams and grams > 0:
                return serving_size, round(grams, 1)

    return "", None


def search_openfoodfacts(query: str, limit: int = 15) -> Dict[str, Any]:
    """
    Interroge Open Food Facts avec un mot-clé et retourne une liste propre de produits.
    Retourne {"results": [...], "error": None} ou {"results": [], "error": "...message..."}.
    """
    terme = query.strip()
    if not terme:
        return {"results": [], "error": "Veuillez saisir un nom de produit à rechercher."}

    # Paramètres envoyés au moteur Search-a-licious d'Open Food Facts
    params = urllib.parse.urlencode(
        {
            "q": terme,
            "page_size": limit,
            "langs": "fr",
            "fields": "code,product_name,product_name_fr,brands,nutriments,serving_size,serving_quantity",
        }
    )
    url = f"{OFF_SEARCH_URL}?{params}"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})

    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            raw_data = response.read().decode("utf-8")
            payload = json.loads(raw_data)
    except urllib.error.HTTPError as exc:
        return {
            "results": [],
            "error": f"Open Food Facts est temporairement indisponible (erreur HTTP {exc.code}). Utilisez la table Ciqual hors ligne ou l'ajout manuel.",
        }
    except urllib.error.URLError as exc:
        # Gestion claire si pas d'internet ou certificat SSL macOS absent sur Python système
        if isinstance(exc.reason, ssl.SSLError):
            return {
                "results": [],
                "error": "Erreur de certificat SSL lors de l'appel à Open Food Facts sur ce Mac. Utilisez la table Ciqual hors ligne ou l'ajout manuel.",
            }
        return {"results": [], "error": "Impossible de joindre Open Food Facts (vérifiez votre connexion internet)."}
    except Exception:
        return {"results": [], "error": "Erreur inattendue lors de la lecture de la réponse Open Food Facts."}

    produits_propres: List[Dict[str, Any]] = []
    for prod in payload.get("hits", []):
        nom = (prod.get("product_name_fr") or prod.get("product_name") or "").strip()
        if not nom:
            continue

        nutriments = prod.get("nutriments") or {}
        kcal_100g = _extract_kcal_per_100g(nutriments)
        # On ignore les fiches sans aucune info calorique exploitable
        if kcal_100g is None:
            continue

        raw_brands = prod.get("brands")
        if isinstance(raw_brands, list):
            marque = str(raw_brands[0]).strip() if raw_brands else ""
        else:
            marque = str(raw_brands or "").split(",")[0].strip()
        portion_name, portion_grams = _extract_portion(prod)

        produits_propres.append(
            {
                "name": nom,
                "brand": marque,
                "kcal_per_100g": kcal_100g,
                "portion_name": portion_name,
                "portion_grams": portion_grams,
                "source": "openfoodfacts",
                "external_code": str(prod.get("code") or "") or None,
            }
        )

    return {"results": produits_propres, "error": None}
