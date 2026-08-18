"""Onglet CCW — pilotage du PC Windows physique CCW et de ses projets depuis
Linux.

Issue #174 (VBoxManage guestcontrol), remplacé par SSH en issue #447 (CCW
tourne désormais sur un PC fixe physique, plus de VM VirtualBox). Cet onglet
remplace l'usage manuel de PowerShell SUR le PC pour les opérations courantes
(ajout de projet, finalisation avec tokens) : tout est piloté depuis CCL
(Linux) via SSH/SCP. Les scripts PowerShell existants restent l'implémentation
sous-jacente, appelés à distance — seul le transport a changé.

SÉCURITÉ — tokens (impératif) :
  Les valeurs de tokens (GH_TOKEN, CLAUDE_CODE_OAUTH_TOKEN) ne transitent
  JAMAIS en argument de ligne de commande (invisibles dans les process/event
  logs Windows), et ne sont JAMAIS journalisés côté Linux. Ils ne vivent que
  dans un fichier temporaire local à permissions 0600, poussé sur le PC via
  scp, lu par un script PowerShell, puis supprimé des DEUX côtés (finally
  Python côté hôte, finally PowerShell côté PC).

CONFIGURATION SSH :
  Lue au moment de l'action (jamais codée en dur), par ordre de priorité pour
  chaque valeur — variable d'environnement d'abord, sinon fichier local
  configs/ccw_ssh.conf (gitignoré — comme les configs/*.conf, format
  « CLÉ = valeur ») :
    1. hôte du PC fixe (IP ou nom réseau local) : CCW_SSH_HOTE / HOTE ;
    2. utilisateur SSH : CCW_SSH_UTILISATEUR / UTILISATEUR (défaut AlainW) ;
    3. chemin de la clé privée SSH sur CCL : CCW_SSH_CLE_PRIVEE / CLE_PRIVEE.
  Prérequis manuels (hors périmètre de ce code) : OpenSSH Server activé sur le
  PC fixe, clé publique installée dans authorized_keys de l'utilisateur SSH.
  Configuration absente/incomplète → l'action renvoie un message clair, aucune
  erreur Flask brute.
"""

import json
import ntpath
import os
import re
import subprocess
import tempfile
from pathlib import Path

from flask import jsonify, request

# Racine du projet (dossier parent du package app/) et dossier des scripts CCW.
DOSSIER_SCRIPT  = Path(__file__).resolve().parent.parent
DOSSIER_WINDOWS = DOSSIER_SCRIPT / "provisioning" / "windows"

FICHIER_CONF_SSH   = DOSSIER_SCRIPT / "configs" / "ccw_ssh.conf"
UTILISATEUR_DEFAUT = "AlainW"

# Destination des scripts sur le PC fixe. Barres obliques (pas de « \ ») :
# acceptées telles quelles par scp comme par powershell.exe -File, et ce code
# tourne sous Linux, où os.path ne comprend pas « \ ».
DEST_DIR_DISTANT  = "C:/Windows/Temp/"
POWERSHELL_DISTANT = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"

# Options ssh/scp communes : authentification par clé uniquement (jamais de
# prompt interactif — un shell watcher ne peut pas répondre à un mot de
# passe), acceptation silencieuse d'une nouvelle clé d'hôte (réseau local de
# confiance), délai de connexion court pour échouer vite si le PC est injoignable.
OPTIONS_SSH = ["-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new",
               "-o", "ConnectTimeout=10"]

# Délais (s) des commandes ssh/scp. Court pour le statut/la liste ; long pour
# l'ajout (clone d'un dépôt) et la finalisation (redémarrage de service).
TIMEOUT_COURT = 90
TIMEOUT_LONG  = 900

# Marqueurs délimitant le JSON émis par lister_projets_ccw.ps1.
MARQUEUR_DEBUT = "<<<CCW_JSON>>>"
MARQUEUR_FIN   = "<<<CCW_END>>>"


# ─── Utilitaires : configuration SSH ───────────────────────────────────────────

