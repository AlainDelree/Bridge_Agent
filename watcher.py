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
from logging.handlers import RotatingFileHandler
from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime

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

# ─── Protocole partagé (identique pour TOUS les projets) ───────────────────────
# Ces noms de labels sont la logique commune du bridge. Les mettre en config
# permettrait à un projet de diverger et de casser le protocole — c'est
# exactement la dérive qu'on veut éviter. Ils restent donc en dur.
# Le NOM des constantes est en français ; la VALEUR (entre guillemets) est le
# label réel sur GitHub, un contrat qu'on ne touche pas.

LABEL_ECRITURE  = "mode_write"    # ARME le mode écriture (--dangerously-skip-permissions)
LABEL_ECHEC     = "needs-human"   # posé après échec définitif : stoppe le retraitement auto
LABEL_FAIT      = "done"          # posé au succès

# Labels de notification (opt-in, cumulatifs avec le bip).
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
    script_bip: Path      = field(default_factory=lambda: Path.home() / "NicLink" / "bip.py")
    log_taille_max_mo: int = 1     # rotation quand le journal dépasse cette taille (Mo)
    log_archives: int      = 5     # nombre d'archives datées conservées
    cmd_backup: str        = ""    # commande de sauvegarde avant modif (mode écriture)
    perimetre: str         = ""    # dossier(s) autorisés pour CCL (vide = pas de restriction)
    modele_ccl: str        = ""    # modèle CCL à utiliser (vide = défaut Claude Code)
    mot_de_passe: str      = ""    # hash sha256 du mot de passe d'accès web (vide = pas d'authentification)
    fichier_contexte: str  = ""    # fichier de contexte projet injecté dans le prompt (chemin relatif au rep_travail ou absolu ; vide = aucun)
    couleur: str           = ""    # couleur d'accent du projet dans l'interface (hex #RRGGBB ; vide = repli map fixe/hash côté frontend)

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
                      else Path.home() / "NicLink" / "bip.py",
        log_taille_max_mo = entier("LOG_TAILLE_MAX_MO", 1),
        log_archives      = entier("LOG_ARCHIVES", 5),
        cmd_backup        = brut.get("CMD_BACKUP", ""),
        perimetre         = brut.get("PERIMETRE", ""),
        modele_ccl        = brut.get("MODELE_CCL", ""),
        mot_de_passe      = brut.get("MOT_DE_PASSE", ""),
        fichier_contexte  = brut.get("FICHIER_CONTEXTE", ""),
        couleur           = brut.get("COULEUR", ""),
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


def configurer_logs(cfg: Config):
    cfg.fichier_log.parent.mkdir(parents=True, exist_ok=True)
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

def bip(fois=1):
    """Bip sonore via bip.py."""
    if CFG.script_bip.exists():
        for _ in range(fois):
            subprocess.run(["python3", str(CFG.script_bip)], capture_output=True)
            time.sleep(0.3)

def notifier_bureau(titre: str, message: str, urgence: str = "normal"):
    """Envoie une bulle de notification bureau via notify-send.
    urgence : 'low', 'normal', 'critical'. 'critical' reste affichée jusqu'à
    clic (utile pour les échecs)."""
    try:
        subprocess.run(
            ["notify-send", "-a", f"Bridge {CFG.nom}", "-u", urgence, titre, message],
            capture_output=True, timeout=5
        )
    except FileNotFoundError:
        log.warning("notify-send introuvable (paquet libnotify-bin non installé ?) — notification bureau ignorée.")
    except Exception as e:
        log.error(f"Erreur notify-send : {e}")

def notifier_ntfy(titre: str, message: str, priorite: str = "default"):
    """Envoie une notification push sur le topic ntfy (téléphone).
    priorite : 'min', 'low', 'default', 'high', 'urgent'."""
    try:
        subprocess.run(
            ["curl", "-s",
             "-H", f"Title: {titre}",
             "-H", f"Priority: {priorite}",
             "-H", "Tags: robot",
             "-d", message,
             CFG.url_ntfy],
            capture_output=True, timeout=10
        )
    except FileNotFoundError:
        log.warning("curl introuvable — notification ntfy ignorée.")
    except Exception as e:
        log.error(f"Erreur ntfy : {e}")

