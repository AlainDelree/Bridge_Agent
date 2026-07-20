#!/usr/bin/env python3
"""
watcher.py — Bridge inter-agents (multi-projets)
Surveille les GitHub Issues labelisées 'for-linux' d'un dépôt et les délègue à
Claude Code. Chaque projet est décrit par un fichier de config (--config).

Usage :
    python3 watcher.py --config configs/bridge_agent.conf
    python3 watcher.py --config configs/bridge_agent.conf --dry-run
    python3 watcher.py --config configs/bridge_agent.conf --interval 30

Lancement de plusieurs projets en parallèle :
    python3 watcher.py --config configs/bridge_agent.conf &
    python3 watcher.py --config configs/alchess.conf &
"""

import subprocess
import json
import time
import logging
import argparse
import sys
import os
import glob
import re
import hashlib
from logging.handlers import RotatingFileHandler
from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime

# Canaux de notification factorisés (issue #187) : partagés avec new_issue.py
# via notifications.py, à la racine du projet. watcher.py tourne toujours avec
# WorkingDirectory = racine du dépôt (voir systemd/watcher@.service), donc
# l'import direct fonctionne. Les enveloppes bip()/notifier*() ci-dessous
# délèguent à ce module en passant les valeurs du CFG courant.
import notifications

# ─── Emplacements fixes (relatifs au script, PAS au cwd du projet) ─────────────
# Les journaux vivent à côté du watcher, quel que soit le projet piloté. Ils ne
# doivent surtout pas atterrir dans le répertoire de travail du projet (il change).
DOSSIER_SCRIPT = Path(__file__).resolve().parent
DOSSIER_LOGS   = DOSSIER_SCRIPT / "logs"

# Historique des durées réelles de traitement (issue #108) : un fichier commun,
# une entrée par issue fermée {projet, type, mode, duree, date}. Vit dans logs/
# (déjà gitignoré, cohérent avec les .conf) : donnée de télémétrie locale, pas de
# source à versionner. Lu par app/issues.py pour estimer la durée d'une issue en
# cours (médiane du même projet+type+mode).
FICHIER_HISTORIQUE = DOSSIER_LOGS / "historique_durees.json"

# Verrous anti-collision inter-process (issue #189). Chaque traitement pose un
# fichier de verrou associé au répertoire de travail EFFECTIF avant de lancer
# claude, et le libère à la fin (y compris en cas d'échec). But : garantir que
# JAMAIS deux process claude ne travaillent simultanément sur le MÊME dossier —
# là où l'ensemble en mémoire `issues_en_cours` ne protège qu'au sein d'un seul
# process watcher, pas entre deux instances/relances. Le verrou vit sous logs/
# (gitignoré), et NON dans le rep_travail lui-même : un fichier déposé dans le
# dossier de travail serait happé par le `git add -A` de la sauvegarde que CCL
# effectue à chaque tâche en mode écriture, puis committé par erreur.
DOSSIER_VERROUS = DOSSIER_LOGS / "verrous"

# Marge (secondes) ajoutée à la durée de traitement plausible d'une issue pour
# décider qu'un verrou est PÉRIMÉ (orphelin d'un watcher tué brutalement sans
# passer par le finally). Au-delà de cette péremption, aucun claude légitime ne
# peut encore tourner (chaque subprocess a son propre timeout) : le verrou est
# réputé abandonné et peut être repris.
PEREMPTION_MARGE_VERROU = 120

# ─── Protocole partagé (identique pour TOUS les projets) ───────────────────────
# Ces noms de labels sont la logique commune du bridge. Les mettre en config
# permettrait à un projet de diverger et de casser le protocole — c'est
# exactement la dérive qu'on veut éviter. Ils restent donc en dur.
# Le NOM des constantes est en français ; la VALEUR (entre guillemets) est le
# label réel sur GitHub, un contrat qu'on ne touche pas.

LABEL_ECRITURE  = "mode_write"    # ARME le mode écriture (--dangerously-skip-permissions)
LABEL_ECHEC     = "needs-human"   # posé après échec définitif : stoppe le retraitement auto
LABEL_FAIT      = "done"          # posé au succès

# Labels de notification (opt-in, cumulatifs avec le bip). Depuis l'issue #187,
# le dispatch concret selon ces labels vit dans notifications.py (module partagé
# avec new_issue.py) ; ces constantes restent ici comme contrat documentaire du
# protocole bridge (valeurs miroir de notifications.LABEL_NOTIF_*).
LABEL_NOTIF_PC   = "notif_pc"     # bip + notify-send (bulle bureau locale)
LABEL_NOTIF_GSM  = "notif_gsm"    # bip + ntfy (push téléphone)
LABEL_NOTIF_TOUS = "notif_tous"   # bip + notify-send + ntfy

PRIORITES_CRITIQUES = {"haute", "critique"}

# Pause (secondes) entre deux tentatives d'une même issue (backoff). Sert aussi
# à calculer, côté navigateur, le budget total de retry du badge (issue #106).
PAUSE_ENTRE_TENTATIVES = 5

# Abréviations du dictionnaire bridge
SOURCES = {"CC": "Claude Chat", "CCL": "Claude Code Linux", "CCW": "Claude Code Windows"}

# ─── Configuration par projet (ce qui CHANGE d'un projet à l'autre) ────────────

@dataclass
class Config:
    """Tout ce qui distingue un projet d'un autre. Rempli une fois au démarrage
    depuis le fichier --config, puis lu partout via l'objet global CFG."""
    # Requis
    nom: str             # identifiant court sans espaces (journal, préfixe notif, prompt)
    depot: str           # ex. "AlainDelree/Bridge_Agent"
    rep_travail: Path    # répertoire de travail de Claude Code pour CE projet
    topic_ntfy: str      # topic ntfy pour les push téléphone

    # Optionnels (défauts sensés)
    label: str            = "for-linux"
    intervalle: int       = 10
    max_essais: int       = 3
    timeout_claude: int   = 300
    timeout_chef: int     = 1200   # défaut plus généreux pour les issues « Chef : » sans TIMEOUT explicite (issue #106)
    timeout_diagnostic: int = 90   # timeout court et fixe de la passe diagnostique avant abandon non-critique (issue #124)
    script_bip: Path      = field(default_factory=lambda: DOSSIER_SCRIPT / "scripts" / "bip.py")
    log_taille_max_mo: int = 1     # rotation quand le journal dépasse cette taille (Mo)
    log_archives: int      = 5     # nombre d'archives datées conservées
    cmd_backup: str        = ""    # commande de sauvegarde avant modif (mode écriture)
    perimetre: str         = ""    # dossier(s) autorisés pour CCL (vide = pas de restriction)
    modele_ccl: str        = ""    # modèle CCL à utiliser (vide = défaut Claude Code)
    mot_de_passe: str      = ""    # hash sha256 du mot de passe d'accès web (vide = pas d'authentification)
    fichier_contexte: str  = ""    # fichier de contexte projet injecté dans le prompt (chemin relatif au rep_travail ou absolu ; vide = aucun)
    couleur: str           = ""    # couleur d'accent du projet dans l'interface (hex #RRGGBB ; vide = repli map fixe/hash côté frontend)
    perimetre_dynamique: bool = False  # périmètre fourni par l'issue (REPO_CIBLE) plutôt que figé dans le .conf — outil d'audit multi-dépôts (issue #125)
    notifier_local: bool   = True  # ce watcher émet-il lui-même bip/notify-send/ntfy à la fin d'une issue (issue #187) ? True = comportement historique. Mettre à False sur la VM CCW (et éventuellement CCL) pour laisser new_issue.py notifier de façon centralisée sur le ThinkPad, sans doublon.

    @property
    def url_ntfy(self) -> str:
        return f"https://ntfy.sh/{self.topic_ntfy}"

    @property
    def fichier_log(self) -> Path:
        return DOSSIER_LOGS / f"watcher-{self.nom}.log"


