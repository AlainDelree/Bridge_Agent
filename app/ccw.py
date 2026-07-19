"""Onglet CCW — pilotage de la VM Windows CCW et de ses projets depuis Linux.

Issue #174. Cet onglet remplace l'usage manuel de PowerShell DANS la VM pour les
opérations courantes (démarrage, ajout de projet, finalisation avec tokens) :
tout est piloté depuis CCL (Linux) via « VBoxManage guestcontrol » (copyto +
run), sur le modèle établi par provisioning/windows/lancer_provisioning.py. Les
scripts PowerShell existants restent l'implémentation sous-jacente, appelés à
distance.

SÉCURITÉ — tokens (impératif) :
  Les valeurs de tokens (GH_TOKEN, CLAUDE_CODE_OAUTH_TOKEN) et le mot de passe
  ccw-admin ne transitent JAMAIS en argument de ligne de commande (invisibles
  dans les process/event logs Windows), et ne sont JAMAIS journalisés côté
  Linux. Ils ne vivent que dans un fichier temporaire local à permissions 0600,
  poussé dans la VM via guestcontrol copyto, lu par un script PowerShell, puis
  supprimé des DEUX côtés (finally Python côté hôte, finally PowerShell côté VM).

MOT DE PASSE ccw-admin (point 5 de l'issue) :
  Lu au moment de l'action (jamais codé en dur), par ordre de priorité :
    1. variable d'environnement CCW_ADMIN_PASSWORD (cohérent avec
       lancer_provisioning.py) ;
    2. sinon fichier local configs/ccw_admin.secret (gitignoré — comme les
       configs/*.conf). Première ligne = le mot de passe.
  Absent des deux → l'action renvoie un message clair, aucune erreur Flask brute.
"""

import contextlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from flask import jsonify, request

# Racine du projet (dossier parent du package app/) et dossier des scripts CCW.
DOSSIER_SCRIPT  = Path(__file__).resolve().parent.parent
DOSSIER_WINDOWS = DOSSIER_SCRIPT / "provisioning" / "windows"

VM_DEFAUT   = "CCW-Build"
USER_DEFAUT = "ccw-admin"

# Destination des scripts DANS la VM (invité). Chemins Windows explicites : ce
# code tourne sous Linux, où os.path ne comprend pas « \ ».
DEST_DIR_INVITE = "C:\\Windows\\Temp\\"
POWERSHELL_INVITE = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"

# Délais (s) des commandes guestcontrol. Court pour le statut/la liste ; long
# pour l'ajout (clone d'un dépôt) et la finalisation (redémarrage de service).
TIMEOUT_COURT = 90
TIMEOUT_LONG  = 900

# Marqueurs délimitant le JSON émis par lister_projets_ccw.ps1.
MARQUEUR_DEBUT = "<<<CCW_JSON>>>"
MARQUEUR_FIN   = "<<<CCW_END>>>"


# ─── Utilitaires : VBoxManage, état de la VM, mot de passe ─────────────────────

def _vboxmanage():
    """Chemin de VBoxManage ou None s'il est introuvable dans le PATH."""
    return shutil.which("VBoxManage")


def _etat_vm(vm: str = VM_DEFAUT) -> str:
    """État brut de la VM (running/poweroff/saved/…), '' si absente/indéterminé.

    Réutilise la même logique que demarrer_ccw.sh : VMState via
    « VBoxManage showvminfo --machinereadable »."""
    vbox = _vboxmanage()
    if not vbox:
        return ""
    try:
        res = subprocess.run(
            [vbox, "showvminfo", vm, "--machinereadable"],
            capture_output=True, text=True, timeout=20,
        )
    except subprocess.SubprocessError:
        return ""
    for ligne in res.stdout.splitlines():
        if ligne.startswith("VMState="):
            return ligne.split("=", 1)[1].strip().strip('"')
    return ""


def _charger_mot_de_passe() -> tuple[str | None, str | None]:
    """(mot_de_passe, source lisible) ou (None, None). JAMAIS journalisé.

    Priorité : variable d'environnement CCW_ADMIN_PASSWORD, puis fichier
    gitignoré configs/ccw_admin.secret (première ligne)."""
    mp = os.environ.get("CCW_ADMIN_PASSWORD")
    if mp:
        return mp, "variable d'environnement CCW_ADMIN_PASSWORD"
    fichier = DOSSIER_SCRIPT / "configs" / "ccw_admin.secret"
    if fichier.exists():
        try:
            val = fichier.read_text(encoding="utf-8").strip()
        except OSError:
            val = ""
        if val:
            return val, f"fichier {fichier.name}"
    return None, None


