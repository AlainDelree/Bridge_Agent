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

MODE NATIF WINDOWS SANS SSH (issue #717, étape F) :
  Quand ce code tourne LUI-MÊME sous Windows (`new_issue.py` natif, sur la
  machine qui héberge les services CCW — ThinkPad éteint, nouveau PC) ET
  qu'aucun hôte SSH n'est configuré, piloter un service CCW n'a pas besoin de
  SSH : le service visé est forcément LOCAL. `_local_natif_sans_ssh()`
  détecte ce cas (`os.name == "nt"` + config SSH absente) ; `nssm` est alors
  appelé EN LOCAL (sans ssh/scp) par `_piloter_service_ccw_action` (donc
  aussi par le démarrage à la demande et par les actions Démarrer/Arrêter/
  Redémarrer de l'onglet CCW). Comportement côté Linux STRICTEMENT inchangé :
  `os.name` y vaut toujours `"posix"`, donc `_local_natif_sans_ssh()` renvoie
  toujours False et la branche SSH historique reste seule utilisée.

  Prérequis manuel (hors périmètre de ce code) : droits de démarrage/arrêt
  sans élévation UAC posés sur le compte local via `sc.exe sdset` — voir
  `provisioning/windows/ccw-commun.psm1::Autoriser-DemarrageServiceCcw` et
  `provisioning/windows/autoriser_demarrage_ccw.ps1`. Sans eux, `nssm start`/
  `stop` en local échoue avec « Access is denied » même pour un compte
  administrateur (jeton bridé par l'UAC en session normale).
"""

import json
import logging
import ntpath
import os
import re
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from flask import has_app_context, jsonify, request

log = logging.getLogger(__name__)

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


def _local_natif_sans_ssh() -> bool:
    """True si CE code tourne NATIVEMENT sous Windows (`new_issue.py` natif,
    sur la machine qui héberge les services CCW) ET qu'aucun hôte SSH n'est
    configuré (issue #717, étape F) : le service visé est alors forcément
    LOCAL, nssm peut être appelé directement sans ssh/scp.

    Comportement Linux STRICTEMENT inchangé : `os.name` y vaut toujours
    `"posix"`, donc cette fonction renvoie toujours False et la branche SSH
    historique reste seule utilisée — exactement comme avant l'issue #717."""
    if os.name != "nt":
        return False
    _, erreur = _charger_config_ssh()
    return erreur is not None


# ─── Utilitaires : droits sc.exe sdset (issue #717) ────────────────────────────
# L'implémentation RÉELLEMENT exécutée est en PowerShell
# (provisioning/windows/ccw-commun.psm1::Autoriser-DemarrageServiceCcw,
# appelée par ajouter_projet_ccw.ps1 et autoriser_demarrage_ccw.ps1) —
# sc.exe n'existe que sous Windows. Les deux fonctions pures ci-dessous sont
# un PORT FIDÈLE du même algorithme (présence d'une entrée pour un SID donné,
# insertion idempotente dans la section D: sans toucher au reste), gardé ICI
# uniquement pour permettre des tests unitaires SANS dépendre de Windows (la
# suite de tests tourne sous Linux) — toute modification de l'algorithme doit
# être répercutée dans LES DEUX implémentations.

def _sddl_contient_sid(sddl: str, sid: str) -> bool:
    """True si une entrée ACE pour ce SID existe déjà dans le descripteur
    (ignore les droits exacts accordés — la seule présence suffit à rendre
    l'opération d'ajout idempotente, comme côté PowerShell)."""
    return bool(re.search(r";;;" + re.escape(sid) + r"\)", sddl))


def _inserer_ace_sddl(sddl: str, ace: str) -> str:
    """Insère `ace` à la fin de la liste des ACE de la section D: (ACL
    discrétionnaire), avant la section S: (SACL, optionnelle) si présente —
    sans toucher à l'en-tête D: ni aux ACE déjà présentes. Lève ValueError si
    `sddl` ne commence pas par une section D: reconnaissable."""
    m = re.match(r"^(D:[^(]*)((?:\([^)]*\))*)(S:.*)?$", sddl)
    if not m:
        raise ValueError(f"Descripteur SDDL inattendu (ne commence pas par D:) : {sddl!r}")
    entete, aces, sacl = m.group(1), m.group(2), m.group(3) or ""
    return entete + aces + ace + sacl


def _ace_demarrage_arret(sid: str) -> str:
    """Entrée SDDL accordant à `sid` le démarrage (RP), l'arrêt (WP) et
    l'interrogation (LC + LO + CR + RC + SW) d'un service — droits
    strictement nécessaires, rien de plus."""
    return f"(A;;LCSWRPWPLOCRRC;;;{sid})"


def _ajouter_droit_demarrage_sddl(sddl: str, sid: str) -> tuple[str, bool]:
    """(nouveau_sddl, a_change). a_change=False si une entrée pour ce SID
    est déjà présente (idempotent, `sddl` renvoyé inchangé)."""
    if _sddl_contient_sid(sddl, sid):
        return sddl, False
    return _inserer_ace_sddl(sddl, _ace_demarrage_arret(sid)), True


# ─── Utilitaires : renouvellement d'UN SEUL token (issue #743) ─────────────────
# Comme pour les fonctions SDDL ci-dessus : l'implémentation RÉELLEMENT
# exécutée est en PowerShell (provisioning/windows/mettre_a_jour_tokens_ccw.ps1,
# fonction Lire-EnvironnementActuelService + section 2 « Résolution des deux
# valeurs ») — ce module Python ne tourne jamais sur le PC fixe Windows. Les
# deux fonctions ci-dessous sont un PORT FIDÈLE du même algorithme, gardé ICI
# uniquement pour permettre des tests unitaires SANS dépendre de Windows/nssm ;
# toute modification de l'algorithme doit être répercutée dans LES DEUX
# implémentations.

# Bornes de plausibilité pour la longueur d'un jeton RECONDUIT (issue #744,
# point 3) — net de sécurité grossier contre une troncature/duplication
# passée inaperçue après nettoyage, PAS une validation de format. Mêmes
# valeurs que le port PowerShell réel (mettre_a_jour_tokens_ccw.ps1).
LONGUEUR_JETON_MIN = 20
LONGUEUR_JETON_MAX = 4096


def _nettoyer_lignes_env_service(texte_brut: str) -> list[str]:
    """Nettoie la sortie BRUTE de « nssm get <service> AppEnvironmentExtra »
    (issue #744) : un essai réel (service CCW-Watcher-Scrabble) a montré que
    cette sortie n'est PAS du texte propre dans tous les contextes
    d'exécution — nssm écrit en UTF-16, parfois redécodé comme du texte 8
    bits (session interactive ou lancement à distance par SSH, où le
    décodage peut différer). Il en résulte un caractère NUL (code 0) après
    CHAQUE caractère ORIGINAL, plus des lignes parasites d'un seul NUL entre
    les variables (le CR et le LF UTF-16 découpés séparément). On retire
    TOUS les NUL d'abord (peu importe leur position), PUIS on redécoupe en
    lignes, on coupe les espaces, et on ignore les lignes vides — fonctionne
    aussi bien sur une sortie déjà propre (sans aucun NUL)."""
    sans_nuls = texte_brut.replace("\x00", "")
    return [ligne.strip() for ligne in sans_nuls.splitlines() if ligne.strip()]


def _extraire_valeur_env_service(texte: str, cle: str) -> str | None:
    """Extrait la valeur de `cle` dans `texte` (sortie, éventuellement brute,
    de « nssm get <service> AppEnvironmentExtra » — une ligne « CLE=valeur »
    par variable), en découpant chaque ligne sur le PREMIER signe égal
    seulement. Ne reconduit JAMAIS une valeur douteuse (issue #744, point 2) :
    None si la clé est absente, présente EN DOUBLE, ou si la valeur trouvée
    est vide ou contient encore un caractère de contrôle après nettoyage —
    jamais affichée/journalisée par l'appelant."""
    lignes_propres = _nettoyer_lignes_env_service(texte)
    trouvees = []
    for ligne in lignes_propres:
        idx = ligne.find("=")
        if idx < 1:
            continue
        if ligne[:idx].strip() == cle:
            trouvees.append(ligne[idx + 1:])
    if len(trouvees) != 1:
        return None
    valeur = trouvees[0]
    if not valeur or any(ord(c) < 32 for c in valeur):
        return None
    return valeur


def _longueur_plausible(valeur: str) -> bool:
    """Contrôle de cohérence AVANT écriture (issue #744, point 3) : la
    longueur d'un jeton reconduit doit rester dans une borne plausible —
    jamais la valeur elle-même, seule sa longueur peut figurer dans un
    message appelant."""
    return LONGUEUR_JETON_MIN <= len(valeur) <= LONGUEUR_JETON_MAX


def _resoudre_jetons_renouvellement(
        gh: str, oauth: str, env_service_texte: str | None) -> tuple[str | None, str | None, str | None]:
    """(gh_final, oauth_final, erreur). Complète le jeton manquant (chaîne
    vide) par sa valeur ACTUELLE dans l'environnement du service (lue par
    nssm get, `env_service_texte` — None si cette lecture a elle-même
    échoué), sans jamais faire sortir cette valeur de cette fonction.

    - aucun des deux jetons fourni → erreur, rien n'est modifiable ;
    - un jeton fourni, l'autre reconduit avec succès → (gh_final, oauth_final,
      None) ;
    - un jeton fourni, l'autre introuvable dans l'environnement actuel
      (service neuf, lecture impossible, variable absente) → erreur, AUCUNE
      valeur n'est retournée (refus sans modification — au moins un jeton
      composé reste requis, message clair demandant les deux) ;
    - deux jetons fournis → comportement inchangé, (gh, oauth, None)."""
    if not gh and not oauth:
        return None, None, "Au moins un jeton (GH_TOKEN ou CLAUDE_CODE_OAUTH_TOKEN) est requis."
    if not gh:
        gh = _extraire_valeur_env_service(env_service_texte, "GH_TOKEN") if env_service_texte else None
        if not gh:
            return None, None, ("GH_TOKEN non fourni et introuvable dans l'environnement actuel "
                                 "du service — fournissez les deux jetons.")
    if not oauth:
        oauth = _extraire_valeur_env_service(env_service_texte, "CLAUDE_CODE_OAUTH_TOKEN") if env_service_texte else None
        if not oauth:
            return None, None, ("CLAUDE_CODE_OAUTH_TOKEN non fourni et introuvable dans l'environnement "
                                 "actuel du service — fournissez les deux jetons.")
    return gh, oauth, None


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
    return subprocess.run(cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout)


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


class _ReponseErreurSansContexte:
    """Substitut minimal d'une réponse jsonify(...) d'échec (même interface
    `.get_json()` que consomment _texte_erreur_json/_erreur_de), utilisé
    UNIQUEMENT quand aucun contexte applicatif Flask n'est actif — thread
    démon de demarrer_service_ccw_arriere_plan (issue #709) ou process séparé
    de scripts/watcher_issues_inbox.py (issue #711, point 4), tous deux
    susceptibles d'appeler _preparer()/_lister_projets_vm() via la fonction
    « pure » _piloter_service_ccw_action SANS qu'un contexte Flask soit
    garanti. jsonify() lève RuntimeError hors contexte applicatif — voir
    _reponse_erreur_ssh ci-dessous."""
    def __init__(self, erreur: str):
        self._erreur = erreur

    def get_json(self):
        return {"succes": False, "erreur": self._erreur}


def _reponse_erreur_ssh(erreur: str):
    """jsonify(...) si un contexte applicatif Flask est actif (c'est TOUJOURS
    le cas pour les routes — comportement strictement inchangé), sinon le
    substitut minimal ci-dessus (issue #711)."""
    if has_app_context():
        return jsonify(succes=False, erreur=erreur)
    return _ReponseErreurSansContexte(erreur)


def _preparer() -> tuple[tuple[str, str, str] | None, object]:
    """Vérif commune avant une opération SSH : configuration disponible
    (hôte, utilisateur, clé privée).

    Retourne ((hote, utilisateur, cle_privee), None) si tout est OK, sinon
    (None, réponse_json_erreur) — jamais une exception Flask brute."""
    ctx, erreur = _charger_config_ssh()
    if erreur:
        return None, _reponse_erreur_ssh(erreur)
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
        return None, _reponse_erreur_ssh(f"Script introuvable : {script.name}")
    try:
        r = _copier(hote, utilisateur, cle_privee, script, TIMEOUT_COURT)
        if r.returncode != 0:
            return None, _reponse_erreur_ssh(_message_echec("copie du script", r))
        r = _executer_ps(hote, utilisateur, cle_privee, script.name, [], TIMEOUT_COURT)
    except subprocess.TimeoutExpired:
        return None, _reponse_erreur_ssh("Délai dépassé en interrogeant le PC fixe (SSH).")
    except subprocess.SubprocessError as e:
        return None, _reponse_erreur_ssh(f"Erreur SSH : {e}")
    projets = _extraire_projets(r.stdout)
    if projets is None:
        return None, _reponse_erreur_ssh(_message_echec("liste des projets", r))
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
    # ajouter_projet_ccw.ps1 importe désormais ccw-commun.psm1 (issue #606) —
    # les deux fichiers doivent atterrir dans le même dossier distant
    # (DEST_DIR_DISTANT) pour que Import-Module (Join-Path $PSScriptRoot ...)
    # le retrouve.
    module_commun = DOSSIER_WINDOWS / "ccw-commun.psm1"
    for s in (script, module_commun):
        if not s.exists():
            return jsonify(succes=False, erreur=f"Script introuvable : {s.name}")
    try:
        r = _copier(hote, utilisateur, cle_privee, module_commun, TIMEOUT_COURT)
        if r.returncode != 0:
            return jsonify(succes=False, erreur=_message_echec("copie du module", r))
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
    PowerShell).

    Issue #743 : UN SEUL des deux tokens peut être fourni (au moins un est
    requis) — celui qui est omis n'est simplement PAS écrit dans le fichier de
    valeurs ; mettre_a_jour_tokens_ccw.ps1 lit alors sa valeur ACTUELLE dans
    l'environnement du service (nssm get) et la reconduit telle quelle, au
    lieu de l'effacer (nssm set … AppEnvironmentExtra REMPLACE toute la
    valeur). Comportement inchangé quand les deux tokens sont fournis."""
    data  = request.json or {}
    nom   = (data.get("nom")   or "").strip()
    topic = (data.get("topic") or "").strip()
    gh    = data.get("gh_token")    or ""
    oauth = data.get("oauth_token") or ""
    if not nom or re.search(r"[\\/\s]", nom):
        return jsonify(succes=False,
            erreur="Nom de projet requis, sans espace ni séparateur de chemin.")
    if not gh and not oauth:
        return jsonify(succes=False,
            erreur="Au moins un des deux tokens (GH_TOKEN ou CLAUDE_CODE_OAUTH_TOKEN) "
                   "est requis — laissez l'autre champ vide pour conserver sa valeur actuelle.")
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
    # + les tokens FOURNIS (clé absente = non fourni, reconduction côté
    # PowerShell — voir docstring) en « clé=valeur ». Jamais journalisé.
    fd, chemin_valeurs = tempfile.mkstemp(prefix="ccw-vals-", suffix=".txt")
    dest_valeurs = DEST_DIR_DISTANT + os.path.basename(chemin_valeurs)
    try:
        os.chmod(chemin_valeurs, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(f"TOPIC_NTFY={topic}\n")
            if gh:
                f.write(f"GH_TOKEN={gh}\n")
            if oauth:
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


def _nom_service_local(nom_projet: str) -> str | None:
    """Résout le nom EXACT du service CCW-Watcher SANS passer par
    lister_projets_ccw.ps1 (indisponible sans SSH — issue #717) : même règle
    que Get-CheminsProjetCcw (ccw-commun.psm1) — projet « Bridge_Agent »
    (insensible à la casse) → service « CCW-Watcher » SANS suffixe, tout
    autre projet → « CCW-Watcher-<NomProjet> ». None si nom_projet est vide,
    contient un séparateur de chemin/espace, ou si le nom de service résultant
    ne respecte pas le format attendu (même garde-fou que la branche SSH)."""
    if not nom_projet or re.search(r"[\\/\s]", nom_projet):
        return None
    nom_projet = nom_projet.strip()
    service = "CCW-Watcher" if nom_projet.lower() == "bridge_agent" else f"CCW-Watcher-{nom_projet}"
    return service if re.match(r"^CCW-Watcher(-\w+)?$", service) else None


def _piloter_service_ccw_action_local(nom_projet: str, action_nssm: str, verbe: str) -> dict:
    """Branche LOCALE (sans SSH) de _piloter_service_ccw_action (issue #717) :
    utilisée quand ce code tourne nativement sous Windows, sur la machine qui
    héberge les services CCW, sans hôte SSH configuré — le service visé est
    alors forcément local. Résout le nom via _nom_service_local (pas de liste
    de projets disponible sans SSH), puis appelle nssm DIRECTEMENT (pas de
    ssh/scp). etat_avant reste toujours None et deja_dans_cet_etat toujours
    False (pas d'info d'état sans SSH — nssm lui-même absorbe un appel sur un
    service déjà dans l'état visé). Même forme de dict que la branche SSH."""
    service = _nom_service_local(nom_projet)
    if service is None:
        return dict(succes=False, service=None, etat_avant=None, deja_dans_cet_etat=False,
                    message="Nom de projet requis, sans espace ni séparateur de chemin.",
                    code=None, sortie=None)
    try:
        r = subprocess.run(["nssm", action_nssm, service], capture_output=True,
                           encoding="cp1252", errors="replace", timeout=TIMEOUT_LONG)
    except FileNotFoundError:
        return dict(succes=False, service=service, etat_avant=None, deja_dans_cet_etat=False,
                    message=f"nssm introuvable dans le PATH local — {verbe} de « {service} » impossible.",
                    code=None, sortie=None)
    except subprocess.TimeoutExpired:
        return dict(succes=False, service=service, etat_avant=None, deja_dans_cet_etat=False,
                    message=f"Délai dépassé — {verbe} du service interrompu (local).",
                    code=None, sortie=None)
    except subprocess.SubprocessError as e:
        return dict(succes=False, service=service, etat_avant=None, deja_dans_cet_etat=False,
                    message=f"Erreur nssm (local) : {e}", code=None, sortie=None)
    succes = (r.returncode == 0)
    return dict(
        succes=succes, service=service, etat_avant=None, deja_dans_cet_etat=False,
        message=None if succes else (
            f"Échec — {verbe} de « {service} » en local (code {r.returncode}). Vérifiez que "
            f"les droits sc.exe sdset ont été posés (provisioning/windows/"
            f"autoriser_demarrage_ccw.ps1) — sinon nssm échoue avec « Access is denied » "
            f"même pour un compte administrateur (jeton bridé par l'UAC)."),
        code=r.returncode, sortie=_sortie_lisible(r),
    )


def _piloter_service_ccw_action(nom_projet: str, action_nssm: str, verbe: str, *,
                                 eviter_si_deja_dans_cet_etat: str | None = None) -> dict:
    """Fonction PURE (issue #709, étape C du retrofit CCW) : nom de projet +
    action nssm (« restart », « start », « stop ») → résolution du nom EXACT
    du service via lister_projets_ccw.ps1 (source de vérité unique — voir
    _lister_projets_vm), ce qui gère de fait le spécial-cas « Bridge_Agent »
    → « CCW-Watcher » (sans suffixe) sans dupliquer la règle, garde-fou sur le
    format du service, puis exécution à distance (nssm est déjà dans le PATH
    du PC fixe). Aucun objet Flask en entrée ni en sortie : extraite de
    _piloter_service_ccw (route) pour être appelable aussi depuis
    app.issues.envoyer() (démarrage à la demande d'une issue for-windows),
    sans dupliquer la résolution du nom de service ni le garde-fou.

    eviter_si_deja_dans_cet_etat : si fourni (ex. « running » pour l'action
    « start »), et que l'état relevé par la MÊME liste de projets (déjà
    nécessaire pour résoudre le nom du service — aucun aller-retour SSH
    supplémentaire) correspond déjà à cette valeur, n'exécute PAS « nssm
    <action> » (idempotence sans SSH inutile). None (défaut) : comportement
    HISTORIQUE, aucune vérification d'état — c'est ce que les 3 routes
    existantes (redémarrer/démarrer/arrêter) utilisent, pour un comportement
    STRICTEMENT inchangé.

    Retourne un dict {succes, service, etat_avant, deja_dans_cet_etat,
    message, code, sortie} :
      - service    : nom exact résolu, ou None si introuvable avant d'avoir
        pu l'identifier (nom invalide, SSH non configuré/en échec, projet
        absent de la liste) ;
      - etat_avant : champ « etat » de la liste des projets au moment de la
        résolution (« running », « stopped », « stoppending », …), ou None si
        le service n'a pas pu être résolu ;
      - deja_dans_cet_etat : True si l'exécution a été court-circuitée par
        eviter_si_deja_dans_cet_etat (aucun appel SSH nssm effectué) ;
      - message    : texte d'erreur en cas d'échec, None sinon ;
      - code       : code de retour de nssm, None si l'exécution SSH n'a pas
        été atteinte (ou court-circuitée) ;
      - sortie     : sortie brute (stdout+stderr) de la commande nssm, None
        si l'exécution SSH n'a pas été atteinte (ou court-circuitée)."""
    if not nom_projet or re.search(r"[\\/\s]", nom_projet):
        return dict(succes=False, service=None, etat_avant=None, deja_dans_cet_etat=False,
                    message="Nom de projet requis, sans espace ni séparateur de chemin.",
                    code=None, sortie=None)
    # Issue #717 : nativement sous Windows sans hôte SSH configuré, le
    # service visé est forcément local — nssm est appelé directement, sans
    # SSH. Couvre aussi bien le démarrage à la demande (_demarrer_service_ccw_sync)
    # que les actions Démarrer/Arrêter/Redémarrer de l'onglet CCW. eviter_si_
    # deja_dans_cet_etat n'a pas d'équivalent ici (pas d'info d'état sans
    # SSH) — sans incidence : seul le démarrage à la demande l'utilise, et nssm
    # absorbe lui-même un appel sur un service déjà dans l'état visé.
    if _local_natif_sans_ssh():
        return _piloter_service_ccw_action_local(nom_projet, action_nssm, verbe)
    ctx, err = _preparer()
    if err:
        return dict(succes=False, service=None, etat_avant=None, deja_dans_cet_etat=False,
                    message=_texte_erreur_json(err), code=None, sortie=None)
    hote, utilisateur, cle_privee = ctx

    projets, err = _lister_projets_vm(hote, utilisateur, cle_privee)
    if err:
        return dict(succes=False, service=None, etat_avant=None, deja_dans_cet_etat=False,
                    message=_texte_erreur_json(err), code=None, sortie=None)
    service = etat_avant = None
    for p in projets:
        if isinstance(p, dict) and str(p.get("projet", "")).strip().lower() == nom_projet.lower():
            service    = (p.get("service") or "").strip()
            etat_avant = (p.get("etat") or "").strip().lower() or None
            break
    if not service:
        return dict(succes=False, service=None, etat_avant=None, deja_dans_cet_etat=False,
                    message=f"Projet « {nom_projet} » introuvable parmi les services "
                            f"CCW-Watcher du PC fixe. Rafraîchissez la liste des projets.",
                    code=None, sortie=None)
    # Garde-fou : le nom vient de la liste (donc de confiance), mais on vérifie
    # qu'il correspond bien au format attendu d'un service CCW avant de
    # l'injecter dans la commande PowerShell.
    if not re.match(r"^CCW-Watcher(-\w+)?$", service):
        return dict(succes=False, service=service, etat_avant=etat_avant, deja_dans_cet_etat=False,
                    message=f"Nom de service inattendu (« {service} ») — abandon par précaution.",
                    code=None, sortie=None)

    if eviter_si_deja_dans_cet_etat is not None and etat_avant == eviter_si_deja_dans_cet_etat:
        return dict(succes=True, service=service, etat_avant=etat_avant, deja_dans_cet_etat=True,
                    message=None, code=None, sortie=None)

    try:
        # « exit $LASTEXITCODE » : propage le code de retour de nssm pour que
        # l'appelant conclue sans ambiguïté (0 = opération OK).
        r = _executer_commande_ps(
            hote, utilisateur, cle_privee,
            f"nssm {action_nssm} {service}; exit $LASTEXITCODE", TIMEOUT_LONG)
    except subprocess.TimeoutExpired:
        return dict(succes=False, service=service, etat_avant=etat_avant, deja_dans_cet_etat=False,
                    message=f"Délai dépassé — {verbe} du service interrompu (SSH).",
                    code=None, sortie=None)
    except subprocess.SubprocessError as e:
        return dict(succes=False, service=service, etat_avant=etat_avant, deja_dans_cet_etat=False,
                    message=f"Erreur SSH : {e}", code=None, sortie=None)

    succes = (r.returncode == 0)
    return dict(
        succes=succes, service=service, etat_avant=etat_avant, deja_dans_cet_etat=False,
        message=None if succes else f"Échec — {verbe} de « {service} » (code {r.returncode}).",
        code=r.returncode, sortie=_sortie_lisible(r),
    )


def _piloter_service_ccw(action_nssm: str, verbe: str):
    """Route Flask : lit le nom de projet depuis request.json, délègue la
    résolution + l'exécution à _piloter_service_ccw_action (fonction pure,
    issue #709) et construit la réponse JSON — comportement STRICTEMENT
    inchangé par rapport à avant l'extraction (mêmes clés, mêmes messages).

    `resultat["code"] is None` discrimine les deux familles de réponse : tant
    que l'exécution SSH n'a pas été atteinte (nom invalide, config SSH
    absente, projet introuvable, garde-fou de format, timeout/erreur SSH),
    seules `succes`/`erreur` sont renvoyées ; une fois nssm réellement
    invoqué, `service`/`sortie` s'y ajoutent — exactement comme avant.

    action_nssm : sous-commande nssm (« restart », « start », « stop »).
    verbe       : nom de l'action pour les messages (« redémarrage », « démarrage »,
                  « arrêt »)."""
    data = request.json or {}
    nom  = (data.get("nom") or "").strip()
    resultat = _piloter_service_ccw_action(nom, action_nssm, verbe)
    if resultat["code"] is None:
        return jsonify(succes=False, erreur=resultat["message"])
    return jsonify(
        succes=resultat["succes"],
        service=resultat["service"],
        sortie=resultat["sortie"],
        erreur=resultat["message"],
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


# ─── Démarrage à la demande depuis la création d'issue (issue #709, étape C) ──
# Contexte (voir en-tête de l'issue) : AppExit 42 Exit (étape A du retrofit)
# fait qu'un watcher CCW qui s'éteint seul (auto-extinction, code 42) n'est
# plus relancé par NSSM — une issue for-windows créée pendant que le service
# est éteint ne serait sinon traitée qu'après un rallumage MANUEL (onglet
# CCW). Symétrique du rallumage auto for-linux (app.watchers.
# redemarrer_si_eteint, issue #600/#202), mais le transport SSH (latence,
# hôte potentiellement injoignable) interdit de bloquer la réponse HTTP de
# envoyer() dessus : voir demarrer_service_ccw_arriere_plan ci-dessous.

def _demarrer_service_ccw_sync(nom_projet: str) -> tuple[bool | None, str]:
    """Cœur SYNCHRONE (délibérément testable sans thread) du démarrage à la
    demande : idempotent (court-circuite nssm si déjà « running », via
    _piloter_service_ccw_action(eviter_si_deja_dans_cet_etat="running") — pas
    d'aller-retour SSH gaspillé), une seule ligne de journal par tentative
    (service, résultat, durée), et au plus UNE courte nouvelle tentative si le
    service est en « stoppending » (observé lors d'un Redémarrer depuis
    l'onglet CCW — nssm start y échoue tant que l'arrêt n'est pas terminé),
    jamais de boucle.

    Issue #717 : sous Windows natif sans hôte SSH configuré,
    _piloter_service_ccw_action bascule elle-même sur nssm EN LOCAL (voir
    _local_natif_sans_ssh) — ce n'est donc plus un cas « non applicable »
    comme avant #717 (où l'absence d'hôte SSH, non distinguable de
    l'exécution Linux, faisait toujours échouer silencieusement _preparer()).
    Reste « non applicable » (service=None) : nom de projet invalide, ou
    (sous Linux, ou Windows AVEC hôte SSH configuré) config SSH absente/
    incomplète.

    Retourne (ccw_demarre, avertissement) :
      - ccw_demarre : True = démarré par cet appel, False = déjà en marche ou
        démarrage échoué, None = non applicable (nom invalide, hôte SSH non
        configuré en mode SSH, projet sans service CCW) ;
      - avertissement : message non bloquant si le démarrage a RÉELLEMENT
        échoué, chaîne vide sinon (déjà en marche, non applicable, ou
        succès)."""
    debut = time.monotonic()
    res = _piloter_service_ccw_action(nom_projet, "start", "démarrage",
                                       eviter_si_deja_dans_cet_etat="running")
    if (res["etat_avant"] == "stoppending" and not res["succes"]
            and not res["deja_dans_cet_etat"]):
        log.info(f"CCW « {nom_projet} » : service en cours d'arrêt (stop pending) — "
                 f"nouvelle tentative dans 2s (une seule, issue #709).")
        time.sleep(2)
        res = _piloter_service_ccw_action(nom_projet, "start", "démarrage",
                                           eviter_si_deja_dans_cet_etat="running")
    duree = time.monotonic() - debut

    if res["service"] is None:
        # Non applicable : hôte SSH non configuré (cas normal de new_issue.py
        # natif sous Windows — l'onglet CCW y affiche déjà ce message), nom
        # invalide, ou projet sans service CCW dans la liste — jamais un
        # message d'erreur à l'utilisateur, seulement le journal (point 3 de
        # l'issue #709).
        log.info(f"CCW « {nom_projet} » : démarrage non applicable "
                 f"({res['message']}), {duree:.1f}s.")
        return None, ""
    if res["deja_dans_cet_etat"]:
        log.info(f"CCW « {res['service']} » : déjà en marche, rien à faire ({duree:.1f}s).")
        return False, ""
    if res["succes"]:
        log.info(f"CCW « {res['service']} » : démarré automatiquement ({duree:.1f}s).")
        return True, ""
    log.warning(f"CCW « {res['service']} » : démarrage échoué ({res['message']}), {duree:.1f}s.")
    return False, ("Le service CCW n'a pas pu être démarré automatiquement — "
                    "démarrez-le depuis l'onglet CCW.")


def demarrer_service_ccw_arriere_plan(nom_projet: str) -> None:
    """Wrapper NON BLOQUANT utilisé par app.issues.envoyer() (issue #709,
    étape C) : la création d'une issue for-windows ne doit JAMAIS attendre un
    aller-retour SSH vers le PC fixe (hôte injoignable, service en
    stop-pending, etc.) — « la création d'issue reste instantanée dans tous
    les cas » (résultat attendu de l'issue). _demarrer_service_ccw_sync tourne
    donc dans un thread démon, borné par les timeouts SSH déjà en place
    (TIMEOUT_COURT pour la liste des projets, TIMEOUT_LONG pour nssm — jamais
    indéfini) ; son résultat n'est donc plus récupérable ici, seule la ligne
    de journal qu'il émet en garde trace. Sans retour utile (None) par
    construction — _demarrer_service_ccw_sync, lui, reste directement
    appelable et testable de façon synchrone sans thread."""
    threading.Thread(target=_demarrer_service_ccw_sync, args=(nom_projet,), daemon=True).start()


def _texte_erreur_json(reponse_json) -> str:
    """Extrait le champ erreur d'une réponse d'échec de _preparer/
    _lister_projets_vm (jsonify(...) en contexte Flask, ou
    _ReponseErreurSansContexte hors contexte — issue #711, même interface
    `.get_json()` dans les deux cas) — même logique que _erreur_de dans
    app/interruption.py, dupliquée ici pour éviter un import circulaire
    (interruption.py importe déjà depuis ce module)."""
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
