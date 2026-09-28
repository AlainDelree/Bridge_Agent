"""Gestion des processus watcher du bridge (un watcher par projet).

Extraite de new_issue.py à l'étape 6 du refactoring modulaire. Regroupe le
cycle de vie des watchers : démarrage, arrêt, détection du PID et les routes
Flask utilisées par le panneau latéral Infrastructure et l'onglet Configuration
de l'interface (l'onglet « Watchers » dédié a été supprimé, issue #626).

Démarrage/arrêt par lancement direct (issue #682, remplace systemd --user
#596) : demarrer_watcher()/arreter_watcher() lancent/arrêtent le process
`watcher.py` directement (subprocess.Popen / SIGTERM), sans dépendance à
systemd — inexistant sous Windows, cible du plan hybride CCL/CCW. Watcher
« local » (ce fichier) = `new_issue.py` et le watcher tournent sur la même
machine, lancé à la demande ; distinct du watcher « délégué » (mécanisme CCW,
`app/ccw.py`, autre machine physique pilotée en SSH — inchangé). Même
principe déjà en place pour le watcher spool (`app/issues_inbox.py`,
`demarrer_watcher_inbox`/`arreter_watcher_inbox`, issue #485), repris ici tel
quel. Rien à superviser côté OS : l'auto-extinction après inactivité
(`DELAI_INACTIVITE_MIN`, watcher.py) et le fichier PID suffisent à tout le
cycle de vie — aucun `Restart=on-failure` en cas de crash, à la différence de
l'ancien service systemd (limite assumée : un crash réel du watcher n'est
plus relancé automatiquement, relance manuelle requise, cf. panneau
Infrastructure).
watcher_actif() reste basé sur le fichier PID (logs/watcher-<nom>.pid) —
publié par watcher.py lui-même à son démarrage, quel que soit son mode de
lancement (terminal ou cet appel) — ce qui laisse inchangés les autres
consommateurs de ce fichier (watcher.py::detecter_conflit_watcher/
_compter_watchers_actifs, app.interruption.interrompre_linux).
"""

import logging
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

from flask import jsonify, request

# app.projets ajoute la racine du projet au sys.path lors de son import (pour
# « from watcher import ») ; on l'importe donc avant watcher.
from app.projets import lister_projets, projet_par_nom
from app.auth import login_requis  # noqa: F401 (exporté pour l'enregistrement des routes)
from watcher import (Config, DOSSIER_SCRIPT, _pid_vivant,
                      taches_en_cours as _taches_en_cours_watcher)

log = logging.getLogger(__name__)

# ─── Redémarrages différés (issue #609) ──────────────────────────────────────
# Un redémarrage FORCÉ (bouton « Enregistrer et relancer », relances manuelles
# du panneau latéral) d'un watcher qui a une tâche en cours ne
# doit JAMAIS la couper : vécu sur relecture_bridge #73 (diagnostic confirmé
# le 24/09/2026) — MAX_WRITE_PARALLELE changé de 1 à 2 puis watcher relancé
# pendant que #73 tournait déjà dans son worktree dédié ; `systemctl --user
# restart` a tué tout le cgroup, y compris le process CCL en cours (pas un
# simple SIGTERM propre) ; au redémarrage, le watcher a repris #73 comme
# premier slot et l'a relancée directement dans REP_TRAVAIL — l'ancien
# comportement du premier slot, supprimé depuis par #611 — travail non isolé
# embarqué dans un commit automatique d'un autre outil puis poussé par
# erreur. Au lieu d'agir immédiatement, demarrer_watcher_ou_differer()
# mémorise ici le nom du projet ; surveiller_redemarrages_differes (thread
# démon démarré par new_issue.py) exécute le redémarrage dès que la tâche qui
# le bloquait se termine.
INTERVALLE_SURVEILLANCE_DIFFERE = 15  # secondes

_verrou_differes = threading.Lock()
_redemarrages_differes: set[str] = set()


# ─── Gestion du processus watcher ────────────────────────────────────────────

def chemin_pid(cfg: Config) -> Path:
    return cfg.fichier_log.parent / f"watcher-{cfg.nom}.pid"


