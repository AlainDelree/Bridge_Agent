"""Interruption ciblée d'une issue en cours, par bouton dans l'onglet
Résultats (issue #323, suite #320 — abandonnée 3 fois faute de TIMEOUT
suffisant, cf. contexte de l'issue).

Contrainte centrale : interrompre UNE issue ne doit pas sacrifier les autres
issues en file pour le même watcher (elles restent ouvertes sur GitHub,
simplement en plan tant que le watcher n'est pas relancé MANUELLEMENT — pas
de rallumage automatique ici, à la différence de #202).

Chaque étape technique renvoie un statut à trois valeurs (succes /
rien_a_faire / echec) + message, jamais un simple booléen — une étape en
échec n'interrompt pas les suivantes, sauf la suppression du verrou qui est
volontairement SAUTÉE si l'arbre de process n'est pas confirmé mort (pour ne
jamais risquer un double traitement, cf. §"points de course" de l'issue).

Résolution du projet : TOUJOURS via le champ DEPOT du .conf
(app.projets.projet_par_depot), jamais déduite du nom du projet ni du
basename de REP_TRAVAIL — ces trois chaînes peuvent diverger (voir
§"résolution des identités" de l'issue #323).

Watcher LOCAL sous Windows natif (issue #701, suite #695) : l'arbre de
process n'est plus reconstruit par /proc (absent sous Windows) mais par
appartenance au Job Object persistant du watcher (créé côté watcher.py,
voir nom_job_watcher_windows) — branche `os.name == "nt"` dans
interrompre_linux (nom historique, gère en réalité le watcher local quel
que soit son OS ; interrompre_windows ci-dessous reste le chemin délégué
SSH vers le PC fixe CCW, pour les issues for-windows).
"""

import ctypes
import ctypes.wintypes
import ntpath
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from flask import jsonify, request

from app.projets import projet_par_depot
from app import github_status
from app.ccw import (
    _preparer, _copier, _executer_ps,
    _lister_projets_vm, _extraire_projets, _message_echec,
    DOSSIER_WINDOWS, TIMEOUT_COURT, TIMEOUT_LONG,
    demarrer_service_ccw_arriere_plan,  # (issue #711, étape D)
)

# app.projets ajoute déjà la racine du projet au sys.path (pour
# « from watcher import »), mais on s'assure ici aussi de l'ordre d'import.
DOSSIER_SCRIPT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(DOSSIER_SCRIPT))
from watcher import _chemin_verrou, _pid_vivant, DOSSIER_LOGS  # noqa: E402

# Job Object PERSISTANT du watcher (issue #695, côté producteur déjà en
# place dans watcher.py) : constantes/structure/fonction de nommage, SANS
# garde OS (importables sous Linux, voir watcher.py §"Job Object PERSISTANT")
# — réutilisées ci-dessous par la branche Windows de la reconstruction
# d'arbre (issue #701).
from watcher import (  # noqa: E402
    nom_job_watcher_windows,
    _JOB_OBJECT_QUERY, _JOB_OBJECT_TERMINATE, _JobObjectBasicProcessIdList,
    _JOBOBJECT_BASIC_PROCESS_ID_LIST, _CAPACITE_PID_JOB_PERSISTANT,
    _PROCESS_QUERY_LIMITED_INFORMATION,
)

LABEL_NEEDS_HUMAN         = "needs-human"
COMMENTAIRE_INTERRUPTION  = "⛔ Interrompu via new_issue.py"
COMMENTAIRE_RELANCE       = "🔄 Relancée via new_issue.py (retrait de needs-human)."

# Étapes dont un échec rend le statut global 'echec_critique' (arbre de
# process non confirmé mort → lock volontairement non nettoyé, risque de
# double traitement si on avait poursuivi).
ETAPES_CRITIQUES = {"attente_fin_process", "verification_orphelin_claude"}


# ─── gh CLI : label + commentaire (indépendants du projet, juste le dépôt) ──

def _ajouter_label_gh(depot: str, numero: int, label: str) -> tuple[str, str]:
    try:
        res = subprocess.run(
            ["gh", "issue", "edit", str(numero), "--repo", depot, "--add-label", label],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=30,
        )
        if res.returncode == 0:
            return "succes", f"Label « {label} » posé."
        return "echec", (res.stderr or res.stdout or "erreur gh inconnue").strip()
    except subprocess.TimeoutExpired:
        return "echec", "Timeout (gh n'a pas répondu en 30s)."
    except FileNotFoundError:
        return "echec", "gh introuvable dans le PATH."
    except Exception as e:
        return "echec", str(e)