CHAMPS_REQUIS = ("NOM", "DEPOT", "REP_TRAVAIL", "TOPIC_NTFY")


def lire_conf(chemin: Path) -> dict:
    """Lecteur 'CLÉ = valeur' minimal, zéro dépendance.
    Ignore les lignes vides et les lignes commentées (#). Les clés sont
    normalisées en MAJUSCULES pour tolérer la casse."""
    donnees: dict[str, str] = {}
    for brut in chemin.read_text(encoding="utf-8").splitlines():
        ligne = brut.strip()
        if not ligne or ligne.startswith("#"):
            continue
        cle, sep, valeur = ligne.partition("=")
        if not sep:                       # ligne sans '=' → ignorée
            continue
        donnees[cle.strip().upper()] = valeur.strip()
    return donnees


def charger_config(chemin: Path) -> Config:
    """Charge et valide un fichier de config. Échoue proprement (message clair +
    sortie) si un champ requis manque ou si un entier est mal formé — mieux vaut
    refuser de démarrer que tourner avec une config bancale."""
    if not chemin.exists():
        sys.exit(f"[config] Fichier introuvable : {chemin}")

    brut = lire_conf(chemin)

    manquants = [c for c in CHAMPS_REQUIS if not brut.get(c)]
    if manquants:
        sys.exit(f"[config] Champs requis manquants dans {chemin.name} : {', '.join(manquants)}")

    def entier(cle: str, defaut: int) -> int:
        val = brut.get(cle)
        if val is None or val == "":
            return defaut
        if not val.lstrip("-").isdigit():
            sys.exit(f"[config] {cle} doit être un entier (lu : '{val}')")
        return int(val)

    def booleen(cle: str, defaut: bool) -> bool:
        val = brut.get(cle)
        if val is None or val == "":
            return defaut
        return val.strip().lower() in ("true", "1", "oui", "yes", "vrai")

    return Config(
        nom         = brut["NOM"],
        depot       = brut["DEPOT"],
        rep_travail = Path(brut["REP_TRAVAIL"]).expanduser(),
        topic_ntfy  = brut["TOPIC_NTFY"],
        label       = brut.get("LABEL") or "for-linux",
        intervalle     = entier("INTERVALLE", 10),
        max_essais     = entier("MAX_ESSAIS", 3),
        timeout_claude = entier("TIMEOUT_CLAUDE", 300),
        timeout_chef   = entier("TIMEOUT_CHEF", 1200),
        timeout_diagnostic = entier("TIMEOUT_DIAGNOSTIC", 90),
        script_bip  = Path(brut["SCRIPT_BIP"]).expanduser() if brut.get("SCRIPT_BIP")
                      else DOSSIER_SCRIPT / "scripts" / "bip.py",
        log_taille_max_mo = entier("LOG_TAILLE_MAX_MO", 1),
        log_archives      = entier("LOG_ARCHIVES", 5),
        cmd_backup        = brut.get("CMD_BACKUP", ""),
        perimetre         = brut.get("PERIMETRE", ""),
        modele_ccl        = brut.get("MODELE_CCL", ""),
        mot_de_passe      = brut.get("MOT_DE_PASSE", ""),
        fichier_contexte  = brut.get("FICHIER_CONTEXTE", ""),
        couleur           = brut.get("COULEUR", ""),
        perimetre_dynamique = booleen("PERIMETRE_DYNAMIQUE", False),
        notifier_local      = booleen("NOTIFIER_LOCAL", True),
    )


# Config globale, remplie dans main() avant toute utilisation.
CFG: Config = None  # type: ignore[assignment]

# ─── Journalisation ───────────────────────────────────────────────────────────
# Le logger existe dès l'import ; ses gestionnaires (fichier + console) sont
# ajoutés dans configurer_logs(), une fois qu'on connaît le nom du projet.
log = logging.getLogger("watcher")


class JournalRotatifDate(RotatingFileHandler):
    """Rotation déclenchée par la TAILLE (héritée de RotatingFileHandler), mais
    l'archive est nommée avec la date/heure de rotation plutôt que .1/.2 :
        watcher-<nom>.log.2026_07_11_08_02
    Le fichier actif garde son nom sans suffixe. Au-delà de backupCount archives,
    les plus anciennes sont supprimées."""

    def doRollover(self):
        if self.stream:
            self.stream.close()
            self.stream = None

        horodatage = datetime.now().strftime("%Y_%m_%d_%H_%M")
        cible = f"{self.baseFilename}.{horodatage}"
        # Deux rotations dans la même minute : on évite l'écrasement.
        if os.path.exists(cible):
            i = 1
            while os.path.exists(f"{cible}_{i}"):
                i += 1
            cible = f"{cible}_{i}"

        if os.path.exists(self.baseFilename):
            os.rename(self.baseFilename, cible)

        self._purger_archives()

        if not self.delay:
            self.stream = self._open()

    def _purger_archives(self):
        """Ne garde que les backupCount archives les plus récentes."""
        if self.backupCount <= 0:
            return
        archives = sorted(glob.glob(f"{self.baseFilename}.*"), key=os.path.getmtime)
        for vieux in archives[:-self.backupCount]:
            try:
                os.remove(vieux)
            except OSError:
                pass


def _forcer_utf8(flux):
    """Reconfigure un flux texte (stdout/stderr) en UTF-8 si possible.

    Sous Windows la console encode par défaut en cp1252 : les messages de log
    contenant de l'Unicode (→ ⚠️ ✗ …) déclenchent alors des UnicodeEncodeError
    répétées (« --- Logging error --- ») qui polluent ccw-service.log (le flux
    stdout est repris par NSSM). reconfigure() existe depuis Python 3.7 ; on le
    garde défensif (getattr) car certains flux redirigés ne l'exposent pas.
    Sous Linux, stdout est déjà en UTF-8 : l'appel est inoffensif (pas de
    régression)."""
    reconfigure = getattr(flux, "reconfigure", None)
    if reconfigure is not None:
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass


def configurer_logs(cfg: Config):
    cfg.fichier_log.parent.mkdir(parents=True, exist_ok=True)
    # Portabilité Windows : force l'UTF-8 sur les flux console repris par le
    # StreamHandler (et par NSSM côté CCW). Le FileHandler, lui, reçoit déjà
    # encoding="utf-8" à sa construction.
    _forcer_utf8(sys.stdout)
    _forcer_utf8(sys.stderr)
    handler_fichier = JournalRotatifDate(
        cfg.fichier_log,
        maxBytes=cfg.log_taille_max_mo * 1024 * 1024,
        backupCount=cfg.log_archives,
        encoding="utf-8",
    )
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            handler_fichier,
            logging.StreamHandler(sys.stdout),
        ],
    )

# ─── Utilitaires ──────────────────────────────────────────────────────────────

# ─── Notifications ─────────────────────────────────────────────────────────────
# Depuis l'issue #187, la logique concrète des canaux (bip, notify-send, ntfy)
# vit dans notifications.py, partagé avec new_issue.py. Les fonctions ci-dessous
# sont des ENVELOPPES minces qui délèguent à ce module en injectant les valeurs
# du CFG courant (nom, url_ntfy, script_bip) et le logger du watcher. Les sites
# d'appel existants (succès/échec/alerte critique) restent inchangés.

def bip(fois=1):
    """Bip sonore via le script bip partagé (Bridge_Agent/scripts/bip.py)."""
    notifications.bip(CFG.script_bip, fois)

def notifier_bureau(titre: str, message: str, urgence: str = "normal"):
    """Bulle de notification bureau via notify-send (voir notifications.py)."""
    notifications.notifier_bureau(CFG.nom, titre, message, urgence, log=log)

def notifier_ntfy(titre: str, message: str, priorite: str = "default"):
    """Notification push ntfy sur le topic du projet (voir notifications.py)."""
    notifications.notifier_ntfy(CFG.url_ntfy, titre, message, priorite, log=log)

