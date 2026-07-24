#!/usr/bin/env python3
"""Test de non-régression — issue #217.

Vérifie que l'auto-extinction du watcher (issue #200) ne se déclenche PAS
immédiatement après un traitement réel, même si ce traitement s'est étiré
au-delà du délai d'inactivité (plusieurs timeouts/retries en cascade), et
qu'elle se déclenche bien lorsque plus rien n'est traitable.

Le test pilote le VRAI `watcher.main()` avec une horloge monotone mockée
(`time.monotonic` / `time.sleep` patchés) et des `lister_issues` /
`traiter_issue` scriptés. Il reproduit le scénario du log réel
`watcher-scrabble.log` (24/07/2026) : une issue détectée, traitement long
(~23 min > délai 20 min) avec succès, puis vérification que le watcher
poursuit son cycle au lieu de s'éteindre « aussitôt après le succès ».

Exécution :  python3 tests/test_auto_extinction_217.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.

Régression historique : avec le code d'AVANT #217 (réarmement de
`derniere_activite` uniquement AVANT le traitement, jamais après), le
scénario 1 provoquait `sys.exit(0)` dès le 2ᵉ cycle — soit une extinction
14 s après un succès réel. Ce test échoue sur ce code et passe sur le code
corrigé.
"""

import sys
import tempfile
from pathlib import Path
from unittest import mock

# Le test vit dans tests/ ; le module watcher.py est à la racine du projet.
RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import watcher  # noqa: E402


class StopLoop(Exception):
    """Sentinelle : simule le sys.exit(0) de l'extinction pour rompre la boucle
    infinie de main() sans tuer le process de test."""


def _issue(numero, traitable=True):
    """Fabrique une issue minimale. traitable=False => label 'done' (ignorée
    par issue_traitable, comme une issue déjà finalisée)."""
    labels = [] if traitable else [{"name": watcher.LABEL_FAIT}]
    return {"number": numero, "title": f"issue #{numero}", "body": "", "labels": labels}


def _ecrire_conf(rep_travail: Path) -> Path:
    """Écrit un .conf minimal valide dans un fichier temporaire."""
    conf = tempfile.NamedTemporaryFile(
        mode="w", suffix=".conf", delete=False, encoding="utf-8"
    )
    conf.write(
        "NOM = test_ext_217\n"
        "DEPOT = exemple/depot-test\n"
        f"REP_TRAVAIL = {rep_travail}\n"
        "TOPIC_NTFY = test-topic\n"
        "INTERVALLE = 1\n"
        "DELAI_INACTIVITE_MIN = 20\n"
    )
    conf.close()
    return Path(conf.name)


def executer_scenario(plan, sleeps, long_proc_s=1380.0, cap=40):
    """Exécute watcher.main() sur un scénario scripté et renvoie un rapport.

    plan       : liste de listes d'issues renvoyées par lister_issues(),
                 une entrée par cycle (au-delà => [] pour toujours).
    sleeps     : liste des avances d'horloge appliquées par chaque time.sleep()
                 (une par cycle ; au-delà => dernière valeur répétée).
    long_proc_s: durée simulée du traitement d'UNE issue traitable (avance
                 d'horloge dans traiter_issue). 1380 s = ~23 min > délai 20 min.
    cap        : nombre max de cycles avant abandon (garde anti-boucle).

    Renvoie {"exited": bool, "cycles_avant_exit": int|None}.
    cycles_avant_exit = nombre de cycles (appels lister_issues) effectués
    avant que l'extinction ne survienne.
    """
    horloge = {"t": 0.0}
    compteur = {"lister": 0}
    etat = {"exited": False, "cycles_avant_exit": None}

    def fake_monotonic():
        return horloge["t"]

    def fake_sleep(_):
        i = min(compteur["lister"] - 1, len(sleeps) - 1)
        horloge["t"] += sleeps[i] if sleeps else 1.0

    def fake_lister():
        i = compteur["lister"]
        compteur["lister"] += 1
        if compteur["lister"] > cap:
            # Garde-fou : si l'extinction ne survient jamais, on rompt.
            raise StopLoop()
        return plan[i] if i < len(plan) else []

    def fake_traiter(issue, dry_run):
        # Simule un traitement long (timeouts + retries en cascade) : seule une
        # issue réellement traitable consomme du temps.
        if watcher.issue_traitable(issue):
            horloge["t"] += long_proc_s

    def fake_exit(code=0):
        etat["exited"] = True
        etat["cycles_avant_exit"] = compteur["lister"]
        raise StopLoop()

    rep_travail = Path(tempfile.mkdtemp(prefix="rep_test_217_"))
    conf = _ecrire_conf(rep_travail)

    argv = ["watcher.py", "--config", str(conf)]
    with mock.patch.object(watcher.time, "monotonic", fake_monotonic), \
         mock.patch.object(watcher.time, "sleep", fake_sleep), \
         mock.patch.object(watcher, "lister_issues", fake_lister), \
         mock.patch.object(watcher, "traiter_issue", fake_traiter), \
         mock.patch.object(watcher, "rafraichir_depot", lambda *a, **k: None), \
         mock.patch.object(watcher.sys, "exit", fake_exit), \
         mock.patch.object(watcher.sys, "argv", argv):
        try:
            watcher.main()
        except StopLoop:
            pass

    conf.unlink(missing_ok=True)
    return etat