def _retirer_label_gh(depot: str, numero: int, label: str) -> tuple[str, str]:
    try:
        res = subprocess.run(
            ["gh", "issue", "edit", str(numero), "--repo", depot, "--remove-label", label],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=30,
        )
        if res.returncode == 0:
            return "succes", f"Label « {label} » retiré."
        return "echec", (res.stderr or res.stdout or "erreur gh inconnue").strip()
    except subprocess.TimeoutExpired:
        return "echec", "Timeout (gh n'a pas répondu en 30s)."
    except FileNotFoundError:
        return "echec", "gh introuvable dans le PATH."
    except Exception as e:
        return "echec", str(e)


def _commenter_gh(depot: str, numero: int, message: str) -> tuple[str, str]:
    try:
        res = subprocess.run(
            ["gh", "issue", "comment", str(numero), "--repo", depot, "--body", message],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=30,
        )
        if res.returncode == 0:
            return "succes", "Commentaire posté."
        return "echec", (res.stderr or res.stdout or "erreur gh inconnue").strip()
    except subprocess.TimeoutExpired:
        return "echec", "Timeout (gh n'a pas répondu en 30s)."
    except FileNotFoundError:
        return "echec", "gh introuvable dans le PATH."
    except Exception as e:
        return "echec", str(e)


# ─── for-linux : arbre de process par remontée /proc (PPID) ────────────────
# Volontairement PAS basé sur le pgid consigné dans le verrou (#322) : ce
# champ peut être absent (claude pas encore lancé) et surtout ne couvre que
# le claude, pas le process watcher.py lui-même — ici on veut l'arbre ENTIER
# (watcher + descendance), identifié par PPID, jamais par nom d'exécutable.

def _snapshot_ppid() -> dict:
    """pid -> ppid pour tous les process actuellement vivants (lecture directe
    de /proc, sans dépendance externe). Un process qui disparaît pendant
    l'énumération est simplement absent du résultat (race normale)."""
    mapping = {}
    proc_dir = Path("/proc")
    if not proc_dir.is_dir():
        return mapping
    for entree in proc_dir.iterdir():
        if not entree.name.isdigit():
            continue
        pid = int(entree.name)
        try:
            for ligne in entree.joinpath("status").read_text(encoding="utf-8", errors="replace").splitlines():
                if ligne.startswith("PPid:"):
                    mapping[pid] = int(ligne.split(":", 1)[1].strip())
                    break
        except (OSError, ValueError):
            continue
    return mapping


def _cmdline(pid: int) -> str:
    try:
        return Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8", "replace").strip()
    except OSError:
        return "(cmdline indisponible)"


def _lister_arbre(pid_racine: int) -> list:
    """(pid, cmdline) de pid_racine et de TOUS ses descendants, par remontée
    /proc/PPid — cible uniquement l'arbre de CE watcher, jamais par nom
    d'exécutable (même esprit que #247 point 4 / #322)."""
    mapping = _snapshot_ppid()
    if pid_racine not in mapping:
        return []   # mort entre la vérification de l'appelant et cet instant (race normale)
    enfants: dict = {}
    for pid, ppid in mapping.items():
        enfants.setdefault(ppid, []).append(pid)
    vus = set()
    a_visiter = [pid_racine]
    resultat = []
    while a_visiter:
        pid = a_visiter.pop()
        if pid in vus:
            continue
        vus.add(pid)
        resultat.append((pid, _cmdline(pid)))
        a_visiter.extend(enfants.get(pid, []))
    return resultat


def _reaper_best_effort(pid: int) -> None:
    """Tente de récupérer (waitpid non bloquant) un pid qui serait un enfant
    DIRECT du process Flask courant — cas du process watcher, lancé par
    demarrer_watcher() (app/watchers.py) via subprocess.Popen SANS jamais
    être attendu ensuite. Sans ce reap, un watcher tué reste ZOMBIE et
    os.kill(pid, 0) continue de le signaler comme vivant indéfiniment,
    faussant la vérification de disparition ci-dessous. Les descendants
    (claude et sa propre descendance) ne sont PAS des enfants directs de ce
    process : ils sont reparentés au sous-reaper (init) dès la mort du
    watcher et réapés par lui, hors de notre contrôle — inutile d'y tenter
    un waitpid (ChildProcessError, ignorée)."""
    try:
        os.waitpid(pid, os.WNOHANG)
    except (ChildProcessError, OSError):
        pass


