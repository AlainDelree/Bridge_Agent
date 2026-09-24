"""Indicateur de rate limit GitHub GraphQL dans le bandeau supérieur (issue #607).

Widget compact toujours visible (bandeau haut de new_issue.py, entre le titre
et le compteur de projets), lu via `gh api rate_limit` côté serveur — cet appel
REST ne consomme NI le quota `core` NI le quota `graphql` (vérifié
empiriquement, issue #263, voir scripts/mesurer_api.py) : le polling de ce
widget ne peut donc pas lui-même épuiser le quota qu'il surveille.
"""

import json
import subprocess

from flask import jsonify


def rate_limit():
    """GET /rate-limit — used/limit/remaining/reset (epoch Unix) du quota
    GraphQL. En cas d'échec (y compris, ironiquement, un rate limit atteint),
    renvoie ok: false plutôt qu'une erreur HTTP : l'onglet affiche alors
    l'état dégradé « ⚡ ? / 5000 » en gris sans planter (issue #607)."""
    try:
        res = subprocess.run(
            ["gh", "api", "rate_limit", "--jq", ".resources.graphql"],
            capture_output=True, text=True, timeout=15,
        )
        if res.returncode != 0:
            return jsonify(ok=False, erreur=(res.stderr or res.stdout or "erreur gh inconnue").strip())
        data = json.loads(res.stdout)
        return jsonify(ok=True, used=data["used"], limit=data["limit"],
                        remaining=data["remaining"], reset=data["reset"])
    except subprocess.TimeoutExpired:
        return jsonify(ok=False, erreur="Timeout (gh n'a pas répondu en 15s).")
    except FileNotFoundError:
        return jsonify(ok=False, erreur="gh introuvable dans le PATH.")
    except Exception as e:
        return jsonify(ok=False, erreur=str(e))
