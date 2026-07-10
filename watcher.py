#!/usr/bin/env python3
"""
watcher.py — Bridge inter-agents AlChess
Surveille les GitHub Issues labelisées 'for-linux' et les délègue à Claude Code.

Usage :
    python3 watcher.py
    python3 watcher.py --dry-run   # simule sans lancer Claude Code
    python3 watcher.py --interval 30
"""

import subprocess
import json
import time
import logging
import argparse
import sys
from pathlib import Path
from datetime import datetime

# ─── Configuration ────────────────────────────────────────────────────────────

REPO           = "AlainDelree/AlChess"
LABEL          = "for-linux"
LABEL_WRITE    = "mode_write"  # label qui ARME le mode écriture (actions permises)
LABEL_FAILED   = "needs-human"  # posé après échec définitif : stoppe le retraitement automatique

# Labels de notification (opt-in : par défaut = beep seul, comme historiquement).
# Ces labels sont cumulatifs avec le beep sonore, pas en remplacement.
LABEL_NOTIF_PC   = "notif_pc"    # beep + notify-send (bulle desktop locale)
LABEL_NOTIF_GSM  = "notif_gsm"   # beep + ntfy (push téléphone)
LABEL_NOTIF_ALL  = "notif_tous"  # beep + notify-send + ntfy

# Topic ntfy — même que le projet site peinture (choix Alain).
# À terme, envisager de le sortir de watcher.py (variable d'env ou fichier de config)
# pour ne pas exposer le topic dans le dépôt si watcher.py y est un jour versionné.
NTFY_TOPIC = "hippocampe-ff-galerie-xyz123"
NTFY_URL   = f"https://ntfy.sh/{NTFY_TOPIC}"

POLL_INTERVAL  = 10          # secondes
MAX_RETRIES    = 3
CLAUDE_TIMEOUT = 300         # secondes avant timeout Claude Code
BIP_SCRIPT     = Path.home() / "NicLink" / "bip.py"
LOG_FILE       = Path.home() / "bridge-agent" / "watcher.log"

PRIORITES_CRITIQUES = {"haute", "critique"}

# Abréviations du dictionnaire bridge
SOURCES = {"CC": "Claude Chat", "CCL": "Claude Code Linux", "CCW": "Claude Code Windows"}

# ─── Logging ──────────────────────────────────────────────────────────────────

LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ]
)
log = logging.getLogger("watcher")

# ─── Utilitaires ──────────────────────────────────────────────────────────────

def bip(fois=1):
    """Bip sonore via bip.py de NicLink."""
    if BIP_SCRIPT.exists():
        for _ in range(fois):
            subprocess.run(["python3", str(BIP_SCRIPT)], capture_output=True)
            time.sleep(0.3)

def notify_desktop(titre: str, message: str, urgence: str = "normal"):
    """Envoie une bulle de notification desktop via notify-send.
    urgence : 'low', 'normal', 'critical'. 'critical' reste affichée jusqu'à
    clic (utile pour les échecs)."""
    try:
        subprocess.run(
            ["notify-send", "-a", "AlChess Bridge", "-u", urgence, titre, message],
            capture_output=True, timeout=5
        )
    except FileNotFoundError:
        log.warning("notify-send introuvable (paquet libnotify-bin non installé ?) — notification desktop ignorée.")
    except Exception as e:
        log.error(f"Erreur notify-send : {e}")

def notify_ntfy(titre: str, message: str, priorite: str = "default"):
    """Envoie une notification push sur le topic ntfy (téléphone).
    priorite : 'min', 'low', 'default', 'high', 'urgent'."""
    try:
        subprocess.run(
            ["curl", "-s",
             "-H", f"Title: {titre}",
             "-H", f"Priority: {priorite}",
             "-H", "Tags: chess_pawn",
             "-d", message,
             NTFY_URL],
            capture_output=True, timeout=10
        )
    except FileNotFoundError:
        log.warning("curl introuvable — notification ntfy ignorée.")
    except Exception as e:
        log.error(f"Erreur ntfy : {e}")

