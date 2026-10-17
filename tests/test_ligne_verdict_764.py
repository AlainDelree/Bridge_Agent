#!/usr/bin/env python3
"""Test de non-régression — issue #764.

Vérifie :
1. `_verdict_final`/`_RE_LIGNE_VERDICT` : seule une ligne AUTONOME portant
   exactement le motif `MARQUEUR_VERDICT_SUCCES`/`MARQUEUR_VERDICT_ECHEC`
   vaut verdict — un ❌ en tête de ligne dans un extrait/une liste de cas
   (l'ancien faux positif, remplacé par cette issue) ne doit plus matcher.
2. Entre plusieurs lignes de verdict dans la même sortie, c'est la PREMIÈRE
   qui l'emporte (correction reprise de l'étude #762, #757 gardait jusqu'ici
   la dernière).
3. `_avertissement_succes_sans_commit` : signalement best-effort, limité au
   mode écriture hors dry-run, qui ne déclenche que si AUCUN commit (hors
   sauvegarde) n'a été fait — jamais d'incidence sur le succès lui-même
   (la fonction ne fait que retourner un texte à ajouter au commentaire).

`git` est le seul outil externe utilisé (dépôts temporaires réels) — aucun
appel réseau.

Exécution :  python3 tests/test_ligne_verdict_764.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import watcher  # noqa: E402


def _init_depot_git(rep: Path) -> None:
    subprocess.run(["git", "init", "-q", "-b", "master", str(rep)], check=True)
    (rep / "fichier.txt").write_text("original\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=rep, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=rep, check=True, capture_output=True)


def _commit(rep: Path, message: str, allow_empty: bool = False) -> None:
    cmd = ["git", "commit", "-q", "-m", message]
    if allow_empty:
        cmd.append("--allow-empty")
    else:
        subprocess.run(["git", "add", "-A"], cwd=rep, check=True, capture_output=True)
    subprocess.run(cmd, cwd=rep, check=True, capture_output=True)


def scenario_absence_de_ligne_verdict():
    """Un rapport sans aucune ligne de verdict (ancien format ✅/❌ seul, ou
    rapport hors format) retourne None — déclenche le garde-fou #581."""
    sortie = "✅ Tâche terminée — ancien format, sans la ligne dédiée #764."
    assert watcher._verdict_final(sortie) is None
    return {"absence_ok": True}


def scenario_caractere_en_tete_de_liste_pas_un_verdict():
    """Un ❌ en tête de ligne dans une liste de cas (le faux positif constaté
    avant #764) ne doit plus être pris pour un verdict : sans la ligne
    autonome dédiée, _verdict_final retourne None."""
    sortie = (
        f"{watcher.MARQUEUR_VERDICT_SUCCES}\n"
        "✅ Tâche terminée — audit des erreurs.\n\n"
        "<details><summary>Détails</summary>\n"
        "Cas rencontrés :\n"
        "❌ permission refusée (cas A)\n"
        "❌ fichier introuvable (cas B)\n"
        "</details>\n"
    )
    assert watcher._verdict_final(sortie) == watcher.MARQUEUR_VERDICT_SUCCES, (
        "les ❌ cités dans la liste de cas ne doivent pas l'emporter sur la "
        "ligne de verdict dédiée, présente en tête")
    return {"faux_positif_elimine_ok": True}


def scenario_ligne_verdict_exacte_succes_et_echec():
    """Les deux motifs, chacun seul sur sa ligne, sont reconnus tels quels."""
    assert watcher._verdict_final(f"{watcher.MARQUEUR_VERDICT_SUCCES}\nsuite du rapport") \
        == watcher.MARQUEUR_VERDICT_SUCCES
    assert watcher._verdict_final(f"{watcher.MARQUEUR_VERDICT_ECHEC}\nsuite du rapport") \
        == watcher.MARQUEUR_VERDICT_ECHEC
    # Espaces de bordure tolérés, mais pas de texte additionnel sur la ligne.
    assert watcher._verdict_final(f"  {watcher.MARQUEUR_VERDICT_SUCCES}  \nsuite") \
        == watcher.MARQUEUR_VERDICT_SUCCES
    assert watcher._verdict_final(f"texte avant {watcher.MARQUEUR_VERDICT_SUCCES}") is None, (
        "le motif cité au milieu d'une ligne (pas autonome) ne doit pas valoir verdict")
    return {"motifs_reconnus_ok": True}


def scenario_premiere_occurrence_gagne():
    """Si la sortie capturée contient DEUX lignes de verdict distinctes
    (rapport réel conforme, puis un tour supplémentaire tardif qui en cite
    une autre — cas #580/#581), c'est la PREMIÈRE qui tranche, pas la
    dernière (correction de l'étude #762 par rapport à #757)."""
    sortie = (
        f"{watcher.MARQUEUR_VERDICT_SUCCES}\n"
        "✅ Tâche terminée — vrai rapport.\n\n"
        "Note de suivi tardive d'un sous-agent :\n"
        f"{watcher.MARQUEUR_VERDICT_ECHEC}\n"
    )
    assert watcher._verdict_final(sortie) == watcher.MARQUEUR_VERDICT_SUCCES
    return {"premiere_occurrence_ok": True}


