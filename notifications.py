#!/usr/bin/env python3
"""
notifications.py — canaux de notification PARTAGÉS du bridge (issue #187).

Ce module factorise la logique de notification qui vivait auparavant dans
watcher.py, afin qu'elle soit importable par les DEUX programmes :

  • watcher.py    (agent CCL / CCW) — notifie à la fin d'une issue qu'il traite ;
  • new_issue.py  (interface web, tourne en permanence sur le ThinkPad d'Alain) —
    détecte les transitions d'issues par polling GitHub et notifie localement,
    y compris pour les issues traitées par le PC Windows (CCW), sans qu'aucun
    appel réseau ne soit initié par le PC CCW.

Les fonctions sont VOLONTAIREMENT sans état et sans dépendance à l'objet global
`CFG` de watcher.py ni à Flask : tout ce dont elles ont besoin (nom du projet,
URL ntfy, chemin du script bip) leur est passé en argument. watcher.py conserve
des enveloppes minces qui les appellent avec les valeurs de son `CFG` ; le
poller de new_issue.py les appelle avec les valeurs du `Config` de chaque projet.

Aucune dépendance externe : subprocess + logging de la stdlib uniquement. Toute
erreur d'un canal (binaire absent, timeout) est journalisée mais n'interrompt
jamais l'appelant — une notification qui échoue ne doit jamais casser un cycle.
"""

import logging
import os
import platform
import subprocess
import time
from pathlib import Path

# ─── Labels de notification (opt-in, cumulatifs avec le bip) ───────────────────
# Contrat partagé du bridge : ces valeurs sont les labels réels sur GitHub.
# Dupliqués volontairement à l'identique dans watcher.py (constantes historiques)
# pour ne pas créer de dépendance d'import watcher → notifications → watcher.
LABEL_NOTIF_PC   = "notif_pc"     # bip + notify-send (bulle bureau locale)
LABEL_NOTIF_GSM  = "notif_gsm"    # bip + ntfy (push téléphone)
LABEL_NOTIF_TOUS = "notif_tous"   # bip + notify-send + ntfy

_log_defaut = logging.getLogger("notifications")


def a_un_label_notif(labels: list[str]) -> bool:
    """Vrai si l'issue porte au moins un label de notification."""
    return (LABEL_NOTIF_PC in labels
            or LABEL_NOTIF_GSM in labels
            or LABEL_NOTIF_TOUS in labels)


def bip(script_bip: Path, fois: int = 1, projet: str | None = None, numero=None,
        tonalite: int = 0):
    """Bip sonore via le script partagé (Bridge_Agent/scripts/traitement_fin.py,
    anciennement bip.py). `script_bip` : chemin du script. Silencieux si absent.
    `projet`/`numero`, si tous deux fournis, sont transmis en CLI au script pour
    qu'il notifie new_issue.py en plus du bip (SSE de rafraîchissement de
    l'onglet Résultats, issue #350) — best-effort côté script, sans incidence
    ici en cas d'échec. `tonalite` (issue #526) : décalage de tonalité en
    demi-tons, propre au projet (lu depuis son .conf par l'appelant) — transmis
    en CLI si non nul, ignoré par les scripts qui ne le supportent pas."""
    script_bip = Path(script_bip)
    if not script_bip.exists():
        return
    argv_supplementaires = []
    if projet and numero is not None:
        argv_supplementaires += ["--projet", str(projet), "--numero", str(numero)]
    if tonalite:
        argv_supplementaires += ["--tonalite", str(tonalite)]
    for _ in range(fois):
        try:
            subprocess.run(["python3", str(script_bip), *argv_supplementaires],
                           capture_output=True, timeout=10)
        except Exception:
            pass
        time.sleep(0.3)


# Bulle Windows (issue #863) : enveloppe System.Windows.Forms.NotifyIcon via
# PowerShell — déjà présent sur tout Windows avec .NET Framework (pas de
# dépendance Python supplémentaire, pas de module PowerShell externe comme
# BurntToast). Titre/message passés par variables d'environnement du
# sous-processus (jamais interpolés dans le texte du script PowerShell) pour
# exclure toute injection, quel que soit leur contenu.
_PS_BULLE_WINDOWS = (
    "Add-Type -AssemblyName System.Windows.Forms;"
    "Add-Type -AssemblyName System.Drawing;"
    "$icone = New-Object System.Windows.Forms.NotifyIcon;"
    "$icone.Icon = [System.Drawing.SystemIcons]::Information;"
    "$icone.BalloonTipIcon = [System.Windows.Forms.ToolTipIcon]$env:BRIDGE_NOTIF_ICONE;"
    "$icone.BalloonTipTitle = $env:BRIDGE_NOTIF_TITRE;"
    "$icone.BalloonTipText = $env:BRIDGE_NOTIF_MESSAGE;"
    "$icone.Visible = $true;"
    "$icone.ShowBalloonTip(5000);"
    "Start-Sleep -Milliseconds 5200;"
    "$icone.Dispose();"
)

_ICONE_PAR_URGENCE = {"critical": "Error", "low": "None"}  # repli 'Info' sinon


