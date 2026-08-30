#!/usr/bin/env python3
"""
watcher_issues_inbox.py — Watcher centralisé du dossier issues_inbox/ (issue #483).

Scrute en continu ~/Bridge_Agent/issues_inbox/ : TOUT fichier déposé (par
Claude Chat ou manuellement, quelle que soit son extension — issue #484,
le dossier fonctionne comme un pool d'impression, rien n'y traîne
silencieusement) est examiné. Un fichier .txt est parsé, validé, puis
transformé en issue GitHub via `gh issue create` — même format d'en-tête et
de labels que app/issues.py (construire_body/construire_labels), pour rester
cohérent avec le flux du formulaire web. Le fichier traité est supprimé
après création réussie ; un fichier invalide (PROJET inconnu, titre vide,
extension différente de .txt, etc.) est déplacé vers issues_inbox/rejected/
avec le détail de l'erreur en suffixe de nom. Anti-doublon (issue #491) :
avant création, réutilise app/issues.py::_issue_ouverte_meme_titre() (garde
du formulaire web, issue #189) pour rejeter un titre déjà porté par une
issue ouverte du même dépôt.

Après création réussie de l'issue, le watcher CCL du projet concerné
(`watcher.py --config configs/<projet>.conf`) est démarré automatiquement
s'il n'est pas déjà actif (issue #486, mode « dépose et oublie ») — via
`demarrer_watcher(forcer=False)` de app/watchers.py, réutilisée telle quelle.

Usage :
    python3 scripts/watcher_issues_inbox.py
    python3 scripts/watcher_issues_inbox.py --config configs/watcher_issues_inbox.conf
    python3 scripts/watcher_issues_inbox.py --once   # un seul cycle (tests)

Config (configs/watcher_issues_inbox.conf, optionnelle — voir charger_config_inbox
ci-dessous) : NOM, REP_TRAVAIL, POLLING_INTERVAL, MAX_LOG_LINES, INBOX_DIR,
REJECTED_DIR, GH_TOKEN. Toutes les clés sont optionnelles ; en son absence, le
watcher tourne avec des défauts sensés (dossiers sous ~/Bridge_Agent). Ce
fichier .conf n'est PAS créé automatiquement par CCL — garde-fou §11 de
BRIDGE_AGENT_DOC.md (CCL ne modifie/crée jamais configs/*.conf) : c'est à
Alain de le créer à la main s'il veut surcharger les défauts.
"""

import argparse
import logging
import os
import re
import subprocess
import sys
import tempfile
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

DOSSIER_SCRIPT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(DOSSIER_SCRIPT))

from watcher import (charger_config, lire_conf, est_titre_chef,  # noqa: E402
                     LABEL_NOTIF_PC, LABEL_NOTIF_GSM, LABEL_NOTIF_TOUS)
from app.watchers import demarrer_watcher  # noqa: E402 (issue #486)
from app.issues import _issue_ouverte_meme_titre  # noqa: E402 (issue #491)

log = logging.getLogger("watcher_issues_inbox")

# ─── Config ─────────────────────────────────────────────────────────────────

DEFAUT_CHEMIN_CONFIG = DOSSIER_SCRIPT / "configs" / "watcher_issues_inbox.conf"

# Fichiers PID/échéance — mêmes chemins que app/issues_inbox.py::CHEMIN_PID /
# CHEMIN_ECHEANCE (issue #485). Ce script ne les CRÉE jamais lui-même (c'est
# le lanceur, app.issues_inbox.demarrer_watcher_inbox(), qui écrit le PID au
# lancement — même logique que app/watchers.py::demarrer_watcher) ; il se
# contente de les supprimer à sa propre auto-extinction, pour que l'interface
# ne montre pas un PID orphelin.
CHEMIN_PID      = DOSSIER_SCRIPT / "logs" / "watcher-issues_inbox.pid"
CHEMIN_ECHEANCE = DOSSIER_SCRIPT / "logs" / "watcher-issues_inbox.echeance"


