#!/usr/bin/env python3
"""
traitement_fin.py — déclencheur de fin de traitement d'une issue, infrastructure
PARTAGÉE du bridge (issues #187, #350). Anciennement `scripts/bip.py` — la clé
de config qui le référence reste `SCRIPT_BIP` pour l'instant (voir CHANGELOG).

Émet le bip sonore historique, puis — si `--projet` et `--numero` sont fournis
— notifie best-effort `new_issue.py` (POST /notifier-fin-issue, issue #350)
pour que l'onglet Résultats se rafraîchisse quasi instantanément (SSE) au lieu
d'attendre un ↻ manuel ou le fetch post-TIMEOUT de #334. Le POST est silencieux
en cas d'échec (new_issue.py non lancé, port fermé, etc.) : le bip reste
fonctionnel indépendamment de ce canal.

Usage :
    python3 traitement_fin.py                                   # un bip seul
    python3 traitement_fin.py --projet bridge_agent --numero 350 # bip + POST
"""

import argparse
import json
import math
import os
import struct
import tempfile
import urllib.request
import wave

F     = 880     # fréquence Hz
DUR   = 1.5     # durée secondes
SR    = 44100   # sample rate
DECAY = 5       # facteur de décroissance de l'enveloppe exponentielle

URL_NOTIFIER_FIN_ISSUE     = "http://localhost:5100/notifier-fin-issue"
TIMEOUT_NOTIFIER_FIN_ISSUE = 1   # s — new_issue.py non lancé ne doit jamais retarder le bip


def bip_plat():
    """Bip sonore court (440 Hz, 0.4 s), sinusoïde plate — ancienne implémentation
    conservée comme référence, non appelée (voir issue #437)."""
    f_plat, dur_plat = 440, 0.4
    samples = [int(32767 * math.sin(2 * math.pi * f_plat * t / SR)) for t in range(int(SR * dur_plat))]
    data = struct.pack('<' + 'h' * len(samples), *samples)

    tmp = tempfile.mktemp(suffix='.wav')
    w = wave.open(tmp, 'w')
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(SR)
    w.writeframes(data)
    w.close()

    os.system(f'aplay {tmp} 2>/dev/null')
    os.remove(tmp)


def bip():
    """Son de cloche douce (880 Hz, enveloppe exponentielle décroissante) via aplay."""
    samples = [
        int(32767 * math.sin(2 * math.pi * F * t / SR) * math.exp(-t * DECAY / SR))
        for t in range(int(SR * DUR))
    ]
    data = struct.pack('<' + 'h' * len(samples), *samples)

    tmp = tempfile.mktemp(suffix='.wav')
    w = wave.open(tmp, 'w')
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(SR)
    w.writeframes(data)
    w.close()

    os.system(f'aplay {tmp} 2>/dev/null')
    os.remove(tmp)


def notifier_fin_issue(projet: str, numero: str):
    """POST best-effort vers new_issue.py (issue #350) : pousse un événement SSE
    `fin_issue` à l'onglet Résultats déjà ouvert. Timeout court et échec
    silencieux — new_issue.py n'est pas toujours lancé, et ce canal ne doit
    jamais faire planter l'appelant (le bip a déjà été émis avant cet appel)."""
    try:
        corps = json.dumps({"projet": projet, "numero": int(numero)}).encode("utf-8")
        requete = urllib.request.Request(
            URL_NOTIFIER_FIN_ISSUE, data=corps,
            headers={"Content-Type": "application/json"}, method="POST",
        )
        urllib.request.urlopen(requete, timeout=TIMEOUT_NOTIFIER_FIN_ISSUE).close()
    except Exception:
        pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--projet", default=None,
                        help="Nom du projet (déclenche le POST /notifier-fin-issue avec --numero)")
    parser.add_argument("--numero", default=None,
                        help="Numéro de l'issue (déclenche le POST /notifier-fin-issue avec --projet)")
    args = parser.parse_args()

    bip()

    if args.projet and args.numero:
        notifier_fin_issue(args.projet, args.numero)


if __name__ == "__main__":
    main()
