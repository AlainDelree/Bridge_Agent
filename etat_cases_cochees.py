#!/usr/bin/env python3
"""
etat_cases_cochees.py — état serveur des cases « traité/lu » de l'onglet
Résultats (issue #629, étape 5a de la refonte web — ARCHITECTURE.md §6).

Contexte : jusqu'ici, la case « traité/lu » de chaque ligne Résultats
(`static/js/app.js::basculerCocheResultat`, clé localStorage
`resultat-coche:<projet>:<numero>`) vit UNIQUEMENT dans le localStorage du
navigateur — état perdu après un plantage du PC, différent selon l'adresse
d'accès (localhost vs LAN), clés accumulées sans fin. Décision d'Alain :
faire passer cet état côté serveur.

Cette étape (5a) n'a livré QUE ce module de stockage + les routes Flask
(`app/cases_cochees.py`) ; le front (`static/js/resultats_coches.js`) les
appelle depuis l'étape 5b (#636), avec reprise idempotente du localStorage
existant via `importer_cases` ci-dessous.

Même modèle que `etat_rate_limit.py` (issue #615) : petit fichier JSON sous
`logs/`, écriture atomique (fichier temporaire + `os.replace`) protégée par
un verrou anti-collision — nécessaire dès que plusieurs requêtes Flask
concurrentes (threaded=True, cf. `new_issue.py`) peuvent cocher/décocher au
même instant.

Format du fichier : `{"<nom_projet>": [<numero>, <numero>, ...], ...}` — les
numéros d'un projet sont dédoublonnés, non triés en stockage (l'ordre n'a
aucune importance fonctionnelle ; `lire_cases_cochees` les trie à la
lecture).
"""

import json
import os
import time
from pathlib import Path

from plafond_nettoyage import numeros_perimes

CHEMIN_ETAT   = Path(__file__).resolve().parent / "logs" / "etat_cases_cochees.json"
CHEMIN_VERROU = CHEMIN_ETAT.with_suffix(".lock")

DELAI_VERROU_S = 2.0   # attente max pour obtenir le verrou avant d'abandonner l'écriture

# Plafond du réglage « limite d'issues par projet » (app/issues.py::
# LIMITE_ISSUES_MAX) : une issue dont le numéro est inférieur ou égal à
# (plus grand numéro connu pour ce projet - PLAFOND_NETTOYAGE) ne peut
# structurellement plus apparaître dans la liste Résultats d'aucun projet —
# sa coche peut donc être nettoyée sans risque de la faire réapparaître
# décochée à tort sous les yeux d'Alain.
PLAFOND_NETTOYAGE = 50