@dataclass
class ConfigInbox:
    nom: str              = "watcher_issues_inbox"
    rep_travail: Path     = DOSSIER_SCRIPT
    polling_interval: int = 5
    max_log_lines: int    = 50
    inbox_dir: Path       = DOSSIER_SCRIPT / "issues_inbox"
    rejected_dir: Path    = DOSSIER_SCRIPT / "issues_inbox" / "rejected"
    gh_token: str         = ""

    @property
    def fichier_log(self) -> Path:
        return DOSSIER_SCRIPT / "logs" / "issues_inbox.log"


def charger_config_inbox(chemin: Path) -> ConfigInbox:
    """Charge configs/watcher_issues_inbox.conf s'il existe ; sinon retourne les
    défauts. Toutes les clés sont optionnelles (contrairement à charger_config()
    des projets) : ce watcher est utilisable dès l'installation, sans .conf."""
    if not chemin.exists():
        return ConfigInbox()

    brut = lire_conf(chemin)
    rep_travail = Path(brut.get("REP_TRAVAIL") or str(DOSSIER_SCRIPT)).expanduser()
    inbox_dir = Path(brut.get("INBOX_DIR") or str(rep_travail / "issues_inbox")).expanduser()
    rejected_dir = Path(brut.get("REJECTED_DIR") or str(inbox_dir / "rejected")).expanduser()

    def entier(cle: str, defaut: int) -> int:
        val = (brut.get(cle) or "").strip()
        return int(val) if val.isdigit() else defaut

    return ConfigInbox(
        nom              = brut.get("NOM") or "watcher_issues_inbox",
        rep_travail      = rep_travail,
        polling_interval = entier("POLLING_INTERVAL", 5),
        max_log_lines    = entier("MAX_LOG_LINES", 50),
        inbox_dir        = inbox_dir,
        rejected_dir     = rejected_dir,
        gh_token         = brut.get("GH_TOKEN") or "",
    )


# ─── Parsing d'en-tête (miroir Python de lireChampEntete/retirerLigneEntete de
# static/js/app.js — même regex, pour ne jamais diverger du format produit par
# Claude Chat / reconnu par le formulaire web) ──────────────────────────────

# Nombre de lignes depuis le tout début du fichier où chercher les champs
# d'en-tête (issue #512). Le bloc en-tête + #Titre: tient toujours largement
# dans cette marge (§3.3 du DOC : au plus une dizaine de champs + les lignes
# de décoration Markdown) ; au-delà, une mention d'un champ dans le corps
# explicatif (ex. exemple illustratif) n'est plus interprétée comme le
# véritable en-tête — seule la PREMIÈRE occurrence, proche du début, compte.
ZONE_ENTETE_LIGNES = 25


def _zone_entete(corps: str) -> str:
    """Préfixe de `corps` limité aux ZONE_ENTETE_LIGNES premières lignes — les
    indices retournés par une recherche dans ce préfixe restent valides tels
    quels dans `corps` (c'est un préfixe exact, pas une copie transformée)."""
    return "".join((corps or "").splitlines(keepends=True)[:ZONE_ENTETE_LIGNES])


def _regex_champ(champ: str) -> re.Pattern:
    # [ \t]* (espaces/tabulations) plutôt que \s* : \s* inclut le saut de ligne,
    # ce qui permet à `^` (ancre de DÉBUT DE LIGNE en mode MULTILINE) de matcher
    # au début d'une ligne VIDE précédant la ligne du champ, puis à \s* d'avaler
    # ce saut de ligne pour atteindre le « | » de la ligne suivante — le match
    # démarre alors une ligne trop tôt (issue #512 : ce cas survient typiquement
    # quand #Titre: précède l'en-tête tabulaire, une ligne vide séparant les
    # deux). retirer_ligne_entete calcule ensuite la fin de ligne avec
    # corps.find("\n", debut) : comme `debut` pointe sur la ligne vide (un seul
    # caractère "\n"), fin == debut et seul CE caractère est retiré — la ligne
    # du champ, elle, reste intacte dans le corps restant.
    return re.compile(rf"^[ \t]*\|[ \t]*{champ}[ \t]*\|([^|]*)\|", re.IGNORECASE | re.MULTILINE)