def watcher_actif(cfg: Config) -> tuple[bool, int | None]:
    """Retourne (actif, pid). Consulte le fichier PID et vérifie que le
    processus existe encore via `_pid_vivant` (watcher.py, sonde
    cross-plateforme POSIX/Windows, issue #584) plutôt qu'un `os.kill(pid, 0)`
    inline (issue #617) — même sonde que watcher.py utilise pour ses propres
    verrous."""
    pid_file = chemin_pid(cfg)
    if not pid_file.exists():
        return False, None
    try:
        pid = int(pid_file.read_text().strip())
    except (OSError, ValueError):
        return False, None
    return (True, pid) if _pid_vivant(pid) else (False, None)


def tache_en_cours(cfg: Config) -> list[dict]:
    """Tâches actuellement en traitement pour ce projet, vues depuis CE
    process (new_issue.py) — séparé du process watcher qui les traite
    réellement (issue #609). S'appuie sur les verrous fichier posés par
    watcher.py pour TOUTE issue (watcher.taches_en_cours), pas sur
    `issues_en_cours` qui reste en mémoire du process watcher, invisible ici.
    Retourne une liste de dict {"rep": str, "mode": str} — vide si le watcher
    n'a aucune tâche en cours à l'instant de l'appel."""
    return _taches_en_cours_watcher(cfg.nom)


def repli_rep_travail(cfg: Config, taches: list[dict] | None = None) -> bool:
    """True si une tâche mode_write est actuellement en cours DIRECTEMENT dans
    REP_TRAVAIL (et non dans un worktree isolé) — depuis l'issue #611, ce
    n'est plus JAMAIS un cas normal : toute tâche mode_write, y compris la
    première d'un lot à MAX_WRITE_PARALLELE > 1, obtient d'abord un worktree
    dédié (`_creer_worktree_avec_retries`, tentatives `-bis`/`-ter`). Cet
    indicateur ne s'active donc plus que pour le repli en tout DERNIER
    recours (issue #589/#611) : `_creer_worktree_avec_retries` a épuisé ses 3
    tentatives (chemin/branche « déjà pris », erreur git) — DISTINCT de
    l'incident relecture_bridge #73 (diagnostic confirmé le 24/09/2026) : #73
    tournait dans son propre worktree quand `systemctl --user restart` (lancé
    pour appliquer un changement de MAX_WRITE_PARALLELE) a tué tout le cgroup,
    dont le process CCL en cours ; au redémarrage, le watcher a repris #73
    comme premier slot et l'a relancée directement dans REP_TRAVAIL — l'ancien
    comportement du premier slot, supprimé depuis par #611, pas ce repli
    #589. Ce repli est désormais aussi signalé activement côté watcher
    (notify-send immédiat, issue #611) — cet indicateur d'interface reste un
    second canal, pas le seul."""
    if taches is None:
        taches = tache_en_cours(cfg)
    rep_travail = str(cfg.rep_travail)
    return any(t["mode"] == "ecriture" and t["rep"] == rep_travail for t in taches)


def _arreter_pid(pid: int) -> None:
    """SIGTERM best-effort sur un PID — cross-plateforme (issue #682) :
    `os.kill(pid, signal.SIGTERM)` sous Windows appelle `TerminateProcess`
    (pas de vrai signal POSIX là-bas, mais l'API Python l'accepte quand même,
    cf. doc `os.kill`) au lieu du couple `CREATE_NEW_PROCESS_GROUP` +
    `GenerateConsoleCtrlEvent` réservé à `CTRL_BREAK_EVENT`/`CTRL_C_EVENT`
    (watcher.py, `_nettoyer_arbre_claude`, cas différent : arrêt propre d'un
    sous-process `claude`, pas terminaison directe). watcher.py n'installe
    aucun gestionnaire pour SIGTERM (seul `KeyboardInterrupt`/SIGINT est géré
    pour l'arrêt manuel en terminal) : la terminaison est donc immédiate des
    deux côtés, sans étape de nettoyage interne — même brutalité qu'un
    `systemctl --user stop` côté systemd. Ne tue PAS la descendance
    éventuelle (tâche `claude` en cours) : à la différence de l'ancien
    `systemctl --user stop`/`restart`, qui tuait tout le cgroup du service
    sans distinction (issue #609, incident relecture_bridge #73) — ce point
    n'est plus un souci ici puisque demarrer_watcher_ou_differer() continue
    de différer tout redémarrage forcé tant qu'une tâche tourne (inchangé).
    Un arrêt manuel (bouton « Arrêter ») pendant une tâche en cours laisse
    désormais le process `claude` en cours orphelin plutôt que de le tuer
    aussi — l'interruption ciblée d'UNE tâche reste le rôle du bouton
    « Interrompre cette issue » (app/interruption.py, arbre de process
    complet via /proc), pas de ce bouton-ci."""
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        pass


