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
"""

import ntpath
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from flask import jsonify, request

from app.projets import projet_par_depot
from app.ccw import (
    _preparer, _base_guest, _fichier_mot_de_passe, _copier, _executer_ps,
    _lister_projets_vm, _extraire_projets, _etat_vm, _message_echec,
    DOSSIER_WINDOWS, TIMEOUT_COURT, TIMEOUT_LONG,
)

# app.projets ajoute déjà la racine du projet au sys.path (pour
# « from watcher import »), mais on s'assure ici aussi de l'ordre d'import.
DOSSIER_SCRIPT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(DOSSIER_SCRIPT))
from watcher import _chemin_verrou, DOSSIER_LOGS  # noqa: E402

LABEL_NEEDS_HUMAN         = "needs-human"
COMMENTAIRE_INTERRUPTION  = "⛔ Interrompu via new_issue.py"

# Étapes dont un échec rend le statut global 'echec_critique' (arbre de
# process non confirmé mort → lock volontairement non nettoyé, risque de
# double traitement si on avait poursuivi).
ETAPES_CRITIQUES = {"attente_fin_process", "verification_orphelin_claude"}


# ─── gh CLI : label + commentaire (indépendants du projet, juste le dépôt) ──

def _ajouter_label_gh(depot: str, numero: int, label: str) -> tuple[str, str]:
    try:
        res = subprocess.run(
            ["gh", "issue", "edit", str(numero), "--repo", depot, "--add-label", label],
            capture_output=True, text=True, timeout=30,
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


def _commenter_gh(depot: str, numero: int, message: str) -> tuple[str, str]:
    try:
        res = subprocess.run(
            ["gh", "issue", "comment", str(numero), "--repo", depot, "--body", message],
            capture_output=True, text=True, timeout=30,
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


def _pid_vivant(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


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


def interrompre_linux(cfg) -> list:
    etapes = []

    pid_file = DOSSIER_LOGS / f"watcher-{cfg.nom}.pid"
    pid_watcher = None
    if pid_file.exists():
        try:
            candidat = int(pid_file.read_text().strip())
            os.kill(candidat, 0)
            pid_watcher = candidat
        except (OSError, ValueError):
            pid_watcher = None

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

    return etapes


# ─── for-windows : via guestcontrol (pattern app/ccw.py) ───────────────────

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
    vbox, mot_de_passe = ctx

    projets, err = _lister_projets_vm(vbox, mot_de_passe)
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
            f"Projet « {cfg.nom} » introuvable parmi les services CCW-Watcher de la VM.")

    # RepDepot dérivé du champ « config » (…\<NomProjet>\configs\*.conf) —
    # jamais reconstruit depuis cfg.nom (Linux) ou le nom du service.
    rep_depot = (ntpath.dirname(ntpath.dirname(config_path)) if config_path
                 else ntpath.join("C:\\CCW", cfg.nom))

    script = DOSSIER_WINDOWS / "interrompre_projet_ccw.ps1"
    if not script.exists():
        return _etapes_windows_echec(f"Script introuvable : {script.name}")

    try:
        with _fichier_mot_de_passe(mot_de_passe) as pf:
            base = _base_guest(vbox, pf)
            r = _copier(base, script, TIMEOUT_COURT)
            if r.returncode != 0:
                return _etapes_windows_echec(_message_echec("copie du script vers la VM", r))
            r = _executer_ps(base, script.name, ["-Service", service, "-RepDepot", rep_depot], TIMEOUT_LONG)
    except subprocess.TimeoutExpired:
        return _etapes_windows_echec("Délai dépassé pendant l'interruption (guestcontrol).")
    except subprocess.SubprocessError as e:
        return _etapes_windows_echec(f"Erreur guestcontrol : {e}")

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
    if agent == "windows":
        reponse["vm_running"] = (_etat_vm() == "running")
    return jsonify(**reponse)