def notifier(labels: list[str], titre: str, message: str,
             urgence_desktop: str = "normal", priorite_ntfy: str = "default"):
    """Dispatch de notification selon les labels de l'issue.
    Le beep est toujours émis (comportement historique). Les canaux additionnels
    (notify-send, ntfy) sont opt-in via les labels notif_pc / notif_gsm / notif_tous."""
    bip(1)
    if LABEL_NOTIF_PC in labels or LABEL_NOTIF_ALL in labels:
        notify_desktop(titre, message, urgence_desktop)
    if LABEL_NOTIF_GSM in labels or LABEL_NOTIF_ALL in labels:
        notify_ntfy(titre, message, priorite_ntfy)

def alerte_critique(issue_number, titre, tentative, labels: list[str]):
    """Alerte pour les issues haute/critique après échec."""
    msg = f"⚠️  ALERTE — Issue #{issue_number} '{titre}' — tentative {tentative} échouée — nouvelle tentative dans {POLL_INTERVAL}s"
    log.warning(msg)
    bip(2)  # 1 bip déjà émis par notifier() ci-dessous → on ajoute 2 bips pour garder le "3 bips" historique de l'alerte critique
    notifier(
        labels,
        titre=f"⚠️ Bridge #{issue_number} — alerte critique",
        message=f"Tentative {tentative} échouée : {titre}\nNouvelle tentative dans {POLL_INTERVAL}s.",
        urgence_desktop="critical",
        priorite_ntfy="high",
    )

def gh(*args) -> dict | list | None:
    """Lance une commande gh et retourne le JSON parsé."""
    cmd = ["gh", *args, "--json"]
    # Pour issue list, on précise les champs
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            log.error(f"gh error: {result.stderr.strip()}")
            return None
        return json.loads(result.stdout)
    except Exception as e:
        log.error(f"gh exception: {e}")
        return None

