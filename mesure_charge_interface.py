#!/usr/bin/env python3
"""mesure_charge_interface.py — échantillonneur CONTINU de la charge de
l'interface web (issue #835 point 3), indépendant de Flask (comme
etat_cases_cochees.py / etat_rate_limit.py) : la couche HTTP (crochets
before_request/after_request, route du résumé page) vit dans
app/charge_interface.py, qui importe ce module.

CE QUI EST MESURÉ, UNE LIGNE JSON PAR MINUTE dans logs/charge_interface.log :
  - secondes de processeur du serveur ET de ses processus fils, en différence
    entre deux échantillons successifs (os.times() : user+system, propres et
    enfants) ;
  - nombre de requêtes HTTP reçues pendant la minute écoulée, leur durée
    totale et leur durée maximale, et la route (gabarit Flask, PAS l'URL
    résolue — voir enregistrer_requete) la plus lente.

AUCUN contenu d'issue, titre, numéro ni secret n'est jamais écrit : seulement
des nombres, un horodatage et un gabarit de route Flask (ex.
« /issue/<nom_projet>/<numero> », jamais la valeur réelle substituée).

Compteurs protégés par un verrou (_VERROU) : le serveur de développement
Flask tourne avec threaded=True (new_issue.py), plusieurs requêtes peuvent
donc appeler enregistrer_requete() en même temps. Les crochets eux-mêmes
restent volontairement légers (une lecture d'horloge, une addition) — jamais
d'E/S disque par requête, seule la boucle d'échantillonnage (une fois par
minute) écrit sur disque.

Ne doit JAMAIS empêcher le démarrage du serveur ni ralentir une requête : la
boucle d'échantillonnage tourne dans un thread daemon (démarré explicitement
par new_issue.py, comme surveiller_heartbeat/surveiller_transitions) et
rattrape toute exception sans jamais s'arrêter ni remonter."""

import json
import logging
import os
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

DOSSIER_SCRIPT = Path(__file__).resolve().parent
sys.path.insert(0, str(DOSSIER_SCRIPT))

from watcher import JournalRotatifDate  # noqa: E402 — réutilise la rotation par taille existante

FICHIER_JOURNAL = DOSSIER_SCRIPT / "logs" / "charge_interface.log"
TAILLE_MAX_OCTETS = 5 * 1024 * 1024   # 5 Mo par fichier (issue #835 point 3 : "quelques mégaoctets")
NB_ARCHIVES = 5                        # "quelques archives"
INTERVALLE_ECHANTILLON_S = 60          # une ligne par minute

_verrou = threading.Lock()
_nb_requetes = 0
_duree_totale_s = 0.0
_duree_max_s = 0.0
_route_la_plus_lente = None

_logger = None  # configuré paresseusement, voir _logger_charge()


