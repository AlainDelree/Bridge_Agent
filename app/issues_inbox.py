"""État de l'onglet « Résultats inbox » + pilotage du watcher spool (issues
#483, #485) + issues en attente (#713).

Lit l'état du watcher_issues_inbox (scripts/watcher_issues_inbox.py) UNIQUEMENT
depuis le disque — aucun appel gh. L'alarme visuelle de l'onglet est pilotée
exclusivement par la présence de fichiers dans issues_inbox/rejected/ (pas de
parsing de log, cf. tâche demandée de l'issue #483) ; l'historique des succès/
rejets est une simple lecture informative de logs/issues_inbox.log, sans effet
sur l'alarme.

Gestion du processus (issue #485) : même principe que chemin_pid/
watcher_actif/demarrer_watcher/arreter_watcher de app/watchers.py, mais pour
le watcher spool UNIQUE (pas de paramètre projet, un seul fichier PID). Le
watcher spool n'a par défaut pas d'auto-extinction (contrairement aux watchers
de projet, DELAI_INACTIVITE_MIN) : une durée optionnelle peut être choisie au
démarrage (--duree-min), auto-extinction interne implémentée par le script
lui-même (voir scripts/watcher_issues_inbox.py::boucle).

Issues en attente (issue #713) : un fichier déposé dans issues_inbox/ avec le
champ d'en-tête ATTENTE rempli est mis de côté par le watcher dans
issues_inbox/en_attente/ (scripts/watcher_issues_inbox.py::traiter_fichier),
AVANT toute validation/création — AUCUNE vérification automatique de la
condition, c'est Alain qui décide. Trois routes ici : `GET /issues-attente`
(liste), `POST /issues-attente/lancer` (retire le champ ATTENTE et renvoie le
fichier dans issues_inbox/ pour un traitement normal, écriture atomique) et
`POST /issues-attente/supprimer`. `GET /issues-inbox/etat` expose en plus le
compteur `nb_en_attente` (durable, relu du disque à chaque appel — le panneau
« Watcher spool » l'interroge déjà en continu, cf. #705). Dossier résolu par
la même config que le watcher (_config() ci-dessous).
"""

import logging
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from flask import jsonify, request

DOSSIER_SCRIPT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(DOSSIER_SCRIPT))
sys.path.insert(0, str(DOSSIER_SCRIPT / "scripts"))

from watcher_issues_inbox import (charger_config_inbox, DEFAUT_CHEMIN_CONFIG,  # noqa: E402
                                  DOSSIER_MOTIFS, SUFFIXE_MOTIF,
                                  lire_condition_attente, retirer_champ_attente,  # (issue #713)
                                  extraire_champs, _chemin_disponible)
from watcher import _pid_vivant  # noqa: E402

log = logging.getLogger("app.issues_inbox")

# Nombre de lignes d'historique renvoyées à l'onglet (le fichier lui-même est
# déjà borné à MAX_LOG_LINES par le watcher — cf. ConfigInbox.max_log_lines).
LIGNES_HISTORIQUE_AFFICHEES = 50

# Fichier PID : même convention que les watchers de projet (app/watchers.py::
# chemin_pid), mais chemin fixe puisqu'il n'existe qu'UN watcher spool.
CHEMIN_PID = DOSSIER_SCRIPT / "logs" / "watcher-issues_inbox.pid"
# Échéance d'auto-extinction (epoch, écrite par demarrer_watcher_inbox() si une
# durée a été choisie) — permet à l'interface d'afficher le temps restant sans
# dépendre de l'horloge interne (monotone) du process watcher, qui tourne dans
# un process séparé de Flask. Absente = watcher lancé « indéfiniment ».
CHEMIN_ECHEANCE = DOSSIER_SCRIPT / "logs" / "watcher-issues_inbox.echeance"


# ─── Gestion du processus ──────────────────────────────────────────────────

def watcher_inbox_actif() -> tuple[bool, int | None]:
    """Retourne (actif, pid) — même logique que app/watchers.py::watcher_actif, via
    watcher._pid_vivant (sonde cross-plateforme POSIX/Windows, issue #584) plutôt
    qu'un `os.kill(pid, 0)` inline."""
    if not CHEMIN_PID.exists():
        return False, None
    try:
        pid = int(CHEMIN_PID.read_text().strip())
    except ValueError:
        return False, None
    return (True, pid) if _pid_vivant(pid) else (False, None)