def _lire_conf_ssh() -> dict:
    """Lecteur 'CLÉ = valeur' minimal de configs/ccw_ssh.conf (gitignoré),
    même format que lire_conf() de watcher.py. Dict vide si le fichier
    n'existe pas ou est illisible."""
    if not FICHIER_CONF_SSH.exists():
        return {}
    donnees: dict[str, str] = {}
    try:
        brut = FICHIER_CONF_SSH.read_text(encoding="utf-8")
    except OSError:
        return {}
    for ligne in brut.splitlines():
        ligne = ligne.strip()
        if not ligne or ligne.startswith("#"):
            continue
        cle, sep, valeur = ligne.partition("=")
        if sep:
            donnees[cle.strip().upper()] = valeur.strip()
    return donnees


def _charger_config_ssh() -> tuple[tuple[str, str, str] | None, str | None]:
    """(hote, utilisateur, cle_privee) ou (None, message d'erreur lisible).

    Priorité PAR VALEUR, comme l'ancien CCW_ADMIN_PASSWORD : variable
    d'environnement d'abord, sinon configs/ccw_ssh.conf (gitignoré)."""
    conf = _lire_conf_ssh()
    hote        = os.environ.get("CCW_SSH_HOTE") or conf.get("HOTE")
    utilisateur = (os.environ.get("CCW_SSH_UTILISATEUR") or conf.get("UTILISATEUR")
                   or UTILISATEUR_DEFAUT)
    cle         = os.environ.get("CCW_SSH_CLE_PRIVEE") or conf.get("CLE_PRIVEE")
    if not hote:
        return None, ("Hôte SSH du PC fixe CCW non configuré. Définissez la variable "
                       "d'environnement CCW_SSH_HOTE, ou créez configs/ccw_ssh.conf "
                       "(gitignoré) avec une ligne HOTE=<ip-ou-nom-reseau-local>.")
    if not cle:
        return None, ("Clé privée SSH non configurée. Définissez la variable "
                       "d'environnement CCW_SSH_CLE_PRIVEE, ou ajoutez une ligne "
                       "CLE_PRIVEE=<chemin> dans configs/ccw_ssh.conf.")
    chemin_cle = Path(cle).expanduser()
    if not chemin_cle.exists():
        return None, f"Clé privée SSH introuvable : {chemin_cle}"
    return (hote, utilisateur, str(chemin_cle)), None


# ─── Utilitaires : commandes ssh/scp ────────────────────────────────────────────

def _base_ssh(hote: str, utilisateur: str, cle_privee: str) -> list[str]:
    """Préfixe commun des commandes ssh (options batch + cible)."""
    return ["ssh", "-i", cle_privee, *OPTIONS_SSH, f"{utilisateur}@{hote}"]


def _quoter(valeur: str) -> str:
    """Encadre une valeur de guillemets doubles pour la commande distante —
    la commande envoyée par ssh est exécutée par le shell distant (cmd.exe
    sous Windows/OpenSSH), pas par un shell POSIX local. Échappe les
    guillemets internes en les doublant (convention cmd.exe)."""
    return '"' + valeur.replace('"', '""') + '"'


def _copier(hote: str, utilisateur: str, cle_privee: str, source_local: Path, timeout: int):
    """Pousse un fichier de l'hôte vers C:/Windows/Temp du PC fixe (scp)."""
    cible = f"{utilisateur}@{hote}:{DEST_DIR_DISTANT}"
    cmd = ["scp", "-i", cle_privee, *OPTIONS_SSH, str(source_local), cible]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def _executer_ps(hote: str, utilisateur: str, cle_privee: str,
                  nom_script: str, args_ps: list[str], timeout: int):
    """Exécute un script .ps1 (déjà poussé dans DEST_DIR_DISTANT) via powershell.exe.

    stdout/stderr proviennent de la console Windows du PC fixe, encodée en
    CP1252 (page de code par défaut), pas en UTF-8 — d'où le décodage
    explicite ci-dessous (errors="replace" en filet de sécurité)."""
    dest = DEST_DIR_DISTANT + nom_script
    commande = " ".join([
        _quoter(POWERSHELL_DISTANT), "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-File", _quoter(dest),
    ] + [_quoter(a) for a in args_ps])
    cmd = _base_ssh(hote, utilisateur, cle_privee) + [commande]
    return subprocess.run(cmd, capture_output=True, encoding="cp1252",
                           errors="replace", timeout=timeout)


