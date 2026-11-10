#!/usr/bin/env python3
"""Test de non-régression — issue #875 : démarrage de session Windows —
sortie en UTF-8, code de sortie lisible, journaux de session bornés.

Vérifie (partie Python seulement — voir le rapport de clôture pour ce qui
reste à essayer sur Windows, le superviseur étant un script PowerShell que
cet environnement Linux ne peut pas exécuter) :
1. `watcher.forcer_utf8` évite le plantage (UnicodeEncodeError) d'un print()
   contenant un caractère absent de cp1252 (la flèche « → » du message de
   mise à jour automatique du dépôt, cause réelle constatée) sur un flux
   simulant la console Windows (TextIOWrapper encodé cp1252) — AVANT
   correctif, le même flux lève bel et bien l'exception, confirmant que le
   scénario reproduit la cause réelle, pas un faux positif.
2. `watcher.forcer_utf8` reste défensif sur un flux qui n'expose pas
   `.reconfigure` (ex. certains flux redirigés) : aucune exception.
3. Le filtre de bruit werkzeug de `new_issue.py` (requêtes /heartbeat et
   fichiers statiques) retient bien les lignes d'accès ordinaires et
   élimine seulement les deux motifs ciblés.
4. `_filtrer_requetes_bruyantes_si_sous_superviseur` n'installe le filtre
   QUE si `BRIDGE_SOUS_SUPERVISEUR_SESSION` est posée — comportement Linux/
   lancer_new_issue.sh (variable absente) strictement inchangé.

Exécution :  python3 tests/test_utf8_codes_sortie_session_875.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import io
import logging
import os
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import watcher  # noqa: E402
import new_issue  # noqa: E402

CARACTERE_PROBLEME = "→"  # celui du message réel de tenter_maj_auto_demarrage()


def _flux_cp1252() -> io.TextIOWrapper:
    """Simule la console Windows : un flux texte encodé cp1252 — même
    encodage que celui retombant par défaut sur un print() Python dont la
    sortie est redirigée vers un fichier sous Windows, sans PYTHONUTF8/
    PYTHONIOENCODING ni reconfigure()."""
    return io.TextIOWrapper(io.BytesIO(), encoding="cp1252")


def scenario_cp1252_plante_sans_correctif():
    """Confirme que le scénario reproduit bien la cause réelle : AVANT tout
    appel à forcer_utf8, écrire le caractère problématique sur un flux
    cp1252 lève UnicodeEncodeError — exactement le plantage constaté dans
    logs\\new_issue-session.log lors de l'essai réel Windows."""
    flux = _flux_cp1252()
    try:
        flux.write(CARACTERE_PROBLEME)
        flux.flush()
        raise AssertionError("cp1252 aurait dû lever UnicodeEncodeError sur « → »")
    except UnicodeEncodeError:
        pass
    return {"cause_reproduite": True}


def scenario_forcer_utf8_evite_le_plantage():
    """Après forcer_utf8(flux), le même caractère s'écrit sans exception, et
    les octets réellement produits sont de l'UTF-8 valide (pas du cp1252
    mal relu — second symptôme constaté : accents mutilés dans le journal)."""
    flux = _flux_cp1252()
    watcher.forcer_utf8(flux)
    flux.write(CARACTERE_PROBLEME)
    flux.flush()
    contenu = flux.buffer.getvalue()
    assert contenu.decode("utf-8") == CARACTERE_PROBLEME, (
        f"octets inattendus après forcer_utf8 : {contenu!r}")
    return {"ecriture_ok": True, "encodage": flux.encoding}


def scenario_forcer_utf8_reste_defensif_sans_reconfigure():
    """Un flux sans `.reconfigure` (ex. certains wrappers de test/CI) ne doit
    jamais faire planter forcer_utf8 lui-même — getattr défensif."""
    class _FluxSansReconfigure:
        pass

    watcher.forcer_utf8(_FluxSansReconfigure())  # ne doit lever aucune exception
    return {"aucune_exception": True}


