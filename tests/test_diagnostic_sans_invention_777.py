#!/usr/bin/env python3
"""Test de non-régression — issue #777 (incident chesscoach #123, point 2) :
le diagnostic automatique (`diagnostiquer_echec`) avait invoqué un
dépassement de délai pour une tentative de 337s sur un délai configuré de
1800s — un diagnostic affirmatif et FAUX, plus nuisible qu'une absence de
diagnostic.

Vérifie :
1. Quand la durée réelle de la dernière tentative est INFÉRIEURE au délai
   configuré, le prompt envoyé au modèle de diagnostic affirme explicitement
   que ce délai n'a PAS été dépassé et interdit de l'évoquer comme cause.
2. Quand elle lui est SUPÉRIEURE (ou égale), le prompt affirme au contraire
   qu'il A été dépassé.
3. L'ancien exemple trompeur (« tâche simplement trop volumineuse pour le
   timeout configuré ») qui orientait le modèle vers cette cause par
   suggestion, même hors de propos, n'apparaît plus dans le prompt.
4. Une réponse `RAS` (aucune cause concrète trouvée) est traitée comme
   l'ABSENCE de diagnostic (None) — préférée à une invention.
5. Une réponse non vide « normale » est bien renvoyée telle quelle.
6. Durée/timeout non numériques (None, ou tout autre type) : aucune
   exception, simplement aucune clause de faits connus insérée (best-effort,
   ne doit jamais faire échouer l'abandon définitif qui en dépend).

`lancer_claude` est remplacé par un faux appelable Python (aucun outil
externe, aucun appel réseau) qui capture le `prompt_perso` reçu.

Exécution :  python3 tests/test_diagnostic_sans_invention_777.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import logging
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import watcher  # noqa: E402


class _FauxLancerClaude:
    """Capture le `prompt_perso` reçu et renvoie une réponse programmée."""

    def __init__(self, reponse: str, succes: bool = True):
        self.reponse = reponse
        self.succes = succes
        self.dernier_prompt = None

    def __call__(self, *args, **kwargs):
        self.dernier_prompt = kwargs.get("prompt_perso")
        return self.succes, self.reponse


def _avec_faux_lancer_claude(faux):
    ancien = watcher.lancer_claude
    watcher.lancer_claude = faux
    return ancien


def _avec_cfg_minimale():
    ancien = watcher.CFG
    watcher.CFG = watcher.Config(nom="test777diag", depot="AlainDelree/x", rep_travail=Path("/tmp"))
    return ancien


def scenario_duree_inferieure_au_timeout_interdit_la_piste_timeout():
    faux = _FauxLancerClaude("- piste quelconque")
    ancien = _avec_faux_lancer_claude(faux)
    try:
        watcher.diagnostiquer_echec(
            9777, "titre", "body", "dernière erreur",
            duree_derniere_tentative=337.0, timeout_tentative=1800,
        )
    finally:
        watcher.lancer_claude = ancien

    prompt = faux.dernier_prompt
    assert prompt is not None, "prompt_perso attendu"
    assert "337" in prompt and "1800" in prompt, "les faits réels (durée, délai) doivent apparaître dans le prompt"
    assert "PAS été dépassé" in prompt, (
        "le prompt doit affirmer explicitement que le délai n'a PAS été "
        "dépassé quand la durée réelle lui est inférieure (incident "
        "chesscoach #123 : 337s pour un délai de 1800s)")
    assert "trop volumineuse pour le timeout configuré" not in prompt, (
        "l'ancien exemple trompeur, qui orientait le modèle vers un "
        "dépassement de délai par simple suggestion, ne doit plus apparaître")
    return {"interdiction_timeout_ok": True}


def scenario_duree_superieure_au_timeout_affirme_le_depassement():
    faux = _FauxLancerClaude("- piste quelconque")
    ancien = _avec_faux_lancer_claude(faux)
    try:
        watcher.diagnostiquer_echec(
            9777, "titre", "body", "Timeout après 1800s",
            duree_derniere_tentative=1800.0, timeout_tentative=1800,
        )
    finally:
        watcher.lancer_claude = ancien

    prompt = faux.dernier_prompt
    assert "été dépassé" in prompt and "PAS été dépassé" not in prompt, (
        "le prompt doit affirmer le dépassement quand la durée réelle "
        "atteint/dépasse le délai configuré")
    return {"affirmation_timeout_ok": True}


def scenario_reponse_ras_traitee_comme_absence_de_diagnostic():
    """Une réponse `RAS` (aucune cause concrète) doit valoir ABSENCE de
    diagnostic — préférée à une invention (point central de l'issue #777)."""
    for variante in ("RAS", "ras", "  RAS  "):
        faux = _FauxLancerClaude(variante)
        ancien = _avec_faux_lancer_claude(faux)
        try:
            resultat = watcher.diagnostiquer_echec(
                9777, "titre", "body", "dernière erreur",
                duree_derniere_tentative=10.0, timeout_tentative=300,
            )
        finally:
            watcher.lancer_claude = ancien
        assert resultat is None, f"réponse {variante!r} aurait dû valoir absence de diagnostic (None), obtenu : {resultat!r}"
    return {"ras_ignore_ok": True}


def scenario_reponse_normale_renvoyee_telle_quelle():
    faux = _FauxLancerClaude("- dépendance manquante constatée dans requirements.txt")
    ancien = _avec_faux_lancer_claude(faux)
    try:
        resultat = watcher.diagnostiquer_echec(
            9777, "titre", "body", "dernière erreur",
            duree_derniere_tentative=10.0, timeout_tentative=300,
        )
    finally:
        watcher.lancer_claude = ancien
    assert resultat == "- dépendance manquante constatée dans requirements.txt"
    return {"reponse_normale_ok": True}


def scenario_faits_non_numeriques_aucune_exception():
    """`duree_derniere_tentative`/`timeout_tentative` absents ou non
    numériques (ex. objet Mock dans un test, cf. régression constatée sur
    test_verification_commentaire_237.py) : aucune exception, simplement pas
    de clause de faits insérée — comportement best-effort inchangé."""
    class _PasUnNombre:
        pass

    for duree, timeout in ((None, None), (None, 300), (10.0, None), (_PasUnNombre(), 300)):
        faux = _FauxLancerClaude("- piste quelconque")
        ancien = _avec_faux_lancer_claude(faux)
        try:
            watcher.diagnostiquer_echec(
                9777, "titre", "body", "dernière erreur",
                duree_derniere_tentative=duree, timeout_tentative=timeout,
            )
        finally:
            watcher.lancer_claude = ancien
        assert "FAIT CONNU ET VÉRIFIÉ" not in faux.dernier_prompt
    return {"robustesse_non_numerique_ok": True}


def main():
    tests = [
        ("durée < délai → prompt interdit explicitement la piste timeout",
         scenario_duree_inferieure_au_timeout_interdit_la_piste_timeout),
        ("durée >= délai → prompt affirme le dépassement",
         scenario_duree_superieure_au_timeout_affirme_le_depassement),
        ("réponse RAS → absence de diagnostic (None), jamais affichée",
         scenario_reponse_ras_traitee_comme_absence_de_diagnostic),
        ("réponse normale → renvoyée telle quelle",
         scenario_reponse_normale_renvoyee_telle_quelle),
        ("faits non numériques (Mock, None...) → aucune exception",
         scenario_faits_non_numeriques_aucune_exception),
    ]

    logging.getLogger().addHandler(logging.NullHandler())
    watcher.log.setLevel(logging.CRITICAL)

    ancien_cfg = _avec_cfg_minimale()
    echecs = 0
    try:
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
    finally:
        watcher.CFG = ancien_cfg

    if echecs:
        print(f"\n❌ {echecs} scénario(s) en échec.")
        return 1
    print("\n✅ Tous les scénarios passent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
