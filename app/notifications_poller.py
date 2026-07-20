"""
app/notifications_poller.py — détection serveur des transitions d'issues et
notification centralisée (issue #187).

Pourquoi ce module existe
-------------------------
Jusqu'ici, c'est watcher.py qui émettait bip/notify-send/ntfy à la fin d'une
issue qu'il traitait. Problème : le watcher CCW tourne dans la VM Windows — son
bip et sa bulle bureau y restent, hors de portée d'Alain, et son ntfy ferait
doublon avec une éventuelle notification centralisée.

Plutôt que la VM ouvre un canal réseau vers le ThinkPad (surface d'attaque,
NAT, secret partagé — approche écartée), new_issue.py — qui tourne en
permanence sur le ThinkPad — détecte LUI-MÊME les transitions en interrogeant
GitHub via `gh` (exactement comme il le fait déjà pour l'onglet Résultats et
les badges). La VM continue de n'écrire QUE sur GitHub (labels, commentaires) ;
new_issue.py lit ces écritures par polling et déclenche les notifications
localement, sur le ThinkPad, quel que soit l'agent (CCL ou CCW) à l'origine.

Transitions détectées (les deux états TERMINAUX d'une issue) :
  • succès           : issue fermée + label `done`      (watcher.fermer_issue) ;
  • échec définitif  : label `needs-human` posé, issue restée ouverte
                       (watcher, abandon non-critique après N tentatives).
Les alertes intermédiaires d'issues critiques (une par tentative ratée) ne sont
PAS répliquées ici : ce ne sont pas des transitions d'état d'issue mais des
signaux transitoires propres au watcher, difficiles à détecter par polling.

Anti-doublon (issue #187, point 4)
----------------------------------
Ce poller et watcher.py peuvent tous deux notifier. Pour éviter qu'Alain
reçoive deux fois le même signal, deux réglages se combinent :
  • côté watcher : `NOTIFIER_LOCAL = false` dans le .conf coupe la notification
    locale du watcher (à poser sur la VM CCW, et sur CCL si l'on bascule en
    centralisation complète) ;
  • côté poller  : la portée `BRIDGE_NOTIF_SCOPE` restreint les transitions
    notifiées (`for-windows` par défaut : uniquement les issues CCW, celles
    justement invisibles à Alain aujourd'hui).
Le défaut livré (`for-windows` + watcher CCL laissé notifiant) est donc SANS
régression ni doublon : CCL notifie via son watcher (déjà fonctionnel), CCW
notifie via ce poller. Pour la centralisation complète recommandée (option a),
voir BRIDGE_AGENT_DOC.md §17.

État mémorisé
-------------
En mémoire process (pas de fichier), volontairement, pour la simplicité (le
suivi de transitions n'a pas besoin de survivre à un redémarrage). Deux
garde-fous évitent de notifier de vieilles issues :
  • filtre de récence : seules les transitions horodatées dans les
    `BRIDGE_NOTIF_RECENCE_MIN` dernières minutes sont considérées ;
  • amorçage au premier passage : au tout premier cycle, les transitions déjà
    présentes sont mémorisées SANS notifier (ligne de base) ; seules les
    transitions apparues ENSUITE déclenchent une notification.

Lecture des labels au moment de la fermeture (issue #187, point 5)
------------------------------------------------------------------
Le poller lit les labels COURANTS de l'issue au moment où il détecte la
transition — pas au démarrage du traitement. Conséquence voulue : Alain peut
ajouter `notif_pc`/`notif_gsm` sur GitHub À TOUT MOMENT tant que l'issue est
ouverte (en file OU en cours de traitement) et recevra bien la notification à
sa fermeture. (Le mécanisme historique de watcher.py capture les labels une
seule fois, au début — un label ajouté après n'a aucun effet.)
"""

import json
import os
import subprocess
import time
from datetime import datetime, timezone

import notifications
from app.projets import lister_projets

# ─── Réglages (surchargeable par variable d'environnement) ─────────────────────
INTERVALLE_S = int(os.environ.get("BRIDGE_NOTIF_INTERVALLE", "60"))   # période de polling (issue #188 : 20→60 s pour alléger la charge gh cumulée)
RECENCE_MIN  = int(os.environ.get("BRIDGE_NOTIF_RECENCE_MIN", "30"))  # fenêtre de récence
SCOPE        = os.environ.get("BRIDGE_NOTIF_SCOPE", "for-windows").strip().lower()
# SCOPE : "for-windows" (défaut, CCW seul) | "for-linux" | "all" | "off"

LABEL_DONE        = "done"
LABEL_NEEDS_HUMAN = "needs-human"


def _log(msg: str):
    """Journalise sur stdout (capturé par lancer_new_issue.sh dans logs/)."""
    print(f"[notif] {msg}", flush=True)


def _gh_list(depot: str, label: str, state: str, champs: str) -> list:
    """`gh issue list --label X --state Y` → liste JSON, ou [] en cas d'erreur.

    On utilise volontairement `--label`/`--state` (API REST-like standard,
    comme partout ailleurs dans issues.py) et PAS `--search` : `--search`
    invoque l'API Search de GraphQL, qui a un quota SÉPARÉ et bien plus strict
    — deux requêtes Search par projet toutes les 20 s saturaient ce quota et
    faisaient remonter « API rate limit already exceeded » jusque dans l'onglet
    Résultats (issue #188). Le tri `sort:updated-desc` disparaît avec `--label`,
    mais il était superflu : on ne dépend que du filtre de récence `_recent()`,
    appliqué issue par issue quel que soit l'ordre. Best-effort : aucune
    exception ne remonte, le poller ne doit jamais mourir sur un hoquet gh."""
    try:
        res = subprocess.run(
            ["gh", "issue", "list",
             "--repo", depot,
             "--label", label,
             "--state", state,
             "--json", champs,
             "--limit", "40"],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=30,
        )
        if res.returncode != 0:
            _log(f"gh erreur ({depot}) : {res.stderr.strip()}")
            return []
        return json.loads(res.stdout or "[]")
    except FileNotFoundError:
        _log("gh introuvable dans le PATH — poller inactif ce cycle.")
        return []
    except Exception as e:
        _log(f"exception gh ({depot}) : {e}")
        return []