def lire_champ_entete(corps: str, champ: str) -> str | None:
    m = _regex_champ(champ).search(_zone_entete(corps))
    if not m:
        return None
    valeur = m.group(1).strip()
    return valeur or None


def retirer_ligne_entete(corps: str, champ: str) -> str:
    m = _regex_champ(champ).search(_zone_entete(corps))
    if not m:
        return corps
    debut = m.start()
    fin = corps.find("\n", debut)
    fin = len(corps) if fin == -1 else fin
    if fin < len(corps) and corps[fin] == "\n":
        return corps[:debut] + corps[fin + 1:]
    if debut > 0 and corps[debut - 1] == "\n":
        return corps[:debut - 1] + corps[fin:]
    return corps[:debut] + corps[fin:]


TITRE_RE = re.compile(r"^#Titre:\s*(.*)$", re.IGNORECASE | re.MULTILINE)

CHAMPS_ENTETE = ("PROJET", "TIMEOUT", "MODELE", "MODE", "LABELS")


def extraire_champs(contenu: str) -> dict:
    """Extrait les champs d'en-tête optionnels, le #Titre: et le corps restant
    (en-tête + ligne #Titre retirés, comme le fait le formulaire web à la
    frappe — cf. detecterProjetDansCorps/detecterTimeoutDansCorps/
    detecterModeDansCorps de static/js/app.js)."""
    valeurs = {champ: lire_champ_entete(contenu, champ) for champ in CHAMPS_ENTETE}

    reste = contenu
    for champ in CHAMPS_ENTETE:
        reste = retirer_ligne_entete(reste, champ)

    m = TITRE_RE.search(reste)
    titre = m.group(1).strip() if m else ""
    if m:
        debut = m.start()
        fin = reste.find("\n", debut)
        fin = len(reste) if fin == -1 else fin + 1
        reste = reste[:debut] + reste[fin:]

    return {
        "projet":       (valeurs["PROJET"] or "").strip(),
        "timeout_brut": valeurs["TIMEOUT"],
        "modele":       (valeurs["MODELE"] or "").strip(),
        "mode_brut":    valeurs["MODE"],
        "labels_brut":  valeurs["LABELS"],
        "titre":        titre,
        "corps":        reste.strip("\n"),
    }


# ─── Découpage multi-blocs — lot (miroir Python de decouperCorpsEnBlocs de
# static/js/app.js, issue #508) : un fichier peut contenir plusieurs blocs
# `#Titre:` à la suite, chacun traité comme une issue indépendante. Même
# principe que le formulaire web : chaque bloc va de son `#Titre:` jusqu'au
# `#Titre:` suivant (exclu) ou la fin du fichier ; le contenu éventuel AVANT
# le premier `#Titre:` n'appartient à aucun bloc et est ignoré — cohérent
# avec decouperCorpsEnBlocs (le mode lot n'existe que pour ≥ 2 occurrences).
# Un fichier ne portant qu'un seul `#Titre:` (ou aucun) reste traité comme
# aujourd'hui, sur le contenu ENTIER (pas sur ce découpage) : c'est le seul
# moyen de conserver la convention mono-issue existante (en-tête `| CHAMP |
# Valeur |` placé AVANT `#Titre:`, §3.3 du DOC) que ce découpage briserait
# s'il était appliqué à un fichier à un seul bloc.
def decouper_corps_en_blocs(contenu: str) -> list[str]:
    debuts = [m.start() for m in TITRE_RE.finditer(contenu or "")]
    if not debuts:
        return []
    texte = contenu
    blocs = []
    for i, debut in enumerate(debuts):
        fin = debuts[i + 1] if i + 1 < len(debuts) else len(texte)
        blocs.append(texte[debut:fin])
    return blocs