def _notifier_bureau_windows(nom_projet: str, titre: str, message: str,
                              urgence: str, log: logging.Logger):
    """Bulle de notification bureau sous Windows (issue #863), sans aucune
    dépendance Python supplémentaire : PowerShell + l'assembly .NET
    System.Windows.Forms, présente sur tout Windows avec .NET Framework.
    Best-effort — toute erreur (PowerShell absent, timeout) est journalisée
    et avalée, jamais propagée. Si le watcher tourne en SERVICE Windows sans
    session de bureau ouverte, la bulle ne peut physiquement pas s'afficher
    (pas de « Session 0 » interactive) : ce cas se traduit ici par un timeout
    ou une erreur PowerShell, journalisé avec un rappel que le canal ntfy
    (`notif_gsm`/`notif_tous`) reste lui disponible indépendamment."""
    env = os.environ.copy()
    env["BRIDGE_NOTIF_TITRE"] = titre
    env["BRIDGE_NOTIF_MESSAGE"] = message
    env["BRIDGE_NOTIF_ICONE"] = _ICONE_PAR_URGENCE.get(urgence, "Info")
    try:
        subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden",
             "-Command", _PS_BULLE_WINDOWS],
            capture_output=True, timeout=10, env=env,
        )
    except FileNotFoundError:
        log.warning("powershell.exe introuvable — notification bureau Windows ignorée "
                     "(le canal ntfy, notif_gsm/notif_tous, reste disponible).")
    except subprocess.TimeoutExpired:
        log.warning("powershell.exe n'a pas répondu à temps pour la bulle de bureau — "
                     "possible watcher en SERVICE Windows sans session de bureau ouverte "
                     "(le canal ntfy, notif_gsm/notif_tous, reste disponible dans ce cas).")
    except Exception as e:
        log.error(f"Erreur notification bureau Windows : {e}")


def notifier_bureau(nom_projet: str, titre: str, message: str,
                    urgence: str = "normal", log: logging.Logger = _log_defaut):
    """Bulle de notification bureau : notify-send sous Linux (comportement
    historique, inchangé), PowerShell/NotifyIcon sous Windows (issue #863).
    urgence : 'low', 'normal', 'critical'. Sous Linux, 'critical' reste
    affichée jusqu'à clic (utile pour les échecs) ; sous Windows, la bulle
    s'efface après un délai fixe quel que soit l'urgence (limite de
    NotifyIcon, voir _notifier_bureau_windows)."""
    if platform.system() == "Windows":
        _notifier_bureau_windows(nom_projet, titre, message, urgence, log)
        return
    try:
        subprocess.run(
            ["notify-send", "-a", f"Bridge {nom_projet}", "-u", urgence, titre, message],
            capture_output=True, timeout=5
        )
    except FileNotFoundError:
        log.warning("notify-send introuvable (paquet libnotify-bin non installé ?) — notification bureau ignorée.")
    except Exception as e:
        log.error(f"Erreur notify-send : {e}")


def notifier_ntfy(url_ntfy: str, titre: str, message: str,
                  priorite: str = "default", log: logging.Logger = _log_defaut):
    """Notification push sur le topic ntfy (téléphone).
    priorite : 'min', 'low', 'default', 'high', 'urgent'.
    TOPIC_NTFY est facultatif (issue #667) : url_ntfy vide (aucun topic
    configuré) → aucune requête réseau tentée, aucune erreur journalisée
    (au plus un log.debug), pas un échec réel."""
    if not url_ntfy:
        log.debug("TOPIC_NTFY non configuré — notification ntfy ignorée.")
        return
    try:
        subprocess.run(
            ["curl", "-s",
             "-H", f"Title: {titre}",
             "-H", f"Priority: {priorite}",
             "-H", "Tags: robot",
             "-d", message,
             url_ntfy],
            capture_output=True, timeout=10
        )
    except FileNotFoundError:
        log.warning("curl introuvable — notification ntfy ignorée.")
    except Exception as e:
        log.error(f"Erreur ntfy : {e}")


def notifier(labels: list[str], nom_projet: str, url_ntfy: str, script_bip: Path,
             titre: str, message: str,
             urgence_bureau: str = "normal", priorite_ntfy: str = "default",
             fois_bip: int = 1, numero=None, tonalite: int = 0,
             log: logging.Logger = _log_defaut):
    """Dispatch de notification selon les labels de l'issue.
    Le bip et les canaux additionnels (notify-send, ntfy) sont opt-in via les
    labels notif_pc / notif_gsm / notif_tous : sans aucun de ces labels, aucun
    signal n'est émis. fois_bip renforce le signal (ex. 3 pour une alerte
    critique). `numero`, si fourni, permet au bip de notifier new_issue.py de
    la fin de CETTE issue précise (SSE, issue #350). `tonalite` (issue #526) :
    décalage de tonalité en demi-tons propre au projet, transmis tel quel à
    bip()."""
    if a_un_label_notif(labels):
        bip(script_bip, fois_bip, projet=nom_projet, numero=numero, tonalite=tonalite)
    if LABEL_NOTIF_PC in labels or LABEL_NOTIF_TOUS in labels:
        notifier_bureau(nom_projet, titre, message, urgence_bureau, log=log)
    if LABEL_NOTIF_GSM in labels or LABEL_NOTIF_TOUS in labels:
        notifier_ntfy(url_ntfy, titre, message, priorite_ntfy, log=log)
