"""Versionnage des fichiers statiques (issue #625, étape 1).

Les navigateurs mettent en cache scripts et feuilles de style. Pour qu'une mise
à jour soit systématiquement rechargée SANS vider le cache à la main, on ajoute
à chaque URL statique une empreinte `?v=<mtime>` : dès qu'un fichier change, sa
date de modification change, donc l'URL change, donc le navigateur refetch.

Deux aides exposées aux gabarits Jinja (enregistrées dans create_app) :

- ``url_statique(chemin)`` : ``url_for('static', ...)`` + ``?v=<mtime>``. À
  utiliser pour toute feuille CSS, tout script classique et pour le point
  d'entrée module du socle.

- ``importmap_socle()`` : JSON d'un *import map* remappant chaque module du socle
  vers son URL versionnée. Nécessaire car les imports RELATIFS entre modules ES
  (``import './store.js'``) ne propagent pas le ``?v=`` du fichier importateur :
  sans import map, changer index.js ne rechargerait pas store.js. Les modules
  gardent des imports relatifs (indispensables pour ``node --test``) ; le
  navigateur, lui, applique l'import map pour le cache-busting par fichier.
"""

import json
from pathlib import Path

from flask import url_for

RACINE = Path(__file__).resolve().parent.parent
DOSSIER_STATIC = RACINE / "static"


def _version(chemin_relatif: str):
    """Empreinte de cache d'un fichier statique = son mtime entier, ou None si
    le fichier est absent (on renvoie alors une URL sans ?v=)."""
    try:
        return str(int((DOSSIER_STATIC / chemin_relatif).stat().st_mtime))
    except OSError:
        return None


def url_statique(chemin_relatif: str) -> str:
    """URL statique versionnée : url_for('static', ...) + '?v=<mtime>'."""
    url = url_for("static", filename=chemin_relatif)
    version = _version(chemin_relatif)
    if version is None:
        return url
    separateur = "&" if "?" in url else "?"
    return f"{url}{separateur}v={version}"


def importmap_socle() -> str:
    """Import map JSON versionnant chaque module ES chargé par le socle.

    Clé = URL résolue du module (``/static/js/socle/store.js``), valeur = même
    URL + ``?v=<mtime>``. Le navigateur remappe ainsi les imports relatifs vers
    leur version courante. Le point d'entrée index.js est inclus pour homogénéité
    (son ``src`` porte déjà son propre ``?v=`` via url_statique).

    Deux familles de modules sont couvertes :
      - ``js/socle/*.js`` : les briques partagées (store/api/sse/… — issue #625) ;
      - ``js/*.js`` (hors ``app.js``) : les MODULES PAR FONCTIONNALITÉ importés par
        index.js (ex. ``resultats.js`` — refonte étape 3, issue #627). ``app.js``
        est exclu : c'est un script CLASSIQUE (jamais importé), déjà versionné via
        ``url_statique`` dans scripts.html. Sans cette famille, un changement de
        ``resultats.js`` seul ne serait pas cache-busté (son URL n'a pas de ``?v=``
        propre, il n'est chargé que par un ``import`` relatif d'index.js)."""
    imports = {}
    try:
        cibles = list((DOSSIER_STATIC / "js" / "socle").glob("*.js"))
        cibles += [f for f in (DOSSIER_STATIC / "js").glob("*.js") if f.name != "app.js"]
        for fichier in cibles:
            rel = fichier.relative_to(DOSSIER_STATIC).as_posix()
            imports[url_for("static", filename=rel)] = url_statique(rel)
    except OSError:
        pass
    return json.dumps({"imports": imports}, ensure_ascii=False)


def enregistrer_aides_statiques(app) -> None:
    """Publie url_statique et importmap_socle comme globales Jinja."""
    app.jinja_env.globals["url_statique"] = url_statique
    app.jinja_env.globals["importmap_socle"] = importmap_socle