# ─── Mode (miroir de app.js::reconnaitreModeTexte / app/issues.py::MODES) ──
# Reconnaissance tolérante — jamais un motif de rejet en soi (§6 du DOC :
# défaut LECTURE si absent/non reconnu), seulement §3 du DOC demande de la
# « reconnaître », pas de la valider strictement.
MODE_SYNONYMES = (
    ("ecriture",       ("écriture", "ecriture", "write", "mode_write")),
    ("lecture_active", ("lecture active", "scratch", "mode_scratch")),
    ("lecture",        ("lecture seule", "lecture", "read", "mode_read")),
)
MODES = {
    "lecture":        ("lecture", None),
    "lecture_active": ("lecture active", "mode_scratch"),
    "ecriture":       ("écriture", "mode_write"),
}


def _sans_accents(texte: str) -> str:
    decompose = unicodedata.normalize("NFKD", texte or "")
    return "".join(c for c in decompose if not unicodedata.combining(c))


def reconnaitre_mode(brut: str | None) -> str:
    if not brut:
        return "lecture"
    normalise = _sans_accents(brut.strip().lower())
    for valeur, motifs in MODE_SYNONYMES:
        for motif in motifs:
            if _sans_accents(motif.lower()) in normalise:
                return valeur
    return "lecture"


MODELES_VALIDES = {"claude-sonnet-5", "claude-opus-4-8", "claude-haiku-4-5", "claude-fable-5"}


# ─── Validation ─────────────────────────────────────────────────────────────

def valider(champs: dict):
    """Retourne (True, "", cfg_projet) si le fichier est exploitable, sinon
    (False, détail_erreur, None)."""
    if not champs["projet"]:
        return False, "en-tête malformé : champ PROJET manquant ou vide.", None

    chemin_conf = DOSSIER_SCRIPT / "configs" / f"{champs['projet']}.conf"
    if not chemin_conf.exists():
        return False, f"projet inconnu : « {champs['projet']} » (configs/{champs['projet']}.conf introuvable).", None
    try:
        cfg_projet = charger_config(chemin_conf)
    except SystemExit as e:
        return False, f"config du projet « {champs['projet']} » invalide : {e}", None

    if not champs["titre"]:
        return False, "titre manquant (ligne « #Titre: » absente ou vide).", None

    if champs["modele"] and champs["modele"] not in MODELES_VALIDES:
        return False, (f"MODELE inconnu : « {champs['modele']} » "
                        f"(valeurs acceptées : {', '.join(sorted(MODELES_VALIDES))})."), None

    if champs["timeout_brut"]:
        valeur = champs["timeout_brut"].strip().lower().rstrip("s")
        if not valeur.isdigit():
            return False, f"TIMEOUT invalide : « {champs['timeout_brut']} » (doit être un nombre).", None

    return True, "", cfg_projet


# ─── Construction body/labels (miroir de app/issues.py::construire_body /
# construire_labels, pour produire des issues indiscernables de celles créées
# via le formulaire web) ────────────────────────────────────────────────────

LABELS_RE = re.compile(r"^\s*\|\s*LABELS\s*\|([^|]*)\|", re.IGNORECASE | re.MULTILINE)


LABELS_NOTIF = {LABEL_NOTIF_PC, LABEL_NOTIF_GSM, LABEL_NOTIF_TOUS}


def construire_labels(champs: dict) -> str:
    extras = [lab.strip() for lab in (champs["labels_brut"] or "").split(",") if lab.strip()]
    labels = ["bridge"]
    if "for-windows" not in extras:
        labels.append("for-linux")
    _, label_mode = MODES[reconnaitre_mode(champs["mode_brut"])]
    if label_mode:
        labels.append(label_mode)
    for extra in extras:
        if extra not in labels:
            labels.append(extra)
    # Label de notification par défaut (issue #490) : notif_pc, sauf si le
    # champ LABELS demande déjà explicitement notif_gsm/notif_tous (miroir du
    # comportement le plus courant côté formulaire, app/issues.py::construire_labels).
    if not (LABELS_NOTIF & set(labels)):
        labels.append(LABEL_NOTIF_PC)
    return ",".join(labels)


