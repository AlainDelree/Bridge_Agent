"""Gestion des processus watcher du bridge (un watcher par projet).

Extraite de new_issue.py à l'étape 6 du refactoring modulaire. Regroupe le
cycle de vie des watchers : démarrage, arrêt, détection du PID et les routes
Flask associées à l'onglet « Watchers » de l'interface.

Démarrage/arrêt via systemd --user (issue #596) : demarrer_watcher()/
arreter_watcher() appellent `systemctl --user start|restart|stop
watcher@<projet>` (unité définie dans systemd/watcher@.service, installée par
installer_services.sh) plutôt que de gérer le process directement
(subprocess.Popen / SIGTERM), pour survivre à un crash (Restart=on-failure)
et à un redémarrage du ThinkPad. watcher_actif() reste basé sur le fichier PID
(logs/watcher-<nom>.pid) — désormais publié par watcher.py lui-même à son
démarrage, quel que soit son mode de lancement (terminal, systemd, ou cet
appel) — ce qui laisse inchangés les autres consommateurs de ce fichier
(watcher.py::detecter_conflit_watcher/_compter_watchers_actifs,
app.interruption.interrompre_linux).
"""

import logging
import os
import subprocess
import threading
import time
from pathlib import Path

from flask import jsonify, request

# app.projets ajoute la racine du projet au sys.path lors de son import (pour
# « from watcher import ») ; on l'importe donc avant watcher.
from app.projets import lister_projets, projet_par_nom
from app.auth import login_requis  # noqa: F401 (exporté pour l'enregistrement des routes)
from watcher import Config, taches_en_cours as _taches_en_cours_watcher

log = logging.getLogger(__name__)

# ─── Redémarrages différés (issue #609) ──────────────────────────────────────
# Un redémarrage FORCÉ (bouton « Enregistrer et relancer », relances manuelles
# du panneau latéral/onglet Watchers) d'un watcher qui a une tâche en cours ne
# doit JAMAIS la couper : vécu sur relecture_bridge #73 — redémarrage pendant
# une issue mode_write, reprise sur un worktree « déjà pris » par la première
# tentative, repli sur REP_TRAVAIL (#589), travail non isolé embarqué dans un
# commit automatique d'un autre outil puis poussé par erreur. Au lieu d'agir
# immédiatement, demarrer_watcher_ou_differer() mémorise ici le nom du projet ;
# surveiller_redemarrages_differes (thread démon démarré par new_issue.py)
# exécute le redémarrage dès que la tâche qui le bloquait se termine.
INTERVALLE_SURVEILLANCE_DIFFERE = 15  # secondes

_verrou_differes = threading.Lock()
_redemarrages_differes: set[str] = set()


# ─── Gestion du processus watcher ────────────────────────────────────────────

def chemin_pid(cfg: Config) -> Path:
    return cfg.fichier_log.parent / f"watcher-{cfg.nom}.pid"


def watcher_actif(cfg: Config) -> tuple[bool, int | None]:
    """Retourne (actif, pid). Consulte le fichier PID et vérifie que le
    processus existe encore (os.kill(pid, 0) ne tue pas, il sonde)."""
    pid_file = chemin_pid(cfg)
    if not pid_file.exists():
        return False, None
    try:
        pid = int(pid_file.read_text().strip())
        os.kill(pid, 0)   # lève OSError si le processus est mort
        return True, pid
    except (OSError, ProcessLookupError, ValueError):
        return False, None


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
    REP_TRAVAIL (et non dans un worktree isolé), pour DEUX raisons distinctes
    (issue #609) — l'interface ne cherche pas à les distinguer, le risque pour
    Alain (dossier principal en cours d'écriture, à ne pas toucher — merge,
    push — avant la fin) est identique dans les deux cas :
      1. Cas NORMAL et fréquent (MAX_WRITE_PARALLELE > 1, cf. `traiter_issue`
         dans watcher.py) : le PREMIER slot d'une parallélisation mode_write
         cible délibérément REP_TRAVAIL, sans worktree — seuls les slots
         suivants (2e tâche mode_write concurrente, etc.) en obtiennent un.
         Dès qu'une seule tâche mode_write tourne (le cas le plus courant),
         cet indicateur est donc normalement actif, pas un signe d'anomalie.
      2. Repli #589 : `_creer_worktree` a échoué (chemin/branche « déjà
         pris », erreur git) — celui qui a coûté le travail perdu de
         relecture_bridge #73 (redémarrage du watcher pendant la tâche,
         reprise sur un worktree déjà pris, repli silencieux sur REP_TRAVAIL,
         travail non isolé embarqué dans un commit d'un autre outil)."""
    if taches is None:
        taches = tache_en_cours(cfg)
    rep_travail = str(cfg.rep_travail)
    return any(t["mode"] == "ecriture" and t["rep"] == rep_travail for t in taches)


