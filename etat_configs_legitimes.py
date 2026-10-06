#!/usr/bin/env python3
"""
etat_configs_legitimes.py — trace des actions volontaires sur configs/*.conf
faites depuis new_issue.py (issue #724, garde-fou #318 affiné).

Contexte : le garde-fou technique #318 (watcher.py, _empreinte_configs /
_restaurer_configs_modifies) compare configs/*.conf avant/après chaque
traitement mode_write et annule TOUT changement détecté — rôle à garder
intact pour une modification faite PAR une issue (CCL/CCW). Mais configs/
est commun à TOUS les projets, et trois gestes volontaires d'Alain y
écrivent aussi depuis new_issue.py, qui peut tourner pendant qu'une issue
mode_write est en cours dans un tout autre projet : création de projet
(`nouveau_projet.ecrire_conf`), suppression de projet
(`supprimer_projet._supprimer_conf`), enregistrement de l'onglet
Configuration (`app/projets.sauvegarder_conf`). Ce module leur donne un
moyen de laisser une trace horodatée, consultée par le garde-fou avant de
restaurer quoi que ce soit : une entrée postérieure au début du traitement
de l'issue court-circuite la restauration pour ce `.conf`.

Stockage : `logs/configs_legitimes.json`, un dict `{nom_fichier: instant_unix}`
— écriture atomique + verrou anti-collision, même mécanisme que
`etat_son_issue.py`/`etat_rate_limit.py`.

Seul ce module ÉCRIT sur demande de new_issue.py : `enregistrer()` n'est
appelée que par `nouveau_projet.py`, `supprimer_projet.py` et
`app/projets.py`. Le code de traitement d'une issue (watcher.py et ce qu'il
invoque — lancer_claude, traiter_issue) n'appelle jamais `enregistrer()`,
seulement `instant_legitime()` en lecture — une issue ne peut donc pas
s'ajouter elle-même à cette trace via le fonctionnement normal du bridge.
"""

import json
import logging
import os
import time
from pathlib import Path

log = logging.getLogger("etat_configs_legitimes")

CHEMIN_ETAT   = Path(__file__).resolve().parent / "logs" / "configs_legitimes.json"
CHEMIN_VERROU = CHEMIN_ETAT.with_suffix(".lock")

DELAI_VERROU_S = 2.0   # attente max pour obtenir le verrou avant d'abandonner

# Durée de validité d'une entrée (secondes) : largement au-delà du TIMEOUT
# maximal d'une issue mode_write (900s en-tête + marge pour les relances) —
# une entrée plus vieille que ça ne peut plus concerner un traitement encore
# en cours ; le garde-fou retrouve alors son comportement strict pour ce
# fichier (test 6 : trace expirée).
DUREE_VALIDITE_S = 3600


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
    """Lit `logs/configs_legitimes.json` — best-effort, jamais d'exception.
    Fichier absent/corrompu → dict vide (comportement inchangé, ne casse rien)."""
    try:
        donnees = json.loads(CHEMIN_ETAT.read_text(encoding="utf-8"))
        return donnees if isinstance(donnees, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _ecrire(donnees: dict) -> bool:
    """Écriture atomique (fichier temporaire + `os.replace`) sous verrou —
    même mécanisme que `etat_son_issue.py::_ecrire`. Retourne True en succès,
    False si le verrou n'a pas pu être obtenu ou en cas d'erreur disque
    (journalisée, jamais levée)."""
    if not _acquerir_verrou():
        log.warning("Verrou non obtenu — écriture de configs_legitimes.json abandonnée.")
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


def _purger(donnees: dict, maintenant: float) -> dict:
    """Retire les entrées expirées (> DUREE_VALIDITE_S) ou de type invalide."""
    return {nom: instant for nom, instant in donnees.items()
            if isinstance(instant, (int, float)) and maintenant - instant < DUREE_VALIDITE_S}


def enregistrer(nom_conf: str, maintenant: float | None = None) -> bool:
    """Enregistre que `nom_conf` (ex. 'annuairetoken.conf') vient d'être créé,
    modifié ou supprimé par un geste volontaire depuis new_issue.py. Horodate
    à l'instant présent (ou `maintenant`, pour figer l'heure dans les tests).
    Purge au passage les entrées expirées. Best-effort : ne lève jamais — une
    erreur d'écriture ici ne doit jamais faire échouer l'action utilisateur
    sous-jacente (création/suppression de projet, enregistrement du .conf)."""
    instant = time.time() if maintenant is None else maintenant
    donnees = _purger(_lire(), instant)
    donnees[nom_conf] = instant
    return _ecrire(donnees)


def instant_legitime(nom_conf: str, maintenant: float | None = None) -> float | None:
    """Horodatage de la dernière action légitime connue sur `nom_conf`, ou
    None si aucune (absente ou expirée). `maintenant` permet aux tests de
    figer l'heure — sans lui, l'horloge système. Lecture seule : c'est la
    fonction appelée par le garde-fou de watcher.py."""
    instant = time.time() if maintenant is None else maintenant
    donnees = _purger(_lire(), instant)
    valeur = donnees.get(nom_conf)
    return valeur if isinstance(valeur, (int, float)) else None