def scenario_1_traitement_long_puis_issue_restante():
    """Reproduit le bug #217 : issue détectée, traitement de ~23 min (> 20 min),
    succès, PUIS une autre issue reste traitable. Le watcher NE doit PAS
    s'éteindre au cycle suivant le succès ; il doit poursuivre le travail."""
    plan = [
        [_issue(238)],   # cycle 1 : traitable → ~23 min de traitement
        [_issue(239)],   # cycle 2 : une autre issue reste → ~23 min
        [],              # cycle 3 : plus rien à traiter
    ]
    # Avances d'horloge de time.sleep() par cycle : ~intervalle pendant le
    # travail, puis un long silence (2000 s) une fois inactif pour laisser
    # l'horloge dépasser le délai et permettre l'extinction légitime.
    sleeps = [1.0, 1.0, 2000.0]
    rap = executer_scenario(plan, sleeps)

    # AVEC le correctif : cycles 2 et 3 s'exécutent (le traitement long ne
    # provoque pas d'extinction prématurée), l'extinction ne survient qu'au
    # cycle 4, une fois réellement inactif.
    # SANS le correctif : extinction dès le cycle 2 (cycles_avant_exit == 1).
    assert rap["exited"], "Le watcher aurait dû finir par s'éteindre (inactif)."
    assert rap["cycles_avant_exit"] >= 3, (
        f"Extinction prématurée : survenue après seulement "
        f"{rap['cycles_avant_exit']} cycle(s) — le traitement long a déclenché "
        f"l'extinction alors qu'une issue restait traitable (bug #217 non corrigé)."
    )
    return rap


def scenario_2_inactivite_reelle_declenche_extinction():
    """Contrôle négatif : aucune issue traitable, l'horloge vieillit au-delà du
    délai → l'extinction DOIT bien se déclencher (le correctif ne la neutralise
    pas)."""
    plan = [[]]  # jamais rien de traitable
    sleeps = [2000.0]  # une seule attente > délai (1200 s) suffit
    rap = executer_scenario(plan, sleeps)
    assert rap["exited"], "Extinction attendue en inactivité réelle, absente."
    return rap


def scenario_3_issue_non_traitable_ne_bloque_pas():
    """Une issue présente mais NON traitable (label 'done') ne doit pas empêcher
    l'extinction : pas de travail réel → pas de réarmement."""
    plan = [[_issue(300, traitable=False)]]
    sleeps = [2000.0]
    rap = executer_scenario(plan, sleeps)
    assert rap["exited"], (
        "Une issue non-traitable ('done') ne doit pas empêcher l'extinction."
    )
    return rap


def main():
    tests = [
        ("traitement long puis issue restante (bug #217)",
         scenario_1_traitement_long_puis_issue_restante),
        ("inactivité réelle → extinction",
         scenario_2_inactivite_reelle_declenche_extinction),
        ("issue non-traitable → extinction non bloquée",
         scenario_3_issue_non_traitable_ne_bloque_pas),
    ]
    echecs = 0
    for nom, fn in tests:
        try:
            rap = fn()
            print(f"  ✓ {nom}  ({rap})")
        except AssertionError as e:
            echecs += 1
            print(f"  ✗ {nom}\n      {e}")
        except Exception as e:  # noqa: BLE001
            echecs += 1
            print(f"  ✗ {nom} — erreur inattendue : {type(e).__name__}: {e}")

    if echecs:
        print(f"\n❌ {echecs} scénario(s) en échec.")
        return 1
    print("\n✅ Tous les scénarios passent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