def _ligne_acces(methode: str, chemin: str) -> str:
    return f'127.0.0.1 - - [10/Nov/2026 12:00:00] "{methode} {chemin} HTTP/1.1" 200 -'


def scenario_filtre_requetes_bruyantes():
    """Le filtre retient /heartbeat et /static/..., laisse passer le reste
    (ex. /envoyer, une requête applicative normale)."""
    filtre = new_issue._FiltreRequetesBruyantes()

    bruyantes = [
        _ligne_acces("GET", "/heartbeat"),
        _ligne_acces("GET", "/heartbeat?t=12345"),
        _ligne_acces("GET", "/static/css/app.css"),
        _ligne_acces("GET", "/static/js/socle/store.js"),
    ]
    normales = [
        _ligne_acces("POST", "/envoyer"),
        _ligne_acces("GET", "/"),
        _ligne_acces("GET", "/issues-attente"),
    ]

    for ligne in bruyantes:
        record = logging.LogRecord("werkzeug", logging.INFO, __file__, 0, ligne, None, None)
        assert filtre.filter(record) is False, f"aurait dû être filtrée : {ligne}"

    for ligne in normales:
        record = logging.LogRecord("werkzeug", logging.INFO, __file__, 0, ligne, None, None)
        assert filtre.filter(record) is True, f"n'aurait pas dû être filtrée : {ligne}"

    return {"bruyantes_filtrees": len(bruyantes), "normales_conservees": len(normales)}


def scenario_filtre_installe_seulement_sous_superviseur():
    """Sans BRIDGE_SOUS_SUPERVISEUR_SESSION (cas Linux / lancer_new_issue.sh
    normal), aucun filtre n'est ajouté au logger werkzeug — comportement
    strictement inchangé. Avec la variable posée (cas du superviseur de
    session Windows), un filtre est ajouté."""
    logger = logging.getLogger("werkzeug")
    nb_avant = len(logger.filters)
    ancienne_valeur = os.environ.pop("BRIDGE_SOUS_SUPERVISEUR_SESSION", None)
    try:
        new_issue._filtrer_requetes_bruyantes_si_sous_superviseur()
        assert len(logger.filters) == nb_avant, "aucun filtre ne doit être ajouté sans la variable"

        os.environ["BRIDGE_SOUS_SUPERVISEUR_SESSION"] = "1"
        new_issue._filtrer_requetes_bruyantes_si_sous_superviseur()
        assert len(logger.filters) == nb_avant + 1, "un filtre doit être ajouté avec la variable posée"
    finally:
        # Nettoyage : retire le(s) filtre(s) ajoutés par ce test, restaure
        # la variable d'environnement — pas d'effet de bord sur les autres
        # tests du dépôt (même logger "werkzeug" partagé par tout le process).
        for f in list(logger.filters):
            if isinstance(f, new_issue._FiltreRequetesBruyantes):
                logger.removeFilter(f)
        if ancienne_valeur is None:
            os.environ.pop("BRIDGE_SOUS_SUPERVISEUR_SESSION", None)
        else:
            os.environ["BRIDGE_SOUS_SUPERVISEUR_SESSION"] = ancienne_valeur

    return {"active_seulement_sous_superviseur": True}


def main():
    tests = [
        ("cp1252 plante bien sur « → » avant correctif (cause réelle reproduite)",
         scenario_cp1252_plante_sans_correctif),
        ("forcer_utf8 évite le plantage et écrit de l'UTF-8 valide",
         scenario_forcer_utf8_evite_le_plantage),
        ("forcer_utf8 reste défensif sans .reconfigure",
         scenario_forcer_utf8_reste_defensif_sans_reconfigure),
        ("filtre werkzeug : /heartbeat et /static/ retirés, le reste conservé",
         scenario_filtre_requetes_bruyantes),
        ("filtre werkzeug installé seulement sous BRIDGE_SOUS_SUPERVISEUR_SESSION",
         scenario_filtre_installe_seulement_sous_superviseur),
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
