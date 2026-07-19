#!/usr/bin/env python3
"""
bip.py — bip sonore court, infrastructure PARTAGÉE du bridge (issue #187).

Historique : ce script vivait dans ~/NicLink/bip.py (dépôt AlChess). Il n'a
rien de spécifique à AlChess — c'est de l'infrastructure commune à TOUS les
projets du bridge (watcher.py et new_issue.py l'appellent pour signaler
sonorement une transition d'issue). Il a donc été déplacé/recréé ici, dans
Bridge_Agent, à côté du reste du bridge.

> Note : la version canonique d'origine (~/NicLink/bip.py) n'a pas pu être
> recopiée octet pour octet — elle est hors du périmètre de l'agent qui a créé
> ce fichier (issue #187, périmètre restreint à ~/Bridge_Agent). Ce script est
> un ÉQUIVALENT fonctionnel : il émet un bip court. Remplacez-le par l'original
> exact si vous préférez un son identique — l'interface d'appel est la même
> (`python3 bip.py`, aucun argument requis).

Usage :
    python3 bip.py           # un bip
    python3 bip.py 3         # trois bips (argument optionnel : nombre de bips)

Le script tente plusieurs backends dans l'ordre et s'arrête au premier qui
fonctionne :
  1. paplay / canberra-gtk-play sur un son système (PulseAudio/PipeWire) ;
  2. aplay sur un son système (ALSA) ;
  3. caractère BEL (\\a) sur le terminal (repli minimal, dépend de la config).

Aucune dépendance Python externe : uniquement la bibliothèque standard et des
binaires système optionnels. Chaque tentative est silencieuse en cas d'échec —
un bip qui échoue ne doit jamais faire planter l'appelant.
"""

import shutil
import subprocess
import sys
import time

# Sons système courants (freedesktop / Ubuntu). Le premier existant est utilisé.
SONS_CANDIDATS = [
    "/usr/share/sounds/freedesktop/stereo/complete.oga",
    "/usr/share/sounds/freedesktop/stereo/bell.oga",
    "/usr/share/sounds/freedesktop/stereo/message.oga",
    "/usr/share/sounds/alsa/Front_Center.wav",
]


def _premier_son_existant() -> str | None:
    from pathlib import Path
    for chemin in SONS_CANDIDATS:
        if Path(chemin).exists():
            return chemin
    return None


def un_bip() -> bool:
    """Émet un bip. Retourne True si un backend a été lancé sans erreur."""
    son = _premier_son_existant()

    # 1. PulseAudio / PipeWire.
    if son and shutil.which("paplay"):
        try:
            subprocess.run(["paplay", son], capture_output=True, timeout=5)
            return True
        except Exception:
            pass

    # 1bis. canberra (thème de sons du bureau) — n'a pas besoin de fichier.
    if shutil.which("canberra-gtk-play"):
        try:
            subprocess.run(["canberra-gtk-play", "-i", "bell"],
                           capture_output=True, timeout=5)
            return True
        except Exception:
            pass

    # 2. ALSA.
    if son and shutil.which("aplay"):
        try:
            subprocess.run(["aplay", "-q", son], capture_output=True, timeout=5)
            return True
        except Exception:
            pass

    # 3. Repli minimal : caractère BEL. Dépend de la config du terminal
    #    (peut être muet), mais ne coûte rien et ne peut pas échouer.
    try:
        sys.stdout.write("\a")
        sys.stdout.flush()
        return True
    except Exception:
        return False


def main():
    fois = 1
    if len(sys.argv) > 1:
        try:
            fois = max(1, int(sys.argv[1]))
        except ValueError:
            fois = 1
    for i in range(fois):
        un_bip()
        if i < fois - 1:
            time.sleep(0.3)


if __name__ == "__main__":
    main()