def lister_issues():
    """Retourne la liste des issues for-linux ouvertes."""
    try:
        result = subprocess.run(
            ["gh", "issue", "list",
             "--repo", REPO,
             "--label", LABEL,
             "--state", "open",
             "--json", "number,title,body,labels,createdAt"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            log.error(f"Erreur gh issue list: {result.stderr.strip()}")
            return []
        return json.loads(result.stdout)
    except Exception as e:
        log.error(f"Exception lister_issues: {e}")
        return []

def extraire_priorite(body: str) -> str:
    """Extrait la priorité depuis le body de l'issue (header bridge)."""
    for line in body.splitlines():
        if "PRIORITE" in line.upper():
            parts = line.split("|")
            if len(parts) >= 3:
                return parts[2].strip().lower()
    return "normale"

def extraire_timeout(body: str) -> int:
    """Extrait le TIMEOUT (en secondes) depuis le body de l'issue (header bridge).
    Le template TACHES-ISSUES.md prévoit un champ '| TIMEOUT | 300s |' ; on le lit
    ici plutôt que d'imposer CLAUDE_TIMEOUT à toutes les tâches sans distinction.
    Retombe sur CLAUDE_TIMEOUT si absent ou mal formé."""
    for line in body.splitlines():
        if "TIMEOUT" in line.upper():
            parts = line.split("|")
            if len(parts) >= 3:
                valeur = parts[2].strip().lower().rstrip("s")
                if valeur.isdigit():
                    return int(valeur)
    return CLAUDE_TIMEOUT

def ajouter_label(number: int, label: str):
    """Ajoute un label à une issue sans la fermer."""
    try:
        subprocess.run(
            ["gh", "issue", "edit", str(number),
             "--repo", REPO,
             "--add-label", label],
            capture_output=True, text=True, timeout=30
        )
    except Exception as e:
        log.error(f"Erreur ajout label '{label}' sur issue #{number}: {e}")

def commenter_issue(number: int, message: str):
    """Poste un commentaire sur une issue."""
    try:
        subprocess.run(
            ["gh", "issue", "comment", str(number),
             "--repo", REPO,
             "--body", message],
            capture_output=True, text=True, timeout=30
        )
    except Exception as e:
        log.error(f"Erreur commentaire issue #{number}: {e}")

def fermer_issue(number: int):
    """Ferme une issue et ajoute le label 'done'."""
    try:
        subprocess.run(
            ["gh", "issue", "close", str(number), "--repo", REPO],
            capture_output=True, text=True, timeout=30
        )
        subprocess.run(
            ["gh", "issue", "edit", str(number),
             "--repo", REPO,
             "--add-label", "done"],
            capture_output=True, text=True, timeout=30
        )
    except Exception as e:
        log.error(f"Erreur fermeture issue #{number}: {e}")

def lancer_claude(issue_number: int, titre: str, body: str, dry_run: bool,
                  autoriser_ecriture: bool = False,
                  timeout: int = CLAUDE_TIMEOUT) -> tuple[bool, str]:
    """
    Lance Claude Code en mode non-interactif sur une issue.

    Par défaut (autoriser_ecriture=False) : Claude Code reste en LECTURE SEULE
    (il diagnostique, lit, grep, mais ne peut pas écrire/exécuter sans confirmation).

    Si autoriser_ecriture=True (label 'mode_write' posé sciemment sur l'issue) :
    on ajoute --dangerously-skip-permissions, ce qui autorise l'écriture de
    fichiers, l'exécution de commandes et les commits. Le garde-fou anti-push
    reste inscrit dans le prompt : Claude Code ne doit JAMAIS git push.

    Retourne (succès, output).
    """
    if autoriser_ecriture:
        garde_fou = """
MODE ÉCRITURE ACTIVÉ — tu es autorisé à modifier des fichiers, exécuter des
commandes et faire des commits git si la tâche le demande.
RÈGLES DE SÉCURITÉ IMPÉRATIVES :
- Fais TOUJOURS un backup pinné avant toute modification :
  python -m nicsoft.utils.backup_manager --pin --label "avant-<description>"
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

    prompt = f"""Tu es l'agent Linux du bridge inter-agents AlChess.
Traite la tâche suivante issue du GitHub Issue #{issue_number} :

TITRE : {titre}

BODY :
{body}
{garde_fou}
Instructions :
1. Lis attentivement la tâche demandée
2. Effectue le travail demandé (dans les limites du mode ci-dessus)
3. Résume ce que tu as fait en quelques lignes (ce sera posté en commentaire sur l'issue)
4. Si tu dois créer une issue for-windows, utilise : gh issue create --repo {REPO} --label "bridge,for-windows" ...

Réponds uniquement avec le résumé de ce que tu as accompli.
"""

    if dry_run:
        mode = "ÉCRITURE" if autoriser_ecriture else "lecture seule"
        log.info(f"[DRY-RUN] Claude Code serait lancé pour issue #{issue_number} (mode {mode})")
        return True, f"[DRY-RUN] Tâche simulée avec succès (mode {mode})."

    cmd = ["claude", "--print"]
    if autoriser_ecriture:
        cmd.append("--dangerously-skip-permissions")
    cmd.append(prompt)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True, text=True,
            timeout=timeout,
            cwd=Path.home() / "NicLink"
        )
        if result.returncode == 0:
            return True, result.stdout.strip()
        else:
            return False, result.stderr.strip() or "Erreur inconnue"
    except subprocess.TimeoutExpired:
        return False, f"Timeout après {timeout}s"
    except FileNotFoundError:
        return False, "Claude Code introuvable (claude non trouvé dans PATH)"
    except Exception as e:
        return False, str(e)

# ─── Traitement d'une issue ────────────────────────────────────────────────────

# Mémoire des issues en cours de traitement (évite les doublons)
issues_en_cours: set[int] = set()

def traiter_issue(issue: dict, dry_run: bool):
    number = issue["number"]
    titre  = issue["title"]
    body   = issue.get("body") or ""

    if number in issues_en_cours:
        return

    labels = [l.get("name", "") for l in issue.get("labels", [])]

    # Une issue déjà marquée 'needs-human' a échoué définitivement lors d'un
    # cycle précédent : on ne la retraite PAS automatiquement, sinon c'est la
    # boucle infinie (ACK → 3 tentatives → timeout → échec → nouveau cycle →
    # ACK → ...) tant qu'un humain n'a pas retiré le label ou fermé l'issue.
    if LABEL_FAILED in labels:
        log.debug(f"Issue #{number} déjà marquée '{LABEL_FAILED}' — ignorée (intervention humaine en attente).")
        return

    issues_en_cours.add(number)
    priorite = extraire_priorite(body)
    critique = priorite in PRIORITES_CRITIQUES
    timeout  = extraire_timeout(body)

    # Détection du label 'mode_write' : arme le mode écriture (actions permises).
    autoriser_ecriture = LABEL_WRITE in labels

    mode_txt = "ÉCRITURE ⚠️" if autoriser_ecriture else "lecture seule"
    log.info(f"→ Issue #{number} détectée : '{titre}' [priorité: {priorite}] [mode: {mode_txt}]")
    if autoriser_ecriture:
        log.warning(f"  ⚠️  MODE ÉCRITURE ARMÉ pour #{number} (label '{LABEL_WRITE}') — actions permises, push interdit.")

    commenter_issue(
        number,
        f"✅ ACK — Issue #{number} reçue par watcher.py (agent Linux). "
        f"Mode : **{mode_txt}**. Traitement en cours..."
    )

    tentative = 0
    while True:
        tentative += 1
        log.info(f"  Tentative {tentative}/{MAX_RETRIES if not critique else '∞'}...")

        succes, output = lancer_claude(number, titre, body, dry_run, autoriser_ecriture, timeout)

        if succes:
            log.info(f"  ✓ Issue #{number} traitée avec succès.")
            commenter_issue(number, f"## Résultat\n\n{output}")
            fermer_issue(number)
            issues_en_cours.discard(number)
            notifier(
                labels,
                titre=f"✅ Bridge #{number} — traitée",
                message=f"'{titre}' traitée avec succès.",
                urgence_desktop="normal",
                priorite_ntfy="default",
            )
            return

        # Échec
        log.warning(f"  ✗ Tentative {tentative} échouée : {output}")

        if tentative >= MAX_RETRIES:
            if critique:
                alerte_critique(number, titre, tentative, labels)
                log.warning(f"  Issue critique #{number} — nouvelle tentative au prochain cycle.")
                issues_en_cours.discard(number)  # sera reprise au prochain poll
                return
            else:
                log.error(f"  Issue #{number} abandonnée après {MAX_RETRIES} tentatives.")
                commenter_issue(number, f"❌ Échec après {MAX_RETRIES} tentatives.\n\nDernière erreur : `{output}`\n\nIntervention humaine requise. Label `{LABEL_FAILED}` posé : cette issue ne sera plus retraitée automatiquement tant que le label n'est pas retiré (ou l'issue fermée) manuellement.")
                ajouter_label(number, LABEL_FAILED)
                notifier(
                    labels,
                    titre=f"❌ Bridge #{number} — échec définitif",
                    message=f"'{titre}' abandonnée après {MAX_RETRIES} tentatives.\nDernière erreur : {output[:200]}",
                    urgence_desktop="critical",
                    priorite_ntfy="high",
                )
                issues_en_cours.discard(number)
                return

        time.sleep(5)  # pause entre tentatives

# ─── Boucle principale ─────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Bridge watcher — agent Linux AlChess")
    parser.add_argument("--dry-run", action="store_true", help="Simule sans lancer Claude Code")
    parser.add_argument("--interval", type=int, default=POLL_INTERVAL, help="Intervalle de polling en secondes")
    args = parser.parse_args()

    log.info("=" * 60)
    log.info(f"Bridge watcher démarré — repo: {REPO} — label: {LABEL}")
    log.info(f"Polling toutes les {args.interval}s — dry-run: {args.dry_run}")
    log.info("=" * 60)

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

        time.sleep(args.interval)

if __name__ == "__main__":
    main()
