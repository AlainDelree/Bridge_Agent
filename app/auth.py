"""Authentification de l'interface web (extraite de new_issue.py, étape 4).

Le mot de passe d'accès est stocké HASHÉ (sha256) dans configs/bridge_agent.conf
sous la clé MOT_DE_PASSE. Vide → interface accessible sans authentification.
Générer le hash avec :  python3 new_issue.py --set-password

Le login est exigé dès que le serveur écoute au-delà de 127.0.0.1 (--lan comme
--externe, issue #831) : en mode local, devant le ThinkPad, l'accès reste
direct. ACCES_RESEAU et MOT_DE_PASSE vivent dans app.config, lus à la requête
via app/etat.py.

Le gabarit de la page de connexion vit dans templates/login.html, rendu via
render_template (comme index.html).

En complément du blocage par SESSION (cookie, ci-dessous) — contourné par la
simple suppression du cookie — un blocage par ADRESSE source est tenu en
mémoire du processus serveur (_ECHECS_PAR_ADRESSE) : perdu au redémarrage,
jamais persisté sur disque, issue #831.
"""

import hashlib
import time
from functools import wraps

from flask import redirect, render_template, request, session, url_for

from app import etat

MAX_ECHECS_LOGIN = 5           # nombre de tentatives avant blocage (session ET adresse)
DUREE_BLOCAGE_ADRESSE = 15 * 60  # secondes de blocage d'une adresse après MAX_ECHECS_LOGIN échecs

MESSAGE_BLOCAGE = "Trop de tentatives échouées. Redémarrez le serveur pour réessayer."

# adresse (str) -> {"echecs": int, "bloque_jusqua": float (horodatage epoch)}
_ECHECS_PAR_ADRESSE: dict[str, dict] = {}


def _adresse_cliente() -> str:
    """Adresse IP source réelle du client courant. Flask/Werkzeug ne fait
    confiance à aucun en-tête de proxy par défaut : `remote_addr` est le pair
    TCP direct, qu'un appareil du réseau local connecté directement au port
    exposé (host 0.0.0.0, --lan comme --externe) ne peut pas forger.

    Exception volontaire : en mode --externe, cloudflared tourne SUR cette
    machine et relaie les requêtes du visiteur distant vers Flask via la
    boucle locale (remote_addr == 127.0.0.1), en posant lui-même l'en-tête
    Cf-Connecting-Ip (adresse réelle du visiteur, posée par l'edge
    Cloudflare). Cet en-tête n'est donc utilisé QUE lorsque remote_addr est
    127.0.0.1/::1 : un appareil du réseau local ne peut pas faire croire que
    son adresse TCP source est la boucle locale (la poignée de main TCP ne
    peut pas aboutir avec une adresse source usurpée), donc ne peut pas
    emprunter ce chemin pour imposer un Cf-Connecting-Ip arbitraire. Si
    l'en-tête est absent (cloudflared non présent, ou hypothèse erronée),
    repli silencieux sur remote_addr — jamais moins sûr qu'avant #831."""
    adresse = request.remote_addr or ""
    if adresse in ("127.0.0.1", "::1"):
        cf_ip = request.headers.get("Cf-Connecting-Ip", "").strip()
        if cf_ip:
            return cf_ip
    return adresse


def _adresse_bloquee(adresse: str) -> bool:
    """True si `adresse` est actuellement bloquée (>= MAX_ECHECS_LOGIN échecs,
    blocage pas encore expiré). Nettoie l'entrée expirée au passage."""
    entree = _ECHECS_PAR_ADRESSE.get(adresse)
    if not entree or entree["echecs"] < MAX_ECHECS_LOGIN:
        return False
    if time.time() >= entree["bloque_jusqua"]:
        del _ECHECS_PAR_ADRESSE[adresse]
        return False
    return True


def _enregistrer_echec_adresse(adresse: str) -> None:
    """Incrémente le compteur d'échecs de `adresse` ; pose (ou prolonge) son
    blocage de DUREE_BLOCAGE_ADRESSE secondes dès le MAX_ECHECS_LOGIN-ième."""
    entree = _ECHECS_PAR_ADRESSE.setdefault(adresse, {"echecs": 0, "bloque_jusqua": 0.0})
    entree["echecs"] += 1
    if entree["echecs"] >= MAX_ECHECS_LOGIN:
        entree["bloque_jusqua"] = time.time() + DUREE_BLOCAGE_ADRESSE


def _reinitialiser_adresse(adresse: str) -> None:
    """Remet `adresse` à zéro (succès de connexion)."""
    _ECHECS_PAR_ADRESSE.pop(adresse, None)


def login_requis(vue):
    """Décorateur : redirige vers /login tant que la session n'est pas
    authentifiée. Inactif si aucun mot de passe n'est configuré ou si le
    serveur n'écoute qu'en local (login exigé dès que ACCES_RESEAU est vrai,
    donc en --lan comme en --externe — issue #831)."""
    @wraps(vue)
    def enveloppe(*args, **kwargs):
        if (etat.get("MOT_DE_PASSE") and etat.get("ACCES_RESEAU")
                and not session.get("authentifie")):
            return redirect(url_for("login"))
        return vue(*args, **kwargs)
    return enveloppe


def login():
    """Formulaire de connexion. Redirige vers l'accueil si aucune authentification
    n'est requise ou si la session est déjà authentifiée. Bloqué si la session
    OU l'adresse source (issue #831) a atteint MAX_ECHECS_LOGIN échecs."""
    if not etat.get("MOT_DE_PASSE") or session.get("authentifie"):
        return redirect(url_for("index"))
    bloque = (session.get("echecs", 0) >= MAX_ECHECS_LOGIN
              or _adresse_bloquee(_adresse_cliente()))
    erreur = MESSAGE_BLOCAGE if bloque else ""
    return render_template("login.html", erreur=erreur, bloque=bloque)


def login_post():
    """Vérifie le mot de passe saisi (sha256) contre MOT_DE_PASSE du .conf.
    Bloque après MAX_ECHECS_LOGIN tentatives échouées, à la fois pour la
    session (cookie) ET pour l'adresse source (issue #831) : supprimer son
    cookie ne contourne plus le blocage tant que l'adresse reste bloquée."""
    mot_de_passe = etat.get("MOT_DE_PASSE")
    if not mot_de_passe:
        return redirect(url_for("index"))

    adresse = _adresse_cliente()
    if session.get("echecs", 0) >= MAX_ECHECS_LOGIN or _adresse_bloquee(adresse):
        return render_template("login.html", bloque=True, erreur=MESSAGE_BLOCAGE)

    saisi = request.form.get("mot_de_passe", "")
    if hashlib.sha256(saisi.encode("utf-8")).hexdigest() == mot_de_passe:
        session["authentifie"] = True
        session.permanent = True  # cookie valable PERMANENT_SESSION_LIFETIME (issue #676)
        session.pop("echecs", None)
        _reinitialiser_adresse(adresse)
        return redirect(url_for("index"))

    session["echecs"] = session.get("echecs", 0) + 1
    _enregistrer_echec_adresse(adresse)
    bloque = session["echecs"] >= MAX_ECHECS_LOGIN or _adresse_bloquee(adresse)
    restantes = MAX_ECHECS_LOGIN - session["echecs"]
    erreur = (MESSAGE_BLOCAGE if bloque else
              f"Mot de passe incorrect. {restantes} tentative(s) restante(s).")
    return render_template("login.html", erreur=erreur, bloque=bloque)


def logout():
    """Ferme la session et renvoie vers le formulaire de connexion."""
    session.clear()
    return redirect(url_for("login"))