def notifier(labels: list[str], titre: str, message: str,
             urgence_bureau: str = "normal", priorite_ntfy: str = "default",
             fois_bip: int = 1):
    """Dispatch de notification selon les labels de l'issue.

    Garde issue #187 : si `NOTIFIER_LOCAL = false` dans le .conf, ce watcher
    n'émet AUCUN signal lui-même — la notification est laissée à new_issue.py,
    qui détecte la transition par polling GitHub et notifie de façon centralisée
    sur le ThinkPad d'Alain (évite les doublons, et fait remonter les transitions
    CCW dont le bip/notify-send tomberaient sinon dans la VM). Par défaut True :
    comportement historique préservé (notamment CCL, déjà fonctionnel)."""
    if not CFG.notifier_local:
        return
    notifications.notifier(
        labels, CFG.nom, CFG.url_ntfy, CFG.script_bip,
        titre, message,
        urgence_bureau=urgence_bureau, priorite_ntfy=priorite_ntfy,
        fois_bip=fois_bip, log=log,
    )

def alerte_critique(numero, titre, tentative, labels: list[str]):
    """Alerte pour les issues haute/critique après échec."""
    msg = f"⚠️  ALERTE — Issue #{numero} '{titre}' — tentative {tentative} échouée — nouvelle tentative dans {CFG.intervalle}s"
    log.warning(msg)
    notifier(
        labels,
        titre=f"⚠️ {CFG.nom} #{numero} — alerte critique",
        message=f"Tentative {tentative} échouée : {titre}\nNouvelle tentative dans {CFG.intervalle}s.",
        urgence_bureau="critical",
        priorite_ntfy="high",
        fois_bip=3,  # 3 bips pour l'alerte critique (au lieu du bip simple par défaut)
    )

def gh(*args) -> dict | list | None:
    """Lance une commande gh et retourne le JSON parsé."""
    cmd = ["gh", *args, "--json"]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=30)
        if res.returncode != 0:
            log.error(f"gh erreur : {res.stderr.strip()}")
            return None
        return json.loads(res.stdout)
    except Exception as e:
        log.error(f"gh exception : {e}")
        return None

def _est_depot_git(rep: Path) -> bool:
    """Vrai si `rep` est situé dans un arbre de travail git valide (garde-fou du
    rafraîchissement automatique, issue #185). On sonde via
    `git rev-parse --is-inside-work-tree` plutôt qu'en testant l'existence d'un
    `.git` : robuste aux sous-répertoires et aux worktrees. Toute erreur (dossier
    absent, git introuvable) est traitée comme « pas un dépôt »."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=rep, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=10,
        )
        return res.returncode == 0 and res.stdout.strip() == "true"
    except (OSError, subprocess.SubprocessError):
        return False


def _tete_git(rep: Path) -> str | None:
    """SHA de HEAD dans `rep`, ou None si indéterminé. Sert à détecter si un
    `git pull` a réellement avancé l'historique, indépendamment de la locale du
    message git (le fast-forward français « Mise à jour … » contient « à jour »,
    ce qui rend toute détection par chaîne peu fiable — issue #185)."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=rep, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=10,
        )
        return res.stdout.strip() if res.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def rafraichir_depot(rep: Path, dry_run: bool = False):
    """Best-effort : rafraîchit le clone local via `git pull --ff-only` en début
    de cycle, pour qu'un watcher (CCL/CCW) travaille automatiquement sur le code
    le plus récent poussé sur origin, sans git pull manuel (issue #185).

    Sécurité par construction — `--ff-only` ne peut RIEN écraser :
      • historique local et distant non divergés → avance en fast-forward ;
      • déjà à jour ou local en avance (commits locaux poussables) → « Already up
        to date », aucune action ;
      • historique DIVERGÉ (backup+fix commité localement par CCL/CCW, en attente
        de push/revue par Alain) → le pull échoue proprement, RIEN n'est écrasé
        ni perdu ; on poursuit simplement sur le code local existant.

    Jamais bloquant : divergence, réseau indisponible ou dossier hors dépôt git
    sont journalisés (message distinct selon la cause) sans faire échouer le
    cycle — le pull est un confort de fraîcheur, pas une précondition.

    En dry-run, on n'altère pas l'arbre de travail local : on se contente de
    signaler ce qui serait fait (cohérent avec le reste du mode simulation)."""
    if not rep.is_dir():
        return
    if not _est_depot_git(rep):
        log.debug(f"  [pull] {rep} n'est pas un dépôt git — rafraîchissement ignoré.")
        return

    if dry_run:
        log.info(f"  [DRY-RUN] [pull] git pull --ff-only serait lancé dans {rep}.")
        return

    tete_avant = _tete_git(rep)

    try:
        res = subprocess.run(
            ["git", "pull", "--ff-only"],
            cwd=rep, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=60,
        )
    except subprocess.TimeoutExpired:
        log.warning(f"  [pull] échoué : délai dépassé sur git pull dans {rep} (réseau lent ?) — poursuite sur le code local.")
        return
    except Exception as e:
        log.warning(f"  [pull] échoué : {e} — poursuite sur le code local.")
        return

    if res.returncode == 0:
        # Détection avancement locale-indépendante : comparer HEAD avant/après
        # plutôt que le message git (« Mise à jour … » contient « à jour »).
        tete_apres = _tete_git(rep)
        if tete_avant and tete_apres and tete_avant != tete_apres:
            log.info(f"  [pull] {rep} mis à jour ({tete_avant[:7]} → {tete_apres[:7]}).")
        else:
            log.debug(f"  [pull] {rep} déjà à jour.")
        return

    # Échec : distinguer la cause pour un message clair et actionnable.
    err = (res.stderr + "\n" + res.stdout).strip()
    err_bas = err.lower()
    if "fast-forward" in err_bas or "diverg" in err_bas:
        log.info("  [pull] ignoré : commits locaux non poussés (fast-forward impossible — "
                 "backup/fix en attente de revue ?) — pensez à git push. Poursuite sur le code local.")
    elif ("could not resolve host" in err_bas or "connection" in err_bas
          or "unable to access" in err_bas or "timed out" in err_bas
          or "network is unreachable" in err_bas):
        premiere = err.splitlines()[0] if err else "réseau indisponible"
        log.warning(f"  [pull] échoué : réseau indisponible ({premiere}) — poursuite sur le code local.")
    else:
        premiere = err.splitlines()[0] if err else "erreur inconnue"
        log.warning(f"  [pull] échoué : {premiere} — poursuite sur le code local.")


def lister_issues():
    """Retourne la liste des issues (label du projet) ouvertes."""
    try:
        res = subprocess.run(
            ["gh", "issue", "list",
             "--repo", CFG.depot,
             "--label", CFG.label,
             "--state", "open",
             "--json", "number,title,body,labels,createdAt"],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=30
        )
        if res.returncode != 0:
            log.error(f"Erreur gh issue list : {res.stderr.strip()}")
            return []
        issues = json.loads(res.stdout)
        # Tri FIFO explicite : la plus ancienne issue en premier (issue #134).
        # createdAt est un timestamp ISO 8601 UTC (…Z), donc l'ordre
        # lexicographique croissant équivaut à l'ordre chronologique croissant.
        # On trie côté Python plutôt que via --order/--sort de gh pour rester
        # robuste aux différences de version de la CLI.
        issues.sort(key=lambda i: i.get("createdAt", ""))
        return issues
    except Exception as e:
        log.error(f"Exception lister_issues : {e}")
        return []

def extraire_priorite(body: str) -> str:
    """Extrait la priorité depuis le body de l'issue (en-tête bridge)."""
    for ligne in body.splitlines():
        if "PRIORITE" in ligne.upper():
            parts = ligne.split("|")
            if len(parts) >= 3:
                return parts[2].strip().lower()
    return "normale"