def notifier(labels: list[str], titre: str, message: str,
             urgence_bureau: str = "normal", priorite_ntfy: str = "default",
             fois_bip: int = 1):
    """Dispatch de notification selon les labels de l'issue.
    Le bip et les canaux additionnels (notify-send, ntfy) sont opt-in via les
    labels notif_pc / notif_gsm / notif_tous : sans aucun de ces labels, aucun
    signal n'est émis. fois_bip permet de renforcer le signal (ex. 3 pour une
    alerte critique)."""
    if LABEL_NOTIF_PC in labels or LABEL_NOTIF_GSM in labels or LABEL_NOTIF_TOUS in labels:
        bip(fois_bip)
    if LABEL_NOTIF_PC in labels or LABEL_NOTIF_TOUS in labels:
        notifier_bureau(titre, message, urgence_bureau)
    if LABEL_NOTIF_GSM in labels or LABEL_NOTIF_TOUS in labels:
        notifier_ntfy(titre, message, priorite_ntfy)

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
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if res.returncode != 0:
            log.error(f"gh erreur : {res.stderr.strip()}")
            return None
        return json.loads(res.stdout)
    except Exception as e:
        log.error(f"gh exception : {e}")
        return None

def lister_issues():
    """Retourne la liste des issues (label du projet) ouvertes."""
    try:
        res = subprocess.run(
            ["gh", "issue", "list",
             "--repo", CFG.depot,
             "--label", CFG.label,
             "--state", "open",
             "--json", "number,title,body,labels,createdAt"],
            capture_output=True, text=True, timeout=30
        )
        if res.returncode != 0:
            log.error(f"Erreur gh issue list : {res.stderr.strip()}")
            return []
        return json.loads(res.stdout)
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

def ajouter_label(numero: int, label: str):
    """Ajoute un label à une issue sans la fermer."""
    try:
        subprocess.run(
            ["gh", "issue", "edit", str(numero),
             "--repo", CFG.depot,
             "--add-label", label],
            capture_output=True, text=True, timeout=30
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
            capture_output=True, text=True, timeout=30
        )
    except Exception as e:
        log.error(f"Erreur commentaire issue #{numero} : {e}")

def fermer_issue(numero: int):
    """Ferme une issue et ajoute le label 'done'."""
    try:
        subprocess.run(
            ["gh", "issue", "close", str(numero), "--repo", CFG.depot],
            capture_output=True, text=True, timeout=30
        )
        subprocess.run(
            ["gh", "issue", "edit", str(numero),
             "--repo", CFG.depot,
             "--add-label", LABEL_FAIT],
            capture_output=True, text=True, timeout=30
        )
    except Exception as e:
        log.error(f"Erreur fermeture issue #{numero} : {e}")

def lancer_claude(numero: int, titre: str, body: str, dry_run: bool,
                  autoriser_ecriture: bool = False,
                  timeout: int = None,
                  modele: str = "",
                  prompt_perso: str = None) -> tuple[bool, str]:
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

    Retourne (succès, sortie).
    """
    if timeout is None:
        timeout = CFG.timeout_claude

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

    if CFG.perimetre:
        clause_perimetre = (
            f"\nPÉRIMÈTRE STRICT — tu ne dois lire, modifier ou exécuter des commandes "
            f"que dans les répertoires suivants : {CFG.perimetre}\n"
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
        log.info(f"[DRY-RUN] Claude Code serait lancé pour issue #{numero} (mode {mode}, cwd {CFG.rep_travail})")
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
            timeout=timeout,
            cwd=CFG.rep_travail
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
                        derniere_erreur: str) -> str | None:
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
    boucle jamais dessus et on ne retente pas."""
    if CFG.perimetre:
        clause_perimetre = (
            f"\nPÉRIMÈTRE STRICT — tu ne dois lire que dans les répertoires "
            f"suivants : {CFG.perimetre}\n"
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

        succes, sortie = lancer_claude(numero, titre, body, dry_run, autoriser_ecriture, timeout, modele)

        if succes:
            log.info(f"  ✓ Issue #{numero} traitée avec succès.")
            commenter_issue(numero, f"## Résultat\n\n{sortie}")
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
                diagnostic = diagnostiquer_echec(numero, titre, body, sortie)
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
