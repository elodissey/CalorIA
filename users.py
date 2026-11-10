"""
users.py — Petit outil en ligne de commande pour gérer les 2 comptes de CalorIA.

Aucune page d'inscription n'existe sur le web : seuls les comptes créés avec
ce script peuvent se connecter à l'application.

Utilisation :
    python3 users.py
"""

import getpass

import auth
import db

MAX_USERS = 2


def _ask_int(prompt: str, default: int) -> int:
    """Demande un entier à l'utilisateur avec une valeur par défaut."""
    while True:
        raw = input(f"{prompt} [{default}] : ").strip()
        if not raw:
            return default
        try:
            val = int(raw)
            if val > 0:
                return val
        except ValueError:
            pass
        print("Veuillez entrer un nombre entier positif.")


def _ask_password() -> str:
    """Demande un mot de passe masqué et sa confirmation."""
    while True:
        pwd = getpass.getpass("Mot de passe : ")
        if len(pwd) < 6:
            print("Choisissez un mot de passe d'au moins 6 caractères.")
            continue
        confirm = getpass.getpass("Confirmez le mot de passe : ")
        if pwd != confirm:
            print("Les deux mots de passe ne correspondent pas, recommencez.")
            continue
        return pwd


def create_account() -> None:
    """Crée un nouveau compte (limité à 2 utilisateurs au total)."""
    if db.count_users() >= MAX_USERS:
        print(f"\nLimite atteinte : {MAX_USERS} comptes existent déjà.")
        return

    username = input("Identifiant du nouvel utilisateur (ex: alice) : ").strip()
    if not username:
        print("Identifiant vide, opération annulée.")
        return

    if db.get_user_by_username(username):
        print(f"L'utilisateur '{username}' existe déjà.")
        return

    password = _ask_password()
    goal_min = _ask_int("Objectif quotidien minimum (kcal/jour)", 1650)
    goal_max = _ask_int("Objectif quotidien maximum (kcal/jour)", 1750)
    ref_kcal = _ask_int("Repère journalier / maintien (kcal/jour)", 1990)

    pwd_hash = auth.hash_password(password)
    user, adopted = db.create_user(username, pwd_hash, goal_min, goal_max, ref_kcal)
    print(f"\nCompte '{user['username']}' créé avec succès !")
    if adopted > 0:
        print(f"-> {adopted} repas déjà enregistrés précédemment ont été rattachés à ce compte.")


def change_password() -> None:
    """Modifie le mot de passe d'un utilisateur existant."""
    username = input("Identifiant de l'utilisateur : ").strip()
    if not db.get_user_by_username(username):
        print("Utilisateur introuvable.")
        return
    password = _ask_password()
    db.update_user_password(username, auth.hash_password(password))
    print(f"Mot de passe mis à jour pour '{username}'.")


def change_goals() -> None:
    """Modifie les objectifs et le repère calorique d'un utilisateur."""
    username = input("Identifiant de l'utilisateur : ").strip()
    existing = db.get_user_by_username(username)
    if not existing:
        print("Utilisateur introuvable.")
        return
    goal_min = _ask_int("Nouvel objectif minimum (kcal/jour)", existing["goal_min"])
    goal_max = _ask_int("Nouvel objectif maximum (kcal/jour)", existing["goal_max"])
    ref_kcal = _ask_int("Nouveau repère journalier (kcal/jour)", existing["ref_kcal"])
    db.update_user_goals(username, goal_min, goal_max, ref_kcal)
    print(f"Objectifs mis à jour pour '{username}'.")


def main() -> None:
    db.init_db()
    while True:
        users = db.list_users()
        print("\n=== Gestion des comptes CalorIA ===")
        if not users:
            print("Aucun compte configuré pour l'instant.")
        else:
            for u in users:
                print(
                    f"- {u['username']} (id={u['id']}) : "
                    f"objectif {u['goal_min']}–{u['goal_max']} kcal | repère {u['ref_kcal']} kcal"
                )

        print("\n1. Créer un compte (max 2)")
        print("2. Changer un mot de passe")
        print("3. Modifier les objectifs caloriques")
        print("4. Quitter")
        choice = input("Votre choix [1-4] : ").strip()

        if choice == "1":
            create_account()
        elif choice == "2":
            change_password()
        elif choice == "3":
            change_goals()
        elif choice == "4":
            break
        else:
            print("Choix invalide.")


if __name__ == "__main__":
    main()
