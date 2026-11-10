"""
ciqual.py — Importation de la table officielle française ANSES Ciqual (2025).

Ce script lit le fichier `ciqual_2025.xlsx` uniquement avec les modules intégrés
à Python (`zipfile`, `xml.etree.ElementTree`, `unicodedata`) — sans aucune librairie externe.
Il alimente la table `ciqual_foods` de `caloria.db` pour disposer hors ligne
de ~3 400 aliments courants, pains de boulangerie, plats cuisinés et boissons.
"""

import os
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from typing import Dict, List, Optional, Tuple

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_XLSX_PATH = os.path.join(BASE_DIR, "ciqual_2025.xlsx")


def normalize_text(text: str) -> str:
    """
    Met en minuscules et retire les accents (ex: 'Pâté' -> 'pate').
    Permet de rechercher facilement même sans taper les accents.
    """
    decomposed = unicodedata.normalize("NFKD", text.lower())
    without_accents = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(without_accents.split())


def _parse_ciqual_number(raw: str) -> Optional[float]:
    """
    Convertit une valeur Ciqual (ex: '57,1', '0,8', 'traces', '-') en float.
    Renvoie None si la donnée est absente ('-').
    """
    val = (raw or "").strip().lower()
    if not val or val == "-":
        return None
    if val == "traces":
        return 0.0
    val = val.lstrip("<").strip().replace(",", ".")
    try:
        num = float(val)
        return round(num, 1) if num >= 0 else None
    except ValueError:
        return None


def read_ciqual_xlsx(xlsx_path: str = DEFAULT_XLSX_PATH) -> List[Tuple[str, str, str, float, str]]:
    """
    Lit `ciqual_2025.xlsx` et retourne une liste de tuples :
        (alim_code, name, group_name, kcal_per_100g, search_text)

    Colonnes connues du fichier officiel Ciqual 2025 (feuille 1) :
    - D : alim_grp_nom_fr (groupe d'aliments)
    - G : alim_code
    - H : alim_nom_fr (nom de l'aliment)
    - J : Energie (kJ / 100 g)
    - K : Energie Règlement UE 1169/2011 (kcal / 100 g)
    - M : Energie facteur Jones (kcal / 100 g)
    """
    if not os.path.isfile(xlsx_path):
        return []

    foods: List[Tuple[str, str, str, float, str]] = []

    with zipfile.ZipFile(xlsx_path, "r") as zf:
        # 1. Lecture de la table des chaînes partagées (format interne des fichiers .xlsx)
        shared_strings: List[str] = []
        if "xl/sharedStrings.xml" in zf.namelist():
            ss_root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            for si in ss_root:
                text = "".join(t.text or "" for t in si.iter() if t.tag.endswith("}t"))
                shared_strings.append(text)

        # 2. Lecture des lignes de la première feuille
        sheet_root = ET.fromstring(zf.read("xl/worksheets/sheet1.xml"))
        for row_idx, row in enumerate(sheet_root.iter()):
            if not row.tag.endswith("}row"):
                continue

            cols: Dict[str, str] = {}
            for cell in row:
                ref = cell.attrib.get("r", "")
                col_letter = "".join(ch for ch in ref if ch.isalpha())
                cell_type = cell.attrib.get("t")
                val_el = next((ch for ch in cell if ch.tag.endswith("}v")), None)
                if val_el is not None and val_el.text is not None:
                    if cell_type == "s":
                        cols[col_letter] = shared_strings[int(val_el.text)]
                    else:
                        cols[col_letter] = val_el.text

            # On saute la ligne d'en-tête (ligne 0)
            if row_idx == 0:
                continue

            code = " ".join((cols.get("G") or "").split())
            name = " ".join((cols.get("H") or "").split())
            group_name = " ".join((cols.get("D") or "").split())
            if not name or not code:
                continue

            # On cherche les kcal dans la colonne K, sinon M, sinon kJ (colonne J) / 4.184
            kcal = _parse_ciqual_number(cols.get("K", ""))
            if kcal is None:
                kcal = _parse_ciqual_number(cols.get("M", ""))
            if kcal is None:
                kj = _parse_ciqual_number(cols.get("J", ""))
                if kj is not None:
                    kcal = round(kj / 4.184, 1)

            if kcal is None:
                continue

            search_text = normalize_text(f"{name} {group_name}")
            foods.append((code, name, group_name, kcal, search_text))

    return foods


if __name__ == "__main__":
    import db

    db.init_db()
    items = read_ciqual_xlsx()
    count = db.import_ciqual_foods(items)
    print(f"Import Ciqual terminé : {count} aliments disponibles hors ligne.")
