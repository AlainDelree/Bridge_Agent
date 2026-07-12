"""Accesseurs à l'état partagé du bridge, stocké dans app.config.

L'état vit dans app.config (posé par create_app) et se lit à la requête via
current_app : aucune valeur n'est figée à l'import sous forme de globale de
module. Hors contexte de requête (threads daemon, gestionnaire de signal), un
contexte applicatif doit être poussé au préalable (with app.app_context()).
"""

from pathlib import Path

from flask import current_app

# Racine du projet (dossier parent du package app/).
RACINE = Path(__file__).resolve().parent.parent


def get(cle):
    """Lit une clé d'état partagé depuis app.config (contexte applicatif requis)."""
    return current_app.config[cle]


def set(cle, valeur):
    """Écrit une clé d'état partagé dans app.config (contexte applicatif requis)."""
    current_app.config[cle] = valeur


def charger_mot_de_passe() -> str:
    """Hash sha256 du mot de passe d'accès, relu depuis bridge_agent.conf.
    Chaîne vide → aucune authentification exigée."""
    # Import différé : évite une dépendance à watcher au chargement du package
    # (le sys.path est complété par new_issue.py avant tout appel).
    from watcher import charger_config

    chemin = RACINE / "configs" / "bridge_agent.conf"
    if not chemin.exists():
        return ""
    try:
        return charger_config(chemin).mot_de_passe.strip()
    except SystemExit:
        return ""
