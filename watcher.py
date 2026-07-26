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
import tempfile
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

# Consignes injectées dans le PROMPT donné à CCL (architecture à trois couches,
# issues #209 puis #211). Vivent à côté du watcher (racine du dépôt), PAS dans le
# rep_travail du projet piloté : elles sont communes à tous les projets. Trois
# couches, de la plus générale à la plus spécifique (§12.1 de BRIDGE_AGENT_DOC.md) :
#   - consignes/globales.md          : NON-optionnel, injecté pour TOUTE issue
#                                       (rappels de sécurité transversaux) ;
#   - consignes/type_<type>.md       : optionnel, selon le TYPE déduit de l'issue
#                                       (ex. type_chef.md) ;
#   - consignes/projet_<projet>.md   : optionnel, selon le projet piloté.
# Depuis #211 l'injection se fait dans le prompt CCL (via lancer_claude), et NON
# plus dans le corps de l'issue GitHub : couverture universelle quel que soit le
# chemin de création (formulaire web, `gh issue create` d'un chef, création
# manuelle GitHub) — même modèle que FICHIER_CONTEXTE/CONTEXTE.md.
DOSSIER_CONSIGNES = DOSSIER_SCRIPT / "consignes"

# Historique des durées réelles de traitement (issue #108) : un fichier commun,
# une entrée par issue fermée {projet, type, mode, duree, date}. Vit dans logs/
# (déjà gitignoré, cohérent avec les .conf) : donnée de télémétrie locale, pas de
# source à versionner. Lu par app/issues.py pour estimer la durée d'une issue en
# cours (médiane du même projet+type+mode).
FICHIER_HISTORIQUE = DOSSIER_LOGS / "historique_durees.json"

# ─── Calibration automatique du TIMEOUT (issue #221) ───────────────────────────
# Deux fichiers d'état JSON, tous deux sous DOSSIER_LOGS (donc déjà gitignorés,
# et déjà PARTAGÉS entre tous les process watcher — DOSSIER_LOGS est fixe,
# relatif au script, pas au projet piloté, cf. commentaire en tête de fichier) :
#   - etat_timeout.json  : par combinaison (projet, TYPE, mode), l'EWMA de la
#     durée typique et de sa variabilité (issues réussies uniquement), plus le
#     multiplicateur de backoff (issues en timeout) — cf. maj_calibration_timeout.
#   - etat_ambiance.json : facteur d'ambiance F (F_reseau/F_local), EWMA à
#     demi-vie TEMPORELLE, GLOBAL à tous les projets — cf. _maj_ambiance.
# Formule (inspirée de l'algorithme RTO TCP, Jacobson/Karels), validée avec
# Alain :  TIMEOUT_suggéré = (duree_typique + k × variabilite) × F × backoff.
# Cette issue calcule et journalise TIMEOUT_suggéré à chaque clôture d'issue,
# mais NE modifie PAS le TIMEOUT réellement appliqué (celui de l'en-tête de
# l'issue reste seul décisif) — l'exposition/consultation est une 3e issue.
FICHIER_ETAT_TIMEOUT   = DOSSIER_LOGS / "etat_timeout.json"
FICHIER_ETAT_AMBIANCE  = DOSSIER_LOGS / "etat_ambiance.json"

K_VARIABILITE               = 4     # constante de départ de la formule (à backtester plus tard)
DEMI_VIE_ISSUES             = 15    # demi-vie de l'EWMA duree_typique/variabilite, EN NOMBRE D'ISSUES
ALPHA_EWMA_ISSUES           = 1 - 0.5 ** (1 / DEMI_VIE_ISSUES)
DEMI_VIE_AMBIANCE_HEURES    = 4.0   # demi-vie de l'EWMA F_reseau/F_local, TEMPORELLE (pas en nb d'issues)
SEUIL_SUCCES_RAPIDE         = 0.7   # succès compté « rapide » si duree_reelle < SEUIL × TIMEOUT courant
SUCCES_RAPIDES_POUR_RESET   = 3     # nb de succès rapides consécutifs pour réinitialiser le backoff
FACTEUR_BACKOFF             = 1.5   # multiplicateur appliqué à chaque timeout de la combinaison
# Plancher minimum du TIMEOUT_suggéré (secondes). Proposition à valider avec
# Alain : dans historique_durees.json actuel (546 issues réussies, aucun
# timeout encore enregistré au 2026-07-25), le 5e percentile des durées
# réelles est ~32s — 30s reste juste sous ce seuil, assez bas pour ne jamais
# gêner une issue légitimement courte, assez haut pour éviter qu'une suite de
# quelques échantillons atypiques (issues de 1-3s, probablement des échecs
# immédiats) ne fasse suggérer un TIMEOUT dérisoire pour une combinaison encore
# peu observée.
TIMEOUT_SUGGERE_PLANCHER    = 30

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

# Backoff (secondes) entre les tentatives du COMMENTAIRE DE RÉSULTAT (issue #195).
# Contrairement à l'ACK et au message d'échec (best-effort), la trace du résultat
# est critique : sans elle, fermer l'issue effacerait silencieusement le travail.
# 1 tentative initiale + 3 tentatives espacées de 5, 10 puis 20 s.
DELAIS_RETRY_RESULTAT = (5, 10, 20)

# Marqueur non ambigu identifiant un commentaire de RÉSULTAT posté par le
# watcher (issue #237). Ligne HTML invisible sur GitHub, placée en tête du
# commentaire. Remplace le repérage par sous-chaîne "## Résultat", qui matchait
# aussi "## Résultat attendu" (titre de section présent dans quasi toutes les
# issues) — un faux positif aurait fermé une issue sans rien traiter si ce
# texte apparaissait un jour dans un commentaire.
MARQUEUR_RESULTAT = "<!-- bridge:resultat -->"

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
    delai_inactivite_min: int = 20  # auto-extinction : minutes sans aucune issue traitable avant que le watcher ne s'arrête proprement (issue #200). 0 = désactivé (le watcher tourne indéfiniment, comportement historique).

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
        delai_inactivite_min = entier("DELAI_INACTIVITE_MIN", 20),
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

def issue_traitable(issue: dict) -> bool:
    """Vrai si l'issue déclenchera un vrai travail ce cycle : ni déjà 'done'
    (finalisation de fermeture seulement, issue #195), ni 'needs-human' (échec
    définitif, ignorée jusqu'à intervention humaine). Sert de définition de
    l'« activité » pour l'auto-extinction (issue #200) : une issue bloquée en
    needs-human ne doit jamais empêcher l'extinction de se déclencher. On se
    fonde uniquement sur les labels (pas d'appel réseau supplémentaire par
    issue) ; le cas 'résultat déjà posté sans label done' reste rare et sera de
    toute façon traité idempotemment par traiter_issue()."""
    labels = [l.get("name", "") for l in issue.get("labels", [])]
    return LABEL_ECHEC not in labels and LABEL_FAIT not in labels

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


