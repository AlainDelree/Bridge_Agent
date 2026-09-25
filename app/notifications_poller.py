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

Liste surveillée plutôt que balayage par projet (issue #624, remplace #623)
-----------------------------------------------------------------------------
Avant #624, chaque cycle balayait, POUR CHAQUE PROJET DANS LA PORTÉE, deux
`gh issue list` (done fermées + needs-human ouvertes) — la portée étant décidée
en filtrant les projets sur le champ LABEL de leur .conf (#614). Bug : LABEL
est un DÉFAUT de projet, pas la vérité — c'est le label for-windows/for-linux
posé sur CHAQUE ISSUE qui dit si elle concerne CCW (voir watcher.py/app/
issues.py, exclusivité des deux labels). Aucun .conf CCL ne portant
LABEL=for-windows, le poller n'interrogeait plus aucun projet et ne détectait
plus aucune transition CCW (diagnostic #621).

Le poller connaît désormais une LISTE d'issues (depot, numéro) à surveiller,
et non plus des projets : `_ISSUES_SURVEILLEES` ci-dessous, en mémoire process
(comme l'ancien `deja_vu`). Remplissage :
  1. `_balayage_initial()`, appelé une fois au démarrage de
     `surveiller_transitions()` : liste, pour TOUS les projets configurés,
     les issues OUVERTES dont le label est dans BRIDGE_NOTIF_SCOPE ;
  2. `ajouter_issue_surveillee()`, appelée EN DIRECT (même process) par
     `app.issues.envoyer` et `app.interruption.route_relancer`, et via la
     route `POST /notifier-issue-a-surveiller` (process séparé) par
     `scripts/watcher_issues_inbox.py` — à chaque création ou relance d'une
     issue dans la portée, sans attendre le prochain démarrage.
Limite documentée (pas traitée) : une issue for-windows créée directement sur
GitHub ou par un chef (`gh issue create` hors des deux chemins ci-dessus) n'est
prise en compte qu'au prochain démarrage de new_issue.py (rattrapée par
`_balayage_initial()`). Voir BRIDGE_AGENT_DOC.md §17.

Liste vide → AUCUN appel gh à ce cycle (le cas courant : CCW n'est utilisé
qu'une ou deux fois par semaine).

Deux détections par issue surveillée, à chaque cycle :
  • prise en charge (commentaire ACK, même logique que /issues-en-attente —
    `app.issues._debut_traitement`/`_commentaires_issue`, réutilisées telles
    quelles) → SSE `debut_issue` sur /stream (voir §17.3) ;
  • transition TERMINALE :
      - succès           : issue fermée + label `done`      (watcher.fermer_issue) ;
      - échec définitif  : label `needs-human` posé, issue restée ouverte
                           (watcher, abandon non-critique après N tentatives).
    → bip/bulle/ntfy selon les labels notif_* de l'issue (comme avant #624) +
    SSE `fin_issue` sur /stream (dans tous les cas, décorrélé des labels
    notif_* — même principe que watcher.py::notifier_fin_sse). L'issue est
    RETIRÉE de la liste surveillée dès cette transition détectée.
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
  • côté poller  : la portée `BRIDGE_NOTIF_SCOPE` restreint les issues
    surveillées (`for-windows` par défaut : uniquement les issues CCW, celles
    justement invisibles à Alain aujourd'hui).
Le défaut livré (`for-windows` + watcher CCL laissé notifiant) est donc SANS
régression ni doublon : CCL notifie via son watcher (déjà fonctionnel), CCW
notifie via ce poller. Pour la centralisation complète recommandée (option a),
voir BRIDGE_AGENT_DOC.md §17.

Garde-fous conservés (issue #624)
----------------------------------
  • anti-spam au démarrage : au tout premier cycle, une issue déjà surveillée
    (ACK et/ou transition terminale déjà présente à l'amorçage) est mémorisée
    SANS notifier (ligne de base) — pas de salve pour des transitions anciennes ;
  • filtre de récence : une transition terminale n'est notifiée que si son
    horodatage tombe dans les `BRIDGE_NOTIF_RECENCE_MIN` dernières minutes ;
  • labels notif_* lus au moment de la détection (pas figés à l'ajout à la
    liste) : Alain peut ajouter `notif_pc`/`notif_gsm` sur GitHub à tout moment
    tant que l'issue est surveillée et recevra bien la notification à sa
    fermeture (issue #187, point 5).
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

from flask import jsonify, request

import notifications
import etat_rate_limit  # état partagé du quota GraphQL (issue #615)
from app.projets import lister_projets, projet_par_depot
# Réutilise la logique de repérage de l'ACK de /issues-en-attente plutôt que
# de la dupliquer (issue #624 — voir _verifier_issue_surveillee ci-dessous).
from app.issues import _commentaires_issue, _debut_traitement

# scripts/ n'est pas un package : on l'ajoute au sys.path (même geste que
# watcher.py et app/issues_inbox.py) pour que `import traitement_fin`
# fonctionne quel que soit l'ordre d'import des modules du package app.
DOSSIER_SCRIPT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(DOSSIER_SCRIPT / "scripts"))
import traitement_fin  # noqa: E402 — POST /notifier-debut-issue et /notifier-fin-issue (SSE /stream, issue #624)

# ─── Réglages (surchargeable par variable d'environnement) ─────────────────────
INTERVALLE_S = int(os.environ.get("BRIDGE_NOTIF_INTERVALLE", "60"))   # période de polling (issue #188 : 20→60 s pour alléger la charge gh cumulée)
RECENCE_MIN  = int(os.environ.get("BRIDGE_NOTIF_RECENCE_MIN", "30"))  # fenêtre de récence
ESPACEMENT_S = float(os.environ.get("BRIDGE_NOTIF_ESPACEMENT", "2"))  # délai entre deux issues surveillées (issue #190 : étaler les appels gh au lieu d'une rafale groupée)
SCOPE        = os.environ.get("BRIDGE_NOTIF_SCOPE", "for-windows").strip().lower()
# SCOPE : "for-windows" (défaut, CCW seul) | "for-linux" | "all" | "off"

LABEL_DONE        = "done"
LABEL_NEEDS_HUMAN = "needs-human"


def _log(msg: str):
    """Journalise sur stdout (capturé par lancer_new_issue.sh dans logs/).

    Horodatage HH:MM:SS local (issue #190) : permet à Alain de corréler un clic
    « Rafraîchir » ressenti comme lent avec un cycle du poller, et de vérifier
    que l'étalement des appels (ESPACEMENT_S) supprime bien le pic de charge."""
    heure = datetime.now().strftime("%H:%M:%S")
    print(f"[notif {heure}] {msg}", flush=True)


def _gh_list(depot: str, label: str, state: str, champs: str) -> list:
    """`gh issue list --label X --state Y` → liste JSON, ou [] en cas d'erreur.

    On utilise volontairement `--label`/`--state` (API REST-like standard,
    comme partout ailleurs dans issues.py) et PAS `--search` : `--search`
    invoque l'API Search de GraphQL, qui a un quota SÉPARÉ et bien plus strict
    — deux requêtes Search par projet toutes les 20 s saturaient ce quota et
    faisaient remonter « API rate limit already exceeded » jusque dans l'onglet
    Résultats (issue #188). Best-effort : aucune exception ne remonte, le
    poller ne doit jamais mourir sur un hoquet gh."""
    _log(f"gh issue list {depot} label={label} state={state}")
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


def _gh_view_issue(depot: str, numero: int, champs: str) -> dict | None:
    """`gh issue view <numero> --repo <depot> --json <champs>` → dict, ou None
    en cas d'erreur. Même philosophie best-effort que `_gh_list()` : un hoquet
    gh ne retire jamais une issue de la liste surveillée, il retarde juste sa
    vérification au cycle suivant (voir _verifier_issue_surveillee)."""
    try:
        res = subprocess.run(
            ["gh", "issue", "view", str(numero), "--repo", depot, "--json", champs],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=30,
        )
        if res.returncode != 0:
            _log(f"gh erreur (issue #{numero}, {depot}) : {res.stderr.strip()}")
            return None
        return json.loads(res.stdout or "{}")
    except FileNotFoundError:
        _log("gh introuvable dans le PATH — poller inactif ce cycle.")
        return None
    except Exception as e:
        _log(f"exception gh (issue #{numero}, {depot}) : {e}")
        return None


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
    """Une issue portant ces labels entre-t-elle dans la portée configurée
    (SCOPE) ? Utilisée à l'ajout à la liste surveillée (ajouter_issue_surveillee)
    — SCOPE=off n'est jamais atteint ici, court-circuité plus haut."""
    if SCOPE == "all":
        return True
    if SCOPE == "for-windows":
        return "for-windows" in labels
    if SCOPE == "for-linux":
        return "for-linux" in labels
    return False


def _labels_scope() -> list[str]:
    """Label(s) GitHub à demander à gh pour le balayage initial (issue #624)
    — miroir de `_dans_la_portee()`, mais retourne les libellés à interroger
    plutôt que de filtrer une liste de labels déjà connue."""
    if SCOPE == "all":
        return ["for-windows", "for-linux"]
    if SCOPE in ("for-windows", "for-linux"):
        return [SCOPE]
    return []  # SCOPE=off déjà court-circuité par surveiller_transitions()


# ─── Liste des issues surveillées (issue #624, remplace le balayage par
# projet de #614) ────────────────────────────────────────────────────────────
# En mémoire process, comme l'ancien `deja_vu` : un redémarrage de
# new_issue.py perd la liste, mais `_balayage_initial()` la reconstruit
# intégralement au prochain démarrage (voir docstring de module).
_ISSUES_SURVEILLEES: dict[tuple, dict] = {}
_verrou_issues = Lock()


def ajouter_issue_surveillee(depot: str, numero: int, labels: list[str]) -> bool:
    """Ajoute une issue OUVERTE à la liste surveillée si ses labels entrent
    dans BRIDGE_NOTIF_SCOPE (`_dans_la_portee()`) — no-op silencieux sinon.
    Idempotent : ré-ajouter une issue déjà présente ne fait rien. Thread-safe :
    appelée aussi bien depuis le thread du poller (`_balayage_initial`) que
    depuis une requête Flask du même process (`app.issues.envoyer`,
    `app.interruption.route_relancer`) ou la route HTTP dédiée ci-dessous
    (`scripts/watcher_issues_inbox.py`, process séparé).

    Retourne True si l'issue est (ou était déjà) surveillée, False si hors
    portée."""
    if not _dans_la_portee(labels):
        return False
    cle = (depot, int(numero))
    with _verrou_issues:
        nouvelle = cle not in _ISSUES_SURVEILLEES
        if nouvelle:
            _ISSUES_SURVEILLEES[cle] = {"ack_connu": False}
    if nouvelle:
        _log(f"issue surveillée ajoutée — {depot}#{numero}")
    return True


def _retirer_issue_surveillee(depot: str, numero: int) -> None:
    with _verrou_issues:
        _ISSUES_SURVEILLEES.pop((depot, numero), None)


def route_surveiller_issue():
    """POST /notifier-issue-a-surveiller (issue #624) — appelé par
    `scripts/watcher_issues_inbox.py` (process SÉPARÉ, ne peut pas muter
    directement `_ISSUES_SURVEILLEES` de ce process) juste après la création
    ou la relance d'une issue dans la portée, pour l'ajouter IMMÉDIATEMENT à
    la liste surveillée sans attendre le prochain `_balayage_initial()`. Corps
    JSON {"depot": ..., "numero": ..., "labels": [...]}. Sans authentification
    (appelé par un script local, pas par un navigateur) — même famille que
    /notifier-fin-issue. Best-effort côté appelant : si new_issue.py n'est pas
    lancé, l'appel échoue silencieusement (voir traitement_fin.py)."""
    corps  = request.get_json(silent=True) or {}
    depot  = corps.get("depot")
    numero = corps.get("numero")
    labels = corps.get("labels") or []
    if not depot or numero is None:
        return jsonify(ok=False, erreur="depot et numero requis"), 400
    surveillee = ajouter_issue_surveillee(depot, int(numero), [str(l) for l in labels])
    return jsonify(ok=True, surveillee=surveillee)


def _balayage_initial() -> None:
    """Balayage UNIQUE (issue #624), au démarrage de `surveiller_transitions()` :
    liste, pour CHAQUE projet configuré (pas seulement ceux dont le LABEL du
    .conf correspond à SCOPE — c'est le label de l'ISSUE qui compte, cf.
    diagnostic #621), les issues OUVERTES portant un label dans la portée, et
    les ajoute à la liste surveillée. Rattrape toute issue for-windows créée
    directement sur GitHub, par un chef, ou pendant que new_issue.py n'était
    pas lancé (limite documentée, pas traitée — voir BRIDGE_AGENT_DOC.md §17)."""
    labels_scope = _labels_scope()
    if not labels_scope:
        return
    for cfg in lister_projets():
        for label in labels_scope:
            for it in _gh_list(cfg.depot, label, "open", "number,labels"):
                numero = it.get("number")
                if numero is not None:
                    ajouter_issue_surveillee(cfg.depot, numero, _labels_de(it))


def _notifier_transition(cfg, numero: int, titre: str, labels: list[str],
                          type_transition: str) -> None:
    """Déclenche `notifications.notifier()` (bip/bulle/ntfy, opt-in via les
    labels notif_*) pour la transition détectée. `labels` : labels COURANTS de
    l'issue, lus par l'appelant au moment de la détection — pas figés à l'ajout
    à la liste surveillée (issue #187, point 5 : notif_* ajouté en cours de
    route est bien pris en compte)."""
    if type_transition == LABEL_DONE:
        notifications.notifier(
            labels, cfg.nom, cfg.url_ntfy, cfg.script_bip,
            titre=f"✅ {cfg.nom} #{numero} — traitée",
            message=f"'{titre}' traitée avec succès.",
            urgence_bureau="normal", priorite_ntfy="default",
            numero=numero, tonalite=cfg.tonalite_bip,
        )
    else:  # needs-human
        notifications.notifier(
            labels, cfg.nom, cfg.url_ntfy, cfg.script_bip,
            titre=f"❌ {cfg.nom} #{numero} — échec définitif",
            message=f"'{titre}' — intervention humaine requise.",
            urgence_bureau="critical", priorite_ntfy="high",
            numero=numero, tonalite=cfg.tonalite_bip,
        )


def _traiter_transition(cfg, numero: int, issue: dict, type_transition: str,
                         horodatage: str, premier_passage: bool) -> None:
    """Une transition terminale (done/needs-human) vient d'être détectée sur
    une issue surveillée : la notifie (sauf amorçage ou transition trop
    ancienne — gardes conservées de #187/#188), pousse le SSE `fin_issue`
    (décorrélé des labels notif_*, comme watcher.py::notifier_fin_sse), puis
    RETIRE l'issue de la liste surveillée dans tous les cas — son cycle de vie
    pour ce poller est terminé."""
    depot = cfg.depot
    if premier_passage:
        _log(f"transition {type_transition} déjà présente à l'amorçage — "
             f"{cfg.nom} #{numero} (pas de notification, ligne de base).")
    elif not _recent(horodatage):
        _log(f"transition {type_transition} trop ancienne, ignorée — "
             f"{cfg.nom} #{numero} ({horodatage}).")
    else:
        titre = issue.get("title") or ""
        labels = _labels_de(issue)
        _log(f"transition {type_transition} — {cfg.nom} #{numero} '{titre}' — labels={labels}")
        _notifier_transition(cfg, numero, titre, labels, type_transition)
        traitement_fin.notifier_fin_issue(cfg.nom, numero)
    _retirer_issue_surveillee(depot, numero)


def _verifier_issue_surveillee(cfg, depot: str, numero: int, etat_issue: dict,
                                premier_passage: bool) -> None:
    """Vérifie UNE issue de la liste surveillée : transition terminale
    (done/needs-human) d'abord, prise en charge (ACK) sinon."""
    issue = _gh_view_issue(depot, numero, "state,title,labels,closedAt,updatedAt")
    if issue is None:
        return  # hoquet gh — retenté au cycle suivant, issue laissée en place

    labels = _labels_de(issue)
    ferme  = (issue.get("state") or "").upper() == "CLOSED"

    if ferme and LABEL_DONE in labels:
        horo = issue.get("closedAt") or issue.get("updatedAt") or ""
        _traiter_transition(cfg, numero, issue, LABEL_DONE, horo, premier_passage)
        return
    if LABEL_NEEDS_HUMAN in labels:
        horo = issue.get("updatedAt") or ""
        _traiter_transition(cfg, numero, issue, LABEL_NEEDS_HUMAN, horo, premier_passage)
        return

    # Pas (encore) de transition terminale : prise en charge (ACK) ? Ne
    # refait pas le travail une fois l'ACK déjà connue (économise l'appel gh
    # de _commentaires_issue à chaque cycle suivant).
    if etat_issue.get("ack_connu"):
        return
    debut = _debut_traitement(_commentaires_issue(cfg, numero))
    if debut is None:
        return
    with _verrou_issues:
        if (depot, numero) in _ISSUES_SURVEILLEES:
            _ISSUES_SURVEILLEES[(depot, numero)]["ack_connu"] = True
    if premier_passage:
        _log(f"ACK déjà présente à l'amorçage — {cfg.nom} #{numero} "
             "(pas de notification, ligne de base).")
    else:
        _log(f"prise en charge détectée — {cfg.nom} #{numero} — SSE debut_issue.")
        traitement_fin.notifier_debut_issue(cfg.nom, numero)


def _cycle(premier_passage: bool) -> None:
    """UN cycle de vérification (extrait de surveiller_transitions() pour être
    testable sans piloter la boucle infinie — issue #624). Liste vide →
    aucune itération → AUCUN appel gh, ni à `_gh_view_issue`/`_commentaires_issue`
    (par issue) ni à `etat_rate_limit.maj_rate_limit` (throttlé une fois par
    cycle, seulement s'il y a eu du travail)."""
    with _verrou_issues:
        a_verifier = list(_ISSUES_SURVEILLEES.items())
    for i, ((depot, numero), etat_issue) in enumerate(a_verifier):
        cfg = projet_par_depot(depot)
        if cfg is None:
            continue  # projet introuvable (config retirée/renommée) — laissé tel quel, retenté au cycle suivant
        _verifier_issue_surveillee(cfg, depot, numero, etat_issue, premier_passage)
        # Espacement inter-issues (issue #190, adapté #624) : étale les appels
        # gh au lieu d'une rafale groupée. Sans effet la plupart du temps
        # (liste vide ou à 1 élément — CCW n'est utilisé qu'une ou deux fois
        # par semaine).
        if ESPACEMENT_S > 0 and i < len(a_verifier) - 1:
            time.sleep(ESPACEMENT_S)
    # Une seule fois par cycle complet (pas par issue, issue #615), et
    # seulement s'il y a eu au moins un appel gh ce cycle (liste vide → aucun
    # appel gh, issue #624).
    if a_verifier:
        etat_rate_limit.maj_rate_limit("app.notifications_poller.surveiller_transitions")


def surveiller_transitions():
    """Boucle de polling (thread démon lancé par new_issue.py). Vérifie à
    chaque cycle les issues de la liste surveillée (ACK + transitions
    terminales) et notifie localement — voir docstring de module pour le
    remplissage de cette liste (issue #624).

    `premier_passage` : au tout premier cycle (juste après le balayage
    initial), on amorce l'état de chaque issue surveillée SANS notifier
    (ligne de base — pas de salve pour des transitions/ACK anciennes)."""
    if SCOPE == "off":
        _log("BRIDGE_NOTIF_SCOPE=off — détection des transitions désactivée.")
        return

    _log(f"détection des transitions active — portée={SCOPE}, "
         f"intervalle={INTERVALLE_S}s, récence={RECENCE_MIN}min, "
         f"espacement={ESPACEMENT_S}s/issue.")

    _balayage_initial()
    premier_passage = True

    while True:
        try:
            _cycle(premier_passage)
            premier_passage = False
        except Exception as e:
            # Filet de sécurité : une erreur inattendue ne doit jamais tuer le
            # thread (sinon plus aucune notification jusqu'au redémarrage).
            _log(f"erreur de cycle (ignorée) : {e}")

        time.sleep(INTERVALLE_S)