def _acquerir_verrou(delai_s: float = DELAI_VERROU_S) -> bool:
    fin = time.monotonic() + delai_s
    while time.monotonic() < fin:
        try:
            fd = os.open(str(CHEMIN_VERROU), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            return True
        except FileExistsError:
            time.sleep(0.05)
    return False


def _liberer_verrou():
    try:
        CHEMIN_VERROU.unlink()
    except FileNotFoundError:
        pass
    except OSError:
        pass


def _lire() -> dict:
    """Lit l'état complet, best-effort (jamais d'exception) : `{}` si le
    fichier est absent, corrompu, ou ne contient pas un objet JSON."""
    try:
        donnees = json.loads(CHEMIN_ETAT.read_text(encoding="utf-8"))
        return donnees if isinstance(donnees, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _ecrire(donnees: dict) -> tuple[bool, str | None]:
    """Écriture atomique protégée par verrou (même pattern que
    `etat_rate_limit.maj_rate_limit`). Retourne `(True, None)` en succès, ou
    `(False, message_erreur)` sinon."""
    if not _acquerir_verrou():
        return False, "Verrou non obtenu — écriture abandonnée."
    try:
        CHEMIN_ETAT.parent.mkdir(parents=True, exist_ok=True)
        tmp = CHEMIN_ETAT.with_name(CHEMIN_ETAT.name + f".tmp{os.getpid()}")
        tmp.write_text(json.dumps(donnees, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, CHEMIN_ETAT)
        return True, None
    except OSError as e:
        return False, str(e)
    finally:
        _liberer_verrou()


def lire_cases_cochees(nom_projet: str) -> list[int]:
    """Liste triée des numéros cochés pour `nom_projet` (vide si aucun)."""
    return sorted(_lire().get(nom_projet, []))


def cocher_issue(nom_projet: str, numero: int) -> tuple[bool, str | None]:
    """Ajoute `numero` aux cases cochées de `nom_projet`. Idempotent : déjà
    coché → succès immédiat, aucune écriture disque."""
    donnees = _lire()
    numeros = donnees.setdefault(nom_projet, [])
    if numero in numeros:
        return True, None
    numeros.append(numero)
    return _ecrire(donnees)


def decocher_issue(nom_projet: str, numero: int) -> tuple[bool, str | None]:
    """Retire `numero` des cases cochées de `nom_projet`. Idempotent : déjà
    décoché (ou projet absent de l'état) → succès immédiat, aucune écriture
    disque."""
    donnees = _lire()
    numeros = donnees.get(nom_projet, [])
    if numero not in numeros:
        return True, None
    numeros = [n for n in numeros if n != numero]
    if numeros:
        donnees[nom_projet] = numeros
    else:
        donnees.pop(nom_projet, None)
    return _ecrire(donnees)


def importer_cases(cases: list) -> tuple[bool, int, str | None]:
    """Import en masse, idempotent (issue #629) : `cases` =
    `[{"projet": ..., "numero": ...}, ...]`, potentiellement plusieurs
    projets à la fois — le localStorage du navigateur n'est pas scindé par
    projet, contrairement à ce fichier. Servira à la reprise de l'existant à
    l'étape 5b : rejouer le même import plusieurs fois de suite produit le
    même état final (les entrées déjà présentes sont ignorées).

    Toute entrée mal formée (`projet` absent/vide, `numero` non entier) est
    ignorée silencieusement plutôt que de faire échouer tout l'import.
    Retourne `(ok, nb_ajoutees, erreur)`."""
    donnees = _lire()
    nb_ajoutees = 0
    for case in cases:
        if not isinstance(case, dict):
            continue
        projet = case.get("projet")
        numero = case.get("numero")
        if not projet or isinstance(numero, bool) or not isinstance(numero, int):
            continue
        numeros = donnees.setdefault(projet, [])
        if numero not in numeros:
            numeros.append(numero)
            nb_ajoutees += 1
    if nb_ajoutees == 0:
        return True, 0, None
    ok, erreur = _ecrire(donnees)
    return ok, (nb_ajoutees if ok else 0), erreur


def nettoyer_anciennes(plafond: int = PLAFOND_NETTOYAGE) -> tuple[bool, int, str | None]:
    """Nettoyage au démarrage de `new_issue.py` (issue #629), SANS AUCUN
    appel GitHub : pour chaque projet, calcule le plus grand numéro connu
    PARMI LES CASES COCHÉES ELLES-MÊMES (aucune autre source disponible sans
    appel réseau), et retire celles dont le numéro est inférieur ou égal à
    (ce maximum - `plafond`) — ces issues sont trop anciennes pour pouvoir
    encore apparaître dans la liste Résultats d'un projet (bornée à
    `plafond` issues au maximum par le réglage « limite par projet », voir
    `app/issues.py::LIMITE_ISSUES_MAX`), donc leur coche ne sera plus jamais
    consultée. Retourne `(ok, nb_supprimees, erreur)`."""
    donnees = _lire()
    nb_supprimees = 0
    modifie = False
    for projet, numeros in list(donnees.items()):
        a_retirer = numeros_perimes(numeros, plafond)
        if not a_retirer:
            continue
        restants = [n for n in numeros if n not in a_retirer]
        nb_supprimees += len(numeros) - len(restants)
        modifie = True
        if restants:
            donnees[projet] = restants
        else:
            donnees.pop(projet, None)
    if not modifie:
        return True, 0, None
    ok, erreur = _ecrire(donnees)
    return ok, (nb_supprimees if ok else 0), erreur


def supprimer_projet(nom_projet: str) -> tuple[bool, str | None]:
    """À la suppression d'un projet (flux existant de #587,
    `supprimer_projet.py`) : retire toutes ses cases cochées. Idempotent :
    projet déjà absent de l'état → succès immédiat, aucune écriture disque."""
    donnees = _lire()
    if nom_projet not in donnees:
        return True, None
    donnees.pop(nom_projet, None)
    return _ecrire(donnees)