@contextlib.contextmanager
def _fichier_mot_de_passe(mot_de_passe: str):
    """Écrit le mot de passe dans un fichier temporaire 0600, supprimé quoi
    qu'il arrive (finally). Le mot de passe n'est jamais passé en argument."""
    fd, chemin = tempfile.mkstemp(prefix="ccw-pw-")
    try:
        os.chmod(chemin, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(mot_de_passe)
        yield chemin
    finally:
        if os.path.exists(chemin):
            os.remove(chemin)


# ─── Utilitaires : commandes guestcontrol ─────────────────────────────────────

def _base_guest(vbox: str, passwordfile: str) -> list[str]:
    """Préfixe commun des commandes guestcontrol (VM + identifiants)."""
    return [
        vbox, "guestcontrol", VM_DEFAUT,
        "--username", USER_DEFAUT,
        "--passwordfile", passwordfile,
    ]


def _copier(base: list[str], source_local: Path, timeout: int):
    """Pousse un fichier de l'hôte vers C:\\Windows\\Temp de la VM (copyto)."""
    cmd = base + ["copyto", "--target-directory", DEST_DIR_INVITE, str(source_local)]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def _executer_ps(base: list[str], nom_script: str, args_ps: list[str], timeout: int):
    """Exécute un script .ps1 (déjà poussé dans DEST_DIR_INVITE) via powershell.exe."""
    dest = DEST_DIR_INVITE + nom_script
    cmd = base + [
        "run",
        "--exe", POWERSHELL_INVITE,
        "--wait-stdout", "--wait-stderr",
        "--",
        "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-File", dest,
    ] + args_ps
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def _message_echec(action: str, res) -> str:
    """Message d'erreur clair à partir d'un CompletedProcess en échec.

    N'expose que stderr/stdout des commandes guestcontrol et des scripts CCW —
    aucun de ces flux ne contient de token (les scripts ne les affichent
    jamais). Tronqué aux derniers caractères pour rester lisible."""
    detail = (res.stderr or res.stdout or "").strip()
    if len(detail) > 1200:
        detail = "…" + detail[-1200:]
    base = f"Échec ({action}, code {res.returncode})."
    return f"{base} {detail}".strip()


def _sortie_lisible(res) -> str:
    """Concatène stdout + stderr d'un CompletedProcess pour affichage brut."""
    parties = [p.strip() for p in (res.stdout, res.stderr) if p and p.strip()]
    return "\n".join(parties)


def _extraire_projets(stdout: str):
    """Extrait la liste JSON émise par lister_projets_ccw.ps1 entre les
    marqueurs. Retourne une liste (éventuellement vide) ou None si illisible."""
    if MARQUEUR_DEBUT not in stdout or MARQUEUR_FIN not in stdout:
        return None
    try:
        bloc = stdout.split(MARQUEUR_DEBUT, 1)[1].split(MARQUEUR_FIN, 1)[0].strip()
        data = json.loads(bloc) if bloc else []
    except (ValueError, IndexError):
        return None
    if isinstance(data, dict):   # ConvertTo-Json déballe un tableau à 1 élément
        return [data]
    if isinstance(data, list):
        return data
    return []


def _preparer() -> tuple[tuple[str, str] | None, object]:
    """Vérifs communes avant une opération guestcontrol : VBoxManage présent,
    VM démarrée, mot de passe disponible.

    Retourne ((vbox, mot_de_passe), None) si tout est OK, sinon
    (None, réponse_json_erreur) — jamais une exception Flask brute."""
    vbox = _vboxmanage()
    if not vbox:
        return None, jsonify(succes=False,
            erreur="VBoxManage introuvable dans le PATH (VirtualBox est-il installé ?).")
    etat = _etat_vm()
    if etat != "running":
        detail = "introuvable (VM non créée)" if etat == "" else f"état actuel : « {etat} »"
        return None, jsonify(succes=False,
            erreur=f"La VM « {VM_DEFAUT} » n'est pas démarrée ({detail}). "
                   f"Démarrez-la d'abord (bouton « Démarrer »).")
    mot_de_passe, _source = _charger_mot_de_passe()
    if not mot_de_passe:
        return None, jsonify(succes=False,
            erreur="Mot de passe ccw-admin non configuré. Définissez la variable "
                   "d'environnement CCW_ADMIN_PASSWORD, ou créez le fichier "
                   "configs/ccw_admin.secret (gitignoré) contenant le mot de passe.")
    return (vbox, mot_de_passe), None


# ─── Routes Flask ─────────────────────────────────────────────────────────────

def ccw_vm_statut():
    """État de la VM CCW-Build (sans rien démarrer)."""
    vbox = _vboxmanage()
    if not vbox:
        return jsonify(succes=False,
            erreur="VBoxManage introuvable dans le PATH (VirtualBox est-il installé ?).")
    etat = _etat_vm()
    if etat == "":
        return jsonify(succes=True, existe=False, etat=None)
    return jsonify(succes=True, existe=True, etat=etat)


def ccw_demarrer_vm():
    """Démarre la VM en headless via demarrer_ccw.sh (réutilise sa logique)."""
    script = DOSSIER_WINDOWS / "demarrer_ccw.sh"
    if not script.exists():
        return jsonify(succes=False, erreur=f"Script introuvable : {script.name}")
    try:
        res = subprocess.run(["bash", str(script)],
                             capture_output=True, text=True, timeout=120)
    except subprocess.SubprocessError as e:
        return jsonify(succes=False, erreur=f"Échec du démarrage : {e}")
    return jsonify(
        succes=(res.returncode == 0),
        sortie=_sortie_lisible(res),
        etat=_etat_vm(),
        erreur=None if res.returncode == 0 else "Le démarrage de la VM a échoué.",
    )


def ccw_projets():
    """Liste les services CCW-Watcher* de la VM et leur état (via guestcontrol)."""
    ctx, err = _preparer()
    if err:
        return err
    vbox, mot_de_passe = ctx
    script = DOSSIER_WINDOWS / "lister_projets_ccw.ps1"
    if not script.exists():
        return jsonify(succes=False, erreur=f"Script introuvable : {script.name}")
    try:
        with _fichier_mot_de_passe(mot_de_passe) as pf:
            base = _base_guest(vbox, pf)
            r = _copier(base, script, TIMEOUT_COURT)
            if r.returncode != 0:
                return jsonify(succes=False, erreur=_message_echec("copie du script", r))
            r = _executer_ps(base, script.name, [], TIMEOUT_COURT)
    except subprocess.TimeoutExpired:
        return jsonify(succes=False,
            erreur="Délai dépassé en interrogeant la VM (guestcontrol).")
    except subprocess.SubprocessError as e:
        return jsonify(succes=False, erreur=f"Erreur guestcontrol : {e}")
    projets = _extraire_projets(r.stdout)
    if projets is None:
        return jsonify(succes=False, erreur=_message_echec("liste des projets", r))
    return jsonify(succes=True, projets=projets)


def ccw_ajouter_projet():
    """Ajoute un projet CCW : pousse + exécute ajouter_projet_ccw.ps1 à distance."""
    data  = request.json or {}
    nom   = (data.get("nom")   or "").strip()
    depot = (data.get("depot") or "").strip()
    if not nom or re.search(r"[\\/\s]", nom):
        return jsonify(succes=False,
            erreur="Nom de projet requis, sans espace ni séparateur de chemin.")
    if not re.match(r"^[^/\s]+/[^/\s]+$", depot):
        return jsonify(succes=False,
            erreur="Dépôt invalide : attendu au format owner/repo (ex. AlainDelree/Scrabble).")
    ctx, err = _preparer()
    if err:
        return err
    vbox, mot_de_passe = ctx
    script = DOSSIER_WINDOWS / "ajouter_projet_ccw.ps1"
    if not script.exists():
        return jsonify(succes=False, erreur=f"Script introuvable : {script.name}")
    try:
        with _fichier_mot_de_passe(mot_de_passe) as pf:
            base = _base_guest(vbox, pf)
            r = _copier(base, script, TIMEOUT_COURT)
            if r.returncode != 0:
                return jsonify(succes=False, erreur=_message_echec("copie du script", r))
            # nom/depot NE sont PAS des secrets (nom de projet + dépôt public) :
            # les passer en argument est sans risque, contrairement aux tokens.
            r = _executer_ps(base, script.name,
                             ["-NomProjet", nom, "-Depot", depot], TIMEOUT_LONG)
    except subprocess.TimeoutExpired:
        return jsonify(succes=False,
            erreur="Délai dépassé pendant l'ajout du projet (clone trop long ?).")
    except subprocess.SubprocessError as e:
        return jsonify(succes=False, erreur=f"Erreur guestcontrol : {e}")
    return jsonify(
        succes=(r.returncode == 0),
        sortie=_sortie_lisible(r),
        erreur=None if r.returncode == 0 else f"Le script a échoué (code {r.returncode}).",
    )


def ccw_finaliser_projet():
    """Finalise un projet : TOPIC_NTFY + tokens, via finaliser_projet_ccw_auto.ps1.

    Les tokens ne transitent JAMAIS en argument : ils sont écrits dans un fichier
    temporaire 0600 poussé dans la VM, lu côté VM par le script PowerShell, puis
    supprimé des deux côtés (finally Python + finally PowerShell)."""
    data  = request.json or {}
    nom   = (data.get("nom")   or "").strip()
    topic = (data.get("topic") or "").strip()
    gh    = data.get("gh_token")    or ""
    oauth = data.get("oauth_token") or ""
    if not nom or re.search(r"[\\/\s]", nom):
        return jsonify(succes=False,
            erreur="Nom de projet requis, sans espace ni séparateur de chemin.")
    if not gh or not oauth:
        return jsonify(succes=False,
            erreur="Les deux tokens (GH_TOKEN et CLAUDE_CODE_OAUTH_TOKEN) sont requis.")
    ctx, err = _preparer()
    if err:
        return err
    vbox, mot_de_passe = ctx

    script_auto   = DOSSIER_WINDOWS / "finaliser_projet_ccw_auto.ps1"
    script_tokens = DOSSIER_WINDOWS / "mettre_a_jour_tokens_ccw.ps1"
    for s in (script_auto, script_tokens):
        if not s.exists():
            return jsonify(succes=False, erreur=f"Script introuvable : {s.name}")

    # Fichier de valeurs (secrets) local, permissions 0600. Contient TOPIC_NTFY
    # + les deux tokens en « clé=valeur ». Jamais journalisé.
    fd, chemin_valeurs = tempfile.mkstemp(prefix="ccw-vals-", suffix=".txt")
    dest_valeurs = DEST_DIR_INVITE + os.path.basename(chemin_valeurs)
    try:
        os.chmod(chemin_valeurs, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(f"TOPIC_NTFY={topic}\n")
            f.write(f"GH_TOKEN={gh}\n")
            f.write(f"CLAUDE_CODE_OAUTH_TOKEN={oauth}\n")
        try:
            with _fichier_mot_de_passe(mot_de_passe) as pf:
                base = _base_guest(vbox, pf)
                # Pousser les deux scripts (l'auto appelle le tokens via
                # $PSScriptRoot → doivent être dans le même dossier) + le
                # fichier de valeurs.
                for s in (script_tokens, script_auto, Path(chemin_valeurs)):
                    r = _copier(base, s, TIMEOUT_COURT)
                    if r.returncode != 0:
                        return jsonify(succes=False,
                            erreur=_message_echec("copie des fichiers vers la VM", r))
                r = _executer_ps(base, script_auto.name,
                                 ["-NomProjet", nom, "-FichierValeurs", dest_valeurs],
                                 TIMEOUT_LONG)
        except subprocess.TimeoutExpired:
            return jsonify(succes=False,
                erreur="Délai dépassé pendant la finalisation (guestcontrol).")
        except subprocess.SubprocessError as e:
            return jsonify(succes=False, erreur=f"Erreur guestcontrol : {e}")
    finally:
        # Nettoyage LOCAL du fichier de secrets. L'homologue distant est
        # supprimé par finaliser_projet_ccw_auto.ps1 dans son finally.
        if os.path.exists(chemin_valeurs):
            os.remove(chemin_valeurs)

    sortie = _sortie_lisible(r)
    # Codes de mettre_a_jour_tokens_ccw.ps1 : 0 = OK, 2 = à vérifier, 1/autre = échec.
    if r.returncode == 0:
        return jsonify(succes=True, sortie=sortie)
    if r.returncode == 2:
        return jsonify(succes=True, avertissement=True, sortie=sortie,
            erreur="Tokens appliqués mais vérification finale non concluante — "
                   "relisez les dernières lignes de log ci-dessous.")
    return jsonify(succes=False, sortie=sortie,
        erreur=f"Échec de la finalisation (code {r.returncode}).")