def _executer_commande_ps(hote: str, utilisateur: str, cle_privee: str,
                           commande: str, timeout: int):
    """Exécute une commande PowerShell arbitraire sur le PC fixe (résolution PATH).

    Utilisé pour lancer un exécutable déjà présent dans le PATH du PC (ex.
    « nssm ») sans avoir à pousser un script .ps1 pour une commande triviale.

    Même remarque que _executer_ps : sortie de la console Windows en
    CP1252, pas en UTF-8."""
    cmd_ps = " ".join([
        _quoter(POWERSHELL_DISTANT), "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-Command", _quoter(commande),
    ])
    cmd = _base_ssh(hote, utilisateur, cle_privee) + [cmd_ps]
    return subprocess.run(cmd, capture_output=True, encoding="cp1252",
                           errors="replace", timeout=timeout)


def _message_echec(action: str, res) -> str:
    """Message d'erreur clair à partir d'un CompletedProcess en échec.

    N'expose que stderr/stdout des commandes ssh/scp et des scripts CCW —
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


def _preparer() -> tuple[tuple[str, str, str] | None, object]:
    """Vérif commune avant une opération SSH : configuration disponible
    (hôte, utilisateur, clé privée).

    Retourne ((hote, utilisateur, cle_privee), None) si tout est OK, sinon
    (None, réponse_json_erreur) — jamais une exception Flask brute."""
    ctx, erreur = _charger_config_ssh()
    if erreur:
        return None, jsonify(succes=False, erreur=erreur)
    return ctx, None


# ─── Routes Flask ─────────────────────────────────────────────────────────────

def _lister_projets_vm(hote: str, utilisateur: str, cle_privee: str):
    """Interroge lister_projets_ccw.ps1 sur le PC fixe (copie + exécution SSH).

    Retourne (projets, None) où projets est une liste de dicts (clés service,
    projet, base, etat, config, topicStatut), ou (None, réponse_json_erreur).
    Source de vérité UNIQUE pour la correspondance projet → nom de service :
    évite de dupliquer une nouvelle fois la règle Bridge_Agent → « CCW-Watcher »
    déjà portée par ce script et finaliser_projet_ccw_auto.ps1 (issue #180)."""
    script = DOSSIER_WINDOWS / "lister_projets_ccw.ps1"
    if not script.exists():
        return None, jsonify(succes=False, erreur=f"Script introuvable : {script.name}")
    try:
        r = _copier(hote, utilisateur, cle_privee, script, TIMEOUT_COURT)
        if r.returncode != 0:
            return None, jsonify(succes=False, erreur=_message_echec("copie du script", r))
        r = _executer_ps(hote, utilisateur, cle_privee, script.name, [], TIMEOUT_COURT)
    except subprocess.TimeoutExpired:
        return None, jsonify(succes=False,
            erreur="Délai dépassé en interrogeant le PC fixe (SSH).")
    except subprocess.SubprocessError as e:
        return None, jsonify(succes=False, erreur=f"Erreur SSH : {e}")
    projets = _extraire_projets(r.stdout)
    if projets is None:
        return None, jsonify(succes=False, erreur=_message_echec("liste des projets", r))
    return projets, None


def ccw_projets():
    """Liste les services CCW-Watcher* du PC fixe et leur état (via SSH)."""
    ctx, err = _preparer()
    if err:
        return err
    hote, utilisateur, cle_privee = ctx
    projets, err = _lister_projets_vm(hote, utilisateur, cle_privee)
    if err:
        return err
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
    hote, utilisateur, cle_privee = ctx
    script = DOSSIER_WINDOWS / "ajouter_projet_ccw.ps1"
    if not script.exists():
        return jsonify(succes=False, erreur=f"Script introuvable : {script.name}")
    try:
        r = _copier(hote, utilisateur, cle_privee, script, TIMEOUT_COURT)
        if r.returncode != 0:
            return jsonify(succes=False, erreur=_message_echec("copie du script", r))
        # nom/depot NE sont PAS des secrets (nom de projet + dépôt public) :
        # les passer en argument est sans risque, contrairement aux tokens.
        r = _executer_ps(hote, utilisateur, cle_privee, script.name,
                         ["-NomProjet", nom, "-Depot", depot], TIMEOUT_LONG)
    except subprocess.TimeoutExpired:
        return jsonify(succes=False,
            erreur="Délai dépassé pendant l'ajout du projet (clone trop long ?).")
    except subprocess.SubprocessError as e:
        return jsonify(succes=False, erreur=f"Erreur SSH : {e}")
    return jsonify(
        succes=(r.returncode == 0),
        sortie=_sortie_lisible(r),
        erreur=None if r.returncode == 0 else f"Le script a échoué (code {r.returncode}).",
    )


def ccw_finaliser_projet():
    """Finalise un projet : TOPIC_NTFY + tokens, via finaliser_projet_ccw_auto.ps1.

    Les tokens ne transitent JAMAIS en argument : ils sont écrits dans un fichier
    temporaire 0600 poussé sur le PC fixe via scp, lu côté PC par le script
    PowerShell, puis supprimé des deux côtés (finally Python + finally
    PowerShell)."""
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
    hote, utilisateur, cle_privee = ctx

    script_auto   = DOSSIER_WINDOWS / "finaliser_projet_ccw_auto.ps1"
    script_tokens = DOSSIER_WINDOWS / "mettre_a_jour_tokens_ccw.ps1"
    for s in (script_auto, script_tokens):
        if not s.exists():
            return jsonify(succes=False, erreur=f"Script introuvable : {s.name}")

    # Fichier de valeurs (secrets) local, permissions 0600. Contient TOPIC_NTFY
    # + les deux tokens en « clé=valeur ». Jamais journalisé.
    fd, chemin_valeurs = tempfile.mkstemp(prefix="ccw-vals-", suffix=".txt")
    dest_valeurs = DEST_DIR_DISTANT + os.path.basename(chemin_valeurs)
    try:
        os.chmod(chemin_valeurs, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(f"TOPIC_NTFY={topic}\n")
            f.write(f"GH_TOKEN={gh}\n")
            f.write(f"CLAUDE_CODE_OAUTH_TOKEN={oauth}\n")
        try:
            # Pousser les deux scripts (l'auto appelle le tokens via
            # $PSScriptRoot → doivent être dans le même dossier) + le
            # fichier de valeurs.
            for s in (script_tokens, script_auto, Path(chemin_valeurs)):
                r = _copier(hote, utilisateur, cle_privee, s, TIMEOUT_COURT)
                if r.returncode != 0:
                    return jsonify(succes=False,
                        erreur=_message_echec("copie des fichiers vers le PC fixe", r))
            r = _executer_ps(hote, utilisateur, cle_privee, script_auto.name,
                             ["-NomProjet", nom, "-FichierValeurs", dest_valeurs],
                             TIMEOUT_LONG)
        except subprocess.TimeoutExpired:
            return jsonify(succes=False,
                erreur="Délai dépassé pendant la finalisation (SSH).")
        except subprocess.SubprocessError as e:
            return jsonify(succes=False, erreur=f"Erreur SSH : {e}")
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


def _piloter_service_ccw(action_nssm: str, verbe: str):
    """Exécute « nssm <action_nssm> <service> » sur le service Windows d'un projet
    CCW, sans toucher au topic ni aux tokens (issues #180 / #203).

    Facteur commun de redemarrer/demarrer/arreter-projet : validation du nom de
    projet reçu, résolution du nom EXACT du service via lister_projets_ccw.ps1
    (source de vérité unique — voir _lister_projets_vm), ce qui gère de fait le
    spécial-cas « Bridge_Agent » → « CCW-Watcher » (sans suffixe) sans dupliquer la
    règle, garde-fou sur le format du service, puis exécution à distance (nssm est
    déjà dans le PATH du PC fixe).

    action_nssm : sous-commande nssm (« restart », « start », « stop »).
    verbe       : nom de l'action pour les messages (« redémarrage », « démarrage »,
                  « arrêt »)."""
    data = request.json or {}
    nom  = (data.get("nom") or "").strip()
    if not nom or re.search(r"[\\/\s]", nom):
        return jsonify(succes=False,
            erreur="Nom de projet requis, sans espace ni séparateur de chemin.")
    ctx, err = _preparer()
    if err:
        return err
    hote, utilisateur, cle_privee = ctx

    projets, err = _lister_projets_vm(hote, utilisateur, cle_privee)
    if err:
        return err
    service = None
    for p in projets:
        if isinstance(p, dict) and str(p.get("projet", "")).strip().lower() == nom.lower():
            service = (p.get("service") or "").strip()
            break
    if not service:
        return jsonify(succes=False,
            erreur=f"Projet « {nom} » introuvable parmi les services CCW-Watcher du PC fixe. "
                   f"Rafraîchissez la liste des projets.")
    # Garde-fou : le nom vient de la liste (donc de confiance), mais on vérifie
    # qu'il correspond bien au format attendu d'un service CCW avant de
    # l'injecter dans la commande PowerShell.
    if not re.match(r"^CCW-Watcher(-\w+)?$", service):
        return jsonify(succes=False,
            erreur=f"Nom de service inattendu (« {service} ») — abandon par précaution.")

    try:
        # « exit $LASTEXITCODE » : propage le code de retour de nssm pour que
        # l'appelant conclue sans ambiguïté (0 = opération OK).
        r = _executer_commande_ps(
            hote, utilisateur, cle_privee,
            f"nssm {action_nssm} {service}; exit $LASTEXITCODE", TIMEOUT_LONG)
    except subprocess.TimeoutExpired:
        return jsonify(succes=False,
            erreur=f"Délai dépassé — {verbe} du service interrompu (SSH).")
    except subprocess.SubprocessError as e:
        return jsonify(succes=False, erreur=f"Erreur SSH : {e}")

    return jsonify(
        succes=(r.returncode == 0),
        service=service,
        sortie=_sortie_lisible(r),
        erreur=None if r.returncode == 0
               else f"Échec — {verbe} de « {service} » (code {r.returncode}).",
    )


def ccw_redemarrer_projet():
    """Redémarre le service Windows d'un projet CCW (issue #180).

    Cas d'usage : relancer un service après une correction manuelle ou un
    diagnostic, sans repasser par PowerShell dans la VM ni reposer topic/tokens.
    Simple « nssm restart <service> » — voir _piloter_service_ccw."""
    return _piloter_service_ccw("restart", "redémarrage")


def ccw_demarrer_projet():
    """Démarre le service Windows d'un projet CCW (issue #203).

    Contrôle indépendant du redémarrage : « nssm start <service> ». Utile pour
    relancer un service précédemment arrêté. Voir _piloter_service_ccw."""
    return _piloter_service_ccw("start", "démarrage")


def ccw_arreter_projet():
    """Arrête le service Windows d'un projet CCW (issue #203).

    Contrôle indépendant du redémarrage : « nssm stop <service> ». Utile pour
    arrêter temporairement un service (économie de ressources VM) sans le
    relancer aussitôt. Voir _piloter_service_ccw."""
    return _piloter_service_ccw("stop", "arrêt")


def _texte_erreur_json(reponse_json) -> str:
    """Extrait le champ erreur d'une réponse jsonify(...) d'échec (_preparer,
    _lister_projets_vm) — même logique que _erreur_de dans app/interruption.py,
    dupliquée ici pour éviter un import circulaire (interruption.py importe déjà
    depuis ce module)."""
    try:
        return reponse_json.get_json().get("erreur") or "Erreur inconnue."
    except Exception:
        return "Erreur inconnue."


def ccw_nettoyer_verrous():
    """Nettoie les verrous CCW orphelins d'un projet (issue #431, bouton
    « 🔒 Nettoyer verrous CCW + redémarrer » prévu par #378) : arrête le
    service, supprime tous les .lock de son dossier de verrous, puis relance
    — un seul aller-retour SSH (copie + exécution de nettoyer_verrous_ccw.ps1),
    sur le modèle d'interrompre_windows() (app/interruption.py).

    Cas d'usage : un verrou orphelin bloque le watcher CCW sans qu'il y ait
    d'issue précise à interrompre (le bouton « Interrompre » n'est disponible
    que sur une issue ouverte précise)."""
    data = request.json or {}
    nom  = (data.get("nom") or "").strip()
    if not nom or re.search(r"[\\/\s]", nom):
        return jsonify(statut="echec",
            message="Nom de projet requis, sans espace ni séparateur de chemin.")

    ctx, err = _preparer()
    if err:
        return jsonify(statut="echec", message=_texte_erreur_json(err))
    hote, utilisateur, cle_privee = ctx

    projets, err = _lister_projets_vm(hote, utilisateur, cle_privee)
    if err:
        return jsonify(statut="echec", message=_texte_erreur_json(err))

    service = config_path = None
    for p in projets:
        if isinstance(p, dict) and str(p.get("projet", "")).strip().lower() == nom.lower():
            service     = (p.get("service") or "").strip()
            config_path = (p.get("config") or "").strip()
            break
    if not service:
        return jsonify(statut="echec",
            message=f"Projet « {nom} » introuvable parmi les services CCW-Watcher du PC fixe. "
                    f"Rafraîchissez la liste des projets.")
    # Même garde-fou que _piloter_service_ccw avant d'injecter le nom du
    # service dans la commande PowerShell.
    if not re.match(r"^CCW-Watcher(-\w+)?$", service):
        return jsonify(statut="echec",
            message=f"Nom de service inattendu (« {service} ») — abandon par précaution.")

    # RepDepot dérivé du champ « config » (…\<NomProjet>\configs\*.conf) —
    # même règle que interrompre_windows() (app/interruption.py).
    rep_depot = (ntpath.dirname(ntpath.dirname(config_path)) if config_path
                 else ntpath.join("C:\\CCW", nom))

    script = DOSSIER_WINDOWS / "nettoyer_verrous_ccw.ps1"
    if not script.exists():
        return jsonify(statut="echec", message=f"Script introuvable : {script.name}")

    try:
        r = _copier(hote, utilisateur, cle_privee, script, TIMEOUT_COURT)
        if r.returncode != 0:
            return jsonify(statut="echec",
                message=_message_echec("copie du script vers le PC fixe", r))
        r = _executer_ps(hote, utilisateur, cle_privee, script.name,
                         ["-Service", service, "-RepDepot", rep_depot], TIMEOUT_LONG)
    except subprocess.TimeoutExpired:
        return jsonify(statut="echec",
            message="Délai dépassé pendant le nettoyage des verrous (SSH).")
    except subprocess.SubprocessError as e:
        return jsonify(statut="echec", message=f"Erreur SSH : {e}")

    etapes = _extraire_projets(r.stdout)
    if etapes is None:
        return jsonify(statut="echec",
            message=_message_echec("nettoyage des verrous CCW", r))

    resume = next((e for e in etapes if isinstance(e, dict) and e.get("etape") == "resume"), None)
    if resume is None:
        return jsonify(statut="echec", message="Réponse du PC fixe vide ou illisible.")

    return jsonify(
        statut=resume.get("statut", "echec"),
        message=resume.get("message", ""),
        service=service,
        etapes=etapes,
        sortie=_sortie_lisible(r),
    )