# ─── Consignes à trois couches injectées dans le prompt CCL (issues #209/#211) ──
# Auparavant (#209) ces consignes étaient injectées dans le CORPS de l'issue par
# app/issues.py::_consignes_injectees, uniquement pour les issues créées via le
# formulaire web. #211 déplace la logique ICI, dans le point d'assemblage unique
# du prompt CCL (lancer_claude), pour couvrir AUSSI les issues créées hors
# formulaire (`gh issue create` par un chef §14, création manuelle GitHub §3).

def _lire_consigne(chemin: Path) -> str | None:
    """Contenu texte d'un fichier de consignes (strippé), ou None s'il est absent
    ou illisible. Best-effort : un fichier manquant n'est pas une erreur ici (les
    couches type/projet sont facultatives), c'est l'appelant qui décide s'il faut
    logger l'absence (cas de globales.md uniquement)."""
    try:
        if chemin.is_file():
            texte = chemin.read_text(encoding="utf-8").strip()
            return texte or None
    except OSError:
        pass
    return None


def _consignes_injectees(nom_projet: str, titre: str, corps: str) -> str:
    """Bloc de consignes à trois couches à injecter dans le prompt CCL (issue #211,
    logique reprise de #209).

    Ordre : globales → type (si présent) → projet (si présent). Chaîne vide si
    aucune couche n'a de contenu. Garde-fous (identiques à #209) :
      - globales.md manquant → log.warning clair, mais on N'échoue PAS (le reste
        de l'injection et le traitement de l'issue se poursuivent) ;
      - type_<type>.md / projet_<projet>.md absents → comportement NORMAL, aucune
        injection pour cette couche, sans log ni avertissement bruyant.

    Le TYPE est déduit via deduire_type_issue sur le titre ET le corps RÉELS de
    l'issue traitée — peu importe qui l'a créée (formulaire, chef en CLI, GitHub) —
    donc le nom de fichier attendu est consignes/type_<type>.md (ex. type_chef.md).
    Le projet est celui piloté par ce watcher (CFG.nom)."""
    blocs = []

    # 1. Couche globale — NON-optionnelle (rappels de sécurité transversaux).
    globales = _lire_consigne(DOSSIER_CONSIGNES / "globales.md")
    if globales:
        blocs.append(globales)
    else:
        log.warning(
            "consignes/globales.md introuvable (%s) : consignes globales non "
            "injectées dans le prompt CCL — traitement poursuivi malgré tout.",
            DOSSIER_CONSIGNES / "globales.md",
        )

    # 2. Couche par TYPE — facultative. deduire_type_issue renvoie toujours une
    # valeur (repli « normal ») ; on n'injecte que si le fichier correspondant
    # existe réellement, donc « normal » (sans type_normal.md) n'injecte rien.
    type_issue = deduire_type_issue(titre, corps)
    if type_issue:
        consigne_type = _lire_consigne(DOSSIER_CONSIGNES / f"type_{type_issue}.md")
        if consigne_type:
            blocs.append(consigne_type)

    # 3. Couche par projet — facultative (aucun fichier créé par défaut, #209).
    if nom_projet:
        consigne_projet = _lire_consigne(DOSSIER_CONSIGNES / f"projet_{nom_projet}.md")
        if consigne_projet:
            blocs.append(consigne_projet)

    return "\n\n".join(blocs)


def _compter_etapes_checklist(body: str) -> int | None:
    """Nombre d'items de checklist Markdown (`- [ ]` / `- [x]`) dans le corps de
    l'issue (issue #220, champ nb_etapes_checklist), ou None si aucune checklist
    n'est présente — valeur brute, aucune interprétation de ce que représentent
    ces items."""
    n = sum(1 for ligne in (body or "").splitlines()
            if re.match(r"\s*[-*]\s*\[[ xX]\]", ligne))
    return n or None


def _detecter_tag_reseau(body: str) -> bool | None:
    """Déduit tag_reseau depuis un marqueur explicite de l'en-tête (issue #220).

    Aucun champ de ce type n'existe aujourd'hui dans le format d'en-tête bridge
    (§6 du DOC : SOURCE/DEST/RETOUR/MODE/PRIORITE/TIMEOUT/PROJET/TYPE/MODELE/
    FICHIER_CONTEXTE/SUITE_DE — pas de champ réseau). On ne fabrique donc PAS de
    détection ici (pas de mot-clé deviné dans le corps) : ceci renvoie toujours
    None pour l'instant, en attendant qu'un futur champ d'en-tête dédié soit
    ajouté par Claude Chat à la rédaction des issues. enregistrer_duree omet la
    clé tag_reseau de l'entrée tant que cette fonction renvoie None."""
    return None