def construire_body(champs: dict, cfg_projet) -> str:
    mode_valeur = reconnaitre_mode(champs["mode_brut"])
    mode_label, _ = MODES[mode_valeur]

    chef = est_titre_chef(champs["titre"])
    if champs["timeout_brut"]:
        timeout = int(champs["timeout_brut"].strip().lower().rstrip("s"))
        if chef:
            timeout = max(timeout, cfg_projet.timeout_chef)
    else:
        timeout = cfg_projet.timeout_chef if chef else cfg_projet.timeout_claude

    lignes = [
        "## En-tête\n",
        "| Champ    | Valeur |",
        "|----------|--------|",
        "| SOURCE   | CC |",
        "| DEST     | CCL |",
        "| RETOUR   | CC |",
        f"| MODE     | {mode_label} |",
        "| PRIORITE | normale |",
        f"| TIMEOUT  | {timeout}s |",
        f"| PROJET   | {cfg_projet.nom} |",
    ]
    if champs["modele"]:
        lignes.append(f"| MODELE   | {champs['modele']} |")

    entete = "\n".join(lignes)
    parties = [p for p in (entete, champs["corps"]) if p]
    return "\n\n".join(parties)


# ─── Journalisation (rotation par NOMBRE DE LIGNES — max_log_lines, distincte
# de la rotation par taille des watchers de projet, cf. issue #483) ────────

def _ecrire_ligne_log(cfg: ConfigInbox, projet: str, statut: str, texte: str) -> None:
    horodatage = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ligne = f"{horodatage} | {projet} | {statut} | {texte}"

    cfg.fichier_log.parent.mkdir(parents=True, exist_ok=True)
    lignes = []
    if cfg.fichier_log.exists():
        lignes = cfg.fichier_log.read_text(encoding="utf-8").splitlines()
    lignes.append(ligne)
    if len(lignes) > cfg.max_log_lines:
        lignes = lignes[-cfg.max_log_lines:]
    cfg.fichier_log.write_text("\n".join(lignes) + "\n", encoding="utf-8")


# ─── Rejet ──────────────────────────────────────────────────────────────────

def _slug(texte: str, longueur_max: int = 40) -> str:
    normalise = _sans_accents(texte or "").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", normalise).strip("-")
    return slug[:longueur_max] or "erreur"


def _deplacer_vers_rejected(cfg: ConfigInbox, chemin: Path, detail: str) -> Path | None:
    """Déplace seul, sans journaliser (issue #508) : un lot dont TOUS les blocs
    ont échoué a déjà journalisé chaque motif individuellement (une ligne par
    bloc, cf. _traiter_lot) — une ligne de log supplémentaire ici ferait
    doublon. `_rejeter` ci-dessous journalise en plus, pour le cas mono-issue
    où aucune autre ligne n'a été écrite."""
    cfg.rejected_dir.mkdir(parents=True, exist_ok=True)
    nom_cible = f"{chemin.stem}__REJETE-{_slug(detail)}{chemin.suffix}"
    cible = cfg.rejected_dir / nom_cible
    i = 1
    while cible.exists():
        cible = cfg.rejected_dir / f"{chemin.stem}__REJETE-{_slug(detail)}-{i}{chemin.suffix}"
        i += 1
    try:
        chemin.rename(cible)
    except OSError as e:
        log.error(f"Impossible de déplacer {chemin.name} vers rejected/ : {e}")
        return None
    log.warning(f"Rejeté : {chemin.name} → {cible.name} ({detail})")
    return cible