def _lister_worktrees_actifs(cfg) -> list:
    """Répertoires frères de REP_TRAVAIL correspondant à des worktrees actifs
    d'une tâche mode_write (issue #337) : même convention de nommage que
    `_chemin_worktree` dans watcher.py — `<CFG.nom>-issue<N>`, où N est un
    numéro d'issue (entier). Scanne le parent de REP_TRAVAIL, jamais
    REP_TRAVAIL lui-même."""
    parent = cfg.rep_travail.parent
    if not parent.is_dir():
        return []
    prefixe = f"{cfg.nom}-issue"
    resultat = []
    for entree in parent.iterdir():
        if not entree.is_dir():
            continue
        suffixe = entree.name[len(prefixe):]
        if entree.name.startswith(prefixe) and suffixe.isdigit():
            resultat.append(entree)
    return resultat


# ─── for-windows natif (watcher local, hors délégation CCW) : arbre de
# process par appartenance au Job Object PERSISTANT (issue #701, suite #695)
# ─────────────────────────────────────────────────────────────────────────
# /proc n'existe pas sous Windows : impossible d'y reconstruire l'arbre par
# PPID comme _lister_arbre ci-dessus. On s'appuie à la place sur le Job
# Object NOMMÉ créé par _preparer_job_persistant_windows (watcher.py, AUTRE
# process) : l'appartenance au job EST l'arbre (watcher + claude + sa
# descendance, par héritage de Job) — TerminateJobObject les tue tous d'un
# coup, sans boucle de SIGKILL ni énumération de processus séparée.

def _cmdline_windows(pid: int) -> str:
    """Windows uniquement — repli de _cmdline (/proc, absent ici) pour
    l'affichage au moment d'un « Interrompre » : chemin de l'image du
    process `pid` (QueryFullProcessImageNameW, droits minimaux — même esprit
    que _pid_vivant côté watcher.py). Volontairement PAS la ligne de commande
    complète : la reconstruire demanderait une énumération de processus
    séparée (CreateToolhelp32Snapshot/WMI), hors de portée de ctypes seul —
    le nom de l'image suffit à identifier le process dans la liste affichée
    (solution la plus simple, cf. issue #701)."""
    handle = ctypes.windll.kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return "(image indisponible)"
    try:
        taille = ctypes.wintypes.DWORD(260)
        tampon = ctypes.create_unicode_buffer(260)
        if ctypes.windll.kernel32.QueryFullProcessImageNameW(handle, 0, tampon, ctypes.byref(taille)):
            return tampon.value
        return "(image indisponible)"
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


