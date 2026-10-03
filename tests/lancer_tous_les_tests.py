#!/usr/bin/env python3
"""Lanceur unique des tests autonomes `tests/test_*.py` — issue #704.

Ces 37 fichiers ne sont PAS collectés par pytest : chacun est un script
autonome avec son propre `main()` (`python3 tests/test_xxx.py`, code de
sortie 0/1). Ce lanceur les exécute un par un, dans un sous-processus isolé,
avec `PYTHONUTF8=1` forcé dans son environnement : sans ce forçage, une
sortie redirigée (fichier/pipe) retombe sous Windows sur l'encodage cp1252
de la console, qui ne sait pas écrire les symboles ✓/✗/❌ des tests (même
famille que le correctif d'encodage #686/#688) — le script plante au tout
premier affichage, avant d'avoir testé quoi que ce soit (faux positif
massif : 30 fichiers sur 37 mesurés en échec le 29-30/09/2026, 33/37 une
fois PYTHONUTF8=1 forcé).

Un test qui s'ignore proprement sous Windows (code de sortie 0 + message
« (ignoré : ... non applicable sous Windows) ») compte comme réussi — c'est
la convention du dépôt pour les scénarios strictement POSIX.

Exécution :  python3 tests/lancer_tous_les_tests.py
Sortie      :  code 0 si tous les fichiers réussissent (code de sortie 0
                chacun), 1 si au moins un échoue ou dépasse son délai.
"""

import os
import subprocess
import sys
import time
from pathlib import Path

DOSSIER_TESTS = Path(__file__).resolve().parent
RACINE = DOSSIER_TESTS.parent
DELAI_MAX_PAR_FICHIER = 120  # secondes


def _derniere_ligne_utile(texte: str) -> str:
    lignes = [l.strip() for l in texte.splitlines() if l.strip()]
    return lignes[-1] if lignes else "(aucune sortie)"


def _lignes_echec(texte: str) -> list[str]:
    """Lignes à afficher pour un fichier en échec : celles qui portent le
    marqueur de scénario en échec (✗) ou le résumé final (« scénario(s) en
    échec »), ou à défaut les 15 dernières lignes de la sortie — la dernière
    ligne seule peut n'être que du bruit normal émis par un scénario qui
    passe (issue #706, cas 516/REPO_CIBLE)."""
    lignes = [l.rstrip() for l in texte.splitlines() if l.strip()]
    if not lignes:
        return ["(aucune sortie)"]
    pertinentes = [l for l in lignes if "✗" in l or "scénario(s) en échec" in l]
    return pertinentes if pertinentes else lignes[-15:]


def _lancer_un_fichier(chemin: Path) -> tuple[int, str]:
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    try:
        resultat = subprocess.run(
            [sys.executable, str(chemin)],
            cwd=RACINE,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=DELAI_MAX_PAR_FICHIER,
        )
        sortie = (resultat.stdout or "") + (resultat.stderr or "")
        return resultat.returncode, sortie
    except subprocess.TimeoutExpired as e:
        sortie = (e.stdout or "") + (e.stderr or "")
        return 1, f"(délai dépassé : > {DELAI_MAX_PAR_FICHIER}s)\n{sortie}"


def main() -> int:
    # Robustesse du lanceur lui-même face à une sortie redirigée sous
    # Windows (même catégorie de problème que celle visée par PYTHONUTF8=1
    # dans les sous-processus) : n'affecte ni stdin ni l'environnement des
    # sous-processus lancés ci-dessous.
    for flux in (sys.stdout, sys.stderr):
        try:
            flux.reconfigure(encoding="utf-8", errors="backslashreplace")
        except AttributeError:
            pass

    fichiers = sorted(DOSSIER_TESTS.glob("test_*.py"))
    if not fichiers:
        print("Aucun fichier tests/test_*.py trouvé.")
        return 1

    echecs = []
    debut_total = time.monotonic()
    for chemin in fichiers:
        debut = time.monotonic()
        code, sortie = _lancer_un_fichier(chemin)
        duree = time.monotonic() - debut
        statut = "✓" if code == 0 else "✗"
        if code == 0:
            print(f"  {statut} {chemin.name:<48} exit={code}  ({duree:.1f}s)  "
                  f"{_derniere_ligne_utile(sortie)}")
        else:
            print(f"  {statut} {chemin.name:<48} exit={code}  ({duree:.1f}s)")
            for ligne in _lignes_echec(sortie):
                print(f"      {ligne}")
            echecs.append(chemin.name)

    duree_totale = time.monotonic() - debut_total
    print(f"\n{len(fichiers)} fichier(s) exécuté(s) en {duree_totale:.1f}s — "
          f"{len(fichiers) - len(echecs)} réussi(s), {len(echecs)} échec(s).")
    if echecs:
        print("❌ Échecs : " + ", ".join(echecs))
        return 1
    print("✅ Tous les fichiers de tests passent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