def _rejeter(cfg: ConfigInbox, chemin: Path, titre: str, projet: str, detail: str) -> None:
    cible = _deplacer_vers_rejected(cfg, chemin, detail)
    if cible is None:
        return
    texte = f"{titre} — {detail}" if titre else detail
    _ecrire_ligne_log(cfg, projet or "(unknown)", "REJECTED", texte)


# ─── Création de l'issue via gh (miroir de app/issues.py::envoyer) ─────────

def _creer_issue(cfg: ConfigInbox, cfg_projet, titre: str, labels: str, body: str):
    # GH_TOKEN n'est surchargé que si explicitement fourni dans le .conf — sinon
    # `gh` utilise son authentification habituelle (session `gh auth login` ou
    # GH_TOKEN déjà exporté dans l'environnement du process, comme new_issue.py).
    env = dict(os.environ, GH_TOKEN=cfg.gh_token) if cfg.gh_token else None
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write(body)
        chemin_body = f.name
    try:
        res = subprocess.run(
            ["gh", "issue", "create",
             "--repo",  cfg_projet.depot,
             "--title", titre,
             "--label", labels,
             "--body-file", chemin_body],
            capture_output=True, text=True, timeout=30, env=env,
        )
        if res.returncode == 0:
            return True, res.stdout.strip()
        return False, res.stderr.strip() or "erreur inconnue de gh."
    except subprocess.TimeoutExpired:
        return False, "timeout (gh n'a pas répondu en 30s)."
    except FileNotFoundError:
        return False, "gh introuvable dans le PATH."
    except Exception as e:
        return False, str(e)
    finally:
        Path(chemin_body).unlink(missing_ok=True)


# ─── Traitement d'un fichier ────────────────────────────────────────────────

def _fichier_pret(chemin: Path) -> bool:
    """Faux si le fichier a été modifié il y a moins d'1s (encore en cours
    d'écriture) — repris au cycle de polling suivant."""
    try:
        return (time.time() - chemin.stat().st_mtime) >= 1.0
    except OSError:
        return False


def _traiter_bloc(cfg: ConfigInbox, contenu_bloc: str):
    """Traite UN bloc — fichier mono-issue entier, ou un des blocs d'un lot
    multi-issues (issue #508) : validation, anti-doublon, création via `gh`,
    démarrage auto du watcher CCL du projet concerné. Exactement le même
    traitement qu'avant l'ajout du multi-blocs, mais sans toucher au fichier
    source ni au log — laissé à l'appelant (mono-issue ou lot), qui décide
    différemment de la disposition finale du fichier selon le cas.

    Retourne (succes, titre, projet, texte, resultat_gh) :
    - échec → `texte` est le détail d'erreur (nom du fichier rejeté + ligne
      de log) ;
    - succès → `texte` est le suffixe optionnel (« — watcher CCL démarré
      (pid N) »), à ajouter au titre dans la ligne de log ; `resultat_gh` est
      la sortie de `gh issue create` (URL), pour le seul log console.
    """
    champs = extraire_champs(contenu_bloc)
    ok, detail, cfg_projet = valider(champs)
    if not ok:
        return False, champs["titre"], champs["projet"], detail, ""

    # Anti-doublon (issue #491) : réutilise telle quelle la garde du formulaire
    # web (_issue_ouverte_meme_titre, app/issues.py — issue #189) pour refuser
    # une issue dont le titre correspond exactement à une issue déjà OUVERTE du
    # même dépôt. Best-effort par construction (cf. docstring de la fonction) :
    # si `gh issue list` échoue, elle retourne None et la création se poursuit.
    doublon = _issue_ouverte_meme_titre(cfg_projet, champs["titre"])
    if doublon is not None:
        return (False, champs["titre"], champs["projet"],
                f"doublon : une issue #{doublon} portant ce titre est déjà ouverte", "")

    labels = construire_labels(champs)
    body = construire_body(champs, cfg_projet)
    succes, resultat = _creer_issue(cfg, cfg_projet, champs["titre"], labels, body)
    if not succes:
        return (False, champs["titre"], champs["projet"],
                f"gh issue create a échoué : {resultat}", "")

    # Démarrage auto du watcher CCL du projet concerné (issue #486) — sans quoi
    # l'issue fraîchement créée resterait en attente indéfiniment si Alain
    # n'a pas déjà lancé ce watcher depuis le panneau Infrastructure. Réutilise
    # demarrer_watcher(forcer=False) de app/watchers.py (mêmes modalités que le
    # bouton « Lancer ») : ne fait rien si le watcher tourne déjà (pas question
    # d'interrompre un traitement d'issue potentiellement en cours sur ce
    # projet), le démarre sinon.
    suffixe = ""
    try:
        demarre, pid = demarrer_watcher(cfg_projet, forcer=False)
        if demarre:
            suffixe = f" — watcher CCL démarré (pid {pid})"
            log.info(f"Watcher CCL démarré pour le projet « {champs['projet']} » (pid {pid}).")
    except Exception as e:
        log.warning(f"Démarrage auto du watcher CCL « {champs['projet']} » échoué : {e}")

    return True, champs["titre"], champs["projet"], suffixe, resultat


