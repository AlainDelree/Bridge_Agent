# DIAGNOSTIC TEMPORAIRE — issue #157, à retirer
"""DIAGNOSTIC TEMPORAIRE — issue #157, à retirer.

Journalisation temporaire, regroupée dans CE SEUL fichier, pour vérifier
objectivement que le correctif du heartbeat/SSE empêche bien les coupures
intempestives quand l'onglet Bridge_Agent passe en arrière-plan.

Tout écrit dans logs/heartbeat_diag.log :
  - chaque heartbeat reçu, avec le delta depuis le précédent ;
  - chaque connexion / déconnexion SSE (/events), avec le nombre de
    connexions actives restantes ;
  - chaque changement de visibilité de l'onglet signalé par le navigateur
    (POST /diag-visibilite) — pour corréler « onglet passé en arrière-plan »
    avec « serveur coupé » ;
  - le delta exact au moment où surveiller_heartbeat() déclenche un arrêt.

POUR RETIRER PROPREMENT (une fois le correctif validé) :
  1. Supprimer ce fichier (app/diag_heartbeat.py).
  2. app/cycle_vie.py : retirer les lignes marquées « DIAGNOSTIC TEMPORAIRE
     — issue #157 » (l'import « from app import diag_heartbeat » + les
     appels diag_heartbeat.log_*()).
  3. app/__init__.py : retirer l'enregistrement de la route /diag-visibilite
     (ligne marquée du même commentaire) et son import.
  4. static/js/app.js : retirer le bloc marqué « DIAGNOSTIC TEMPORAIRE —
     issue #157 » dans demarrerCycleVie() (le console.log + le fetch vers
     /diag-visibilite). Garder l'appel envoyerHeartbeat() du visibilitychange
     et le relèvement du seuil : ils font partie du correctif, pas du diag.
  5. Supprimer logs/heartbeat_diag.log.
"""

import threading
import time
from pathlib import Path

from flask import jsonify, request

RACINE = Path(__file__).resolve().parent.parent
FICHIER = RACINE / "logs" / "heartbeat_diag.log"

_lock = threading.Lock()
_dernier_hb = {"t": None}   # horodatage du heartbeat précédent (pour le delta)


def _ecrire(ligne: str) -> None:
    horo = time.strftime("%Y-%m-%d %H:%M:%S")
    with _lock:
        try:
            with open(FICHIER, "a", encoding="utf-8") as f:
                f.write(f"[{horo}] {ligne}\n")
        except OSError:
            pass   # le diagnostic ne doit jamais casser le service


def log_heartbeat() -> None:
    """Trace un heartbeat POST /heartbeat reçu et son delta avec le précédent."""
    now = time.time()
    with _lock:
        prec = _dernier_hb["t"]
        _dernier_hb["t"] = now
    delta = f"{now - prec:.1f}s" if prec is not None else "premier"
    _ecrire(f"HEARTBEAT reçu (delta depuis précédent : {delta})")


def log_sse(evenement: str, connexions: int) -> None:
    """Trace une (dé)connexion SSE /events et le nb de connexions restantes."""
    _ecrire(f"SSE {evenement} (connexions actives : {connexions})")


def log_arret(delta_hb: float, delta_sse: float, connexions: int,
              seuil_hb: float, seuil_sse: float) -> None:
    """Trace le déclenchement d'un arrêt par surveiller_heartbeat(), avec les
    deltas exacts et de combien les seuils ont été dépassés."""
    _ecrire(
        "ARRÊT déclenché par surveiller_heartbeat — "
        f"delta_heartbeat={delta_hb:.1f}s (seuil {seuil_hb:.0f}s), "
        f"delta_SSE={delta_sse:.1f}s (seuil {seuil_sse:.0f}s), "
        f"connexions_SSE={connexions}"
    )


def visibilite():
    """Route POST /diag-visibilite : le navigateur signale un changement de
    visibilité de l'onglet (document.hidden true/false), avec son horodatage."""
    data = request.get_json(silent=True) or {}
    etat = data.get("etat", "?")
    horo_client = data.get("horodatage", "?")
    _ecrire(f"VISIBILITÉ onglet={etat} (horodatage client={horo_client})")
    return jsonify(ok=True)
