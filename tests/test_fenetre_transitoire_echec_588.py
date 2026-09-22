#!/usr/bin/env python3
"""Test de non-régression — issue #588 : `_debut_traitement()` (app/issues.py)
affichait à tort "en file" pour une issue qui vient d'échouer définitivement.

Cause : le commentaire "Échec après N tentatives" (posté par watcher.py juste
avant le label needs-human — deux appels gh distincts, non atomiques)
réinitialisait systématiquement `debut` à None, y compris pendant la courte
fenêtre transitoire où needs-human n'est pas encore posé pour le cycle ACTUEL
qui vient d'échouer. Le fix (FENETRE_TRANSITOIRE_ECHEC_S / `_echec_recent`)
ne réinitialise `debut` que si ce marqueur n'est PAS récent (< 120s), pour
distinguer :
- le cycle ACTUEL qui vient de se terminer (marqueur récent) → conserver
  `debut` (l'ACK du cycle en cours), pas de retour à "en file" ;
- le cycle PRÉCÉDENT d'une issue relancée après retrait manuel de
  needs-human (marqueur ancien, issue #525 à préserver) → `debut` = None
  jusqu'à une nouvelle ACK.

Fonction pure, aucun accès réseau/gh nécessaire.

Exécution :  python3 tests/test_fenetre_transitoire_echec_588.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from app.issues import _debut_traitement, FENETRE_TRANSITOIRE_ECHEC_S  # noqa: E402


def _iso(delta_s: float) -> str:
    """Horodatage ISO 8601 (format gh, suffixe Z) à `delta_s` secondes
    avant maintenant (delta_s positif = dans le passé)."""
    dt = datetime.now(timezone.utc) - timedelta(seconds=delta_s)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _ack(delta_s: float) -> dict:
    return {"body": "🤖 ACK — watcher.py a pris en charge cette issue.",
            "createdAt": _iso(delta_s)}


def _echec(delta_s: float, n=3) -> dict:
    return {"body": f"❌ Échec après {n} tentatives.\n\nDernière erreur : `...`",
            "createdAt": _iso(delta_s)}


def scenario_588_echec_recent_conserve_debut():
    """Cycle ACTUEL qui vient d'échouer (marqueur < 120s) : needs-human est
    en cours de pose côté GitHub → ne doit PAS retomber à "en file", `debut`
    doit rester l'ACK du cycle qui vient de tourner plusieurs minutes."""
    ack = _ack(900)  # ACK il y a 15 min
    commentaires = [ack, _echec(5)]  # échec posté il y a 5s
    debut = _debut_traitement(commentaires)
    assert debut == ack["createdAt"], (
        f"debut aurait dû rester l'ACK du cycle en cours ({ack['createdAt']}), "
        f"obtenu : {debut}"
    )


def scenario_588_echec_a_la_limite_de_la_fenetre():
    """Juste sous le seuil (marqueur récent) : `debut` conservé."""
    ack = _ack(900)
    commentaires = [ack, _echec(FENETRE_TRANSITOIRE_ECHEC_S - 1)]
    debut = _debut_traitement(commentaires)
    assert debut == ack["createdAt"], (
        "Juste sous le seuil de la fenêtre transitoire, debut doit rester "
        f"l'ACK du cycle en cours, obtenu : {debut}"
    )


def scenario_525_echec_ancien_repasse_en_file():
    """Non-régression #525 : issue relancée après retrait manuel de
    needs-human, ACK du cycle précédent dans l'historique, marqueur d'échec
    ANCIEN (> 120s, ex. issue relancée après plusieurs minutes/heures) : doit
    toujours afficher "en file" (debut = None) tant qu'aucune nouvelle ACK
    n'est postée."""
    ack_ancienne = _ack(3600)  # ACK du cycle précédent, il y a 1h
    commentaires = [ack_ancienne, _echec(FENETRE_TRANSITOIRE_ECHEC_S + 1)]
    debut = _debut_traitement(commentaires)
    assert debut is None, (
        f"Scénario #525 : debut aurait dû redevenir None (en file), obtenu : {debut}"
    )


def scenario_525_nouvelle_ack_apres_relance():
    """Non-régression #525 : une fois l'issue reprise après relance, la
    nouvelle ACK (postée après le marqueur d'échec, quel que soit son âge)
    doit primer, y compris quand le marqueur d'échec était récent."""
    ack_ancienne = _ack(3600)
    nouvelle_ack = _ack(30)
    commentaires = [ack_ancienne, _echec(FENETRE_TRANSITOIRE_ECHEC_S + 100), nouvelle_ack]
    debut = _debut_traitement(commentaires)
    assert debut == nouvelle_ack["createdAt"], (
        f"La nouvelle ACK après relance doit faire foi, obtenu : {debut}"
    )


def scenario_aucun_commentaire():
    """Issue jamais prise en charge : aucun commentaire → debut = None."""
    assert _debut_traitement([]) is None


def scenario_ack_simple_sans_echec():
    """Déroulement normal (pas d'échec) : debut = createdAt de l'ACK."""
    ack = _ack(60)
    debut = _debut_traitement([ack])
    assert debut == ack["createdAt"]


def main():
    tests = [
        ("#588 : échec récent (fenêtre transitoire) → debut conservé, pas 'en file'",
         scenario_588_echec_recent_conserve_debut),
        ("#588 : échec juste sous le seuil → debut conservé",
         scenario_588_echec_a_la_limite_de_la_fenetre),
        ("#525 : échec ancien (issue relancée) → 'en file' préservé",
         scenario_525_echec_ancien_repasse_en_file),
        ("#525 : nouvelle ACK après relance → fait foi",
         scenario_525_nouvelle_ack_apres_relance),
        ("aucun commentaire → debut = None", scenario_aucun_commentaire),
        ("ACK simple sans échec → debut = ACK", scenario_ack_simple_sans_echec),
    ]
    echecs = 0
    for nom, fn in tests:
        try:
            fn()
            print(f"  ✓ {nom}")
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