def _traiter_lot(cfg: ConfigInbox, chemin: Path, blocs: list) -> None:
    """Traite un fichier multi-blocs (issue #508) : chaque bloc est traité
    séquentiellement par `_traiter_bloc` — JAMAIS en parallèle, cohérent avec
    `envoyerLot` côté formulaire web (pas de conflit `gh`). Chaque résultat
    (succès ou échec) est journalisé individuellement, une ligne par bloc. Le
    fichier n'est supprimé qu'une fois tous les blocs traités : normalement si
    au moins un bloc a réussi (un échec partiel ne doit pas re-proposer
    indéfiniment les blocs déjà réussis au prochain cycle) ; déplacé vers
    `rejected/` seulement si TOUS ont échoué."""
    nb_total = len(blocs)
    nb_ok = 0
    for i, bloc in enumerate(blocs, start=1):
        succes, titre, projet, texte, resultat_gh = _traiter_bloc(cfg, bloc)
        if succes:
            nb_ok += 1
            _ecrire_ligne_log(cfg, projet, "OK", titre + texte)
            log.info(f"Lot {chemin.name} [{i}/{nb_total}] créée : {titre} → {resultat_gh}")
        else:
            _ecrire_ligne_log(cfg, projet or "(unknown)", "REJECTED",
                               f"{titre} — {texte}" if titre else texte)
            log.warning(f"Lot {chemin.name} [{i}/{nb_total}] rejeté : "
                        f"{titre or '(sans titre)'} — {texte}")

    if nb_ok == 0:
        _deplacer_vers_rejected(cfg, chemin, f"lot : {nb_total} bloc(s) échoué(s)")
        return

    try:
        chemin.unlink()
    except OSError as e:
        log.warning(f"Lot traité ({nb_ok}/{nb_total} OK) mais suppression de "
                    f"{chemin.name} échouée : {e}")

    log.info(f"Lot {chemin.name} terminé : {nb_ok}/{nb_total} issue(s) créée(s).")