def _arreter_arbre_windows(cfg) -> tuple:
    """Windows uniquement : rouvre PAR NOM (nom_job_watcher_windows) le job
    persistant du watcher `cfg.nom`, liste ses PID membres pour l'affichage,
    puis tue l'arbre entier via TerminateJobObject. Renvoie (etapes,
    arbre_mort), avec les MÊMES noms d'étape que la branche Linux
    (arreter_arbre_watcher / attente_fin_process) — contrat identique côté
    appelant (interrompre_linux) et côté route Flask.

    Cas limites (issue #701, point 4) :
    - Job introuvable (OpenJobObjectW échoue) : watcher déjà mort, ou lancé
      avant #695 (pas de job persistant) → 'rien_a_faire', PAS 'echec' (rien
      d'anormal, juste rien à faire ici).
    - Liste de PID tronquée (plus de membres que _CAPACITE_PID_JOB_PERSISTANT) :
      signalée dans le message, mais la terminaison porte quand même sur TOUT
      le job (TerminateJobObject n'a pas besoin de connaître les PID un par
      un, à la différence de l'énumération d'affichage)."""
    etapes = []
    nom = nom_job_watcher_windows(cfg.nom)
    handle = ctypes.windll.kernel32.OpenJobObjectW(
        _JOB_OBJECT_QUERY | _JOB_OBJECT_TERMINATE, False, nom)
    if not handle:
        etapes.append({"etape": "arreter_arbre_watcher", "statut": "rien_a_faire",
                        "message": f"Aucun job persistant « {nom} » (watcher déjà arrêté, "
                                   f"ou lancé avant #695 sans job persistant)."})
        etapes.append({"etape": "attente_fin_process", "statut": "rien_a_faire",
                        "message": "Rien à attendre."})
        return etapes, True

    info = _JOBOBJECT_BASIC_PROCESS_ID_LIST()
    taille_retour = ctypes.wintypes.DWORD(0)
    requete_ok = ctypes.windll.kernel32.QueryInformationJobObject(
        handle, _JobObjectBasicProcessIdList, ctypes.byref(info),
        ctypes.sizeof(info), ctypes.byref(taille_retour))

    arbre = []
    tronque = False
    if requete_ok:
        nb = min(info.NumberOfProcessIdsInList, _CAPACITE_PID_JOB_PERSISTANT)
        tronque = info.NumberOfAssignedProcesses > _CAPACITE_PID_JOB_PERSISTANT
        arbre = [(int(info.ProcessIdList[i]), _cmdline_windows(int(info.ProcessIdList[i])))
                 for i in range(nb)]

    if arbre:
        details = ", ".join(f"{pid} ({img})" for pid, img in arbre)
    elif requete_ok:
        details = "(aucun membre)"
    else:
        details = "(liste de PID indisponible)"
    if tronque:
        details += f" — liste tronquée à {_CAPACITE_PID_JOB_PERSISTANT} PID (job plus peuplé)."

    try:
        termine_ok = bool(ctypes.windll.kernel32.TerminateJobObject(handle, 1))
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)

    if not termine_ok:
        etapes.append({"etape": "arreter_arbre_watcher", "statut": "echec",
                        "message": f"TerminateJobObject a échoué. Membres listés : {details}"})
        etapes.append({"etape": "attente_fin_process", "statut": "echec",
                        "message": "Sautée : terminaison du job non confirmée."})
        return etapes, False

    etapes.append({"etape": "arreter_arbre_watcher", "statut": "succes",
                    "message": f"Job terminé (TerminateJobObject) : {details}"})

    if not requete_ok:
        etapes.append({"etape": "attente_fin_process", "statut": "succes",
                        "message": "Job terminé ; confirmation individuelle impossible "
                                   "(liste de PID indisponible), considéré mort."})
        return etapes, True

    limite = time.monotonic() + 5
    survivants = list(arbre)
    while True:
        survivants = [(pid, img) for pid, img in survivants if _pid_vivant(pid)]
        if not survivants or time.monotonic() >= limite:
            break
        time.sleep(0.05)

    if survivants:
        noms = ", ".join(f"{pid} ({img})" for pid, img in survivants)
        etapes.append({"etape": "attente_fin_process", "statut": "echec",
                        "message": f"Process encore vivant(s) après 5s : {noms} — lock NON nettoyé."})
        return etapes, False

    etapes.append({"etape": "attente_fin_process", "statut": "succes",
                    "message": "Arbre confirmé mort."})
    return etapes, True


# Étape "neutraliser_relance_systemd" retirée (issue #682) : elle empêchait
# systemd --user (unité `watcher@<projet>.service`, `Restart=on-failure`,
# issue #596) de voir le SIGKILL de l'arbre ci-dessus comme un crash à
# relancer, ce qui aurait contredit le contrat de #323 (« le watcher n'est
# JAMAIS relancé automatiquement après une interruption »). Depuis #682, le
# watcher n'est plus supervisé par aucun service au cycle de vie propre
# (Popen direct, détaché, sans dépendance à systemd — inexistant sous
# Windows) : rien ne peut plus le relancer de son propre chef après un
# SIGKILL, sur aucun des deux OS. Le contrat de #323 est donc respecté sans
# action supplémentaire ici — aucun équivalent Popen à cette étape.