def est_titre_chef(titre: str) -> bool:
    """Vrai si le titre désigne une tâche « Chef » (pattern chef/ouvriers, §14).
    Cohérent avec la détection côté navigateur (app.js) : titre commençant par
    « Chef », insensible à la casse (ex. « Chef : orchestrer … »)."""
    return bool(re.match(r"chef\b", (titre or "").strip(), re.IGNORECASE))


# Types d'issue reconnus pour l'historique des durées (issue #108). L'ordre du
# tuple n'a pas d'importance ; « normal » est le repli.
TYPES_ISSUE = ("chef", "ouvrier", "spec_vue", "spec_metier", "spec_persistance", "normal")


def _classer_valeur_type(valeur: str) -> str | None:
    """Normalise une valeur brute (champ TYPE) vers un type canonique, ou None si
    elle ne correspond à rien de connu. Tolère les variantes (métier/metier,
    spec_vue/vue, …)."""
    v = (valeur or "").strip().lower()
    if not v:
        return None
    if "ouvrier" in v:
        return "ouvrier"
    if "chef" in v:
        return "chef"
    if "persistance" in v:
        return "spec_persistance"
    if "métier" in v or "metier" in v:
        return "spec_metier"
    if "vue" in v:
        return "spec_vue"
    return None


def deduire_type_issue(titre: str, body: str) -> str:
    """Déduit le TYPE d'une issue pour l'historique des durées (issue #108).
    Renvoie l'un de TYPES_ISSUE. Priorité : champ « | TYPE | … | » de l'en-tête
    bridge (source explicite, seul canal pour les spec_*), puis préfixe du titre
    (Chef/Ouvrier, cohérent avec est_titre_chef et app.js), sinon « normal »."""
    for ligne in (body or "").splitlines():
        if "| TYPE" in ligne.upper():
            parts = ligne.split("|")
            if len(parts) >= 3:
                t = _classer_valeur_type(parts[2])
                if t:
                    return t
    # Repli sur le préfixe du titre : on n'y accepte QUE chef/ouvrier (un titre
    # « Ajouter la vue X » ne doit pas devenir spec_vue par accident).
    prefixe = _classer_valeur_type((titre or "").strip().split(":")[0])
    if prefixe in ("chef", "ouvrier"):
        return prefixe
    return "normal"