def scenario_sans_commit_signale_hors_dry_run_mode_ecriture():
    """Mode écriture, hors dry-run, un seul commit après `tete_avant_
    traitement` (la sauvegarde) → signalement non vide, avec warning loggé."""
    with tempfile.TemporaryDirectory() as tmp:
        rep = Path(tmp) / "projet"
        rep.mkdir()
        _init_depot_git(rep)
        tete = watcher._tete_git(rep)
        _commit(rep, "avant-tache-test764", allow_empty=True)

        avertissement = watcher._avertissement_succes_sans_commit(
            9764, watcher.MODE_ECRITURE, False, rep, tete)
        assert avertissement != "", "un succès sans commit au-delà de la sauvegarde doit être signalé"
        assert "sauvegarde" in avertissement.lower()
        return {"signale_ok": True}


def scenario_avec_commit_fix_pas_de_signalement():
    """Même scénario, mais avec un second commit (le « fix ») après la
    sauvegarde → aucun signalement."""
    with tempfile.TemporaryDirectory() as tmp:
        rep = Path(tmp) / "projet"
        rep.mkdir()
        _init_depot_git(rep)
        tete = watcher._tete_git(rep)
        _commit(rep, "avant-tache-test764", allow_empty=True)
        (rep / "fichier.txt").write_text("modifie\n", encoding="utf-8")
        _commit(rep, "fix-tache-test764")

        avertissement = watcher._avertissement_succes_sans_commit(
            9764, watcher.MODE_ECRITURE, False, rep, tete)
        assert avertissement == "", "un commit de fix au-delà de la sauvegarde doit supprimer le signalement"
        return {"pas_de_signalement_ok": True}


def scenario_hors_mode_ecriture_ou_dry_run_jamais_signale():
    """Portée stricte (#764) : lecture seule, lecture active et dry-run ne
    doivent JAMAIS déclencher ce signalement, même sans commit — ces modes
    n'attendent aucun commit."""
    with tempfile.TemporaryDirectory() as tmp:
        rep = Path(tmp) / "projet"
        rep.mkdir()
        _init_depot_git(rep)
        tete = watcher._tete_git(rep)

        for mode, dry_run in (
            (watcher.MODE_LECTURE, False),
            (watcher.MODE_LECTURE_ACTIVE, False),
            (watcher.MODE_ECRITURE, True),
        ):
            assert watcher._avertissement_succes_sans_commit(9764, mode, dry_run, rep, tete) == ""
        # `tete_avant_traitement` absent (None) : jamais renseigné hors mode
        # écriture par `_demarrer_traitement` — même en mode écriture, pas de
        # signalement possible sans cette référence.
        assert watcher._avertissement_succes_sans_commit(9764, watcher.MODE_ECRITURE, False, rep, None) == ""
        return {"portee_stricte_ok": True}


def scenario_depot_inaccessible_best_effort():
    """Dépôt git inaccessible (chemin inexistant) : la capture échoue
    silencieusement — "" retourné, aucune exception propagée. Le point de
    vigilance de l'issue est que cette incapacité ne doit priver QUE du
    signalement, jamais de la clôture."""
    chemin_inexistant = Path(tempfile.gettempdir()) / "ne-devrait-pas-exister-764"
    avertissement = watcher._avertissement_succes_sans_commit(
        9764, watcher.MODE_ECRITURE, False, chemin_inexistant, "0" * 40)
    assert avertissement == ""
    return {"best_effort_ok": True}


def main():
    tests = [
        ("absence de ligne de verdict → None (garde-fou #581 inchangé)",
         scenario_absence_de_ligne_verdict),
        ("❌ en tête de ligne dans une liste de cas → plus un faux positif",
         scenario_caractere_en_tete_de_liste_pas_un_verdict),
        ("lignes de verdict succès/échec reconnues, motif cité en ligne ignoré",
         scenario_ligne_verdict_exacte_succes_et_echec),
        ("deux lignes de verdict distinctes → la PREMIÈRE tranche",
         scenario_premiere_occurrence_gagne),
        ("succès mode écriture, 1 seul commit (sauvegarde) → signalé",
         scenario_sans_commit_signale_hors_dry_run_mode_ecriture),
        ("succès mode écriture, commit de fix présent → pas de signalement",
         scenario_avec_commit_fix_pas_de_signalement),
        ("lecture seule / lecture active / dry-run / tête absente → jamais signalé",
         scenario_hors_mode_ecriture_ou_dry_run_jamais_signale),
        ("dépôt inaccessible → best-effort, aucune exception",
         scenario_depot_inaccessible_best_effort),
    ]

    logging.getLogger().addHandler(logging.NullHandler())
    watcher.log.setLevel(logging.CRITICAL)

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