def _logger_charge():
    """Logger dédié (PAS logging.basicConfig, qui affecterait le logger
    racine) — propagate=False : une ligne de ce journal ne doit jamais
    atterrir aussi dans logs/new_issue.log (sortie standard du serveur)."""
    global _logger
    if _logger is not None:
        return _logger
    FICHIER_JOURNAL.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("bridge_agent.charge_interface")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not logger.handlers:
        handler = JournalRotatifDate(
            str(FICHIER_JOURNAL), maxBytes=TAILLE_MAX_OCTETS, backupCount=NB_ARCHIVES, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
    _logger = logger
    return logger


def differences_cpu(avant, apres) -> float:
    """Secondes de processeur écoulées entre deux appels de `os.times()` —
    utilisateur + système, PROPRES et ENFANTS (les éventuels sous-processus
    git lancés par le serveur, issue #835 point 3). Pure : ne lit jamais
    l'horloge elle-même, pour rester testable sans attendre une minute."""
    return ((apres.user - avant.user) + (apres.system - avant.system)
            + (apres.children_user - avant.children_user)
            + (apres.children_system - avant.children_system))


def enregistrer_requete(route: str, duree_s: float) -> None:
    """Appelée par le crochet after_request (app/charge_interface.py) pour
    CHAQUE requête — sous verrou (compatible serveur multi-fils), mais rien
    d'autre qu'une addition et une comparaison : jamais d'I/O ici."""
    global _nb_requetes, _duree_totale_s, _duree_max_s, _route_la_plus_lente
    with _verrou:
        _nb_requetes += 1
        _duree_totale_s += duree_s
        if duree_s > _duree_max_s:
            _duree_max_s = duree_s
            _route_la_plus_lente = route


def relever_et_remettre_a_zero():
    """Lit puis remet à zéro les compteurs de requêtes — sous verrou, pour
    qu'aucune requête concurrente ne soit comptée deux fois ni perdue.
    Renvoie (nb_requetes, duree_totale_s, duree_max_s, route_la_plus_lente)."""
    global _nb_requetes, _duree_totale_s, _duree_max_s, _route_la_plus_lente
    with _verrou:
        valeurs = (_nb_requetes, _duree_totale_s, _duree_max_s, _route_la_plus_lente)
        _nb_requetes, _duree_totale_s, _duree_max_s, _route_la_plus_lente = 0, 0.0, 0.0, None
    return valeurs


def ligne_echantillon(horodatage, cpu_s, nb_requetes, duree_totale_s, duree_max_s, route_plus_lente) -> str:
    """Ligne JSON d'un échantillon de charge serveur (point 3) — pure,
    aucun contenu d'issue/titre/numéro/secret : seulement des nombres, un
    horodatage et un gabarit de route Flask (jamais l'URL résolue)."""
    return json.dumps({
        "type": "echantillon",
        "horodatage": horodatage,
        "cpu_s": cpu_s,
        "nb_requetes": nb_requetes,
        "duree_totale_s": duree_totale_s,
        "duree_max_s": duree_max_s,
        "route_plus_lente": route_plus_lente,
    }, ensure_ascii=False)


def ligne_resume_precharge(horodatage, nb_issues_preparees, nb_requetes,
                            duree_totale_ms, duree_max_ms, mode) -> str:
    """Ligne JSON du résumé d'une série de préparations envoyée par la page
    (point 4) — pure, mêmes garanties que ligne_echantillon ci-dessus."""
    return json.dumps({
        "type": "resume_precharge",
        "horodatage": horodatage,
        "nb_issues_preparees": nb_issues_preparees,
        "nb_requetes": nb_requetes,
        "duree_totale_ms": duree_totale_ms,
        "duree_max_ms": duree_max_ms,
        "mode": mode,
    }, ensure_ascii=False)


def ecrire_ligne(ligne: str) -> None:
    """Ajoute une ligne (déjà construite par ligne_echantillon/
    ligne_resume_precharge) au journal dédié, rotation par taille incluse."""
    _logger_charge().info(ligne)


def horodatage() -> str:
    """Horodatage UTC au format ISO, seconde près — utilisé pour les deux
    types de ligne (échantillon et résumé de précharge) ; exposée (pas
    préfixée _) car app/charge_interface.py l'appelle aussi pour le résumé."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _boucle_echantillonnage() -> None:
    """Tourne indéfiniment dans un thread daemon (voir demarrer_echantillonnage)
    — une exception sur UN échantillon ne doit jamais arrêter les suivants ni
    remonter au thread principal (le serveur doit continuer à tourner quoi
    qu'il arrive)."""
    cpu_avant = os.times()
    while True:
        time.sleep(INTERVALLE_ECHANTILLON_S)
        try:
            cpu_apres = os.times()
            cpu_s = differences_cpu(cpu_avant, cpu_apres)
            cpu_avant = cpu_apres
            nb_requetes, duree_totale_s, duree_max_s, route = relever_et_remettre_a_zero()
            ecrire_ligne(ligne_echantillon(
                horodatage(), round(cpu_s, 3), nb_requetes,
                round(duree_totale_s, 3), round(duree_max_s, 3), route))
        except Exception as e:   # best-effort strict : jamais d'impact sur le serveur
            print(f"[mesure_charge_interface] échantillon ignoré : {e}", file=sys.stderr)


def demarrer_echantillonnage() -> threading.Thread:
    """Démarre la boucle d'échantillonnage dans un thread daemon (s'arrête
    avec le serveur, jamais retardé) — appelée explicitement par
    new_issue.py, comme surveiller_heartbeat/surveiller_transitions (pas
    depuis app.create_app(), pour ne pas démarrer un thread à chaque création
    d'application de test)."""
    thread = threading.Thread(target=_boucle_echantillonnage, daemon=True)
    thread.start()
    return thread