def enregistrer_duree(projet: str, type_issue: str, mode: str,
                      duree_s: float | None, date_iso: str, *,
                      body: str = "", nb_projets_actifs: int = 0,
                      expiree: bool = False):
    """Ajoute une mesure de durée réelle (ACK → fermeture, ou ACK → timeout si
    expiree=True) à l'historique commun (issue #108, étendu #220). Best-effort :
    toute erreur est journalisée sans jamais interrompre le traitement de
    l'issue. Le fichier est une liste JSON d'objets ; issue #220 étend chaque
    entrée avec des champs BRUTS (aucune tranche/catégorisation) en préparation
    d'une future calibration automatique du TIMEOUT : longueur_corps_issue,
    nb_etapes_checklist, nb_fichiers_cibles (toujours None ici — pas de
    convention fiable pour lister les fichiers cibles dans un corps libre,
    mieux vaut None qu'une extraction fragile par regex), nb_projets_actifs_au_
    lancement, expiree, et tag_reseau (omis tant qu'aucun marqueur explicite
    n'existe, cf. _detecter_tag_reseau)."""
    try:
        DOSSIER_LOGS.mkdir(parents=True, exist_ok=True)
        historique = []
        if FICHIER_HISTORIQUE.exists():
            try:
                historique = json.loads(FICHIER_HISTORIQUE.read_text(encoding="utf-8")) or []
            except (json.JSONDecodeError, OSError):
                historique = []   # fichier corrompu : on repart d'une liste vide
        entree = {
            "projet": projet,
            "type":   type_issue,
            "mode":   mode,
            "duree":  round(duree_s) if duree_s is not None else None,   # secondes
            "date":   date_iso,
            "longueur_corps_issue": len(body or ""),
            "nb_etapes_checklist": _compter_etapes_checklist(body),
            "nb_fichiers_cibles": None,
            "nb_projets_actifs_au_lancement": nb_projets_actifs,
            "expiree": expiree,
        }
        tag_reseau = _detecter_tag_reseau(body)
        if tag_reseau is not None:
            entree["tag_reseau"] = tag_reseau
        historique.append(entree)
        FICHIER_HISTORIQUE.write_text(
            json.dumps(historique, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        log.error(f"Erreur enregistrement historique durée : {e}")


# ─── Calibration automatique du TIMEOUT — mécanique EWMA (issue #221) ──────────
# Fichiers d'état partagés par tous les process watcher (voir constantes en tête
# de fichier). Deux garde-fous communs :
#   - lecture/écriture protégées par un verrou fichier court + écriture atomique
#     (tempfile + os.replace) : plusieurs watchers de projets différents peuvent
#     clore une issue quasi simultanément, AUCUN écrasement concurrent ne doit
#     corrompre l'état ;
#   - best-effort intégral : toute erreur est journalisée sans jamais faire
#     échouer le traitement de l'issue (même contrat que enregistrer_duree).

VERROU_ETAT_PEREMPTION = 30  # secondes — la section critique (lecture JSON + calcul + écriture) dure quelques ms ; au-delà, verrou orphelin (process tué)


def _verrou_etat(chemin_etat: Path) -> Path:
    return chemin_etat.with_name(chemin_etat.name + ".lock")


def _acquerir_verrou_etat(chemin_etat: Path, essais: int = 50, attente_s: float = 0.1) -> bool:
    """Verrou court par création atomique O_CREAT|O_EXCL (portable, même
    mécanisme que acquerir_verrou pour les répertoires de travail — mais durée
    de rétention bien plus courte, cf. VERROU_ETAT_PEREMPTION). Attente active
    bornée (5s max par défaut) : la section critique est toujours brève, pas de
    raison de faire attendre le cycle du watcher longtemps."""
    verrou = _verrou_etat(chemin_etat)
    for _ in range(essais):
        try:
            chemin_etat.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(str(verrou), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            os.close(fd)
            return True
        except FileExistsError:
            try:
                age = time.time() - verrou.stat().st_mtime
            except OSError:
                age = None
            if age is not None and age > VERROU_ETAT_PEREMPTION:
                try:
                    verrou.unlink()
                except OSError:
                    pass
                continue
            time.sleep(attente_s)
        except OSError as e:
            log.warning(f"Verrou d'état {verrou} inobtenable ({e}).")
            return False
    return False


def _liberer_verrou_etat(chemin_etat: Path):
    try:
        _verrou_etat(chemin_etat).unlink()
    except FileNotFoundError:
        pass
    except OSError as e:
        log.warning(f"Libération du verrou d'état {chemin_etat} impossible ({e}).")


def _lire_json_best_effort(chemin: Path) -> dict:
    if not chemin.exists():
        return {}
    try:
        return json.loads(chemin.read_text(encoding="utf-8")) or {}
    except (json.JSONDecodeError, OSError):
        return {}   # fichier absent/corrompu : on repart d'un état vide


def _ecrire_json_atomique(chemin: Path, donnees: dict):
    chemin.parent.mkdir(parents=True, exist_ok=True)
    tmp = chemin.with_name(chemin.name + f".tmp{os.getpid()}")
    tmp.write_text(json.dumps(donnees, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, chemin)   # atomique sur un même système de fichiers (POSIX et Windows)


def _maj_etat_json(chemin: Path, fonction_maj):
    """Lecture-modification-écriture protégée d'un fichier d'état JSON partagé.
    `fonction_maj(donnees)` reçoit le dict courant (vide si absent/corrompu) et
    le modifie en place ; sa valeur de retour, si non None, remplace `donnees`
    avant l'écriture atomique. Verrou non obtenu ou exception : la mise à jour
    est abandonnée pour ce cycle (journalisée), jamais propagée à l'appelant."""
    if not _acquerir_verrou_etat(chemin):
        log.warning(f"Verrou d'état {chemin.name} non obtenu — mise à jour ignorée pour ce cycle.")
        return
    try:
        donnees = _lire_json_best_effort(chemin)
        resultat = fonction_maj(donnees)
        _ecrire_json_atomique(chemin, resultat if resultat is not None else donnees)
    except Exception as e:
        log.error(f"Erreur mise à jour état {chemin.name} : {e}")
    finally:
        _liberer_verrou_etat(chemin)


def _ewma_maj(valeur_precedente: float | None, nouvelle_valeur: float, alpha: float) -> float:
    """EWMA classique à alpha fixe (mise à jour PAR ISSUE, pas temporelle).
    Sans valeur précédente, la série démarre à la première observation."""
    if valeur_precedente is None:
        return nouvelle_valeur
    return alpha * nouvelle_valeur + (1 - alpha) * valeur_precedente


def _alpha_temporel(delta_heures: float, demi_vie_heures: float) -> float:
    """Poids de la nouvelle observation pour une EWMA à demi-vie TEMPORELLE
    (issue #221, F_reseau/F_local) : plus l'écart depuis la dernière mise à
    jour est grand, plus l'ancienne valeur est oubliée. delta_heures <= 0
    (observations quasi simultanées, ou horloge en recul) : traité comme une
    observation fraîche (alpha = 1), plutôt que de produire un poids négatif
    ou nul incohérent."""
    if delta_heures <= 0:
        return 1.0
    return 1 - 0.5 ** (delta_heures / demi_vie_heures)


def _cle_combinaison(projet: str, type_issue: str, mode: str) -> str:
    return f"{projet}|{type_issue}|{mode}"


def _maj_combinaison_timeout(donnees: dict, cle: str, *, duree_s: float,
                              timeout_courant: int, expiree: bool) -> tuple[float | None, dict]:
    """Met à jour, DANS `donnees` (le dict complet d'etat_timeout.json), l'entrée
    de la combinaison `cle`. Retourne (duree_typique_AVANT_maj, etat_APRES_maj).

    Sur timeout (expiree=True) : multiplicateur_backoff *= FACTEUR_BACKOFF
    immédiatement, compteur de succès rapides consécutifs remis à zéro. AUCUNE
    mise à jour de duree_typique/variabilite (ces EWMA ne portent que sur les
    issues RÉUSSIES, cf. §1 de l'issue #221 — un timeout ne mesure pas une
    durée réelle de traitement, seulement le plafond atteint).

    Sur succès (expiree=False) : variabilite d'abord (écart absolu à
    duree_typique AVANT cette observation, sinon la mise à jour de
    duree_typique fausserait l'écart mesuré), puis duree_typique. Si la durée
    réelle est < SEUIL_SUCCES_RAPIDE × timeout_courant, incrémente le compteur
    de succès rapides consécutifs ; au bout de SUCCES_RAPIDES_POUR_RESET,
    réinitialise le backoff à 1.0. Un succès non « rapide » remet le compteur à
    zéro sans toucher au backoff lui-même."""
    combinaisons = donnees.setdefault("combinaisons", {})
    etat = combinaisons.setdefault(cle, {
        "duree_typique": None,
        "variabilite": None,
        "multiplicateur_backoff": 1.0,
        "succes_rapides_consecutifs": 0,
        "n_observations": 0,
    })

    duree_typique_avant = etat.get("duree_typique")

    if expiree:
        etat["multiplicateur_backoff"] = etat.get("multiplicateur_backoff", 1.0) * FACTEUR_BACKOFF
        etat["succes_rapides_consecutifs"] = 0
    else:
        ecart = abs(duree_s - duree_typique_avant) if duree_typique_avant is not None else 0.0
        etat["variabilite"] = _ewma_maj(etat.get("variabilite"), ecart, ALPHA_EWMA_ISSUES)
        etat["duree_typique"] = _ewma_maj(duree_typique_avant, duree_s, ALPHA_EWMA_ISSUES)
        etat["n_observations"] = etat.get("n_observations", 0) + 1

        if timeout_courant and duree_s < SEUIL_SUCCES_RAPIDE * timeout_courant:
            etat["succes_rapides_consecutifs"] = etat.get("succes_rapides_consecutifs", 0) + 1
            if etat["succes_rapides_consecutifs"] >= SUCCES_RAPIDES_POUR_RESET:
                etat["multiplicateur_backoff"] = 1.0
                etat["succes_rapides_consecutifs"] = 0
        else:
            etat["succes_rapides_consecutifs"] = 0

    return duree_typique_avant, etat


def _maj_ambiance(donnees: dict, cle_f: str, ratio: float, date_iso: str):
    """Met à jour (dans `donnees`, le dict complet d'etat_ambiance.json) l'EWMA
    à demi-vie temporelle de `cle_f` ('F_reseau' ou 'F_local') avec la nouvelle
    observation `ratio`. Sans horodatage précédent exploitable, la série
    démarre à `ratio` (alpha effectif = 1)."""
    bloc = donnees.setdefault(cle_f, {"valeur_ewma": None, "derniere_maj": None})
    delta_h = None
    if bloc.get("valeur_ewma") is not None and bloc.get("derniere_maj"):
        try:
            avant = datetime.fromisoformat(bloc["derniere_maj"])
            maintenant = datetime.fromisoformat(date_iso)
            delta_h = (maintenant - avant).total_seconds() / 3600
        except (ValueError, TypeError):
            delta_h = None
    if delta_h is None:
        bloc["valeur_ewma"] = ratio
    else:
        alpha = _alpha_temporel(delta_h, DEMI_VIE_AMBIANCE_HEURES)
        bloc["valeur_ewma"] = alpha * ratio + (1 - alpha) * bloc["valeur_ewma"]
    bloc["derniere_maj"] = date_iso


def maj_calibration_timeout(*, projet: str, type_issue: str, mode: str,
                            duree_s: float, timeout_courant: int, expiree: bool,
                            body: str, date_iso: str) -> float | None:
    """Point d'entrée de la calibration automatique du TIMEOUT (issue #221),
    appelé après CHAQUE clôture d'issue (succès ou timeout), au même site que
    enregistrer_duree. Met à jour etat_timeout.json (combinaison projet/TYPE/
    mode) et, sur succès avec tag_reseau connu, etat_ambiance.json (F_reseau/
    F_local, global à tous les projets). Journalise et retourne le
    TIMEOUT_suggéré (secondes, plancher appliqué) pour cette combinaison, ou
    None si le calcul n'a pas pu aboutir (verrou d'état non obtenu, ou aucune
    observation de succès encore enregistrée pour cette combinaison).

    N'APPLIQUE RIEN au comportement d'exécution actuel : le TIMEOUT réellement
    utilisé pour lancer claude reste exclusivement celui de extraire_timeout()
    — cette fonction ne fait que calculer et journaliser."""
    cle = _cle_combinaison(projet, type_issue, mode)
    capture = {}

    def _maj_timeout(donnees):
        duree_typique_avant, etat = _maj_combinaison_timeout(
            donnees, cle, duree_s=duree_s, timeout_courant=timeout_courant, expiree=expiree)
        capture["duree_typique_avant"] = duree_typique_avant
        capture["etat"] = dict(etat)
        return donnees

    _maj_etat_json(FICHIER_ETAT_TIMEOUT, _maj_timeout)

    etat = capture.get("etat")
    if etat is None:
        log.warning(f"Calibration TIMEOUT [{cle}] : état inobtenable ce cycle — TIMEOUT_suggéré non calculé.")
        return None

    # F n'est alimenté QUE par les succès (comme duree_typique, §1 de l'issue) :
    # un timeout est plafonné à la valeur configurée, pas une mesure de la durée
    # réelle nécessaire — l'inclure biaiserait F vers le haut artificiellement.
    # Et seulement si tag_reseau est explicitement connu (jamais deviné, §2).
    tag_reseau = _detecter_tag_reseau(body)
    duree_typique_avant = capture.get("duree_typique_avant")
    if not expiree and tag_reseau is not None and duree_typique_avant:
        ratio = duree_s / duree_typique_avant
        cle_f = "F_reseau" if tag_reseau else "F_local"

        def _maj_f(donnees, cle_f=cle_f, ratio=ratio):
            _maj_ambiance(donnees, cle_f, ratio, date_iso)
            return donnees

        _maj_etat_json(FICHIER_ETAT_AMBIANCE, _maj_f)

    duree_typique = etat.get("duree_typique")
    if duree_typique is None:
        log.info(f"Calibration TIMEOUT [{cle}] : aucun succès encore enregistré — TIMEOUT_suggéré non calculable.")
        return None

    # F_pertinent pour la SUGGESTION : F_reseau si CETTE issue est taguée réseau,
    # F_local sinon (par défaut en l'absence de tag — hypothèse la moins
    # généreuse). Lecture indépendante de la mise à jour ci-dessus : même une
    # observation qui n'a pas pu alimenter F (tag inconnu) doit pouvoir lire le
    # F déjà établi par d'autres observations.
    ambiance = _lire_json_best_effort(FICHIER_ETAT_AMBIANCE)
    cle_f_lecture = "F_reseau" if tag_reseau else "F_local"
    f_brut = (ambiance.get(cle_f_lecture) or {}).get("valeur_ewma")
    f_pertinent = max(1.0, f_brut) if f_brut is not None else 1.0   # plancher F >= 1.0 : n'allonge jamais, ne raccourcit jamais

    variabilite = etat.get("variabilite") or 0.0
    backoff = etat.get("multiplicateur_backoff", 1.0)
    suggere = max((duree_typique + K_VARIABILITE * variabilite) * f_pertinent * backoff,
                  TIMEOUT_SUGGERE_PLANCHER)

    log.info(
        f"Calibration TIMEOUT [{cle}] : duree_typique={duree_typique:.1f}s "
        f"variabilite={variabilite:.1f}s F({cle_f_lecture})={f_pertinent:.3f} "
        f"backoff={backoff:.3f} → TIMEOUT_suggéré={suggere:.0f}s"
        + (" [issue expirée]" if expiree else "")
    )
    return suggere


def lire_timeout_suggere(projet: str, type_issue: str, mode: str) -> float | None:
    """Lit (sans écrire ni verrouiller) le TIMEOUT_suggéré actuellement en
    vigueur pour la combinaison (projet, TYPE, mode), à partir de l'état déjà
    persisté par maj_calibration_timeout (issue #221).

    Sert au commentaire de clôture d'une issue en ÉCHEC définitif (issue
    #222) : contrairement au cas succès, l'appel à maj_calibration_timeout
    pour CET échec a déjà eu lieu (une fois par tentative expirée, dans la
    boucle de retry) — le rappeler ici biaiserait l'EWMA en comptant deux
    fois la même observation. Une simple lecture de l'état déjà à jour suffit.
    Best-effort : retourne None si l'état est illisible ou si aucun succès n'a
    encore été enregistré pour cette combinaison (mêmes conditions que
    maj_calibration_timeout)."""
    try:
        cle = _cle_combinaison(projet, type_issue, mode)
        combo = _lire_json_best_effort(FICHIER_ETAT_TIMEOUT).get(cle)
        if not combo:
            return None
        duree_typique = combo.get("duree_typique")
        if duree_typique is None:
            return None
        variabilite = combo.get("variabilite") or 0.0
        backoff = combo.get("multiplicateur_backoff", 1.0)

        # F_local par défaut (hypothèse la moins généreuse) : cette lecture
        # est hors contexte d'une issue précise, donc sans tag_reseau connu —
        # même choix par défaut que maj_calibration_timeout en l'absence de tag.
        f_brut = (_lire_json_best_effort(FICHIER_ETAT_AMBIANCE).get("F_local") or {}).get("valeur_ewma")
        f_pertinent = max(1.0, f_brut) if f_brut is not None else 1.0

        return max((duree_typique + K_VARIABILITE * variabilite) * f_pertinent * backoff,
                    TIMEOUT_SUGGERE_PLANCHER)
    except Exception as e:
        log.warning(f"Lecture TIMEOUT_suggéré [{projet}/{type_issue}/{mode}] impossible : {e}")
        return None


def formater_bloc_calibration(duree_s: float, timeout_courant: int, suggere: float | None) -> str:
    """Bloc lisible à ajouter au commentaire de clôture GitHub d'une issue
    (issue #222) : durée réelle de traitement et TIMEOUT_suggéré calculé par
    la calibration automatique (issue #221).

    Seul canal fiable pour transmettre cette information calculée localement
    à Claude Chat, qui n'a pas accès direct aux fichiers d'état du ThinkPad
    (etat_timeout.json, etat_ambiance.json, historique_durees.json — tous
    gitignorés)."""
    bloc = f"\n\n---\n⏱️ Durée réelle : {duree_s:.0f}s (TIMEOUT courant : {timeout_courant}s)"
    if suggere is not None:
        bloc += f"\n📊 TIMEOUT_suggéré (calibration automatique, issue #221) : {suggere:.0f}s"
    return bloc


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


def _compter_watchers_actifs() -> int:
    """Nombre de watchers actuellement en cours d'exécution, tous projets
    confondus (issue #220, champ nb_projets_actifs_au_lancement de l'historique
    des durées). Réutilise les mêmes fichiers PID (logs/watcher-<nom>.pid, §13 du
    DOC) que detecter_conflit_watcher, plutôt qu'un scan brut du dossier logs/."""
    return sum(1 for cfg in _lister_projets_connus() if _watcher_actif(cfg))


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

def commenter_issue(numero: int, message: str) -> bool:
    """Poste un commentaire sur une issue.

    Retourne True si `gh` a réussi (returncode 0), False sinon. Avant issue #195
    le code de retour n'était jamais inspecté : `subprocess.run` retourne
    normalement même sur exit non-zéro, donc un échec réseau intermittent de
    `gh issue comment` restait silencieux côté Python.

    Passe le message via `--body-file` (fichier temporaire UTF-8) plutôt que
    `--body <message>` (issue #237) : sous Windows la ligne de commande est
    plafonnée à 32767 caractères, dépassés par un rapport de build
    multi-étapes — `gh` retournait alors un exit code 0 sans avoir rien posté
    (troncature silencieuse en amont). `--body-file` supprime aussi tout
    problème d'échappement de shell."""
    fichier_tmp = None
    try:
        with tempfile.NamedTemporaryFile(
                mode="w", suffix=".md", delete=False,
                encoding="utf-8") as f:
            f.write(message)
            fichier_tmp = f.name
        res = subprocess.run(
            ["gh", "issue", "comment", str(numero),
             "--repo", CFG.depot,
             "--body-file", fichier_tmp],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=30
        )
        if res.returncode != 0:
            log.error(f"Erreur commentaire issue #{numero} (code {res.returncode}) : {res.stderr.strip()}")
            return False
        return True
    except Exception as e:
        log.error(f"Erreur commentaire issue #{numero} : {e}")
        return False
    finally:
        if fichier_tmp:
            try:
                Path(fichier_tmp).unlink(missing_ok=True)
            except OSError:
                pass

def editer_dernier_commentaire(numero: int, message: str) -> bool:
    """Édite le dernier commentaire posté par le watcher sur l'issue
    (`gh issue comment --edit-last`), au lieu d'en poster un nouveau.

    Sert à enrichir le commentaire de résultat déjà posté avec le bloc de
    calibration TIMEOUT (issue #222) : la durée réelle et le TIMEOUT_suggéré
    ne sont connus qu'APRÈS la fermeture de l'issue (maj_calibration_timeout
    a besoin de duree_reelle), donc après le premier `commenter_resultat_avec_
    retry`. Best-effort : un échec ici n'affecte ni la clôture déjà effectuée
    ni le commentaire déjà en place (juste privé de son bloc calibration).

    Passe le message via `--body-file` pour la même raison que
    `commenter_issue` (issue #237)."""
    fichier_tmp = None
    try:
        with tempfile.NamedTemporaryFile(
                mode="w", suffix=".md", delete=False,
                encoding="utf-8") as f:
            f.write(message)
            fichier_tmp = f.name
        res = subprocess.run(
            ["gh", "issue", "comment", str(numero),
             "--repo", CFG.depot,
             "--edit-last",
             "--body-file", fichier_tmp],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=30
        )
        if res.returncode != 0:
            log.error(f"Erreur édition dernier commentaire issue #{numero} (code {res.returncode}) : {res.stderr.strip()}")
            return False
        return True
    except Exception as e:
        log.error(f"Erreur édition dernier commentaire issue #{numero} : {e}")
        return False
    finally:
        if fichier_tmp:
            try:
                Path(fichier_tmp).unlink(missing_ok=True)
            except OSError:
                pass

def _commentaire_marque_present(numero: int, marqueur: str = MARQUEUR_RESULTAT) -> bool:
    """Relit l'issue et indique si un commentaire portant `marqueur` est bien
    présent (issue #237). Sert à VÉRIFIER qu'un commentaire a réellement été
    créé plutôt que de faire confiance au seul code de retour de `gh` (celui-ci
    peut rendre 0 sans qu'aucun commentaire n'existe, cf. issue #236).

    En cas d'erreur de lecture, retourne False (on ne peut pas confirmer la
    présence => la tentative est traitée comme un échec, quitte à reposter)."""
    try:
        res = subprocess.run(
            ["gh", "issue", "view", str(numero),
             "--repo", CFG.depot,
             "--json", "comments"],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=30
        )
        if res.returncode != 0:
            log.error(f"Erreur lecture commentaires issue #{numero} (code {res.returncode}) : {res.stderr.strip()}")
            return False
        data = json.loads(res.stdout or "{}")
        return any(marqueur in (c.get("body") or "")
                   for c in data.get("comments", []))
    except Exception as e:
        log.error(f"Erreur vérification présence commentaire issue #{numero} : {e}")
        return False

def commenter_resultat_avec_retry(numero: int, message: str) -> bool:
    """Poste le commentaire de RÉSULTAT avec retry/backoff (issue #195).

    1 tentative initiale, puis jusqu'à 3 tentatives espacées de 5, 10 puis 20 s
    (DELAIS_RETRY_RESULTAT). Retourne True dès qu'une tentative réussit, False si
    toutes échouent. Réservé au commentaire de résultat : l'ACK et le message
    d'échec restent best-effort sans retry.

    VÉRIFICATION post-publication (issue #236/#237) : un exit code 0 de `gh`
    ne suffit plus à conclure au succès — l'incident #236 a montré un
    commentaire jamais créé malgré un code de retour 0 (dépassement de la
    limite argv Windows, cf. `commenter_issue`). Après chaque tentative
    rendant 0, on relit l'issue et on exige la présence effective du
    commentaire (marqueur `MARQUEUR_RESULTAT`, ajouté par l'appelant en tête
    de `message`) avant de retourner True. Si la relecture ne le trouve pas,
    la tentative est traitée comme un échec et on enchaîne sur la suivante."""
    def _tentative() -> bool:
        if not commenter_issue(numero, message):
            return False
        if not _commentaire_marque_present(numero):
            log.error(
                f"  Commentaire de résultat #{numero} : `gh` a rendu 0 mais aucun "
                f"commentaire correspondant n'a été retrouvé à la relecture — "
                f"traité comme un échec (issue #236)."
            )
            return False
        return True

    if _tentative():
        return True
    for delai in DELAIS_RETRY_RESULTAT:
        log.warning(f"  Commentaire de résultat #{numero} échoué — nouvelle tentative dans {delai}s.")
        time.sleep(delai)
        if _tentative():
            return True
    log.error(f"  Commentaire de résultat #{numero} échoué après {1 + len(DELAIS_RETRY_RESULTAT)} tentatives.")
    return False

def resultat_deja_poste(numero: int) -> bool:
    """Garde d'idempotence (issue #195) : indique si l'issue porte déjà un
    commentaire de résultat posté par le watcher.

    Repère le commentaire par `MARQUEUR_RESULTAT` (issue #237), une ligne HTML
    invisible ajoutée en tête du message de résultat — et non plus par la
    sous-chaîne "## Résultat", qui matchait aussi "## Résultat attendu" (titre
    de section présent dans quasi toutes nos issues) : si ce texte atterrissait
    un jour dans un commentaire, l'ancienne garde fermait l'issue sans rien
    traiter.

    Sert à éviter un retraitement complet à tort si l'issue est reprise alors
    qu'un cycle précédent avait réussi le commentaire mais échoué la fermeture
    (coupure réseau entre `comment` et `close`). En cas d'erreur de lecture, on
    retourne False (comportement historique : on retraite) plutôt que de risquer
    de sauter à tort une issue réellement non traitée."""
    return _commentaire_marque_present(numero)

def fermer_issue(numero: int) -> bool:
    """Ferme une issue et ajoute le label 'done'.

    Retourne True seulement si les DEUX sous-commandes (`close` puis
    `add-label`) ont réussi (issue #238, sur le modèle de `commenter_issue`
    depuis #195) : avant #238 aucun des deux codes de retour n'était
    inspecté, si bien qu'une issue pouvait être fermée sans recevoir le
    label 'done', ou le recevoir sans être fermée, en silence complet — deux
    états incohérents ensuite mal interprétés par la garde d'idempotence
    (LABEL_FAIT / resultat_deja_poste en tête de `traiter_issue`) et par
    l'interface web.

    Les deux sous-commandes sont tentées inconditionnellement (comme avant
    #238), pour ne pas transformer un échec de `close` en un label manquant
    évitable. Aucune compensation automatique en cas d'échec partiel : on se
    contente de journaliser l'état incohérent obtenu, pour diagnostic."""
    try:
        res_close = subprocess.run(
            ["gh", "issue", "close", str(numero), "--repo", CFG.depot],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=30
        )
        close_ok = res_close.returncode == 0
        if not close_ok:
            log.error(f"Erreur fermeture issue #{numero} (code {res_close.returncode}) : {res_close.stderr.strip()}")

        res_label = subprocess.run(
            ["gh", "issue", "edit", str(numero),
             "--repo", CFG.depot,
             "--add-label", LABEL_FAIT],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=30
        )
        label_ok = res_label.returncode == 0
        if not label_ok:
            log.error(f"Erreur ajout label '{LABEL_FAIT}' sur issue #{numero} (code {res_label.returncode}) : {res_label.stderr.strip()}")

        if close_ok and not label_ok:
            log.error(f"  État incohérent issue #{numero} : FERMÉE mais SANS le label '{LABEL_FAIT}' (pas de compensation automatique).")
        elif label_ok and not close_ok:
            log.error(f"  État incohérent issue #{numero} : label '{LABEL_FAIT}' posé mais issue NON fermée (pas de compensation automatique).")

        return close_ok and label_ok
    except Exception as e:
        log.error(f"Erreur fermeture issue #{numero} : {e}")
        return False

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

    # Consignes à trois couches (globales/type/projet) injectées dans le prompt
    # CCL (issue #211). Placées APRÈS le bloc CONTEXTE et AVANT la clause de
    # périmètre / le garde-fou : choix assumé de regrouper toutes les « règles »
    # (consignes de sécurité globales, spécificités de type/projet, périmètre,
    # garde-fou mode écriture) en fin de prompt, zone la mieux suivie par le
    # modèle. Couverture universelle : quel que soit le chemin de création de
    # l'issue (formulaire web, `gh issue create` d'un chef, création manuelle
    # GitHub), le point de passage unique reste ce prompt. Mêmes garde-fous que
    # #209 (globales.md manquant → warning sans bloquer ; type/projet absents →
    # silencieux) — voir _consignes_injectees.
    bloc_consignes = ""
    consignes = _consignes_injectees(CFG.nom, titre, body)
    if consignes:
        bloc_consignes = f"\nCONSIGNES (injectées automatiquement) :\n---\n{consignes}\n---\n"

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
{bloc_contexte}{bloc_consignes}{clause_perimetre}{garde_fou}
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

    # Garde d'idempotence (issue #195). Une issue peut revenir ici OUVERTE alors
    # que son travail est déjà fait : un cycle précédent avait réussi le
    # commentaire de résultat mais échoué la fermeture (coupure réseau entre
    # `comment` et `close`), ou posé le label `done` sans réussir le `close`. On
    # NE relance PAS claude à tort (double exécution d'une tâche d'écriture) : on
    # se contente de re-tenter la fermeture, puis on rend la main.
    if LABEL_FAIT in labels or resultat_deja_poste(numero):
        log.info(f"  Issue #{numero} déjà traitée (résultat commenté) — finalisation de la fermeture, pas de retraitement.")
        if not fermer_issue(numero):
            log.warning(f"  Finalisation de la fermeture #{numero} toujours incomplète — nouvelle tentative au prochain cycle.")
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
        # Nombre de watchers actifs au lancement DE CETTE ISSUE (issue #220, champ
        # nb_projets_actifs_au_lancement) — figé une fois pour toute la durée du
        # traitement (succès ou timeouts successifs), pas recalculé à chaque tentative.
        nb_projets_actifs_debut = _compter_watchers_actifs()

        tentative = 0
        while True:
            tentative += 1
            log.info(f"  Tentative {tentative}/{CFG.max_essais if not critique else '∞'}...")

            succes, sortie = lancer_claude(numero, titre, body, dry_run, autoriser_ecriture,
                                           timeout, modele,
                                           perimetre=perimetre_effectif, cwd=cwd_effectif)

            if succes:
                log.info(f"  ✓ Issue #{numero} traitée avec succès.")
                message_resultat = f"{MARQUEUR_RESULTAT}\n## Résultat\n\n{avertissement_conflit}{sortie}"
                # Le commentaire de résultat est critique (issue #195) : on le
                # poste avec retry/backoff et on ne ferme l'issue QUE s'il a réussi.
                if not commenter_resultat_avec_retry(numero, message_resultat):
                    # Échec réseau persistant : fermer l'issue effacerait
                    # silencieusement le travail. On la laisse OUVERTE (ni `close`
                    # ni label `done`) pour reprise au prochain cycle. La garde
                    # d'idempotence en tête de traiter_issue évitera de relancer
                    # claude à tort si un cycle ultérieur finit par poster le
                    # commentaire mais échoue encore la fermeture.
                    log.error(
                        f"  ✗ Commentaire de résultat #{numero} impossible après retries — "
                        f"issue laissée OUVERTE pour reprise (non fermée)."
                    )
                    notifier(
                        labels,
                        titre=f"⚠️ {CFG.nom} #{numero} — résultat non posté",
                        message=(f"'{titre}' traitée, mais le commentaire de résultat a échoué "
                                 f"(réseau). Issue laissée ouverte pour reprise au prochain cycle."),
                        urgence_bureau="critical",
                        priorite_ntfy="high",
                    )
                    issues_en_cours.discard(numero)
                    return
                if not fermer_issue(numero):
                    log.warning(f"  Fermeture de l'issue #{numero} incomplète (close/label) — sera retentée au prochain cycle via la garde d'idempotence.")
                issues_en_cours.discard(numero)
                # Historique des durées (issue #108) : durée réelle ACK → fermeture,
                # catégorisée par projet/type/mode, pour l'estimation prédictive.
                type_issue_close = deduire_type_issue(titre, body)
                mode_close        = "write" if autoriser_ecriture else "read"
                duree_reelle      = time.monotonic() - debut_traitement
                date_iso_close    = datetime.now().isoformat(timespec="seconds")
                enregistrer_duree(
                    CFG.nom,
                    type_issue_close,
                    mode_close,
                    duree_reelle,
                    date_iso_close,
                    body=body,
                    nb_projets_actifs=nb_projets_actifs_debut,
                )
                # Calibration automatique du TIMEOUT (issue #221) : met à jour les
                # EWMA duree_typique/variabilite/backoff (par combinaison) et F
                # (global), puis journalise le TIMEOUT_suggéré — sans effet sur le
                # TIMEOUT réellement appliqué (extraire_timeout reste seul décisif).
                suggere = maj_calibration_timeout(
                    projet=CFG.nom,
                    type_issue=type_issue_close,
                    mode=mode_close,
                    duree_s=duree_reelle,
                    timeout_courant=timeout,
                    expiree=False,
                    body=body,
                    date_iso=date_iso_close,
                )
                # Exposition du TIMEOUT_suggéré dans le commentaire de clôture
                # GitHub (issue #222) : seul canal fiable pour transmettre cette
                # info calculée localement à Claude Chat (pas d'accès direct aux
                # fichiers d'état gitignorés du ThinkPad). Connue seulement APRÈS
                # la fermeture (dépend de duree_reelle) : on édite le commentaire
                # de résultat déjà posté (gh --edit-last) plutôt que d'en poster
                # un second. Best-effort — n'affecte pas la clôture déjà faite.
                if not editer_dernier_commentaire(
                        numero, message_resultat + formater_bloc_calibration(duree_reelle, timeout, suggere)):
                    log.warning(f"  Ajout du bloc calibration au commentaire #{numero} échoué (best-effort, non bloquant).")
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

            # Trace du timeout dans l'historique des durées (issue #220) : avant ce
            # correctif, une tentative expirée (subprocess.TimeoutExpired dans
            # lancer_claude, message "Timeout après <N>s") ne laissait AUCUNE trace
            # dans historique_durees.json — seulement dans le log texte du watcher.
            # Un enregistrement minimal (expiree=True) est ajouté ICI, PAR TENTATIVE
            # expirée (pas seulement à l'abandon définitif), pour permettre de
            # compter la fréquence réelle des timeouts dans une future issue — y
            # compris pour les issues critiques en retry infini, qui n'atteignent
            # jamais la branche d'abandon ci-dessous.
            if sortie.startswith("Timeout après"):
                type_issue_expire = deduire_type_issue(titre, body)
                mode_expire        = "write" if autoriser_ecriture else "read"
                duree_expiree      = time.monotonic() - debut_traitement
                date_iso_expire    = datetime.now().isoformat(timespec="seconds")
                enregistrer_duree(
                    CFG.nom,
                    type_issue_expire,
                    mode_expire,
                    duree_expiree,
                    date_iso_expire,
                    body=body,
                    nb_projets_actifs=nb_projets_actifs_debut,
                    expiree=True,
                )
                # Calibration automatique du TIMEOUT (issue #221) : sur timeout,
                # multiplicateur_backoff *= FACTEUR_BACKOFF immédiatement pour cette
                # combinaison (par tentative expirée, même logique que ci-dessus).
                maj_calibration_timeout(
                    projet=CFG.nom,
                    type_issue=type_issue_expire,
                    mode=mode_expire,
                    duree_s=duree_expiree,
                    timeout_courant=timeout,
                    expiree=True,
                    body=body,
                    date_iso=date_iso_expire,
                )

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
                    # Exposition du TIMEOUT_suggéré dans le commentaire de clôture
                    # GitHub, ici aussi côté échec (issue #222). Simple LECTURE de
                    # l'état (lire_timeout_suggere), pas un nouvel appel à
                    # maj_calibration_timeout : chaque tentative expirée l'a déjà
                    # mis à jour ci-dessus — le rappeler ici compterait deux fois la
                    # même observation dans l'EWMA.
                    type_issue_echec = deduire_type_issue(titre, body)
                    mode_echec        = "write" if autoriser_ecriture else "read"
                    duree_echec       = time.monotonic() - debut_traitement
                    suggere_echec     = lire_timeout_suggere(CFG.nom, type_issue_echec, mode_echec)
                    message_echec += formater_bloc_calibration(duree_echec, timeout, suggere_echec)
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

    if CFG.delai_inactivite_min > 0:
        log.info(f"Auto-extinction activée : arrêt après {CFG.delai_inactivite_min} min sans issue traitable.")
    else:
        log.info("Auto-extinction désactivée (DELAI_INACTIVITE_MIN = 0) — watcher permanent.")

    # Horloge monotone d'inactivité (issue #200). Initialisée AVANT la boucle
    # pour qu'un watcher fraîchement démarré ne s'éteigne pas au premier cycle,
    # puis réarmée à chaque cycle comportant au moins une issue traitable.
    derniere_activite = time.monotonic()

    while True:
        # Test d'inactivité en tête de cycle, AVANT lister_issues() et AVANT tout
        # traitement (issue #200). Rester dans la boucle synchrone garantit qu'un
        # cycle de retry en cours (ex. #183, jusqu'à ~20 min) n'est jamais
        # interrompu : on ne teste qu'entre deux cycles complets. delai 0 =
        # mécanisme désactivé.
        if CFG.delai_inactivite_min > 0:
            inactif_s = time.monotonic() - derniere_activite
            if inactif_s > CFG.delai_inactivite_min * 60:
                log.info(f"⏻ Auto-extinction : aucune issue traitable depuis "
                         f"{CFG.delai_inactivite_min} min — arrêt propre du watcher.")
                # Nettoyage du fichier PID, par cohérence avec arreter_watcher()
                # (app/watchers.py) : sans ça l'interface afficherait un PID
                # orphelin au lieu de « inactif ».
                pid_file = DOSSIER_LOGS / f"watcher-{CFG.nom}.pid"
                pid_file.unlink(missing_ok=True)
                sys.exit(0)

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
            # Activité = présence d'au moins une issue réellement traitable (ni
            # done, ni needs-human). On réarme AVANT le traitement : le cycle qui
            # suit ne testera l'inactivité qu'une fois ce traitement terminé, donc
            # un retry long n'est jamais interrompu (issue #200).
            travail_a_faire = any(issue_traitable(i) for i in issues)
            if travail_a_faire:
                derniere_activite = time.monotonic()
            if issues:
                log.info(f"{len(issues)} issue(s) en attente.")
                for issue in issues:
                    traiter_issue(issue, dry_run=args.dry_run)
            else:
                log.debug("Aucune issue en attente.")
            # Réarmement APRÈS traitement (issue #217). Le réarme d'avant-cycle
            # (ci-dessus) date le DÉBUT du travail, pas sa fin : le traitement
            # d'une (ou plusieurs) issue(s) peut s'étirer bien au-delà du délai
            # d'inactivité — plusieurs timeouts de 300s + retries en cascade, cf.
            # log watcher-scrabble 24/07/2026 : ~23 min pour une seule issue. Sans
            # ce second réarme, l'horloge resterait « périmée » (figée au début du
            # cycle) et le test d'extinction en tête du cycle SUIVANT se
            # déclencherait immédiatement après un travail réel qui vient tout
            # juste de se terminer (extinction ~14 s après un succès). On réarme
            # donc de nouveau ICI, avec l'instant réel de fin de traitement, dès
            # qu'au moins une issue traitable a été traitée ce cycle. L'extinction
            # reste possible quand plus rien n'est traitable (le flag est faux).
            if travail_a_faire:
                derniere_activite = time.monotonic()
        except KeyboardInterrupt:
            log.info("Watcher arrêté par l'utilisateur.")
            sys.exit(0)
        except Exception as e:
            log.error(f"Erreur boucle principale : {e}")

        time.sleep(intervalle)

if __name__ == "__main__":
    main()
