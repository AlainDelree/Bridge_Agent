#!/usr/bin/env python3
"""
etat_son_issue.py — choix du son (plat/cloche) PAR ISSUE (issue #630).

Contexte : l'interrupteur GLOBAL plat/cloche (`scripts/son_actif.txt`, issues
#498/#527) reste la règle par défaut. Cette issue ajoute la possibilité de
basculer UNE issue précise (projet + numéro) en plat ou en cloche pour
elle-même, sans toucher au réglage global ni aux autres issues. Le réglage PAR
PROJET envisagé un temps (tonalité `TONALITE_BIP`, script `SCRIPT_BIP`) est
abandonné au profit de ce choix PAR ISSUE, plus fin.

Stockage : `logs/son_issues.json`, un dict `{projet: {numero_str: "plat"|
"cloche"}}` — écriture atomique + verrou anti-collision, même mécanisme que
`etat_rate_limit.py` (issue #615) : `scripts/traitement_fin.py` (process
séparé, un par bip) et le process Flask de `new_issue.py` (routes de
`app/son_issue.py`, nettoyage au démarrage) écrivent tous les deux ce fichier.

Nettoyage (même règle que les cases cochées côté navigateur, `resultat-coche:`
dans `static/js/app.js`/`persistance.js`) : purge, PAR PROJET, des entrées dont
le numéro est ≤ (plus grand numéro connu de ce projet dans ce fichier − 50) —
`nettoyer_entrees_perimees()`, appelée au démarrage de `new_issue.py`. Purge
totale d'un projet — `nettoyer_projet()` — à sa suppression (`supprimer_projet.py`).

Aucune dépendance à Flask : les fonctions reçoivent tout en argument (projet,
numéro), sur le même principe que `notifications.py`/`etat_rate_limit.py`.
"""

import json
import logging
import os
import time
from pathlib import Path

log = logging.getLogger("etat_son_issue")

CHEMIN_ETAT   = Path(__file__).resolve().parent / "logs" / "son_issues.json"
CHEMIN_VERROU = CHEMIN_ETAT.with_suffix(".lock")

DELAI_VERROU_S      = 2.0   # attente max pour obtenir le verrou avant d'abandonner
SONS_VALIDES         = ("plat", "cloche")
MARGE_CONSERVATION_N = 50   # nombre d'issues récentes conservées par projet (nettoyage)


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
    except OSError as e:
        log.warning(f"Libération du verrou {CHEMIN_VERROU.name} impossible ({e}).")


def _lire() -> dict:
    """Lit `logs/son_issues.json` — best-effort, jamais d'exception. Fichier
    absent/corrompu → dict vide (comportement inchangé, ne casse rien)."""
    try:
        donnees = json.loads(CHEMIN_ETAT.read_text(encoding="utf-8"))
        return donnees if isinstance(donnees, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _ecrire(donnees: dict) -> bool:
    """Écriture atomique (fichier temporaire + `os.replace`) sous verrou —
    même mécanisme que `etat_rate_limit.py::maj_rate_limit`. Retourne True en
    succès, False si le verrou n'a pas pu être obtenu ou en cas d'erreur
    disque (journalisée, jamais levée)."""
    if not _acquerir_verrou():
        log.warning("Verrou non obtenu — écriture de son_issues.json abandonnée.")
        return False
    try:
        CHEMIN_ETAT.parent.mkdir(parents=True, exist_ok=True)
        tmp = CHEMIN_ETAT.with_name(CHEMIN_ETAT.name + f".tmp{os.getpid()}")
        tmp.write_text(json.dumps(donnees, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, CHEMIN_ETAT)
        return True
    except OSError as e:
        log.warning(f"Écriture de {CHEMIN_ETAT.name} impossible ({e}).")
        return False
    finally:
        _liberer_verrou()


def son_choisi(projet: str, numero: int) -> str | None:
    """Choix enregistré pour CETTE issue (`projet` + `numero`), ou None si
    aucun choix n'a été fait (l'appelant doit alors retomber sur l'interrupteur
    global `son_actif.txt`). Best-effort, jamais d'exception."""
    entree = _lire().get(str(projet), {})
    valeur = entree.get(str(int(numero))) if isinstance(entree, dict) else None
    return valeur if valeur in SONS_VALIDES else None


def definir_son(projet: str, numero: int, son: str | None) -> tuple[bool, str | None]:
    """Enregistre le choix pour cette issue (`son` dans SONS_VALIDES), ou le
    retire (`son` None ou vide → l'interrupteur global reprend la main pour
    cette issue). Retourne (succes, erreur)."""
    if son is not None and son not in SONS_VALIDES:
        return False, f"Valeur invalide (attendu 'plat', 'cloche' ou null) : {son!r}"

    donnees = _lire()
    cle_projet = str(projet)
    cle_numero = str(int(numero))

    if son is None:
        entree = donnees.get(cle_projet)
        if isinstance(entree, dict) and cle_numero in entree:
            entree.pop(cle_numero)
            if not entree:
                donnees.pop(cle_projet, None)
        else:
            return True, None  # rien à retirer — no-op réussi
    else:
        donnees.setdefault(cle_projet, {})[cle_numero] = son

    return _ecrire(donnees), None


def nettoyer_projet(projet: str) -> bool:
    """Retire TOUTES les entrées d'un projet — appelé à sa suppression
    (`supprimer_projet.py`). No-op réussi si le projet n'a aucune entrée."""
    donnees = _lire()
    if str(projet) not in donnees:
        return True
    donnees.pop(str(projet), None)
    return _ecrire(donnees)


def nettoyer_entrees_perimees(marge: int = MARGE_CONSERVATION_N) -> dict:
    """Purge, PROJET PAR PROJET, les entrées dont le numéro est ≤ (plus grand
    numéro connu de CE projet dans ce fichier − `marge`) — même règle que le
    nettoyage des cases cochées côté navigateur. Appelée au démarrage de
    `new_issue.py`. Retourne {projet: nb_entrees_retirees} pour les projets
    effectivement modifiés (dict vide si rien à purger)."""
    donnees = _lire()
    retirees: dict[str, int] = {}
    modifie = False

    for projet, entree in list(donnees.items()):
        if not isinstance(entree, dict) or not entree:
            continue
        try:
            numeros = {int(n): n for n in entree}
        except (TypeError, ValueError):
            continue
        plus_grand = max(numeros)
        seuil = plus_grand - marge
        a_retirer = [brut for n, brut in numeros.items() if n <= seuil]
        if not a_retirer:
            continue
        for brut in a_retirer:
            entree.pop(brut, None)
        modifie = True
        retirees[projet] = len(a_retirer)
        if not entree:
            donnees.pop(projet, None)

    if modifie:
        _ecrire(donnees)
    return retirees
