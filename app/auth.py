"""Authentification de l'interface web (extraite de new_issue.py, étape 4).

Le mot de passe d'accès est stocké HASHÉ (sha256) dans configs/bridge_agent.conf
sous la clé MOT_DE_PASSE. Vide → interface accessible sans authentification.
Générer le hash avec :  python3 new_issue.py --set-password

Le login n'est exigé qu'en mode --externe (accès distant via tunnel) : en mode
local, devant le ThinkPad, l'accès est direct. MODE_EXTERNE et MOT_DE_PASSE
vivent dans app.config, lus à la requête via app/etat.py.

Le gabarit de la page de connexion vit dans templates/login.html, rendu via
render_template (comme index.html).
"""

import hashlib
from functools import wraps

from flask import redirect, render_template, request, session, url_for

from app import etat

MAX_ECHECS_LOGIN = 5   # nombre de tentatives avant blocage de la session


def login_requis(vue):
    """Décorateur : redirige vers /login tant que la session n'est pas
    authentifiée. Inactif si aucun mot de passe n'est configuré ou en mode
    local (login exigé uniquement en mode --externe)."""
    @wraps(vue)
    def enveloppe(*args, **kwargs):
        if (etat.get("MOT_DE_PASSE") and etat.get("MODE_EXTERNE")
                and not session.get("authentifie")):
            return redirect(url_for("login"))
        return vue(*args, **kwargs)
    return enveloppe


def login():
    """Formulaire de connexion. Redirige vers l'accueil si aucune authentification
    n'est requise ou si la session est déjà authentifiée."""
    if not etat.get("MOT_DE_PASSE") or session.get("authentifie"):
        return redirect(url_for("index"))
    bloque = session.get("echecs", 0) >= MAX_ECHECS_LOGIN
    erreur = ("Trop de tentatives échouées. Redémarrez le serveur pour réessayer."
              if bloque else "")
    return render_template("login.html", erreur=erreur, bloque=bloque)


def login_post():
    """Vérifie le mot de passe saisi (sha256) contre MOT_DE_PASSE du .conf.
    Bloque la session après MAX_ECHECS_LOGIN tentatives échouées."""
    mot_de_passe = etat.get("MOT_DE_PASSE")
    if not mot_de_passe:
        return redirect(url_for("index"))
    if session.get("echecs", 0) >= MAX_ECHECS_LOGIN:
        return render_template(
            "login.html", bloque=True,
            erreur="Trop de tentatives échouées. Redémarrez le serveur pour réessayer.")

    saisi = request.form.get("mot_de_passe", "")
    if hashlib.sha256(saisi.encode("utf-8")).hexdigest() == mot_de_passe:
        session["authentifie"] = True
        session.pop("echecs", None)
        return redirect(url_for("index"))

    session["echecs"] = session.get("echecs", 0) + 1
    restantes = MAX_ECHECS_LOGIN - session["echecs"]
    bloque = restantes <= 0
    erreur = ("Trop de tentatives échouées. Redémarrez le serveur pour réessayer."
              if bloque else
              f"Mot de passe incorrect. {restantes} tentative(s) restante(s).")
    return render_template("login.html", erreur=erreur, bloque=bloque)


def logout():
    """Ferme la session et renvoie vers le formulaire de connexion."""
    session.clear()
    return redirect(url_for("login"))
