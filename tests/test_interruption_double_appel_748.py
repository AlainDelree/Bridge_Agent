#!/usr/bin/env python3
"""Test de non-régression — issue #748 (point 3 : protection côté serveur).

Avant cette issue, AUCUNE garde n'existait autour de route_interrompre
(app/interruption.py) : vérifié par lecture de code (aucun threading.Lock, aucun
état « en cours » par projet) ET par le scénario
`scenario_sans_garde_deux_appels_dupliquent_tout` ci-dessous, qui appelle
`_executer_interruption` (le cœur technique, factorisé mais fonctionnellement
identique à l'ancien corps de route_interrompre) directement depuis deux
threads : les DEUX s'exécutent entièrement, dupliquant label + étapes +
commentaire GitHub — exactement ce qu'aurait produit un double clic rapproché
sur le bouton « Interrompre » avant #748 (incident Scrabble #452 : appel déjà
long de plusieurs secondes, aucun retour visuel, second clic pendant
l'attente).

`scenario_double_appel_concurrent_second_refuse` vérifie la correction :
route_interrompre() pose désormais un verrou par PROJET (pas par issue —
interrompre_linux/interrompre_windows agissent sur l'arbre ENTIER du watcher
d'un projet, pas sur une issue précise) ; un second appel pendant qu'un
premier tourne déjà pour ce projet répond IMMÉDIATEMENT (409, deja_en_cours)
SANS exécuter la moindre étape.

Aucun `gh` ni sous-processus réel : `_executer_interruption` est appelée avec
un faux cœur technique (compteur + threading.Event pour piloter la durée du
premier appel).

Exécution :  python3 tests/test_interruption_double_appel_748.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import flask  # noqa: E402

import app.interruption as interruption  # noqa: E402

APP_FLASK = flask.Flask(__name__)
CFG_TEST = SimpleNamespace(depot="AlainDelree/depot-test748", nom="projet748")


def _appeler_interrompre(payload: dict):
    with APP_FLASK.test_request_context("/interrompre", json=payload):
        resp = interruption.route_interrompre()
    if isinstance(resp, tuple):
        body, code = resp
    else:
        body, code = resp, 200
    return body.get_json(), code


def scenario_sans_garde_deux_appels_dupliquent_tout():
    """Documente le comportement ANTÉRIEUR à #748 : sans la garde de
    route_interrompre (appel direct du cœur technique, deux threads
    concurrents), les deux exécutions tournent intégralement — double
    label, double jeu d'étapes, double commentaire."""
    compteur = {"n": 0}
    verrou_compteur = threading.Lock()

    def _faux_label(depot, numero, label):
        return "succes", "label posé"

    def _faux_etapes_linux(cfg):
        with verrou_compteur:
            compteur["n"] += 1
        time.sleep(0.05)
        return [{"etape": "arreter_arbre_watcher", "statut": "succes", "message": "ok"}]

    def _faux_commentaire(depot, numero, message):
        return "succes", "commentaire posté"

    with mock.patch.object(interruption, "_ajouter_label_gh", _faux_label), \
         mock.patch.object(interruption, "interrompre_linux", _faux_etapes_linux), \
         mock.patch.object(interruption, "_commenter_gh", _faux_commentaire):

        resultats = [None, None]

        def _lancer(i):
            resultats[i] = interruption._executer_interruption(
                CFG_TEST.depot, 452, CFG_TEST, "linux")

        t1 = threading.Thread(target=_lancer, args=(0,))
        t2 = threading.Thread(target=_lancer, args=(1,))
        t1.start(); t2.start()
        t1.join(timeout=5); t2.join(timeout=5)

    assert compteur["n"] == 2, (
        f"sans garde, les DEUX appels auraient dû exécuter entièrement les étapes "
        f"(duplication) — compteur={compteur['n']}, reproduit le risque pré-#748."
    )
    assert resultats[0]["succes"] and resultats[1]["succes"]
    return {"executions": compteur["n"]}


def scenario_double_appel_concurrent_second_refuse():
    """Avec route_interrompre (garde par projet, issue #748) : pendant qu'un
    premier appel tourne pour « projet748 », un second appel CONCURRENT pour
    ce MÊME projet répond immédiatement « déjà en cours » (409), sans jamais
    appeler le cœur technique une seconde fois."""
    interruption._projets_en_interruption.clear()
    compteur = {"n": 0}
    debloquer = threading.Event()
    premier_entre = threading.Event()

    def _faux_executer(depot, numero, cfg, agent):
        compteur["n"] += 1
        premier_entre.set()
        debloquer.wait(timeout=5)
        return dict(succes=True, agent=agent, statut_global="ok", etapes=[])

    resultat_premier = {}

    def _appel_bloquant():
        with mock.patch.object(interruption, "projet_par_depot", lambda d: CFG_TEST):
            resultat_premier["corps"], resultat_premier["code"] = _appeler_interrompre(
                {"depot": CFG_TEST.depot, "numero": 452, "labels": []})

    try:
        with mock.patch.object(interruption, "_executer_interruption", _faux_executer), \
             mock.patch.object(interruption, "projet_par_depot", lambda d: CFG_TEST):

            t1 = threading.Thread(target=_appel_bloquant)
            t1.start()
            assert premier_entre.wait(timeout=5), "le premier appel n'a jamais atteint le cœur technique"

            # Second appel CONCURRENT pour le MÊME projet, pendant que le
            # premier est toujours bloqué dans _faux_executer.
            corps_second, code_second = _appeler_interrompre(
                {"depot": CFG_TEST.depot, "numero": 453, "labels": []})

            assert code_second == 409, f"attendu 409, obtenu {code_second} : {corps_second}"
            assert corps_second.get("deja_en_cours") is True, corps_second
            assert corps_second.get("succes") is False, corps_second
            assert compteur["n"] == 1, (
                f"le second appel n'aurait jamais dû exécuter le cœur technique "
                f"(compteur={compteur['n']})"
            )

            debloquer.set()
            t1.join(timeout=5)
    finally:
        debloquer.set()
        interruption._projets_en_interruption.clear()

    assert resultat_premier["code"] == 200, resultat_premier
    assert resultat_premier["corps"]["succes"] is True, resultat_premier
    assert compteur["n"] == 1, "le premier appel doit avoir exécuté le cœur technique exactement une fois"

    # Le verrou ne doit plus être tenu une fois les deux appels terminés —
    # un futur appel légitime doit pouvoir repasser.
    assert "projet748" not in interruption._projets_en_interruption
    return {"executions": compteur["n"], "code_second_appel": code_second}


def main():
    tests = [
        ("sans garde (appel direct du cœur) : deux appels concurrents dupliquent tout",
         scenario_sans_garde_deux_appels_dupliquent_tout),
        ("avec route_interrompre : second appel concurrent → 409 déjà en cours, rien refait",
         scenario_double_appel_concurrent_second_refuse),
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