def interrompre_linux(cfg) -> list:
    """Nom historique (issue #323) : interrompt en fait le watcher LOCAL,
    quel que soit son OS — par opposition à interrompre_windows ci-dessous,
    qui délègue par SSH au PC fixe CCW (voir route_interrompre : le choix
    entre les deux se fait sur le label for-windows de l'issue, pas sur l'OS
    courant). Sur CE process, `os.name` détermine seulement COMMENT l'arbre
    de process est reconstruit/arrêté (issue #701, suite #695) : par PPID
    via /proc sous Linux, par appartenance au Job Object persistant du
    watcher sous Windows (/proc y est absent) — tout le reste (verrou,
    worktrees) est un simple fichier, identique sur les deux OS."""
    etapes = []

    if os.name == "nt":
        etapes_arbre, arbre_mort = _arreter_arbre_windows(cfg)
        etapes.extend(etapes_arbre)
    else:
        pid_file = DOSSIER_LOGS / f"watcher-{cfg.nom}.pid"
        pid_watcher = None
        if pid_file.exists():
            try:
                candidat = int(pid_file.read_text().strip())
            except ValueError:
                candidat = None
            if candidat is not None and _pid_vivant(candidat):
                pid_watcher = candidat

        arbre = _lister_arbre(pid_watcher) if pid_watcher else []

        if not arbre:
            etapes.append({"etape": "arreter_arbre_watcher", "statut": "rien_a_faire",
                            "message": "Aucun process watcher vivant (PID absent ou mort)."})
            etapes.append({"etape": "attente_fin_process", "statut": "rien_a_faire",
                            "message": "Rien à attendre."})
            arbre_mort = True
        else:
            for pid, _cmd in arbre:
                try:
                    os.kill(pid, signal.SIGKILL)
                except OSError:
                    pass
            details = ", ".join(f"{pid} ({cmd})" for pid, cmd in arbre)
            etapes.append({"etape": "arreter_arbre_watcher", "statut": "succes",
                            "message": f"Arbre tué (SIGKILL) : {details}"})

            limite = time.monotonic() + 5
            survivants = list(arbre)
            while True:
                if pid_watcher is not None:
                    _reaper_best_effort(pid_watcher)   # évite un faux "vivant" (zombie non réapé)
                survivants = [(pid, cmd) for pid, cmd in survivants if _pid_vivant(pid)]
                if not survivants or time.monotonic() >= limite:
                    break
                time.sleep(0.05)

            if survivants:
                noms = ", ".join(f"{pid} ({cmd})" for pid, cmd in survivants)
                etapes.append({"etape": "attente_fin_process", "statut": "echec",
                                "message": f"Process encore vivant(s) après 5s : {noms} — lock NON nettoyé."})
                arbre_mort = False
            else:
                etapes.append({"etape": "attente_fin_process", "statut": "succes",
                                "message": "Arbre confirmé mort."})
                arbre_mort = True

    if not arbre_mort:
        etapes.append({"etape": "suppression_verrou", "statut": "echec",
                        "message": "Sautée : arbre de process non confirmé mort (voir étape précédente)."})
        etapes.append({"etape": "reverification_verrou", "statut": "echec",
                        "message": "Sautée : suppression non tentée."})
        return etapes

    verrou = _chemin_verrou(cfg.rep_travail)
    try:
        verrou.unlink()
        statut_suppr = "succes"
        etapes.append({"etape": "suppression_verrou", "statut": "succes",
                        "message": f"Verrou supprimé : {verrou.name}"})
    except FileNotFoundError:
        statut_suppr = "rien_a_faire"
        etapes.append({"etape": "suppression_verrou", "statut": "rien_a_faire",
                        "message": f"Aucun verrou présent ({verrou.name}) — libéré normalement ou jamais posé."})
    except OSError as e:
        statut_suppr = "echec"
        etapes.append({"etape": "suppression_verrou", "statut": "echec", "message": str(e)})

    if statut_suppr == "echec":
        etapes.append({"etape": "reverification_verrou", "statut": "echec",
                        "message": "Sautée : échec de suppression déjà signalé ci-dessus."})
    elif verrou.exists():
        etapes.append({"etape": "reverification_verrou", "statut": "echec",
                        "message": f"Un verrou frais est réapparu ({verrou.name}) — course #202 probable "
                                   f"(nouvelle issue for-linux relancée entre-temps ?). Non resupprimé."})
    else:
        etapes.append({"etape": "reverification_verrou", "statut": "succes",
                        "message": "Absence du verrou confirmée."})

    # Verrous des worktrees actifs (issue #337 / #340) : l'arbre de process
    # est confirmé mort à ce stade (arbre_mort, garde-fou déjà appliqué plus
    # haut) — il tuait déjà les threads worktree en cours, mais ne libérait
    # jusqu'ici QUE le verrou de REP_TRAVAIL, laissant les worktrees bloqués
    # jusqu'à péremption naturelle (limite documentée dans WORKTREES.md §4,
    # désormais corrigée).
    worktrees = _lister_worktrees_actifs(cfg)
    if not worktrees:
        etapes.append({"etape": "suppression_verrous_worktrees", "statut": "rien_a_faire",
                        "message": "Aucun worktree actif détecté."})
    else:
        for chemin in worktrees:
            verrou_wt = _chemin_verrou(chemin)
            nom_etape = f"suppression_verrou_worktree_{chemin.name}"
            try:
                verrou_wt.unlink()
                etapes.append({"etape": nom_etape, "statut": "succes",
                                "message": f"Verrou supprimé : {verrou_wt.name}"})
            except FileNotFoundError:
                etapes.append({"etape": nom_etape, "statut": "rien_a_faire",
                                "message": f"Aucun verrou présent ({verrou_wt.name}) — libéré normalement ou jamais posé."})
            except OSError as e:
                etapes.append({"etape": nom_etape, "statut": "echec", "message": str(e)})

    return etapes