def traiter_fichier(cfg: ConfigInbox, chemin: Path) -> None:
    if chemin.suffix.lower() != ".txt":
        _rejeter(cfg, chemin, "", "", "extension invalide : attendu .txt")
        return

    try:
        contenu = chemin.read_text(encoding="utf-8")
    except OSError as e:
        _rejeter(cfg, chemin, "", "", f"lecture impossible : {e}")
        return

    # Lot multi-issues (issue #508) : ≥ 2 blocs « #Titre: » dans le fichier —
    # même seuil que enModeLot() côté formulaire web. En-dessous (0 ou 1), le
    # fichier reste traité comme avant sur son contenu ENTIER (pas sur un
    # bloc découpé), pour ne pas casser la convention mono-issue existante
    # (en-tête possiblement placé AVANT #Titre:, cf. decouper_corps_en_blocs).
    blocs = decouper_corps_en_blocs(contenu)
    if len(blocs) >= 2:
        _traiter_lot(cfg, chemin, blocs)
        return

    succes, titre, projet, texte, resultat_gh = _traiter_bloc(cfg, contenu)
    if not succes:
        _rejeter(cfg, chemin, titre, projet, texte)
        return

    try:
        chemin.unlink()
    except OSError as e:
        log.warning(f"Issue créée ({resultat_gh}) mais suppression de {chemin.name} échouée : {e}")

    _ecrire_ligne_log(cfg, projet, "OK", titre + texte)
    log.info(f"Créée : {chemin.name} → {resultat_gh}")


def traiter_dossier(cfg: ConfigInbox) -> None:
    if not cfg.inbox_dir.is_dir():
        return
    for chemin in sorted(cfg.inbox_dir.glob("*")):
        if chemin == cfg.rejected_dir:
            continue
        if not chemin.is_file() or not _fichier_pret(chemin):
            continue
        try:
            traiter_fichier(cfg, chemin)
        except Exception as e:
            log.error(f"Erreur inattendue en traitant {chemin.name} : {e}")


# ─── Boucle principale ──────────────────────────────────────────────────────

def configurer_logs() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def boucle(cfg: ConfigInbox, once: bool = False, duree_min: int = 0) -> None:
    cfg.inbox_dir.mkdir(parents=True, exist_ok=True)
    cfg.rejected_dir.mkdir(parents=True, exist_ok=True)
    log.info(f"watcher_issues_inbox démarré — {cfg.inbox_dir} "
              f"(intervalle {cfg.polling_interval}s, log max {cfg.max_log_lines} lignes)")

    # Auto-extinction interne sur une durée fixe (issue #485), même principe
    # que l'auto-extinction par inactivité de watcher.py (§20 du DOC) : à
    # l'écoulement du délai, arrêt propre (sys.exit(0)) et suppression du
    # fichier PID (+ échéance) pour que l'interface ne montre pas un PID
    # orphelin. Horloge MONOTONE (comme watcher.py) : insensible à un
    # changement d'heure système pendant que le watcher tourne.
    if duree_min > 0:
        log.info(f"Auto-extinction activée : arrêt après {duree_min} min (issue #485).")
        echeance_monotone = time.monotonic() + duree_min * 60
    else:
        log.info("Auto-extinction désactivée (durée non fixée) — watcher permanent.")
        echeance_monotone = None

    while True:
        traiter_dossier(cfg)
        if once:
            return
        if echeance_monotone is not None and time.monotonic() >= echeance_monotone:
            log.info(f"⏻ Auto-extinction : durée de {duree_min} min écoulée — "
                      f"arrêt propre du watcher.")
            CHEMIN_PID.unlink(missing_ok=True)
            CHEMIN_ECHEANCE.unlink(missing_ok=True)
            sys.exit(0)
        time.sleep(cfg.polling_interval)


def main() -> None:
    parser = argparse.ArgumentParser(description="Watcher issues_inbox — bridge_agent (issue #483)")
    parser.add_argument("--config", default=str(DEFAUT_CHEMIN_CONFIG),
                        help="Chemin du .conf (optionnel — défauts sensés sinon)")
    parser.add_argument("--once", action="store_true",
                        help="Un seul cycle de traitement puis quitte (tests)")
    parser.add_argument("--duree-min", type=int, default=0,
                        help="Auto-extinction après ce délai en minutes (0/absent = désactivé, tourne indéfiniment ; issue #485)")
    args = parser.parse_args()

    configurer_logs()
    cfg = charger_config_inbox(Path(args.config))
    boucle(cfg, once=args.once, duree_min=args.duree_min)


if __name__ == "__main__":
    main()
