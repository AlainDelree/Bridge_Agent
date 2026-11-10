"""diagnostic_copie.py — point d'entrée MINIMAL du journal de diagnostic
durable de la copie presse-papier (issue #878 : clics « sans effet » sur la
case à cocher de l'onglet Résultats, intermittents, juste après un redessin
de ligne ou après une longue inactivité d'onglet).

Désactivé par défaut — voir identite.diagnostic_copie() (réglage
DIAGNOSTIC_COPIE de identite_locale.conf). Ce module n'écrit RIEN quand ce
réglage est désactivé : aucun fichier créé, aucun répertoire de logs/
provoqué par un simple déploiement non configuré.

Volontairement minimal, SANS AUCUNE EXÉCUTION : le corps de la requête est
une ligne de texte brut déjà formatée côté client
(static/js/socle/diagnostic_copie.js), jamais interprétée ni parsée ici —
juste tronquée à une longueur courte, nettoyée des retours à la ligne (pour
rester UNE ligne de log) et ajoutée telle quelle au fichier. Aucune donnée
sensible n'y transite (pas le contenu du presse-papier ni le texte du
rapport, seulement des métadonnées techniques — voir le docstring du module
JS pour le détail des champs)."""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from flask import request

import identite

RACINE = Path(__file__).resolve().parent.parent
FICHIER_LOG = RACINE / "logs" / "diagnostic_copie.log"

# Borne défensive de la ligne acceptée — ce point d'entrée ne reçoit QUE du
# texte court (métadonnées techniques, voir l'en-tête du module JS
# correspondant), jamais un corps de rapport ou un contenu presse-papier.
LONGUEUR_MAX_LIGNE = 2000

# Rotation par taille (même principe que watcher.py::configurer_logs, sans sa
# variante par date — ce journal n'a pas besoin de distinguer les jours, son
# usage est une enquête ponctuelle, pas un suivi au long cours).
TAILLE_MAX_OCTETS = 2 * 1024 * 1024
NB_ARCHIVES = 3

_journal = None


def _obtenir_journal() -> logging.Logger:
    """Logger dédié, créé paresseusement (jamais au simple import de ce
    module) — le répertoire logs/ et le fichier ne sont créés qu'au premier
    appel RÉEL, c'est-à-dire seulement si DIAGNOSTIC_COPIE est actif ET qu'un
    clic a eu lieu.

    `logging.Logger(...)` en instanciation DIRECTE, PAS `logging.getLogger(...)` :
    ce dernier mémorise les loggers dans un registre GLOBAL par nom
    (`logging.Logger.manager.loggerDict`), partagé par tout le process —
    `route_dc._journal = None` (tests) ne suffirait alors pas à obtenir un
    logger réellement neuf, celui déjà enregistré sous ce nom (et son
    handler, pointant l'ANCIEN FICHIER_LOG) serait repris tel quel."""
    global _journal
    if _journal is not None:
        return _journal
    FICHIER_LOG.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        FICHIER_LOG, maxBytes=TAILLE_MAX_OCTETS, backupCount=NB_ARCHIVES, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    journal = logging.Logger("diagnostic_copie")
    journal.setLevel(logging.INFO)
    journal.propagate = False
    journal.addHandler(handler)
    _journal = journal
    return journal


def route_diagnostic_copie():
    """POST /diagnostic-copie — appelée par la page à chaque clic sur une
    case de copie (fire-and-forget, fetch keepalive côté client : jamais
    attendue, ne retarde donc jamais le clic ni l'écriture presse-papier).

    NO-OP strict si DIAGNOSTIC_COPIE est désactivé (défaut) : ni lecture ni
    écriture de fichier, réponse 204 immédiate — pour qu'une installation qui
    n'a jamais activé ce réglage n'ait STRICTEMENT AUCUNE trace de son
    existence sur disque."""
    if not identite.diagnostic_copie():
        return ("", 204)
    brut = request.get_data(as_text=True) or ""
    ligne = brut[:LONGUEUR_MAX_LIGNE].replace("\n", " ").replace("\r", " ").strip()
    if ligne:
        _obtenir_journal().info(ligne)
    return ("", 204)
