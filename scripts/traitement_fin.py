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

Choix du son (issue #498, affiné #630) : `main()` décide entre `bip_plat()`
(440 Hz, sinusoïde plate) et `bip()` (880 Hz, cloche à enveloppe exponentielle
décroissante ; voir #437 et sa révocation) selon DEUX niveaux, dans cet
ordre :
  1. **choix PAR ISSUE** (`--projet` + `--numero` fournis) : lu dans
     `logs/son_issues.json` via `etat_son_issue.son_choisi()` — voir
     `app/son_issue.py` pour les routes GET/POST qui l'alimentent (issue
     #630, backend seul pour l'instant, pas encore de bouton dans
     l'interface) ;
  2. sinon, **interrupteur GLOBAL** `scripts/son_actif.txt` (une seule ligne,
     `plat` ou `cloche`, issue #498) — pilote le son pour TOUTES les issues
     sans choix propre. Fichier absent, illisible, ou valeur non reconnue →
     défaut inchangé (`plat`), pour ne rien casser silencieusement. Depuis
     l'issue #527, ce fichier n'a plus besoin d'être édité à la main : un
     interrupteur dans le panneau flottant Infrastructure de `new_issue.py`
     (`#pl-zone-son`, routes GET/POST `/son-actif` dans `app/son.py`) l'écrit
     directement, effectif au bip suivant sans redémarrage d'aucun processus.
Les DEUX niveaux sont best-effort (`etat_son_issue` comme `son_actif()`
tolèrent fichier absent/corrompu sans jamais lever) : un bip ne doit jamais
échouer pour une raison de résolution du son.

Tonalité (issue #526, abandonnée comme réglage PAR PROJET en #630) :
`--tonalite <demi-tons>` décale la fréquence de synthèse
(`f_effective = f_base × 2^(demi-tons/12)`), appliqué aux DEUX sons quel que
soit le choix ci-dessus. Depuis #630, le chemin RÉEL du bip (watcher.py,
app/notifications_poller.py) n'appelle plus jamais ce script avec une
tonalité autre que neutre (0) — les clés `.conf` `TONALITE_BIP`/`SCRIPT_BIP`
ne sont plus lues sur ce chemin. `--tonalite` reste utilisé par les boutons
de TEST de l'onglet Configuration (`/tester-bip/<projet>`, `/tester-son`),
volontairement non touchés par #630 (retrait prévu à l'étape 8, en même
temps que l'onglet lui-même). `--tonalite` absent ou `0` → fréquence de base
inchangée (comportement historique).

Usage :
    python3 traitement_fin.py                                   # un bip seul (interrupteur global)
    python3 traitement_fin.py --projet bridge_agent --numero 350 # bip (choix de l'issue si défini) + POST
    python3 traitement_fin.py --tonalite -4                      # bip décalé de -4 demi-tons (tests uniquement)
"""

import argparse
import json
import math
import os
import struct
import subprocess
import sys
import tempfile
import urllib.request
import wave
from pathlib import Path

# etat_son_issue.py vit à la racine du dépôt (parent de scripts/) — ajouté au
# sys.path pour fonctionner quel que soit le cwd depuis lequel ce script est
# lancé (toujours invoqué via `subprocess.run(["python3", <chemin absolu>])`,
# voir notifications.py::bip()).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import etat_son_issue  # noqa: E402
import utils  # noqa: E402 (issue #635 — notifications_reseau_neutralisees)

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

    subprocess.run(["aplay", tmp], capture_output=True)
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

    subprocess.run(["aplay", tmp], capture_output=True)
    os.remove(tmp)


def son_actif() -> str:
    """Lit `FICHIER_SON_ACTIF` ('plat' ou 'cloche') — interrupteur GLOBAL
    (issue #498), appliqué à toute issue sans choix propre (issue #630, voir
    `son_a_jouer()`). Absent, illisible, ou valeur non reconnue → 'plat'
    (défaut inchangé, ne casse rien silencieusement)."""
    try:
        with open(FICHIER_SON_ACTIF, "r", encoding="utf-8") as f:
            valeur = f.read().strip().lower()
        if valeur in ("plat", "cloche"):
            return valeur
    except OSError:
        pass
    return "plat"


def son_a_jouer(projet: str | None, numero) -> str:
    """Son effectivement joué (issue #630) : le choix PAR ISSUE s'il existe
    (`projet`+`numero` fournis ET une entrée enregistrée dans
    `logs/son_issues.json`), sinon l'interrupteur GLOBAL (`son_actif()`).
    Best-effort — `etat_son_issue.son_choisi()` ne lève jamais, mais un
    import/appel imprévisible ne doit quand même jamais faire échouer le
    bip lui-même."""
    if projet and numero is not None:
        try:
            choix = etat_son_issue.son_choisi(projet, int(numero))
        except Exception:
            choix = None
        if choix is not None:
            return choix
    return son_actif()


def _notifier(url: str, projet: str, numero: str):
    """POST JSON {"projet", "numero"} best-effort vers new_issue.py, timeout
    court et échec silencieux — new_issue.py n'est pas toujours lancé, et ce
    canal ne doit jamais faire planter l'appelant. Partagé par
    notifier_fin_issue et notifier_debut_issue (issue #515). Neutralisé
    pendant les tests (issue #635, utils.notifications_reseau_neutralisees) :
    un projet/numéro fictif de test ne doit jamais atteindre un new_issue.py
    réellement lancé sur le poste."""
    if utils.notifications_reseau_neutralisees():
        return
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

    if son_a_jouer(args.projet, args.numero) == "cloche":
        bip(args.tonalite)
    else:
        bip_plat(args.tonalite)

    if args.projet and args.numero:
        notifier_fin_issue(args.projet, args.numero)


if __name__ == "__main__":
    main()
