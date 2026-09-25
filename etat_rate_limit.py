#!/usr/bin/env python3
"""
etat_rate_limit.py — état partagé du quota GitHub GraphQL (issue #615).

Contexte : le widget /rate-limit (issue #607) affichait jusqu'ici une valeur
rafraîchie UNIQUEMENT par le polling JS à intervalle fixe (30s, voir
app/rate_limit.py + static/js/app.js) — une rafale de consommation gh entre
deux polls pouvait épuiser le quota sans que le widget le reflète.

Piste initiale envisagée (issue #615) : capturer les headers HTTP
`x-ratelimit-*` de CHAQUE appel gh existant via `gh ... --include`. Écartée
après vérification : les sous-commandes utilisées dans ce projet (`gh issue
list/view/create/close/edit/comment`) n'exposent PAS `--include`/`-i` — seule
`gh api` l'a (gh 2.45.0). Réécrire tous ces appels en `gh api` équivalents
pour gagner ces headers aurait été une réécriture disproportionnée pour ce
ticket (repli explicitement permis par l'issue).

Repli retenu : après chaque appel gh SIGNIFICATIF (création/fermeture d'issue
— watcher.py, app/issues.py, app/notifications_poller.py), rafraîchir le
quota via un appel dédié `gh api rate_limit` (celui-ci ne consomme NI le
quota core NI le quota graphql, vérifié empiriquement issue #263, cf.
scripts/mesurer_api.py) et persister le résultat dans un état partagé —
fichier JSON, écriture atomique + verrou anti-collision, même pattern que
etat_timeout.json/etat_ambiance.json (issue #221) puisque watcher.py tourne
dans un process SÉPARÉ de celui de l'app Flask qui sert /rate-limit : un
simple attribut de module ne suffirait pas à partager l'état entre les deux.

Aucune dépendance à Flask/CFG : les fonctions reçoivent tout en argument
(origine de l'appel), sur le même principe que notifications.py.
"""

import json
import logging
import os
import subprocess
import time
from pathlib import Path

log = logging.getLogger("etat_rate_limit")

CHEMIN_ETAT   = Path(__file__).resolve().parent / "logs" / "etat_rate_limit.json"
CHEMIN_VERROU = CHEMIN_ETAT.with_suffix(".lock")

DELAI_VERROU_S = 2.0   # attente max pour obtenir le verrou avant d'abandonner ce cycle


def _acquerir_verrou(delai_s: float = DELAI_VERROU_S) -> bool:
    fin = time.monotonic() + delai_s
    while time.monotonic() < fin:
        try:
            fd = os.open(str(CHEMIN_VERROU), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            return True
        except FileExistsError:
            time.sleep(0.05)
    return False


def _liberer_verrou():
    try:
        CHEMIN_VERROU.unlink()
    except FileNotFoundError:
        pass
    except OSError as e:
        log.warning(f"Libération du verrou {CHEMIN_VERROU.name} impossible ({e}).")


def _interroger_gh(timeout_s: float) -> tuple[dict | None, str | None]:
    """Appelle `gh api rate_limit`. Retourne (data, None) en succès, ou
    (None, message_erreur) sinon — ne lève jamais."""
    try:
        res = subprocess.run(
            ["gh", "api", "rate_limit", "--jq", ".resources.graphql"],
            capture_output=True, text=True, timeout=timeout_s,
        )
        if res.returncode != 0:
            return None, (res.stderr or res.stdout or "erreur gh inconnue").strip()
        return json.loads(res.stdout), None
    except subprocess.TimeoutExpired:
        return None, f"Timeout (gh n'a pas répondu en {timeout_s:.0f}s)."
    except FileNotFoundError:
        return None, "gh introuvable dans le PATH."
    except Exception as e:
        return None, str(e)


def maj_rate_limit(origine: str, *, timeout_s: float = 15) -> tuple[dict | None, str | None]:
    """Rafraîchit le quota GraphQL et persiste le résultat dans
    logs/etat_rate_limit.json — best-effort, ne lève jamais : un échec ici ne
    doit jamais faire échouer l'appel gh significatif qui vient de se
    produire.

    `origine` (ex. "watcher.fermer_issue", "app.issues.envoyer") est
    journalisé en DEBUG à chaque mise à jour — permet de corréler une
    consommation anormale du quota avec sa source (module/fonction) lors d'un
    futur épisode (issue #615).

    Retourne (donnees, None) en succès — donnees = {used, limit, remaining,
    reset, origine, maj_epoch} — ou (None, message_erreur) sinon."""
    data, erreur = _interroger_gh(timeout_s)
    if data is None:
        log.debug(f"maj_rate_limit({origine}) : échec ({erreur})")
        return None, erreur

    donnees = {
        "used": data["used"], "limit": data["limit"],
        "remaining": data["remaining"], "reset": data["reset"],
        "origine": origine, "maj_epoch": int(time.time()),
    }
    if _acquerir_verrou():
        try:
            CHEMIN_ETAT.parent.mkdir(parents=True, exist_ok=True)
            tmp = CHEMIN_ETAT.with_name(CHEMIN_ETAT.name + f".tmp{os.getpid()}")
            tmp.write_text(json.dumps(donnees, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp, CHEMIN_ETAT)
        except OSError as e:
            log.warning(f"Écriture de {CHEMIN_ETAT.name} impossible ({e}).")
        finally:
            _liberer_verrou()
    else:
        log.debug(f"maj_rate_limit({origine}) : verrou non obtenu, état partagé non mis à jour.")

    log.debug(f"rate limit GraphQL mis à jour par {origine} : "
              f"{donnees['used']}/{donnees['limit']} utilisé(s), "
              f"{donnees['remaining']} restant(s).")
    return donnees, None


def lire_rate_limit() -> dict | None:
    """Lit l'état partagé le plus récent (best-effort, jamais d'exception).
    None si le fichier est absent/corrompu — l'appelant (route /rate-limit)
    doit alors se rabattre sur un appel gh direct via maj_rate_limit()."""
    try:
        return json.loads(CHEMIN_ETAT.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