def enregistrer_duree(projet: str, type_issue: str, mode: str,
                      duree_s: float, date_iso: str):
    """Ajoute une mesure de durée réelle (ACK → fermeture) à l'historique commun
    (issue #108). Best-effort : toute erreur est journalisée sans jamais
    interrompre le traitement de l'issue. Le fichier est une simple liste JSON
    d'objets {projet, type, mode, duree, date}."""
    try:
        DOSSIER_LOGS.mkdir(parents=True, exist_ok=True)
        historique = []
        if FICHIER_HISTORIQUE.exists():
            try:
                historique = json.loads(FICHIER_HISTORIQUE.read_text(encoding="utf-8")) or []
            except (json.JSONDecodeError, OSError):
                historique = []   # fichier corrompu : on repart d'une liste vide
        historique.append({
            "projet": projet,
            "type":   type_issue,
            "mode":   mode,
            "duree":  round(duree_s),   # secondes
            "date":   date_iso,
        })
        FICHIER_HISTORIQUE.write_text(
            json.dumps(historique, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        log.error(f"Erreur enregistrement historique durée : {e}")


def extraire_timeout(body: str, titre: str = "") -> int:
    """Extrait le TIMEOUT (en secondes) depuis le body de l'issue (en-tête bridge).
    Si absent ou mal formé, retombe sur le défaut du projet — mais un défaut plus
    généreux (CFG.timeout_chef) pour les issues « Chef : » (tâches monolithiques
    plus longues), afin d'éviter un dépassement du seul cycle standard (issue #106).

    Filet de sécurité (issue #111) : pour une tâche « Chef : », on applique
    max(valeur_trouvée, CFG.timeout_chef) au lieu de la première valeur telle
    quelle. L'interface place son tableau d'en-tête (TIMEOUT du formulaire, souvent
    le défaut 300s) AVANT le corps collé ; comme on retient la PREMIÈRE occurrence,
    ce défaut pouvait écraser un « | TIMEOUT | 1200s | » collé plus bas et faire
    échouer une tâche Chef sur un dépassement (cause de #108). Le plancher garantit
    qu'une tâche Chef ne tourne jamais sous son budget dédié, même si une valeur
    plus basse est trouvée en premier."""
    chef = est_titre_chef(titre)
    for ligne in body.splitlines():
        if "TIMEOUT" in ligne.upper():
            parts = ligne.split("|")
            if len(parts) >= 3:
                valeur = parts[2].strip().lower().rstrip("s")
                if valeur.isdigit():
                    trouve = int(valeur)
                    return max(trouve, CFG.timeout_chef) if chef else trouve
    if chef:
        return CFG.timeout_chef
    return CFG.timeout_claude

def extraire_modele(body: str) -> str:
    """Extrait le MODELE depuis le body de l'issue (en-tête bridge).
    Retombe sur CFG.modele_ccl (lui-même vide = défaut Claude Code) si absent."""
    for ligne in body.splitlines():
        if "| MODELE" in ligne.upper():
            parts = ligne.split("|")
            if len(parts) >= 3:
                valeur = parts[2].strip()
                if valeur and valeur.lower() not in ("", "-", "défaut", "defaut"):
                    return valeur
    return CFG.modele_ccl

def extraire_repo_cible(body: str) -> str:
    """Extrait le REPO_CIBLE depuis le body de l'issue (en-tête bridge).
    Calqué sur extraire_timeout/extraire_modele : cherche une ligne
    « | REPO_CIBLE | <chemin absolu> | » et retourne le chemin tel quel (str),
    ou "" si le champ est absent ou vide.

    Ne concerne que les projets à périmètre dynamique (issue #125) : le chemin
    renvoyé sert de périmètre effectif ET de cwd pour cette exécution, après
    validation par valider_repo_cible()."""
    for ligne in body.splitlines():
        if "| REPO_CIBLE" in ligne.upper():
            parts = ligne.split("|")
            if len(parts) >= 3:
                valeur = parts[2].strip()
                if valeur and valeur.lower() not in ("", "-"):
                    return valeur
    return ""

def valider_repo_cible(chemin: str) -> tuple[bool, str]:
    """Valide un REPO_CIBLE avant tout lancement de CCL (issue #125).

    Vérifie, dans cet ordre :
      1. le chemin est absolu et ne contient aucune séquence de traversée '..'
         (Path.resolve() puis comparaison stricte au chemin fourni : toute
         normalisation — '..' ou lien symbolique — le fait diverger et donc
         refuser) ;
      2. le chemin existe et est un dossier ;
      3. le dossier appartient au même utilisateur système que le process
         watcher (st_uid == os.getuid()).

    Retourne (True, "") si tout passe, sinon (False, raison explicite). L'échec
    d'une seule vérification suffit à refuser — c'est une erreur de
    configuration/issue, pas un échec transitoire : aucun retry côté appelant."""
    if not chemin:
        return False, "chemin vide"
    p = Path(chemin)
    if not p.is_absolute():
        return False, "le chemin doit être absolu"
    resolu = p.resolve()
    if resolu != p:
        return False, ("le chemin contient une séquence de traversée '..' ou n'est "
                       "pas canonique (lien symbolique) — fournir un chemin absolu direct")
    if not resolu.is_dir():
        return False, "le chemin n'existe pas ou n'est pas un dossier"
    try:
        proprietaire = resolu.stat().st_uid
    except OSError as e:
        return False, f"impossible de lire les métadonnées du dossier ({e})"
    if proprietaire != os.getuid():
        return False, (f"le dossier n'appartient pas à l'utilisateur du watcher "
                       f"(uid propriétaire {proprietaire} ≠ uid watcher {os.getuid()})")
    return True, ""

# ─── Détection de conflit avec un watcher actif (issue #125) ───────────────────
# Variantes LOCALES de app.projets.lister_projets() et app.watchers.watcher_actif() :
# app.projets importe watcher — réutiliser ces fonctions ici créerait un import
# circulaire. On réplique donc la même logique (glob des .conf, sonde du fichier
# PID) plutôt que d'importer le package app depuis le watcher.

def _lister_projets_connus() -> list[Config]:
    """Charge tous les projets (un configs/*.conf = un projet). Équivalent local
    de app.projets.lister_projets() ; ignore silencieusement les configs
    invalides (même contrat : except SystemExit)."""
    projets = []
    for chemin in sorted(DOSSIER_SCRIPT.glob("configs/*.conf")):
        try:
            projets.append(charger_config(chemin))
        except SystemExit:
            pass
    return projets

def _watcher_actif(cfg: Config) -> bool:
    """Vrai si un watcher tourne pour ce projet. Équivalent local de
    app.watchers.watcher_actif() : lit le fichier PID et sonde le processus
    (os.kill(pid, 0) ne tue pas, il vérifie l'existence)."""
    pid_file = DOSSIER_LOGS / f"watcher-{cfg.nom}.pid"
    if not pid_file.exists():
        return False
    try:
        pid = int(pid_file.read_text().strip())
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError, ValueError):
        return False

def detecter_conflit_watcher(repo_cible_resolu: Path, projet_courant: str) -> str | None:
    """Cherche un projet connu, watcher actif, dont le rep_travail ou le
    périmètre chevauche repo_cible_resolu (chemins résolus, égalité ou relation
    parent/enfant). Retourne le nom du projet en conflit, ou None.

    Approche pragmatique (issue #125) : pas de verrou distribué, juste de la
    transparence. Le projet courant est exclu (son propre watcher est forcément
    actif puisqu'il traite l'issue en cours)."""
    for cfg in _lister_projets_connus():
        if cfg.nom == projet_courant:
            continue
        if not _watcher_actif(cfg):
            continue
        candidats = [cfg.rep_travail]
        if cfg.perimetre:
            candidats += [Path(part.strip()) for part in cfg.perimetre.split(",")
                          if part.strip()]
        for candidat in candidats:
            try:
                cr = candidat.expanduser().resolve()
            except (OSError, RuntimeError):
                continue
            if (cr == repo_cible_resolu
                    or cr in repo_cible_resolu.parents
                    or repo_cible_resolu in cr.parents):
                return cfg.nom
    return None

def ajouter_label(numero: int, label: str):
    """Ajoute un label à une issue sans la fermer."""
    try:
        subprocess.run(
            ["gh", "issue", "edit", str(numero),
             "--repo", CFG.depot,
             "--add-label", label],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=30
        )
    except Exception as e:
        log.error(f"Erreur ajout label '{label}' sur issue #{numero} : {e}")

def commenter_issue(numero: int, message: str):
    """Poste un commentaire sur une issue."""
    try:
        subprocess.run(
            ["gh", "issue", "comment", str(numero),
             "--repo", CFG.depot,
             "--body", message],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=30
        )
    except Exception as e:
        log.error(f"Erreur commentaire issue #{numero} : {e}")

def fermer_issue(numero: int):
    """Ferme une issue et ajoute le label 'done'."""
    try:
        subprocess.run(
            ["gh", "issue", "close", str(numero), "--repo", CFG.depot],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=30
        )
        subprocess.run(
            ["gh", "issue", "edit", str(numero),
             "--repo", CFG.depot,
             "--add-label", LABEL_FAIT],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=30
        )
    except Exception as e:
        log.error(f"Erreur fermeture issue #{numero} : {e}")

def lancer_claude(numero: int, titre: str, body: str, dry_run: bool,
                  autoriser_ecriture: bool = False,
                  timeout: int = None,
                  modele: str = "",
                  prompt_perso: str = None,
                  perimetre: str = None,
                  cwd: Path = None) -> tuple[bool, str]:
    """
    Lance Claude Code en mode non-interactif sur une issue.

    Par défaut (autoriser_ecriture=False) : LECTURE SEULE (diagnostic, pas d'écriture).
    Si autoriser_ecriture=True (label 'mode_write' posé sciemment) : on ajoute
    --dangerously-skip-permissions. Le garde-fou anti-push reste dans le prompt.

    prompt_perso : si fourni, remplace intégralement le prompt standard (titre/body
    + garde-fou + format de réponse imposé). Sert aux passes qui ont besoin d'un
    prompt sur mesure — ex. la passe diagnostique (issue #124), qui ne doit PAS
    demander de résoudre la tâche. Le reste de la machinerie (dry-run, cwd, timeout,
    modèle, --dangerously-skip-permissions selon autoriser_ecriture) est inchangé.

    perimetre / cwd : surchargent respectivement CFG.perimetre (clause de prompt) et
    CFG.rep_travail (répertoire réel du subprocess). None = valeur du .conf. Servent
    au périmètre dynamique (issue #125) : pour un projet à périmètre dynamique, ces
    deux valeurs viennent du champ REPO_CIBLE de l'issue, pas de la config.

    Retourne (succès, sortie).
    """
    if timeout is None:
        timeout = CFG.timeout_claude

    perimetre_effectif = CFG.perimetre if perimetre is None else perimetre
    cwd_effectif = CFG.rep_travail if cwd is None else cwd

    if autoriser_ecriture:
        if CFG.cmd_backup:
            consigne_backup = (
                "- Fais TOUJOURS une sauvegarde avant toute modification, en lançant "
                f"cette commande depuis le répertoire du projet :\n  {CFG.cmd_backup}"
            )
        else:
            consigne_backup = (
                "- Fais TOUJOURS une sauvegarde de l'état courant avant toute modification "
                "(par exemple un commit git de tout le dossier), afin de permettre un retour arrière."
            )
        garde_fou = f"""
MODE ÉCRITURE ACTIVÉ — tu es autorisé à modifier des fichiers, exécuter des
commandes et faire des commits git si la tâche le demande.
RÈGLES DE SÉCURITÉ IMPÉRATIVES :
{consigne_backup}
- Ne fais JAMAIS 'git push' ni 'git push --force' : Alain pousse lui-même,
  manuellement, après avoir vérifié tes commits.
- N'exécute aucune commande destructrice (rm -rf large, git reset --hard sur du
  travail non sauvegardé, git filter-repo, force-push) sans que la tâche le
  demande EXPLICITEMENT.
- En cas de doute, préfère t'arrêter et décrire ce que tu ferais plutôt que d'agir.
"""
    else:
        garde_fou = """
MODE LECTURE SEULE — tu ne dois que lire, analyser et rapporter. N'écris aucun
fichier, n'exécute aucune commande modifiant l'état du système ou du dépôt.
"""

    # Contexte projet optionnel : fichier décrivant l'architecture, les
    # conventions, l'historique. Injecté tel quel dans le prompt pour donner à
    # CCL une connaissance du projet sans alourdir chaque issue.
    bloc_contexte = ""
    if CFG.fichier_contexte:
        chemin_ctx = Path(CFG.fichier_contexte).expanduser()
        if not chemin_ctx.is_absolute():
            chemin_ctx = CFG.rep_travail / chemin_ctx
        if chemin_ctx.exists():
            try:
                contenu = chemin_ctx.read_text(encoding="utf-8", errors="replace")
                LIMITE = 4000
                if len(contenu) > LIMITE:
                    contenu = contenu[:LIMITE] + "\n[...contexte tronqué à 4000 caractères...]"
                bloc_contexte = (
                    f"\nCONTEXTE DU PROJET (lu depuis {chemin_ctx}) :\n"
                    f"---\n{contenu}\n---\n"
                )
            except Exception as e:
                log.warning(f"Lecture du fichier de contexte '{chemin_ctx}' impossible : {e}")
        else:
            log.warning(f"Fichier de contexte '{chemin_ctx}' introuvable — rien injecté.")

    if perimetre_effectif:
        clause_perimetre = (
            f"\nPÉRIMÈTRE STRICT — tu ne dois lire, modifier ou exécuter des commandes "
            f"que dans les répertoires suivants : {perimetre_effectif}\n"
            f"Toute action en dehors de ce périmètre est interdite, même si la tâche "
            f"le demande explicitement. En cas de doute, arrête-toi et signale-le.\n"
        )
    else:
        clause_perimetre = ""

    if prompt_perso is not None:
        prompt = prompt_perso
    else:
        prompt = f"""Tu es l'agent Linux (CCL) du bridge inter-agents, projet « {CFG.nom} ».
Traite la tâche suivante issue du GitHub Issue #{numero} :

TITRE : {titre}

BODY :
{body}
{bloc_contexte}{clause_perimetre}{garde_fou}
Instructions :
1. Lis attentivement la tâche demandée
2. Effectue le travail demandé (dans les limites du mode ci-dessus)
3. Si tu dois créer une issue for-windows, utilise : gh issue create --repo {CFG.depot} --label "bridge,for-windows" ...

Réponds avec ce format exact, sans rien ajouter avant ni après :

✅ Tâche terminée — [résumé en une ligne de ce qui a été fait]
Commits : [hash backup] (backup) + [hash fix] (fix) — ou "aucun" si lecture seule
py_compile : OK / N/A — push : aucun

<details>
<summary>Détails complets</summary>

[Ici : description complète de chaque modification, fichiers touchés,
 lignes ajoutées/supprimées, décisions prises, points d'attention.]

</details>

Le bloc <details> est rendu par GitHub comme un accordéon dépliable —
les informations sont là mais n'encombrent pas la lecture rapide.

Si la tâche échoue, remplace ✅ par ❌ et explique la cause en une ligne.
"""

    if dry_run:
        mode = "ÉCRITURE" if autoriser_ecriture else "lecture seule"
        log.info(f"[DRY-RUN] Claude Code serait lancé pour issue #{numero} (mode {mode}, cwd {cwd_effectif})")
        return True, f"[DRY-RUN] Tâche simulée avec succès (mode {mode})."

    cmd = ["claude", "--print"]
    if modele:
        cmd += ["--model", modele]
    if autoriser_ecriture:
        cmd.append("--dangerously-skip-permissions")
    cmd.append(prompt)

    try:
        res = subprocess.run(
            cmd,
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=timeout,
            cwd=cwd_effectif
        )
        if res.returncode == 0:
            return True, res.stdout.strip()
        else:
            return False, res.stderr.strip() or "Erreur inconnue"
    except subprocess.TimeoutExpired:
        return False, f"Timeout après {timeout}s"
    except FileNotFoundError:
        return False, "Claude Code introuvable (claude non trouvé dans PATH)"
    except Exception as e:
        return False, str(e)


def diagnostiquer_echec(numero: int, titre: str, body: str,
                        derniere_erreur: str,
                        perimetre: str = None,
                        cwd: Path = None) -> str | None:
    """Passe diagnostique courte et en LECTURE SEULE, lancée juste avant de poser
    'needs-human' sur une issue non critique abandonnée (issue #124).

    But : donner à Alain quelques pistes concrètes sur la cause du timeout / de
    l'échec répété, sans qu'il ait à ouvrir lui-même une session Claude Code pour
    un diagnostic qui tient souvent en quelques dizaines de secondes de lecture.

    Ne tente JAMAIS de résoudre la tâche : autoriser_ecriture=False (lecture seule,
    même si l'issue d'origine était en mode écriture) et prompt dédié qui demande
    explicitement de ne PAS corriger. Timeout court et fixe (CFG.timeout_diagnostic),
    indépendant du timeout de la tâche d'origine.

    Best-effort : retourne le texte du diagnostic, ou None si la passe elle-même
    échoue / timeout (l'appelant n'ajoute alors simplement aucune section). On ne
    boucle jamais dessus et on ne retente pas.

    perimetre / cwd : mêmes surcharges que lancer_claude (issue #125). Pour un
    projet à périmètre dynamique, le diagnostic doit lire dans REPO_CIBLE et y
    être lancé, pas dans le rep_travail figé du .conf (placeholder)."""
    perimetre_effectif = CFG.perimetre if perimetre is None else perimetre
    if perimetre_effectif:
        clause_perimetre = (
            f"\nPÉRIMÈTRE STRICT — tu ne dois lire que dans les répertoires "
            f"suivants : {perimetre_effectif}\n"
        )
    else:
        clause_perimetre = ""

    prompt = f"""Tu es l'agent Linux (CCL) du bridge inter-agents, projet « {CFG.nom} ».
Une tâche (GitHub Issue #{numero}) a échoué de façon répétée et va être confiée à
un humain. NE tente PAS de résoudre la tâche : n'écris aucun fichier, n'exécute
aucune commande modifiant l'état du système ou du dépôt.

Ton unique rôle est un diagnostic RAPIDE et en LECTURE SEULE. À partir du titre,
du corps de la tâche et de la dernière erreur ci-dessous, liste les 3 à 5 causes
LES PLUS PROBABLES de ce timeout / échec répété — par exemple : boucle infinie
suspectée, commande interactive qui attend une entrée, opération réseau/IO lente,
dépendance manquante, tâche simplement trop volumineuse pour le timeout configuré,
etc. Reste concret et bref.

TITRE : {titre}

BODY :
{body}

DERNIÈRE ERREUR : {derniere_erreur}
{clause_perimetre}
Réponds uniquement par une courte liste à puces (3 à 5 pistes) des causes les plus
probables, sans préambule ni conclusion, et sans tenter de corriger quoi que ce soit."""

    try:
        succes, sortie = lancer_claude(
            numero, titre, body, dry_run=False,
            autoriser_ecriture=False,
            timeout=CFG.timeout_diagnostic,
            modele=CFG.modele_ccl,
            prompt_perso=prompt,
            perimetre=perimetre,
            cwd=cwd,
        )
    except Exception as e:
        log.warning(f"  Passe diagnostique #{numero} indisponible (exception : {e}).")
        return None

    if succes and sortie.strip():
        return sortie.strip()
    log.info(f"  Passe diagnostique #{numero} indisponible (échec/timeout) — abandon sans diagnostic.")
    return None

# ─── Traitement d'une issue ────────────────────────────────────────────────────

# Mémoire des issues en cours de traitement (évite les doublons)
issues_en_cours: set[int] = set()


def _chemin_verrou(rep_travail: Path) -> Path:
    """Chemin du fichier de verrou associé à un répertoire de travail donné.

    La clé est le chemin RÉSOLU du rep_travail : deux instances de watcher visant
    le même dossier (même via deux .conf différents, ou une relance) obtiennent
    le MÊME verrou, donc s'excluent mutuellement. Le nom garde un préfixe lisible
    (basename du dossier) suivi d'une empreinte du chemin complet pour rester
    unique et débuggable. Le fichier vit sous DOSSIER_VERROUS (logs/, gitignoré),
    jamais dans rep_travail (cf. commentaire de DOSSIER_VERROUS)."""
    resolu = rep_travail.expanduser().resolve()
    empreinte = hashlib.sha1(str(resolu).encode("utf-8")).hexdigest()[:12]
    return DOSSIER_VERROUS / f"{resolu.name or 'racine'}-{empreinte}.lock"


def acquerir_verrou(rep_travail: Path, timeout_projet: int) -> Path | None:
    """Tente de poser un verrou exclusif sur `rep_travail`. Retourne le chemin du
    verrou si acquis, ou None si un AUTRE traitement le détient déjà (verrou
    vivant) — l'appelant doit alors s'abstenir de lancer claude.

    Un verrou plus vieux que la durée de traitement plausible d'une issue est
    considéré comme PÉRIMÉ (orphelin d'un watcher tué sans passer par le finally)
    et repris. La borne tient compte des tentatives multiples : au pire un
    traitement légitime dure max_essais × (timeout + pause) ; au-delà (+ marge),
    plus aucun claude légitime ne tourne.

    Création atomique via O_CREAT|O_EXCL : si un autre process gagne la course
    entre le test de péremption et la création, l'ouverture échoue proprement et
    on renvoie None (pas de double lancement).

    Best-effort sur les erreurs d'E/S annexes : si le dossier de verrous ne peut
    être créé ou le fichier posé (permissions…), on journalise et on renvoie le
    chemin quand même plutôt que de bloquer indéfiniment le traitement — la
    protection en mémoire (issues_en_cours) reste active dans ce cas dégradé."""
    verrou = _chemin_verrou(rep_travail)
    try:
        DOSSIER_VERROUS.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        log.warning(f"Dossier de verrous {DOSSIER_VERROUS} incréable ({e}) — verrou désactivé pour cette issue.")
        return verrou   # dégradé : on poursuit, issues_en_cours protège encore dans ce process

    peremption = CFG.max_essais * (timeout_projet + PAUSE_ENTRE_TENTATIVES) + PEREMPTION_MARGE_VERROU

    if verrou.exists():
        try:
            age = time.time() - verrou.stat().st_mtime
        except OSError:
            age = None
        if age is not None and age < peremption:
            return None   # verrou vivant : un autre traitement est en cours sur ce dossier
        # Verrou périmé (ou stat illisible) : on le reprend.
        log.warning(
            f"Verrou périmé sur {rep_travail} "
            f"(âge {int(age) if age is not None else '?'}s ≥ {int(peremption)}s) — repris "
            f"(watcher précédent probablement tué avant libération)."
        )
        try:
            verrou.unlink()
        except FileNotFoundError:
            pass
        except OSError as e:
            log.warning(f"Suppression du verrou périmé {verrou} impossible ({e}).")

    try:
        fd = os.open(str(verrou), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except FileExistsError:
        return None   # course perdue : un autre process vient de poser le verrou
    except OSError as e:
        log.warning(f"Pose du verrou {verrou} impossible ({e}) — on poursuit sans verrou fichier.")
        return verrou   # dégradé, comme ci-dessus
    try:
        os.write(fd, f"pid={os.getpid()} projet={CFG.nom} rep={rep_travail}\n".encode("utf-8"))
    finally:
        os.close(fd)
    return verrou


def liberer_verrou(verrou: Path | None):
    """Supprime le fichier de verrou (best-effort). Appelée dans un finally pour
    garantir la libération même en cas d'échec/exception du traitement."""
    if not verrou:
        return
    try:
        verrou.unlink()
    except FileNotFoundError:
        pass
    except OSError as e:
        log.warning(f"Libération du verrou {verrou} impossible ({e}).")


def traiter_issue(issue: dict, dry_run: bool):
    numero = issue["number"]
    titre  = issue["title"]
    body   = issue.get("body") or ""

    if numero in issues_en_cours:
        return

    labels = [l.get("name", "") for l in issue.get("labels", [])]

    # Une issue déjà 'needs-human' a échoué définitivement : on ne la retraite
    # PAS (sinon boucle infinie) tant qu'un humain n'a pas retiré le label.
    if LABEL_ECHEC in labels:
        log.debug(f"Issue #{numero} déjà marquée '{LABEL_ECHEC}' — ignorée (intervention humaine en attente).")
        return

    issues_en_cours.add(numero)
    priorite = extraire_priorite(body)
    critique = priorite in PRIORITES_CRITIQUES
    timeout  = extraire_timeout(body, titre)
    modele   = extraire_modele(body)

    autoriser_ecriture = LABEL_ECRITURE in labels

    mode_txt = "ÉCRITURE ⚠️" if autoriser_ecriture else "lecture seule"
    log.info(f"→ Issue #{numero} détectée : '{titre}' [priorité: {priorite}] [mode: {mode_txt}]")
    if autoriser_ecriture:
        log.warning(f"  ⚠️  MODE ÉCRITURE ARMÉ pour #{numero} (label '{LABEL_ECRITURE}') — actions permises, push interdit.")

    # Périmètre effectif de cette exécution (issue #125). Par défaut : celui du
    # .conf. Pour un projet à périmètre dynamique, il vient du champ REPO_CIBLE de
    # l'issue et devient à la fois le périmètre de la clause de prompt ET le cwd
    # réel du subprocess. Toute erreur de config/issue ici est définitive (pas de
    # retry) : commentaire explicite + label 'needs-human' pour stopper la reprise.
    perimetre_effectif = CFG.perimetre
    cwd_effectif       = CFG.rep_travail
    avertissement_conflit = ""

    if CFG.perimetre_dynamique:
        repo_cible = extraire_repo_cible(body)
        if not repo_cible:
            log.error(f"  Issue #{numero} : PERIMETRE_DYNAMIQUE actif mais champ REPO_CIBLE absent — abandon (aucun repli).")
            commenter_issue(
                numero,
                f"❌ Échec de configuration — ce projet est en **périmètre dynamique** "
                f"(`PERIMETRE_DYNAMIQUE = true`) mais l'issue ne fournit pas de champ "
                f"`| REPO_CIBLE | <chemin absolu> |`. Aucun repli sur le répertoire de "
                f"travail du `.conf` n'est effectué — le périmètre doit être explicite. "
                f"Corrigez l'en-tête de l'issue puis retirez le label `{LABEL_ECHEC}` "
                f"pour relancer."
            )
            ajouter_label(numero, LABEL_ECHEC)
            issues_en_cours.discard(numero)
            return

        valide, raison = valider_repo_cible(repo_cible)
        if not valide:
            log.error(f"  Issue #{numero} : REPO_CIBLE refusé ({raison}) — abandon, aucun lancement de CCL.")
            commenter_issue(
                numero,
                f"❌ `REPO_CIBLE` refusé — `{repo_cible}` : {raison}.\n\n"
                f"Aucun lancement de CCL (erreur de configuration/issue, pas un échec "
                f"transitoire). Corrigez le champ `REPO_CIBLE` puis retirez le label "
                f"`{LABEL_ECHEC}` pour relancer."
            )
            ajouter_label(numero, LABEL_ECHEC)
            issues_en_cours.discard(numero)
            return

        repo_cible_resolu  = Path(repo_cible).resolve()
        perimetre_effectif = str(repo_cible_resolu)
        cwd_effectif       = repo_cible_resolu
        log.info(f"  Périmètre dynamique : REPO_CIBLE = {repo_cible_resolu} (périmètre + cwd de cette exécution).")

        # Transparence (issue #125) : si un autre watcher actif partage ce dossier,
        # on ne bloque pas mais on signale le risque en tête du résultat.
        conflit = detecter_conflit_watcher(repo_cible_resolu, CFG.nom)
        if conflit:
            log.warning(f"  ⚠️  Conflit potentiel : watcher '{conflit}' actif sur {repo_cible_resolu}.")
            avertissement_conflit = (
                f"⚠️ Traitement lancé pendant qu'un watcher actif sur ce dépôt "
                f"(projet {conflit}) pouvait être en train d'écrire — certains constats "
                f"peuvent être obsolètes.\n\n"
            )

    # Garde-fou anti-collision inter-process (issue #189) : AVANT l'ACK et tout
    # lancement de claude, on pose un verrou exclusif sur le répertoire de travail
    # effectif. Si un AUTRE process (autre instance/relance de watcher, ou un
    # doublon d'issue traité en parallèle) détient déjà ce verrou, on NE lance PAS
    # un second claude sur le même dossier : on relâche l'issue (retirée de
    # issues_en_cours, sans ACK) pour qu'elle soit reprise au prochain cycle, une
    # fois le verrou libéré. issues_en_cours ne protège que dans CE process ; le
    # verrou fichier étend la protection entre process.
    verrou = acquerir_verrou(cwd_effectif, timeout)
    if verrou is None:
        log.warning(
            f"  Issue #{numero} différée : un autre traitement détient déjà le verrou "
            f"sur {cwd_effectif} — collision évitée, reprise au prochain cycle."
        )
        issues_en_cours.discard(numero)
        return

    try:
        commenter_issue(
            numero,
            f"✅ ACK — Issue #{numero} reçue par watcher.py (agent Linux, projet {CFG.nom}). "
            f"Mode : **{mode_txt}**. Traitement en cours..."
        )
        # Départ du chrono de durée réelle (ACK → fermeture), pour l'historique des
        # durées (issue #108). monotonic() pour la mesure d'écoulement (insensible aux
        # changements d'heure système).
        debut_traitement = time.monotonic()

        tentative = 0
        while True:
            tentative += 1
            log.info(f"  Tentative {tentative}/{CFG.max_essais if not critique else '∞'}...")

            succes, sortie = lancer_claude(numero, titre, body, dry_run, autoriser_ecriture,
                                           timeout, modele,
                                           perimetre=perimetre_effectif, cwd=cwd_effectif)

            if succes:
                log.info(f"  ✓ Issue #{numero} traitée avec succès.")
                commenter_issue(numero, f"## Résultat\n\n{avertissement_conflit}{sortie}")
                fermer_issue(numero)
                issues_en_cours.discard(numero)
                # Historique des durées (issue #108) : durée réelle ACK → fermeture,
                # catégorisée par projet/type/mode, pour l'estimation prédictive.
                enregistrer_duree(
                    CFG.nom,
                    deduire_type_issue(titre, body),
                    "write" if autoriser_ecriture else "read",
                    time.monotonic() - debut_traitement,
                    datetime.now().isoformat(timespec="seconds"),
                )
                notifier(
                    labels,
                    titre=f"✅ {CFG.nom} #{numero} — traitée",
                    message=f"'{titre}' traitée avec succès.",
                    urgence_bureau="normal",
                    priorite_ntfy="default",
                )
                return

            # Échec
            log.warning(f"  ✗ Tentative {tentative} échouée : {sortie}")

            if tentative >= CFG.max_essais:
                if critique:
                    alerte_critique(numero, titre, tentative, labels)
                    log.warning(f"  Issue critique #{numero} — nouvelle tentative au prochain cycle.")
                    issues_en_cours.discard(numero)  # sera reprise au prochain poll
                    return
                else:
                    log.error(f"  Issue #{numero} abandonnée après {CFG.max_essais} tentatives.")
                    # Passe diagnostique courte, en lecture seule, avant l'abandon
                    # définitif (issue #124) : quelques pistes concrètes pour éviter à
                    # Alain d'ouvrir lui-même une session juste pour comprendre le
                    # timeout. Best-effort — n'ajoute rien si elle échoue/timeout.
                    log.info(f"  Passe diagnostique courte (lecture seule, {CFG.timeout_diagnostic}s) pour #{numero}...")
                    diagnostic = diagnostiquer_echec(numero, titre, body, sortie,
                                                     perimetre=perimetre_effectif,
                                                     cwd=cwd_effectif)
                    message_echec = (
                        f"❌ Échec après {CFG.max_essais} tentatives.\n\n"
                        f"Dernière erreur : `{sortie}`\n\n"
                    )
                    if diagnostic:
                        message_echec += (
                            f"🔍 Pistes probables (diagnostic automatique) :\n\n"
                            f"{diagnostic}\n\n"
                        )
                    message_echec += (
                        f"Intervention humaine requise. Label `{LABEL_ECHEC}` posé : "
                        f"cette issue ne sera plus retraitée automatiquement tant que le "
                        f"label n'est pas retiré (ou l'issue fermée) manuellement."
                    )
                    commenter_issue(numero, message_echec)
                    ajouter_label(numero, LABEL_ECHEC)
                    notifier(
                        labels,
                        titre=f"❌ {CFG.nom} #{numero} — échec définitif",
                        message=f"'{titre}' abandonnée après {CFG.max_essais} tentatives.\nDernière erreur : {sortie[:200]}",
                        urgence_bureau="critical",
                        priorite_ntfy="high",
                    )
                    issues_en_cours.discard(numero)
                    return

            time.sleep(PAUSE_ENTRE_TENTATIVES)  # backoff entre tentatives
    finally:
        # Libération garantie du verrou (succès, échec définitif, exception,
        # reprise critique). Sans ce finally, un crash laisserait un verrou
        # orphelin — d'où aussi la péremption côté acquerir_verrou.
        liberer_verrou(verrou)

# ─── Boucle principale ─────────────────────────────────────────────────────────

def main():
    global CFG

    parser = argparse.ArgumentParser(description="Bridge watcher — agent Linux (multi-projets)")
    parser.add_argument("--config", required=True, help="Fichier de config du projet (ex. configs/bridge_agent.conf)")
    parser.add_argument("--dry-run", action="store_true", help="Simule sans lancer Claude Code")
    parser.add_argument("--interval", type=int, default=None, help="Surcharge l'intervalle de polling (secondes)")
    args = parser.parse_args()

    # Résolution tolérante du chemin de config : tel quel, sinon relatif au script.
    chemin = Path(args.config)
    if not chemin.exists():
        chemin = DOSSIER_SCRIPT / args.config

    CFG = charger_config(chemin)
    configurer_logs(CFG)

    intervalle = args.interval if args.interval is not None else CFG.intervalle

    log.info("=" * 60)
    log.info(f"Bridge watcher démarré — projet: {CFG.nom} — dépôt: {CFG.depot} — label: {CFG.label}")
    log.info(f"cwd Claude Code: {CFG.rep_travail} — journal: {CFG.fichier_log}")
    log.info(f"Polling toutes les {intervalle}s — dry-run: {args.dry_run}")
    log.info(f"contexte projet: {CFG.fichier_contexte or 'aucun'}")
    log.info("=" * 60)

    if not CFG.rep_travail.is_dir():
        log.warning(f"⚠️  Le répertoire de travail '{CFG.rep_travail}' n'existe pas (ou n'est pas un dossier). "
                    f"Claude Code échouera tant que ce n'est pas corrigé dans la config.")

    if args.dry_run:
        log.info("[DRY-RUN] Mode simulation activé — Claude Code ne sera pas lancé.")

    while True:
        try:
            # Rafraîchissement automatique du clone local en début de cycle
            # (issue #185). Choix : au début du cycle, sur CFG.rep_travail (le
            # clone fixe du projet), plutôt qu'avant chaque issue — c'est le
            # dépôt propre du watcher, il ne change pas d'une issue à l'autre, et
            # un pull par cycle suffit à la fraîcheur voulue. Les projets à
            # périmètre dynamique (REPO_CIBLE par issue) ne sont volontairement
            # PAS rafraîchis ici : ce sont des dépôts-cibles d'audit, pas le clone
            # de travail du watcher. Best-effort, jamais bloquant.
            rafraichir_depot(CFG.rep_travail, dry_run=args.dry_run)
            issues = lister_issues()
            if issues:
                log.info(f"{len(issues)} issue(s) en attente.")
                for issue in issues:
                    traiter_issue(issue, dry_run=args.dry_run)
            else:
                log.debug("Aucune issue en attente.")
        except KeyboardInterrupt:
            log.info("Watcher arrêté par l'utilisateur.")
            sys.exit(0)
        except Exception as e:
            log.error(f"Erreur boucle principale : {e}")

        time.sleep(intervalle)

if __name__ == "__main__":
    main()