def demarrer_watcher(cfg: Config, forcer: bool = True) -> tuple[bool, int | None]:
    """Lance (ou relance) le watcher du projet via `systemctl --user`
    (issue #596). Si forcer=False et qu'un watcher tourne déjà, retourne
    (False, pid_existant) sans y toucher. Si forcer=True, l'unité est
    redémarrée (démarrée si elle était éteinte) — `systemctl restart`
    fonctionne aussi bien sur une unité déjà active qu'inactive.
    Retourne (redemarré, pid) ; pid peut être None si watcher.py n'a pas
    encore publié son fichier PID au terme du court sondage ci-dessous
    (démarrage anormalement lent), sans que ce soit un échec pour autant."""
    actif, pid_ancien = watcher_actif(cfg)
    if actif and not forcer:
        return False, pid_ancien

    unite  = f"watcher@{cfg.nom}"
    action = "restart" if actif else "start"
    subprocess.run(["systemctl", "--user", action, unite],
                    check=True, capture_output=True, text=True, timeout=15)

    # watcher.py publie son PID dès son démarrage (issue #596) — court
    # sondage pour laisser à systemd + Python le temps de le faire.
    pid_file = chemin_pid(cfg)
    for _ in range(30):
        if pid_file.exists():
            try:
                return True, int(pid_file.read_text().strip())
            except ValueError:
                pass
        time.sleep(0.1)
    return True, None


def demarrer_watcher_ou_differer(cfg: Config, forcer: bool) -> tuple[str, int | None]:
    """Point d'entrée de la route /lancer-watcher (bouton « Enregistrer et
    relancer » de l'onglet Configuration, relances manuelles du panneau
    latéral et de l'onglet Watchers) — DISTINCT de demarrer_watcher() (issue
    #609) : un redémarrage FORCÉ (forcer=True) d'un watcher qui a une tâche en
    cours (verrou fichier actif, cf. tache_en_cours ci-dessus) n'est jamais
    exécuté immédiatement, il COUPERAIT cette tâche. Vécu sur relecture_bridge
    #73 : configuration enregistrée puis watcher relancé pendant une issue
    mode_write déjà lancée par CCL — au redémarrage, l'issue a été reprise,
    son worktree était « déjà pris » par la première tentative, repli sur
    REP_TRAVAIL (#589) ; le travail, non isolé, a été embarqué dans un commit
    automatique d'un autre outil puis poussé par erreur.

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
    (systemctl, projet supprimé entre-temps...) est journalisée et n'empêche
    ni la sonde suivante ni le traitement des autres projets différés."""
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
    (systemctl --user, Linux-only par construction depuis #596) puisse
    s'appliquer, mais sur le ROUTAGE de l'issue traitée — labels for-linux/
    for-windows (#164) décidant si CETTE issue relève bien du watcher CCL
    local plutôt que de CCW. C'est une décision propre à l'appelant (qui a
    accès aux labels de l'issue), pas à ce helper (qui ne reçoit qu'un cfg de
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
    """Arrête le watcher du projet via `systemctl --user stop` (issue #596) —
    un arrêt délibéré de ce point de vue pour systemd, qui ne déclenche donc
    jamais `Restart=on-failure` de watcher@<projet>.service (à la différence
    d'un SIGKILL externe, cf. app.interruption._neutraliser_relance_systemd).
    Retourne (succès, message)."""
    actif, pid = watcher_actif(cfg)
    if not actif:
        return False, "watcher déjà inactif"
    unite = f"watcher@{cfg.nom}"
    try:
        subprocess.run(["systemctl", "--user", "stop", unite],
                        check=True, capture_output=True, text=True, timeout=15)
    except subprocess.CalledProcessError as e:
        return False, (e.stderr or str(e)).strip()
    except subprocess.TimeoutExpired:
        return False, "délai dépassé (systemctl --user stop)"
    chemin_pid(cfg).unlink(missing_ok=True)
    return True, f"watcher arrêté (pid {pid})"


# ─── Routes Flask ──────────────────────────────────────────────────────────────

def watchers():
    """Retourne le statut de tous les projets disponibles. `tache_en_cours`,
    `repli_rep_travail` et `redemarrage_differe` (issue #609) permettent à
    l'onglet Watchers/au panneau latéral d'afficher visiblement qu'un
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