# ─── for-windows : via SSH sur le PC fixe (pattern app/ccw.py) ─────────────

ETAPES_WINDOWS_TECHNIQUES = ("arret_service_ccw", "verification_orphelin_claude", "suppression_verrou_ccw")


def _etapes_windows_echec(message: str) -> list:
    return [{"etape": nom, "statut": "echec", "message": message} for nom in ETAPES_WINDOWS_TECHNIQUES]


def _erreur_de(reponse_json) -> str:
    """Extrait le champ erreur d'une réponse jsonify(...) d'échec d'app.ccw."""
    try:
        return reponse_json.get_json().get("erreur") or "Erreur inconnue."
    except Exception:
        return "Erreur inconnue."


def interrompre_windows(cfg) -> list:
    ctx, err = _preparer()
    if err:
        return _etapes_windows_echec(_erreur_de(err))
    hote, utilisateur, cle_privee = ctx

    projets, err = _lister_projets_vm(hote, utilisateur, cle_privee)
    if err:
        return _etapes_windows_echec(_erreur_de(err))

    service = config_path = None
    for p in projets:
        if isinstance(p, dict) and str(p.get("projet", "")).strip().lower() == cfg.nom.lower():
            service     = (p.get("service") or "").strip()
            config_path = (p.get("config") or "").strip()
            break
    if not service:
        return _etapes_windows_echec(
            f"Projet « {cfg.nom} » introuvable parmi les services CCW-Watcher du PC fixe.")

    # RepDepot dérivé du champ « config » (…\<NomProjet>\configs\*.conf) —
    # jamais reconstruit depuis cfg.nom (Linux) ou le nom du service.
    rep_depot = (ntpath.dirname(ntpath.dirname(config_path)) if config_path
                 else ntpath.join("C:\\CCW", cfg.nom))

    script = DOSSIER_WINDOWS / "interrompre_projet_ccw.ps1"
    if not script.exists():
        return _etapes_windows_echec(f"Script introuvable : {script.name}")

    try:
        r = _copier(hote, utilisateur, cle_privee, script, TIMEOUT_COURT)
        if r.returncode != 0:
            return _etapes_windows_echec(_message_echec("copie du script vers le PC fixe", r))
        r = _executer_ps(hote, utilisateur, cle_privee, script.name,
                         ["-Service", service, "-RepDepot", rep_depot], TIMEOUT_LONG)
    except subprocess.TimeoutExpired:
        return _etapes_windows_echec("Délai dépassé pendant l'interruption (SSH).")
    except subprocess.SubprocessError as e:
        return _etapes_windows_echec(f"Erreur SSH : {e}")

    resultats = _extraire_projets(r.stdout)
    if resultats is None:
        return _etapes_windows_echec(_message_echec("interruption du projet CCW", r))

    etapes = []
    for item in resultats:
        if not isinstance(item, dict):
            continue
        etapes.append({
            "etape":   item.get("etape", "?"),
            "statut":  item.get("statut", "echec"),
            "message": item.get("message", ""),
        })
    if not etapes:
        return _etapes_windows_echec("Réponse de la VM vide ou illisible.")
    return etapes


# ─── Route Flask ─────────────────────────────────────────────────────────────