def demarrer_watcher(cfg: Config, forcer: bool = True) -> tuple[bool, int | None]:
    """Lance (ou relance) le watcher du projet par lancement direct
    (`subprocess.Popen`, issue #682 — remplace `systemctl --user` #596,
    inexistant sous Windows). Si forcer=False et qu'un watcher tourne déjà,
    retourne (False, pid_existant) sans y toucher. Si forcer=True et qu'un
    watcher tourne déjà, il est arrêté (SIGTERM + court délai pour lui
    laisser le temps de libérer son fichier PID, même principe que
    app/issues_inbox.py::demarrer_watcher_inbox) avant le nouveau lancement.

    Détaché du process appelant (new_issue.py) : `start_new_session=True`
    côté POSIX (même pattern que app/issues_inbox.py, watcher.py::
    lancer_claude), `CREATE_NEW_PROCESS_GROUP` côté Windows (flag déjà
    utilisé par watcher.py::lancer_claude — rien de nouveau à inventer à ce
    niveau). stdout/stderr redirigés en ajout vers le journal habituel du
    projet (cfg.fichier_log) : watcher.py gère lui-même sa rotation via son
    propre logger (RotatingFileHandler) sur ce même fichier, donc ceci ne
    capture que ce qui y échapperait (traceback non attrapée avant que le
    logger soit configuré, etc.) — écriture en ajout (`O_APPEND`) donc sans
    conflit avec les écritures du logger.

    Retourne (redemarré, pid) : pid est TOUJOURS celui du process fraîchement
    lancé (`proc.pid`, connu immédiatement, contrairement à l'ancien sondage
    du fichier PID nécessaire quand systemd gérait le process sans nous en
    donner le PID directement) — watcher.py republiera lui-même ce même PID
    dans logs/watcher-<nom>.pid dès son propre démarrage (issue #596,
    inchangé), sans effet puisque la valeur est identique."""
    actif, pid_ancien = watcher_actif(cfg)
    if actif and not forcer:
        return False, pid_ancien

    if actif and pid_ancien:
        _arreter_pid(pid_ancien)
        time.sleep(0.8)

    chemin_config = DOSSIER_SCRIPT / "configs" / f"{cfg.nom}.conf"
    if not chemin_config.exists():
        raise FileNotFoundError(f"Config introuvable : {chemin_config}")

    pid_file = chemin_pid(cfg)
    pid_file.parent.mkdir(parents=True, exist_ok=True)

    kwargs_popen = dict(cwd=DOSSIER_SCRIPT)
    if os.name == "nt":
        kwargs_popen["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs_popen["start_new_session"] = True

    with open(cfg.fichier_log, "a", encoding="utf-8") as f_log:
        proc = subprocess.Popen(
            [sys.executable, str(DOSSIER_SCRIPT / "watcher.py"), "--config", str(chemin_config)],
            stdout=f_log, stderr=f_log, **kwargs_popen,
        )

    pid_file.write_text(str(proc.pid))
    return True, proc.pid


def demarrer_watcher_ou_differer(cfg: Config, forcer: bool) -> tuple[str, int | None]:
    """Point d'entrée de la route /lancer-watcher (bouton « Enregistrer et
    relancer » de l'onglet Configuration, relances manuelles du panneau
    latéral) — DISTINCT de demarrer_watcher() (issue
    #609) : un redémarrage FORCÉ (forcer=True) d'un watcher qui a une tâche en
    cours (verrou fichier actif, cf. tache_en_cours ci-dessus) n'est jamais
    exécuté immédiatement, il COUPERAIT cette tâche. Vécu sur relecture_bridge
    #73 (diagnostic confirmé le 24/09/2026) : MAX_WRITE_PARALLELE changé de 1
    à 2 puis watcher relancé pendant que #73 tournait déjà dans son worktree
    dédié — `systemctl --user restart` a tué tout le cgroup, dont le process
    CCL en cours ; au redémarrage, le watcher a repris #73 comme premier slot
    et l'a relancée directement dans REP_TRAVAIL (ancien comportement du
    premier slot, supprimé depuis par #611, PAS le repli #589) ; le travail,
    non isolé, a été embarqué dans un commit automatique d'un autre outil
    puis poussé par erreur.

    Le redémarrage est mémorisé dans _redemarrages_differes plutôt qu'exécuté :
    surveiller_redemarrages_differes (thread démon démarré par new_issue.py)
    l'exécute automatiquement dès que la tâche qui le bloquait se termine —
    aucune action manuelle supplémentaire requise.

    forcer=False est délégué tel quel à demarrer_watcher (comportement
    inchangé : démarre seulement si éteint, jamais de coupure possible
    puisqu'un watcher avec une tâche en cours est par construction déjà actif).

    Retourne (statut, pid) : statut ∈ {"demarre", "deja_actif", "differe"}."""
    actif, pid_ancien = watcher_actif(cfg)
    if actif and forcer and tache_en_cours(cfg):
        with _verrou_differes:
            _redemarrages_differes.add(cfg.nom)
        log.info(f"Redémarrage de « {cfg.nom} » différé (issue #609) : tâche en cours.")
        return "differe", pid_ancien
    redemarre, pid = demarrer_watcher(cfg, forcer=forcer)
    return ("demarre" if redemarre else "deja_actif"), pid


def surveiller_redemarrages_differes():
    """Thread démon (issue #609), démarré par new_issue.py à côté des autres
    threads de fond (surveiller_heartbeat, surveiller_transitions) : exécute
    les redémarrages mémorisés par demarrer_watcher_ou_differer() dès que la
    tâche qui les bloquait se termine — sondée à chaque passage, jamais
    supposée terminée après un délai fixe. Best-effort : une exception isolée
    (échec de lancement, projet supprimé entre-temps...) est journalisée et
    n'empêche ni la sonde suivante ni le traitement des autres projets
    différés."""
    while True:
        time.sleep(INTERVALLE_SURVEILLANCE_DIFFERE)
        with _verrou_differes:
            noms = list(_redemarrages_differes)
        for nom in noms:
            cfg = projet_par_nom(nom)
            if cfg is None:
                # Projet supprimé entre-temps : plus rien à différer.
                with _verrou_differes:
                    _redemarrages_differes.discard(nom)
                continue
            if tache_en_cours(cfg):
                continue  # toujours occupé — retenté au prochain passage
            try:
                demarrer_watcher(cfg, forcer=True)
                log.info(f"Redémarrage différé de « {nom} » exécuté (tâche terminée, issue #609).")
            except Exception as e:
                log.warning(f"Redémarrage différé de « {nom} » a échoué : {e}")
            with _verrou_differes:
                _redemarrages_differes.discard(nom)


def redemarrer_si_eteint(cfg: Config, *, tracer: bool = False) -> tuple[bool | None, int | None, str]:
    """Enrobage de demarrer_watcher(cfg, forcer=False) (« relance seulement
    s'il est éteint »), factorisé (issue #600) à partir de 5 sites qui le
    dupliquaient avec des comportements divergents en cas d'échec —
    app/issues.py, app/interruption.py, app/projet_ccw.py,
    scripts/watcher_issues_inbox.py (×2). Un échec n'est plus jamais
    silencieux : log.warning systématique (app/projet_ccw.py avalait
    auparavant l'exception sans aucune trace, ni log ni JSON).

    Garde for-linux : PAS internalisée ici. Dans app/issues.py et
    app/interruption.py, la garde ne porte pas sur le fait que ce mécanisme
    (lancement direct du watcher **local**, portable Linux/Windows depuis
    #682) puisse s'appliquer, mais sur le ROUTAGE de l'issue traitée —
    labels for-linux/for-windows (#164) décidant si CETTE issue relève bien
    du watcher local (CCL, ou son pendant Windows une fois adopté) plutôt
    que du watcher **délégué** (CCW, autre machine physique pilotée en SSH,
    inchangé par #682). C'est une décision propre à l'appelant (qui a accès
    aux labels de l'issue), pas à ce helper (qui ne reçoit qu'un cfg de
    projet et n'a aucune notion de labels) : elle reste à ces 2 sites,
    inchangée. Les 3 autres sites ne l'ont jamais eue car ils visent toujours
    un watcher for-linux par construction (projet bridge_agent lui-même, ou
    contexte déjà filtré) — rien à y ajouter.

    Retourne (demarre, pid, trace) : demarre=True si le watcher a été
    effectivement (re)lancé à cet appel, False s'il tournait déjà, None si le
    démarrage a échoué (distinction reprise d'app/interruption.py, pour ne
    pas confondre « rien à faire » et « échec ») ; trace est une chaîne prête
    à insérer dans un commentaire GitHub (préfixée par deux sauts de ligne,
    format repris d'app/interruption.py et scripts/watcher_issues_inbox.py)
    quand tracer=True — vide sinon, y compris en cas d'échec."""
    try:
        demarre, pid = demarrer_watcher(cfg, forcer=False)
    except Exception as e:
        log.warning(f"Redémarrage auto du watcher CCL « {cfg.nom} » échoué : {e}")
        trace = (f"\n\n⚠️ Redémarrage auto du watcher CCL « {cfg.nom} » échoué : {e}"
                  if tracer else "")
        return None, None, trace

    trace = ""
    if demarre and tracer:
        trace = (f"\n\n⚙️ Watcher CCL du projet « {cfg.nom} » redémarré "
                  f"automatiquement (il était éteint — pid {pid}).")
    return demarre, pid, trace


def arreter_watcher(cfg: Config) -> tuple[bool, str]:
    """Arrête le watcher du projet par SIGTERM direct (issue #682, remplace
    `systemctl --user stop` #596 — voir _arreter_pid pour la portée exacte,
    notamment vis-à-vis d'une tâche `claude` en cours). Retourne (succès,
    message)."""
    actif, pid = watcher_actif(cfg)
    if not actif:
        return False, "watcher déjà inactif"
    _arreter_pid(pid)
    chemin_pid(cfg).unlink(missing_ok=True)
    return True, f"watcher arrêté (pid {pid})"


# ─── Routes Flask ──────────────────────────────────────────────────────────────

def watchers():
    """Retourne le statut de tous les projets disponibles. `tache_en_cours`,
    `repli_rep_travail` et `redemarrage_differe` (issue #609) permettent au
    panneau latéral d'afficher visiblement qu'un
    redémarrage serait dangereux ou a été différé, et qu'une tâche mode_write
    tourne directement dans REP_TRAVAIL (repli #589, pas de worktree isolé) —
    auquel cas le dossier principal du projet ne doit pas être touché (merge,
    push) avant la fin."""
    resultat = []
    with _verrou_differes:
        differes = set(_redemarrages_differes)
    for cfg in lister_projets():
        actif, pid = watcher_actif(cfg)
        taches = tache_en_cours(cfg) if actif else []
        resultat.append({
            "nom":               cfg.nom,
            "depot":             cfg.depot,
            "actif":             actif,
            "pid":               pid,
            "tache_en_cours":    bool(taches),
            "repli_rep_travail": repli_rep_travail(cfg, taches),
            "redemarrage_differe": cfg.nom in differes,
        })
    return jsonify(resultat)


def lancer_watcher():
    """Lance ou relance le watcher du projet.
    relancer=true → redémarre même s'il tourne déjà (différé si une tâche est
    en cours, issue #609 — voir demarrer_watcher_ou_differer).
    relancer=false → démarre seulement s'il est inactif."""
    data    = request.json or {}
    cfg     = projet_par_nom(data.get("projet", ""))
    if not cfg:
        return jsonify(succes=False, erreur="Projet introuvable.")
    forcer  = data.get("relancer", True)
    try:
        statut, pid = demarrer_watcher_ou_differer(cfg, forcer)
        return jsonify(succes=True, pid=pid,
                        redemarré=(statut == "demarre"),
                        differe=(statut == "differe"))
    except Exception as e:
        return jsonify(succes=False, erreur=str(e))


def arreter_watcher_route():
    """Arrête le watcher du projet."""
    data = request.json or {}
    cfg  = projet_par_nom(data.get("projet", ""))
    if not cfg:
        return jsonify(succes=False, erreur="Projet introuvable.")
    ok, msg = arreter_watcher(cfg)
    return jsonify(succes=ok, message=msg)


def statut(nom_projet):
    """Indique si le watcher de ce projet est en cours d'exécution."""
    cfg = projet_par_nom(nom_projet)
    if not cfg:
        return jsonify(actif=False)
    actif, pid = watcher_actif(cfg)
    return jsonify(actif=actif, pid=pid)
