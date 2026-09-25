"""Indicateur de rate limit GitHub GraphQL dans le bandeau supérieur (issue #607).

Widget compact toujours visible (bandeau haut de new_issue.py, entre le titre
et le compteur de projets). Historiquement alimenté par un appel dédié `gh api
rate_limit` à chaque requête du widget (30s, cf. static/js/app.js) — cet appel
REST ne consomme NI le quota `core` NI le quota `graphql` (vérifié
empiriquement, issue #263, voir scripts/mesurer_api.py).

Depuis l'issue #615 : la route sert d'abord l'état partagé (`etat_rate_limit`,
logs/etat_rate_limit.json), rafraîchi par watcher.py/app/issues.py/
app/notifications_poller.py juste après chaque appel gh SIGNIFICATIF (création
ou fermeture d'issue) — s'il est assez frais, elle évite un appel gh dédié
supplémentaire. Sinon (état absent ou plus vieux que SEUIL_FRAICHEUR_S), elle
retombe sur l'appel gh direct d'origine, qui met lui-même à jour l'état
partagé au passage."""

import time

from flask import jsonify

from etat_rate_limit import lire_rate_limit, maj_rate_limit

# Le widget interroge /rate-limit toutes les 30s (static/js/app.js) : en
# dessous de ce seuil, l'état partagé — potentiellement rafraîchi entretemps
# par un appel gh significatif d'un AUTRE process (watcher.py) — est réputé
# assez frais pour éviter un appel gh dédié de plus.
SEUIL_FRAICHEUR_S = 20


def rate_limit():
    """GET /rate-limit — used/limit/remaining/reset (epoch Unix) du quota
    GraphQL. En cas d'échec (y compris, ironiquement, un rate limit atteint),
    renvoie ok: false plutôt qu'une erreur HTTP : l'onglet affiche alors
    l'état dégradé « ⚡ ? / 5000 » en gris sans planter (issue #607)."""
    etat = lire_rate_limit()
    if etat and time.time() - etat.get("maj_epoch", 0) <= SEUIL_FRAICHEUR_S:
        return jsonify(ok=True, used=etat["used"], limit=etat["limit"],
                        remaining=etat["remaining"], reset=etat["reset"])

    donnees, erreur = maj_rate_limit("app.rate_limit.rate_limit")
    if donnees is None:
        return jsonify(ok=False, erreur=erreur)
    return jsonify(ok=True, used=donnees["used"], limit=donnees["limit"],
                    remaining=donnees["remaining"], reset=donnees["reset"])
