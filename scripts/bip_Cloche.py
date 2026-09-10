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
    python3 bip.py                          # un bip
    python3 bip.py 3                        # trois bips (argument positionnel optionnel)
    python3 bip.py --tonalite -3             # bip décalé de -3 demi-tons (issue #526)

Le script tente plusieurs backends dans l'ordre et s'arrête au premier qui
fonctionne :
  1. paplay / canberra-gtk-play sur un son système (PulseAudio/PipeWire) ;
  2. aplay sur un son système (ALSA) ;
  3. caractère BEL (\\a) sur le terminal (repli minimal, dépend de la config).

Tonalité par projet (issue #526) : `--tonalite <demi-tons>` décale la hauteur
du son joué via l'effet `pitch` de `sox` (en centièmes de demi-ton : 100 cents
= 1 demi-ton), pour distinguer à l'oreille quel projet vient de terminer une
issue sans gérer une bibliothèque de sons. `sox` absent, `--tonalite 0`
(défaut) ou toute erreur de transformation → repli silencieux sur le son
d'origine, inchangé (jamais d'échec total, même philosophie que le reste du
script). Le backend canberra (1bis, pas de fichier à transformer) ignore la
tonalité.

Aucune dépendance Python externe : uniquement la bibliothèque standard et des
binaires système optionnels (dont `sox`, optionnel, pour la tonalité). Chaque
tentative est silencieuse en cas d'échec — un bip qui échoue ne doit jamais
faire planter l'appelant.
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# Sons système courants (freedesktop / Ubuntu). Le premier existant est utilisé.
SONS_CANDIDATS = [
    "/usr/share/sounds/freedesktop/stereo/complete.oga",
    "/usr/share/sounds/freedesktop/stereo/bell.oga",
    "/usr/share/sounds/freedesktop/stereo/message.oga",
    "/usr/share/sounds/alsa/Front_Center.wav",
]


def _premier_son_existant() -> str | None:
    for chemin in SONS_CANDIDATS:
        if Path(chemin).exists():
            return chemin
    return None


def _son_transforme(son: str, demitons: int) -> tuple[str, bool]:
    """Décale la tonalité de `son` de `demitons` demi-tons via `sox pitch`
    (issue #526). Retourne (chemin_a_jouer, est_temporaire) : le fichier
    d'origine, inchangé, si `demitons` vaut 0, si `sox` est absent du système,
    ou si la transformation échoue pour toute raison — jamais d'exception
    propagée."""
    if not demitons or not shutil.which("sox"):
        return son, False
    tmp = tempfile.mktemp(suffix=".wav")
    try:
        resultat = subprocess.run(
            ["sox", son, tmp, "pitch", str(demitons * 100)],
            capture_output=True, timeout=5,
        )
        if resultat.returncode == 0 and Path(tmp).exists() and Path(tmp).stat().st_size > 0:
            return tmp, True
    except Exception:
        pass
    try:
        os.remove(tmp)
    except OSError:
        pass
    return son, False


def un_bip(demitons: int = 0) -> bool:
    """Émet un bip, éventuellement décalé en tonalité de `demitons` demi-tons
    (issue #526). Retourne True si un backend a été lancé sans erreur."""
    son = _premier_son_existant()
    son_joue, temporaire = _son_transforme(son, demitons) if son else (None, False)

    try:
        # 1. PulseAudio / PipeWire.
        if son_joue and shutil.which("paplay"):
            try:
                subprocess.run(["paplay", son_joue], capture_output=True, timeout=5)
                return True
            except Exception:
                pass

        # 1bis. canberra (thème de sons du bureau) — n'a pas besoin de fichier,
        # la tonalité ne s'y applique donc pas.
        if shutil.which("canberra-gtk-play"):
            try:
                subprocess.run(["canberra-gtk-play", "-i", "bell"],
                               capture_output=True, timeout=5)
                return True
            except Exception:
                pass

        # 2. ALSA.
        if son_joue and shutil.which("aplay"):
            try:
                subprocess.run(["aplay", "-q", son_joue], capture_output=True, timeout=5)
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
    finally:
        if temporaire:
            try:
                os.remove(son_joue)
            except OSError:
                pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("fois", nargs="?", type=int, default=1,
                        help="Nombre de bips (défaut 1)")
    parser.add_argument("--projet", default=None,
                        help="Non utilisé par ce script (accepté pour compatibilité avec notifications.py::bip())")
    parser.add_argument("--numero", default=None,
                        help="Non utilisé par ce script (idem --projet)")
    parser.add_argument("--tonalite", type=int, default=0,
                        help="Décalage de tonalité en demi-tons (issue #526), 0 = neutre")
    args = parser.parse_args()

    fois = max(1, args.fois or 1)
    for i in range(fois):
        un_bip(args.tonalite)
        if i < fois - 1:
            time.sleep(0.3)


if __name__ == "__main__":
    main()
