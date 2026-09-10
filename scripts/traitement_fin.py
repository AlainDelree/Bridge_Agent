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
fonctionnel indépendamment de ce canal. `notifier_debut_issue` (issue #515,
POST /notifier-debut-issue) est le pendant côté DÉBUT de traitement — appelé
directement par watcher.py::notifier_debut_sse (pas via ce script, pas de bip
associé à un démarrage), il partage seulement l'infrastructure `_notifier` de
ce module.

Choix du son (issue #498) : `main()` lit `scripts/son_actif.txt` (une seule
ligne, `plat` ou `cloche`) pour décider quelle implémentation appeler —
`bip_plat()` (440 Hz, sinusoïde plate) ou `bip()` (880 Hz, cloche à enveloppe
exponentielle décroissante ; voir #437 et sa révocation). Ce seul fichier
pilote le son pour TOUS les projets utilisant ce script partagé (via
`SCRIPT_BIP`), sans avoir à toucher aux `configs/*.conf` individuels. Fichier
absent, illisible, ou contenant une valeur non reconnue → défaut inchangé
(`plat`), pour ne rien casser silencieusement. Depuis l'issue #527, ce fichier
n'a plus besoin d'être édité à la main : un interrupteur GLOBAL dans le
panneau flottant Infrastructure de `new_issue.py` (`#pl-zone-son`, routes
GET/POST `/son-actif` dans `app/son.py`) l'écrit directement, effectif au bip
suivant sans redémarrage d'aucun processus.

Tonalité par projet (issue #526) : `--tonalite <demi-tons>` décale la
fréquence de synthèse (`f_effective = f_base × 2^(demi-tons/12)`), appliqué
aux DEUX sons (`bip_plat()` et `bip()`) quel que soit le choix ci-dessus —
la tonalité (par projet, via `TONALITE_BIP` dans le `.conf`) et le son actif
(global, `son_actif.txt`) sont deux réglages orthogonaux. Comme le son est
synthétisé en Python (pas de fichier à transformer), aucun outil externe
supplémentaire n'est requis ici — contrairement à `scripts/bip_Cloche.py`
qui, lui, pitch-shifte un fichier son existant via `sox`. `--tonalite`
absent ou `0` → fréquence de base inchangée (comportement historique).

Usage :
    python3 traitement_fin.py                                   # un bip seul
    python3 traitement_fin.py --projet bridge_agent --numero 350 # bip + POST
    python3 traitement_fin.py --tonalite -4                      # bip décalé de -4 demi-tons
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
URL_NOTIFIER_DEBUT_ISSUE   = "http://localhost:5100/notifier-debut-issue"
TIMEOUT_NOTIFIER_FIN_ISSUE = 1   # s — new_issue.py non lancé ne doit jamais retarder le bip

FICHIER_SON_ACTIF = os.path.join(os.path.dirname(os.path.abspath(__file__)), "son_actif.txt")


def _frequence_decalee(f_base: float, demitons: int) -> float:
    """Fréquence décalée de `demitons` demi-tons (issue #526). Échelle
    logarithmique standard (12 demi-tons = une octave = ×2), 0 → f_base
    inchangée."""
    return f_base * (2 ** (demitons / 12)) if demitons else f_base


def bip_plat(demitons: int = 0):
    """Bip sonore court (440 Hz, 0.4 s), sinusoïde plate — son par défaut
    (voir issue #437 et #498, `son_actif()` ci-dessous pour le choix du son).
    `demitons` (issue #526) : décalage de tonalité par projet."""
    f_plat, dur_plat = _frequence_decalee(440, demitons), 0.4
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


def bip(demitons: int = 0):
    """Son de cloche douce (880 Hz, enveloppe exponentielle décroissante) via
    aplay. `demitons` (issue #526) : décalage de tonalité par projet."""
    f = _frequence_decalee(F, demitons)
    samples = [
        int(32767 * math.sin(2 * math.pi * f * t / SR) * math.exp(-t * DECAY / SR))
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


def son_actif() -> str:
    """Lit `FICHIER_SON_ACTIF` ('plat' ou 'cloche'). Absent, illisible, ou valeur
    non reconnue → 'plat' (défaut inchangé, ne casse rien silencieusement)."""
    try:
        with open(FICHIER_SON_ACTIF, "r", encoding="utf-8") as f:
            valeur = f.read().strip().lower()
        if valeur in ("plat", "cloche"):
            return valeur
    except OSError:
        pass
    return "plat"


def _notifier(url: str, projet: str, numero: str):
    """POST JSON {"projet", "numero"} best-effort vers new_issue.py, timeout
    court et échec silencieux — new_issue.py n'est pas toujours lancé, et ce
    canal ne doit jamais faire planter l'appelant. Partagé par
    notifier_fin_issue et notifier_debut_issue (issue #515)."""
    try:
        corps = json.dumps({"projet": projet, "numero": int(numero)}).encode("utf-8")
        requete = urllib.request.Request(
            url, data=corps,
            headers={"Content-Type": "application/json"}, method="POST",
        )
        urllib.request.urlopen(requete, timeout=TIMEOUT_NOTIFIER_FIN_ISSUE).close()
    except Exception:
        pass


def notifier_fin_issue(projet: str, numero: str):
    """POST best-effort vers new_issue.py (issue #350) : pousse un événement SSE
    `fin_issue` à l'onglet Résultats déjà ouvert."""
    _notifier(URL_NOTIFIER_FIN_ISSUE, projet, numero)


def notifier_debut_issue(projet: str, numero: str):
    """POST best-effort vers new_issue.py (issue #515), appelé par
    watcher.py::notifier_debut_sse juste après l'ACK d'une issue : pousse un
    événement SSE `debut_issue`, pour signaler une issue potentiellement
    encore inconnue du navigateur (créée pendant une absence)."""
    _notifier(URL_NOTIFIER_DEBUT_ISSUE, projet, numero)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--projet", default=None,
                        help="Nom du projet (déclenche le POST /notifier-fin-issue avec --numero)")
    parser.add_argument("--numero", default=None,
                        help="Numéro de l'issue (déclenche le POST /notifier-fin-issue avec --projet)")
    parser.add_argument("--tonalite", type=int, default=0,
                        help="Décalage de tonalité en demi-tons (issue #526), 0 = neutre")
    args = parser.parse_args()

    if son_actif() == "cloche":
        bip(args.tonalite)
    else:
        bip_plat(args.tonalite)

    if args.projet and args.numero:
        notifier_fin_issue(args.projet, args.numero)


if __name__ == "__main__":
    main()