def route_interrompre():
    """POST /interrompre — interrompt le traitement en cours d'UNE issue,
    sans toucher aux autres issues en file pour le même watcher.

    Toujours, quel que soit le résultat des étapes techniques : label
    needs-human posé + commentaire d'interruption posté (sortie du circuit +
    trace GitHub). Le watcher n'est JAMAIS relancé automatiquement — relance
    manuelle des deux côtés (bouton « Lancer watcher » côté CCL, onglet CCW
    côté CCW-Watcher)."""
    data   = request.json or {}
    depot  = (data.get("depot") or "").strip()
    numero = data.get("numero")
    labels = [str(l).strip().lower() for l in (data.get("labels") or [])]

    if not depot:
        return jsonify(succes=False, erreur="Dépôt GitHub manquant."), 400
    if not str(numero).isdigit():
        return jsonify(succes=False, erreur="Numéro d'issue invalide."), 400
    numero = int(numero)

    cfg = projet_par_depot(depot)
    if not cfg:
        return jsonify(succes=False, erreur=f"Aucun projet configuré pour le dépôt « {depot} »."), 404

    agent = "windows" if "for-windows" in labels else "linux"

    # Étape impérative en premier : sortie du circuit + trace, quel que soit
    # le résultat des étapes techniques qui suivent (posée dans TOUS les cas).
    statut_label, msg_label = _ajouter_label_gh(depot, numero, LABEL_NEEDS_HUMAN)
    etapes = [{"etape": "label_needs_human", "statut": statut_label, "message": msg_label}]

    etapes += interrompre_windows(cfg) if agent == "windows" else interrompre_linux(cfg)

    statut_comment, msg_comment = _commenter_gh(depot, numero, COMMENTAIRE_INTERRUPTION)
    etapes.append({"etape": "commentaire", "statut": statut_comment, "message": msg_comment})

    if any(e["etape"] in ETAPES_CRITIQUES and e["statut"] == "echec" for e in etapes):
        statut_global = "echec_critique"
    elif any(e["statut"] == "echec" for e in etapes):
        statut_global = "succes_partiel"
    else:
        statut_global = "ok"

    reponse = dict(succes=True, agent=agent, statut_global=statut_global, etapes=etapes)
    return jsonify(**reponse)


def relancer_issue(depot: str, numero: int, commentaire: str = COMMENTAIRE_RELANCE) -> tuple[str, list]:
    """Cœur de la relance (issue #460) : retrait du label needs-human + trace
    en commentaire GitHub — remet une issue en file d'attente sans recréer de
    nouvelle issue. Factorisée hors de route_relancer() pour être réutilisable
    hors contexte HTTP (champ RELANCE d'issues_inbox/, issue #516), qui poste
    un commentaire de trace différent (mentionnant les champs corrigés).

    Il n'existe PAS de label « pending » dans ce projet : le watcher
    (watcher.py) traite déjà toute issue OUVERTE for-linux/for-windows tant
    qu'elle ne porte ni `done` ni `needs-human` (voir LABEL_ECHEC/LABEL_FAIT
    dans watcher.py) — retirer needs-human suffit donc à la rendre de nouveau
    éligible au prochain cycle. Ne relance PAS le watcher lui-même (même
    esprit que interrompre_linux/interrompre_windows ci-dessus : action
    manuelle séparée si le watcher est éteint)."""
    statut_label, msg_label = _retirer_label_gh(depot, numero, LABEL_NEEDS_HUMAN)
    etapes = [{"etape": "retrait_label_needs_human", "statut": statut_label, "message": msg_label}]

    statut_comment, msg_comment = _commenter_gh(depot, numero, commentaire)
    etapes.append({"etape": "commentaire", "statut": statut_comment, "message": msg_comment})

    statut_global = "echec" if any(e["statut"] == "echec" for e in etapes) else "ok"

    # Alerte explicite de panne GitHub (issue #732, point d'appel « relance ») :
    # un succès referme un épisode de panne en cours ; un échec classé « panne
    # probable » (timeout/réseau/5xx — jamais une erreur gh normale) en ouvre un.
    if statut_global == "ok":
        github_status.signaler_resultat_gh(True, origine="relancer_issue")
    else:
        panne = any(e["statut"] == "echec" and github_status.classer_echec_gh(e["message"])
                    for e in etapes)
        github_status.signaler_resultat_gh(False, panne_probable=panne, origine="relancer_issue")

    return statut_global, etapes


