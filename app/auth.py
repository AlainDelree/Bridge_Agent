"""Authentification de l'interface web (extraite de new_issue.py, étape 4).

Le mot de passe d'accès est stocké HASHÉ (sha256) dans configs/bridge_agent.conf
sous la clé MOT_DE_PASSE. Vide → interface accessible sans authentification.
Générer le hash avec :  python3 new_issue.py --set-password

Le login n'est exigé qu'en mode --externe (accès distant via tunnel) : en mode
local, devant le ThinkPad, l'accès est direct. MODE_EXTERNE et MOT_DE_PASSE
vivent dans app.config, lus à la requête via app/etat.py.

Le gabarit de la page de connexion (TEMPLATE_LOGIN) est conservé ici en chaîne
inline et rendu via render_template_string : il n'a pas été extrait vers
templates/ (contrairement à index.html) car il n'est utilisé que par ce module.
"""

import hashlib
from functools import wraps

from flask import (redirect, render_template_string, request, session,
                   url_for)

from app import etat

MAX_ECHECS_LOGIN = 5   # nombre de tentatives avant blocage de la session


TEMPLATE_LOGIN = """<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Bridge Agent — Connexion</title>
<style>
body{font-family:system-ui,sans-serif;font-size:14px;background:#f0efe9;color:#1a1a18;
  min-height:100vh;margin:0;display:flex;align-items:center;justify-content:center;padding:28px 16px}
.carte{background:#fff;border:1px solid #ddd;border-radius:12px;max-width:360px;width:100%;
  padding:28px;box-shadow:0 1px 3px rgba(0,0,0,.05)}
.carte h1{font-size:16px;font-weight:500;margin:0 0 4px;display:flex;align-items:center;gap:9px}
.carte p.sous{color:#888;font-size:12px;margin:0 0 20px}
label{display:block;font-size:12px;color:#555;margin-bottom:6px}
input[type=password]{width:100%;box-sizing:border-box;padding:9px 12px;border:1px solid #ccc;
  border-radius:6px;font-size:14px;color:#1a1a18}
input[type=password]:focus{outline:none;border-color:#1a1a18}
button{width:100%;margin-top:16px;padding:9px 16px;border:1px solid #1a1a18;border-radius:6px;
  font-size:14px;background:#1a1a18;color:#fff;cursor:pointer}
button:hover{background:#333}
button:disabled{background:#999;border-color:#999;cursor:not-allowed}
.erreur{background:#f8d7da;color:#721c24;border-radius:6px;padding:9px 12px;font-size:12px;
  margin-bottom:16px}
</style>
</head>
<body>
  <form class="carte" method="post" action="/login">
    <h1>
      <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
        <rect x="4" y="11" width="16" height="9" rx="2"/><path d="M8 11V7a4 4 0 018 0v4"/>
      </svg>
      Bridge Agent
    </h1>
    <p class="sous">Accès protégé — saisissez le mot de passe.</p>
    {% if erreur %}<div class="erreur">{{ erreur }}</div>{% endif %}
    <label for="mot_de_passe">Mot de passe</label>
    <input type="password" id="mot_de_passe" name="mot_de_passe" autofocus
           {% if bloque %}disabled{% endif %}>
    <button type="submit" {% if bloque %}disabled{% endif %}>Connexion</button>
  </form>
</body>
</html>"""


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
    return render_template_string(TEMPLATE_LOGIN, erreur=erreur, bloque=bloque)


def login_post():
    """Vérifie le mot de passe saisi (sha256) contre MOT_DE_PASSE du .conf.
    Bloque la session après MAX_ECHECS_LOGIN tentatives échouées."""
    mot_de_passe = etat.get("MOT_DE_PASSE")
    if not mot_de_passe:
        return redirect(url_for("index"))
    if session.get("echecs", 0) >= MAX_ECHECS_LOGIN:
        return render_template_string(
            TEMPLATE_LOGIN, bloque=True,
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
    return render_template_string(TEMPLATE_LOGIN, erreur=erreur, bloque=bloque)


def logout():
    """Ferme la session et renvoie vers le formulaire de connexion."""
    session.clear()
    return redirect(url_for("login"))
