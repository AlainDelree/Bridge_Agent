#!/usr/bin/env python3
"""
notifications.py — canaux de notification PARTAGÉS du bridge (issue #187).

Ce module factorise la logique de notification qui vivait auparavant dans
watcher.py, afin qu'elle soit importable par les DEUX programmes :

  • watcher.py    (agent CCL / CCW) — notifie à la fin d'une issue qu'il traite ;
  • new_issue.py  (interface web, tourne en permanence sur le ThinkPad d'Alain) —
    détecte les transitions d'issues par polling GitHub et notifie localement,
    y compris pour les issues traitées par la VM Windows (CCW), sans qu'aucun
    appel réseau ne soit initié par la VM.

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


def bip(script_bip: Path, fois: int = 1):
    """Bip sonore via le script bip.py. `script_bip` : chemin du script (le
    partagé Bridge_Agent/scripts/bip.py par défaut). Silencieux si absent."""
    script_bip = Path(script_bip)
    if not script_bip.exists():
        return
    for _ in range(fois):
        try:
            subprocess.run(["python3", str(script_bip)], capture_output=True, timeout=10)
        except Exception:
            pass
        time.sleep(0.3)


def notifier_bureau(nom_projet: str, titre: str, message: str,
                    urgence: str = "normal", log: logging.Logger = _log_defaut):
    """Bulle de notification bureau via notify-send.
    urgence : 'low', 'normal', 'critical'. 'critical' reste affichée jusqu'à
    clic (utile pour les échecs)."""
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
    priorite : 'min', 'low', 'default', 'high', 'urgent'."""
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
             fois_bip: int = 1, log: logging.Logger = _log_defaut):
    """Dispatch de notification selon les labels de l'issue.
    Le bip et les canaux additionnels (notify-send, ntfy) sont opt-in via les
    labels notif_pc / notif_gsm / notif_tous : sans aucun de ces labels, aucun
    signal n'est émis. fois_bip renforce le signal (ex. 3 pour une alerte
    critique)."""
    if a_un_label_notif(labels):
        bip(script_bip, fois_bip)
    if LABEL_NOTIF_PC in labels or LABEL_NOTIF_TOUS in labels:
        notifier_bureau(nom_projet, titre, message, urgence_bureau, log=log)
    if LABEL_NOTIF_GSM in labels or LABEL_NOTIF_TOUS in labels:
        notifier_ntfy(url_ntfy, titre, message, priorite_ntfy, log=log)