def route_relancer():
    """POST /relancer-issue — remet en file d'attente une issue bloquée en
    needs-human (issue #460), sans recréer une nouvelle issue. Mince wrapper
    Flask autour de relancer_issue() ci-dessus, qui porte la logique réelle.

    Redémarrage auto du watcher CCL cible si éteint (issue #574) : c'était le
    seul des trois chemins qui remettent une issue en circuit à ne PAS
    redémarrer le watcher si l'auto-extinction par inactivité (#200) l'a
    éteint entre-temps — à la différence de la création d'issue
    (app/issues.py::envoyer, #202) et du bloc RELANCE
    (scripts/watcher_issues_inbox.py::_traiter_relance, #572), qui le font
    déjà tous les deux. Même garde que ces deux chemins (for-linux) et même
    philosophie : un échec du démarrage ne doit JAMAIS transformer une
    relance réussie en erreur (try/except large), tracé dans le commentaire
    posté sur l'issue ET dans la réponse JSON plutôt que silencieux.

    for-windows (issue #711, étape D du retrofit CCW) : symétrique, mais vers
    le service CCW délégué (PC fixe, SSH) via demarrer_service_ccw_arriere_plan
    (#709, étape C) — strictement non bloquant (thread démon, jamais de
    résultat récupérable ici), à la différence du watcher CCL ci-dessus :
    rien n'est donc ajouté au commentaire ni à la réponse JSON pour ce cas."""
    data   = request.json or {}
    depot  = (data.get("depot") or "").strip()
    numero = data.get("numero")
    labels = [str(l).strip().lower() for l in (data.get("labels") or [])]

    if not depot:
        return jsonify(succes=False, erreur="Dépôt GitHub manquant."), 400
    if not str(numero).isdigit():
        return jsonify(succes=False, erreur="Numéro d'issue invalide."), 400
    numero = int(numero)

    cfg = projet_par_depot(depot)

    trace_watcher = ""
    watcher_demarre, watcher_pid = None, None
    if cfg and "for-linux" in labels:
        from app.watchers import redemarrer_si_eteint
        watcher_demarre, watcher_pid, trace_watcher = redemarrer_si_eteint(cfg, tracer=True)
    elif cfg and "for-windows" in labels:
        demarrer_service_ccw_arriere_plan(cfg.nom)

    statut_global, etapes = relancer_issue(depot, numero, commentaire=COMMENTAIRE_RELANCE + trace_watcher)

    # Décoche la case « traité/lu » de cette issue dans l'onglet Résultats
    # (issue #721, même intention que le chemin fichier RELANCE #720) :
    # l'issue va produire un nouveau résultat, elle ne doit plus apparaître
    # comme déjà lue. Même process que l'état des cases (new_issue.py) :
    # appel direct à la fonction partagée, pas de notification réseau.
    # Seulement si la relance a réussi (sinon la case ne doit pas changer),
    # et seulement si le projet est connu localement (cfg, sinon pas de case
    # possible pour ce dépôt).
    if statut_global == "ok" and cfg:
        from app.cases_cochees import decocher_et_diffuser
        decocher_et_diffuser(cfg.nom, numero)

    # Ré-ajout à la liste surveillée par le poller de notifications (issue
    # #624) : une issue for-windows relancée avait été RETIRÉE de la liste au
    # moment de son échec définitif (needs-human) — sans ce ré-ajout, ni sa
    # future prise en charge (ACK) ni sa clôture ne seraient plus détectées.
    # Seulement si le retrait du label a bien réussi (statut_global == "ok") :
    # sinon needs-human reste posé et ré-ajouter l'issue ferait redétecter la
    # MÊME transition needs-human au prochain cycle. Même process → appel
    # direct, pas de HTTP.
    if statut_global == "ok" and "for-windows" in labels:
        from app.notifications_poller import ajouter_issue_surveillee
        ajouter_issue_surveillee(depot, numero, labels)

    # Même classification que relancer_issue() ci-dessus (issue #732), à
    # destination du JS : il déclenche la vérification de statut GitHub
    # seulement sur ce signal, jamais sur un échec « normal » de la relance.
    panne_probable = any(e["statut"] == "echec" and github_status.classer_echec_gh(e["message"])
                          for e in etapes)
    return jsonify(succes=True, statut_global=statut_global, etapes=etapes,
                   watcher_demarre=watcher_demarre, watcher_pid=watcher_pid,
                   panne_probable=panne_probable)