def _recent(horodatage: str) -> bool:
    """Vrai si l'horodatage ISO 8601 (…Z) tombe dans la fenêtre de récence."""
    if not horodatage:
        return False
    try:
        dt = datetime.fromisoformat(horodatage.replace("Z", "+00:00"))
    except ValueError:
        return False
    age_s = (datetime.now(timezone.utc) - dt).total_seconds()
    return 0 <= age_s <= RECENCE_MIN * 60


def _labels_de(issue: dict) -> list[str]:
    return [(l.get("name") or "") for l in issue.get("labels", [])]


def _dans_la_portee(labels: list[str]) -> bool:
    """La transition entre-t-elle dans la portée configurée (SCOPE) ?"""
    if SCOPE == "all":
        return True
    if SCOPE == "for-windows":
        return "for-windows" in labels
    if SCOPE == "for-linux":
        return "for-linux" in labels
    return False


def _transitions_projet(cfg) -> list[dict]:
    """Retourne les transitions terminales RÉCENTES d'un projet, chacune sous la
    forme {number, title, labels, type, horodatage}. type ∈ {done, needs-human}."""
    transitions = []

    # Succès : issues fermées portant `done`. Pas de tri gh (le tri
    # `sort:updated-desc` n'existe qu'avec --search) : le filtre de récence
    # `_recent()` ci-dessous sélectionne les bonnes issues quel que soit l'ordre.
    for it in _gh_list(
        cfg.depot,
        LABEL_DONE, "closed",
        "number,title,labels,closedAt,updatedAt",
    ):
        horo = it.get("closedAt") or it.get("updatedAt") or ""
        if _recent(horo):
            transitions.append({
                "number": it.get("number"), "title": it.get("title") or "",
                "labels": _labels_de(it), "type": LABEL_DONE, "horodatage": horo,
            })

    # Échec définitif : issues ouvertes portant `needs-human`.
    for it in _gh_list(
        cfg.depot,
        LABEL_NEEDS_HUMAN, "open",
        "number,title,labels,updatedAt",
    ):
        horo = it.get("updatedAt") or ""
        if _recent(horo):
            transitions.append({
                "number": it.get("number"), "title": it.get("title") or "",
                "labels": _labels_de(it), "type": LABEL_NEEDS_HUMAN, "horodatage": horo,
            })

    return transitions


def _notifier_transition(cfg, tr: dict):
    """Déclenche la notification locale pour une transition, en lisant les labels
    COURANTS de l'issue (bonus issue #187 : notif_* ajouté en cours de route
    est bien pris en compte)."""
    numero = tr["number"]
    titre  = tr["title"]
    labels = tr["labels"]
    if tr["type"] == LABEL_DONE:
        notifications.notifier(
            labels, cfg.nom, cfg.url_ntfy, cfg.script_bip,
            titre=f"✅ {cfg.nom} #{numero} — traitée",
            message=f"'{titre}' traitée avec succès.",
            urgence_bureau="normal", priorite_ntfy="default",
        )
    else:  # needs-human
        notifications.notifier(
            labels, cfg.nom, cfg.url_ntfy, cfg.script_bip,
            titre=f"❌ {cfg.nom} #{numero} — échec définitif",
            message=f"'{titre}' — intervention humaine requise.",
            urgence_bureau="critical", priorite_ntfy="high",
        )


def surveiller_transitions():
    """Boucle de polling (thread démon lancé par new_issue.py). Détecte les
    transitions d'issues de tous les projets actifs et notifie localement.

    `deja_vu` : ensemble des clés (depot, numero, type) déjà notifiées, pour ne
    signaler chaque transition qu'une fois. `premier_passage` : au tout premier
    cycle, on amorce `deja_vu` sans notifier (ligne de base — pas de spam de
    vieilles issues au démarrage)."""
    if SCOPE == "off":
        _log("BRIDGE_NOTIF_SCOPE=off — détection des transitions désactivée.")
        return

    _log(f"détection des transitions active — portée={SCOPE}, "
         f"intervalle={INTERVALLE_S}s, récence={RECENCE_MIN}min.")

    deja_vu: set[tuple] = set()
    premier_passage = True

    while True:
        try:
            for cfg in lister_projets():
                for tr in _transitions_projet(cfg):
                    if not _dans_la_portee(tr["labels"]):
                        continue
                    cle = (cfg.depot, tr["number"], tr["type"])
                    if cle in deja_vu:
                        continue
                    deja_vu.add(cle)
                    if premier_passage:
                        continue  # amorçage silencieux au démarrage
                    _log(f"transition {tr['type']} — {cfg.nom} #{tr['number']} "
                         f"'{tr['title']}' — labels={tr['labels']}")
                    _notifier_transition(cfg, tr)
            premier_passage = False
        except Exception as e:
            # Filet de sécurité : une erreur inattendue ne doit jamais tuer le
            # thread (sinon plus aucune notification jusqu'au redémarrage).
            _log(f"erreur de cycle (ignorée) : {e}")

        time.sleep(INTERVALLE_S)