def _temps_restant_s():
    """Secondes avant l'auto-extinction, ou None si aucune durée n'a été
    fixée au démarrage (le watcher tourne indéfiniment)."""
    if not CHEMIN_ECHEANCE.exists():
        return None
    try:
        echeance = float(CHEMIN_ECHEANCE.read_text().strip())
    except (OSError, ValueError):
        return None
    return max(0.0, echeance - time.time())


def demarrer_watcher_inbox(duree_min: int = 0) -> tuple[bool, int]:
    """Lance (ou relance) le watcher spool. Redémarre TOUJOURS s'il tourne
    déjà — pas de refus silencieux (issue #485) : la nouvelle durée remplace
    l'ancienne. duree_min=0 → tourne indéfiniment (comportement historique)."""
    actif, pid_ancien = watcher_inbox_actif()
    if actif and pid_ancien:
        try:
            # SIGTERM (15) sûr sous Windows : routé par CPython vers
            # TerminateProcess(), hors du piège os.kill(pid, 0)/CTRL_C_EVENT
            # (issue #682) qui ne concerne que le signal 0. Ne pas retoucher.
            os.kill(pid_ancien, signal.SIGTERM)
            time.sleep(0.8)
        except OSError:
            pass

    CHEMIN_PID.parent.mkdir(parents=True, exist_ok=True)
    watcher_script = DOSSIER_SCRIPT / "scripts" / "watcher_issues_inbox.py"
    cmd = [sys.executable, str(watcher_script)]
    if duree_min > 0:
        cmd += ["--duree-min", str(duree_min)]

    # Détachement du process lancé — même pattern que watcher.py::lancer_claude
    # (issue D, app/watchers.py) : start_new_session=True est POSIX-only et lève
    # sous Windows, où CREATE_NEW_PROCESS_GROUP isole le routage Ctrl+Break.
    kwargs_popen = dict(stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if os.name == "nt":
        kwargs_popen["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs_popen["start_new_session"] = True

    proc = subprocess.Popen(cmd, **kwargs_popen)
    CHEMIN_PID.write_text(str(proc.pid))
    if duree_min > 0:
        CHEMIN_ECHEANCE.write_text(str(time.time() + duree_min * 60))
    else:
        CHEMIN_ECHEANCE.unlink(missing_ok=True)
    return True, proc.pid


def arreter_watcher_inbox() -> tuple[bool, str]:
    """Arrête le watcher spool via SIGTERM. Retourne (succès, message)."""
    actif, pid = watcher_inbox_actif()
    if not actif:
        return False, "watcher déjà inactif"
    try:
        # SIGTERM (15) sûr sous Windows : voir commentaire équivalent dans
        # demarrer_watcher_inbox() ci-dessus (issue #682).
        os.kill(pid, signal.SIGTERM)
        CHEMIN_PID.unlink(missing_ok=True)
        CHEMIN_ECHEANCE.unlink(missing_ok=True)
        return True, f"watcher arrêté (pid {pid})"
    except OSError as e:
        return False, str(e)


def _config():
    """Relit configs/watcher_issues_inbox.conf à chaque appel (comme
    app/projets.py::get_config) — reflète toujours l'état réel du fichier,
    y compris s'il a été créé/modifié à la main par Alain après le démarrage
    du serveur. Absent : défauts sensés (voir ConfigInbox)."""
    return charger_config_inbox(DEFAUT_CHEMIN_CONFIG)


def _motif_rejet(cfg, nom_fichier: str) -> str | None:
    """Motif de refus complet, lu depuis le sidecar
    `rejected/.motifs/<nom_fichier>.motif` écrit par
    watcher_issues_inbox.py::_ecrire_motif_rejet (issue #631) au moment du
    déplacement vers rejected/. Simple lecture disque : reste consultable
    après coup, y compris après un redémarrage de new_issue.py. None si
    absent (sidecar non écrit ou illisible) — le nom tronqué du fichier
    (slug du motif, cf. _slug côté watcher) reste alors l'unique indice,
    comme avant #631."""
    try:
        chemin_motif = cfg.rejected_dir / DOSSIER_MOTIFS / f"{nom_fichier}{SUFFIXE_MOTIF}"
        return chemin_motif.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def _nb_en_attente(cfg) -> int:
    """Nombre d'éléments actuellement mis de côté dans en_attente/ (issue
    #713) — compteur durable, relu du disque à chaque appel comme le reste de
    cette route (jamais un fichier à traiter par le watcher, cf.
    traiter_dossier qui ignore déjà tout sous-dossier)."""
    if not cfg.en_attente_dir.is_dir():
        return 0
    return sum(1 for chemin in cfg.en_attente_dir.iterdir() if chemin.is_file())


def etat_inbox():
    """Retourne :
      - alarme     : True si issues_inbox/rejected/ contient au moins un fichier
      - rejetes    : [{nom, date, motif}] triés du plus récent au plus ancien —
                     motif (issue #631) est le détail de refus en texte
                     intégral (sidecar <nom>.motif), None si indisponible
      - historique : dernières lignes de logs/issues_inbox.log (plus récente
                     en premier), purement informatif
      - nb_en_attente : nombre d'éléments mis de côté par le champ ATTENTE
        (issue #713), jamais comptés comme des fichiers à traiter
      - watcher_actif, watcher_pid, watcher_restant_s : état du processus
        watcher spool (issue #485) — restant_s = None si actif sans durée
        fixée (indéfini) ou si inactif.
    """
    cfg = _config()

    rejetes = []
    if cfg.rejected_dir.is_dir():
        for chemin in cfg.rejected_dir.iterdir():
            # Les sidecars de motif (issue #631) vivent dans le sous-dossier
            # DOSSIER_MOTIFS (rejected/.motifs/), jamais directement dans
            # rejected/ — .is_file() les exclut donc déjà naturellement de
            # cette liste (un dossier n'est pas un fichier), sans logique de
            # filtrage supplémentaire à maintenir ici.
            if not chemin.is_file():
                continue
            try:
                horodatage = chemin.stat().st_mtime
            except OSError:
                continue
            rejetes.append({"nom": chemin.name, "date": horodatage,
                             "motif": _motif_rejet(cfg, chemin.name)})
    rejetes.sort(key=lambda r: r["date"], reverse=True)

    historique = []
    if cfg.fichier_log.exists():
        try:
            lignes = cfg.fichier_log.read_text(encoding="utf-8").splitlines()
            historique = list(reversed(lignes[-LIGNES_HISTORIQUE_AFFICHEES:]))
        except OSError:
            historique = []

    actif, pid = watcher_inbox_actif()

    return jsonify(
        alarme=len(rejetes) > 0,
        rejetes=rejetes,
        historique=historique,
        inbox_dir=str(cfg.inbox_dir),
        rejected_dir=str(cfg.rejected_dir),
        en_attente_dir=str(cfg.en_attente_dir),
        nb_en_attente=_nb_en_attente(cfg),
        watcher_actif=actif,
        watcher_pid=pid,
        watcher_restant_s=_temps_restant_s() if actif else None,
    )


def demarrer_watcher_inbox_route():
    """Démarre (ou relance, si déjà actif) le watcher spool. JSON attendu :
    {duree_min: N} — 0 ou absent = tourne indéfiniment."""
    data = request.json or {}
    try:
        duree_min = int(data.get("duree_min") or 0)
    except (TypeError, ValueError):
        return jsonify(succes=False, erreur="duree_min invalide.")
    if duree_min < 0:
        return jsonify(succes=False, erreur="duree_min doit être positif ou nul.")
    try:
        _, pid = demarrer_watcher_inbox(duree_min)
        return jsonify(succes=True, pid=pid, duree_min=duree_min)
    except Exception as e:
        return jsonify(succes=False, erreur=str(e))


def arreter_watcher_inbox_route():
    """Arrête le watcher spool."""
    ok, msg = arreter_watcher_inbox()
    return jsonify(succes=ok, message=msg)


# ─── Issues en attente — champ ATTENTE (issue #713) ────────────────────────
# Ces trois routes n'opèrent QUE sur issues_inbox/en_attente/, jamais sur
# issues_inbox/ lui-même (hors l'écriture atomique de /lancer) — aucune
# vérification de la condition elle-même, c'est Alain qui juge.

def _identifiant_attente_valide(nom: str) -> bool:
    """Identifiant = simple nom de fichier existant dans en_attente/, AUCUNE
    séparation de chemin (traversée de répertoire interdite)."""
    return bool(nom) and nom not in (".", "..") and "/" not in nom and "\\" not in nom


def _lire_item_attente(chemin: Path) -> dict | None:
    """{id, titre, projet, date, condition} pour un fichier d'en_attente/, ou
    None si illisible. `extraire_champs` est réutilisé tel quel pour
    titre/projet — le champ ATTENTE lui-même (encore présent dans ce
    fichier) est lu séparément via lire_condition_attente, cohérent avec le
    fait qu'il n'est jamais retiré avant le lancement (POST .../lancer)."""
    try:
        contenu = chemin.read_text(encoding="utf-8")
    except OSError:
        return None
    champs = extraire_champs(contenu)
    try:
        date_depot = chemin.stat().st_mtime
    except OSError:
        date_depot = 0.0
    return {
        "id": chemin.name,
        "titre": champs["titre"],
        "projet": champs["projet"],
        "date": date_depot,
        "condition": lire_condition_attente(contenu) or "",
    }


def issues_attente_liste():
    """GET /issues-attente — éléments mis de côté par le champ ATTENTE, du
    plus ancien au plus récent (pour ne pas oublier les plus vieux)."""
    cfg = _config()
    items = []
    if cfg.en_attente_dir.is_dir():
        for chemin in cfg.en_attente_dir.iterdir():
            if not chemin.is_file():
                continue
            item = _lire_item_attente(chemin)
            if item is not None:
                items.append(item)
    items.sort(key=lambda it: it["date"])
    return jsonify(items=items)


def issues_attente_lancer():
    """POST /issues-attente/lancer — JSON {id: <nom de fichier>}. Retire le
    champ ATTENTE puis écrit le résultat dans issues_inbox/ de façon
    atomique (fichier temporaire + renommage, même dossier donc même
    système de fichiers — le watcher ne doit jamais lire un fichier à moitié
    écrit, cf. _fichier_pret) avant de supprimer l'élément d'en_attente/. Si
    l'écriture échoue, l'élément reste en place (rien n'est perdu)."""
    data = request.json or {}
    nom = (data.get("id") or "").strip()
    if not _identifiant_attente_valide(nom):
        return jsonify(succes=False, erreur="identifiant invalide."), 400

    cfg = _config()
    chemin = cfg.en_attente_dir / nom
    if not chemin.is_file():
        return jsonify(succes=False, erreur="élément introuvable."), 404

    try:
        contenu = chemin.read_text(encoding="utf-8")
    except OSError as e:
        return jsonify(succes=False, erreur=f"lecture impossible : {e}"), 500

    nouveau_contenu = retirer_champ_attente(contenu)
    cfg.inbox_dir.mkdir(parents=True, exist_ok=True)
    cible = _chemin_disponible(cfg.inbox_dir, nom)
    try:
        fd, tmp_nom = tempfile.mkstemp(dir=str(cfg.inbox_dir), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(nouveau_contenu)
            os.replace(tmp_nom, cible)
        except OSError:
            Path(tmp_nom).unlink(missing_ok=True)
            raise
    except OSError as e:
        return jsonify(succes=False, erreur=f"écriture impossible : {e}"), 500

    try:
        chemin.unlink()
    except OSError as e:
        log.warning(f"Lancée ({cible.name}) mais suppression de l'élément "
                    f"en attente {nom} échouée : {e}")

    return jsonify(succes=True, fichier=cible.name)


def issues_attente_supprimer():
    """POST /issues-attente/supprimer — JSON {id: <nom de fichier>}. Simple
    suppression du fichier d'en_attente/, sans archivage (le texte d'origine
    reste de toute façon dans la conversation Claude Chat qui l'a produit)."""
    data = request.json or {}
    nom = (data.get("id") or "").strip()
    if not _identifiant_attente_valide(nom):
        return jsonify(succes=False, erreur="identifiant invalide."), 400

    cfg = _config()
    chemin = cfg.en_attente_dir / nom
    if not chemin.is_file():
        return jsonify(succes=False, erreur="élément introuvable."), 404

    try:
        chemin.unlink()
    except OSError as e:
        return jsonify(succes=False, erreur=str(e)), 500

    return jsonify(succes=True)
