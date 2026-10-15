#!/usr/bin/env python3
"""Test de non-régression — issue #761 : correction de trois défauts de
l'issue #760.

Vérifie :
1. `_construire_cmd_vibe`/`_construire_cmd_claude` reçoivent bien `cwd` ;
   `vibe` le transmet via `--workdir`, `claude` le reçoit mais l'ignore —
   commande produite pour l'agent en production strictement inchangée.
2. `_construire_cmd_vibe` lève `ModeAgentIndisponible` en MODE_LECTURE_ACTIVE
   (aucune confinement réel possible côté CLI vibe) — `lancer_claude` la
   capture et retourne un échec ordinaire (pas de crash).
3. `_detecter_erreur_bloquante` ne doit JAMAIS être nourri par le rapport de
   l'agent : un rapport contenant des mots ordinaires ("invalid api key",
   "quota"...) mais sans marqueur ✅/❌ de clôture (garde-fou #581) ne doit
   PAS déclencher un arrêt définitif — l'issue continue de consommer ses
   tentatives normalement. Un vrai stderr de process (code de retour non
   nul) contenant une signature DOIT, lui, déclencher l'arrêt immédiat.

`gh` et `claude` sont remplacés par de faux exécutables (même technique que
tests/test_lecture_active_327.py) : aucun appel réseau réel. Le CLI `vibe`
n'est volontairement jamais invoqué (consigne des issues #760/#761 : pas de
session réelle, facturée) — les scénarios 1 et 2 appellent directement les
fonctions Python concernées, sans lancer de process.

Exécution :  python3 tests/test_corrections_erreurs_bloquantes_761.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import logging
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import watcher  # noqa: E402
from garde_fou_faux_executables import verifier_faux_executables_actifs  # noqa: E402


def _issue_minimale(numero: int, titre: str, labels: list[str]) -> dict:
    return {
        "number": numero,
        "title": titre,
        "body": "| PRIORITE | normale |\n| TIMEOUT | 30s |\n",
        "labels": [{"name": lab} for lab in labels],
    }


def scenario_cwd_transmis_vibe_claude_inchange():
    """Point 1 : `cwd` atteint bien `construire_cmd` pour les deux agents.
    `vibe` le traduit en `--workdir` ; `claude` produit EXACTEMENT la même
    commande qu'avant l'issue #761 (cwd ignoré, aucun flag ajouté)."""
    cwd = Path("/tmp/exemple_perimetre_761")

    cmd_vibe_ecriture = watcher._construire_cmd_vibe(watcher.MODE_ECRITURE, "", "PROMPT", cwd)
    assert cmd_vibe_ecriture == ["vibe", "--agent", "bridge_ecriture", "--workdir", str(cwd), "--prompt", "PROMPT"], (
        f"commande vibe inattendue : {cmd_vibe_ecriture}")

    cmd_vibe_lecture = watcher._construire_cmd_vibe(watcher.MODE_LECTURE, "", "PROMPT", cwd)
    assert cmd_vibe_lecture == ["vibe", "--agent", "plan", "--workdir", str(cwd), "--prompt", "PROMPT"], (
        f"commande vibe inattendue : {cmd_vibe_lecture}")

    # Régression : la commande produite pour claude (agent en production)
    # reste identique à celle d'avant #759/#760/#761, quel que soit `cwd`.
    attendu_ecriture = ["claude", "--print", "--model", "sonnet", "--dangerously-skip-permissions", "PROMPT"]
    assert watcher._construire_cmd_claude(watcher.MODE_ECRITURE, "sonnet", "PROMPT", cwd) == attendu_ecriture
    assert watcher._construire_cmd_claude(watcher.MODE_ECRITURE, "sonnet", "PROMPT", Path("/autre/chemin")) == attendu_ecriture

    attendu_lecture = ["claude", "--print", "--model", "sonnet", "PROMPT",
                        "--allowedTools", ",".join(watcher.OUTILS_LECTURE_AUTORISES)]
    assert watcher._construire_cmd_claude(watcher.MODE_LECTURE, "sonnet", "PROMPT", cwd) == attendu_lecture

    return {"vibe_workdir_ok": True, "claude_inchange": True}


def scenario_lecture_active_vibe_indisponible():
    """Point 2 : MODE_LECTURE_ACTIVE indisponible pour vibe — exception
    explicite, et `lancer_claude` la convertit en échec ordinaire (sans
    crash, sans lancer de process `vibe` réel)."""
    cwd = Path("/tmp/exemple_perimetre_761")
    try:
        watcher._construire_cmd_vibe(watcher.MODE_LECTURE_ACTIVE, "", "PROMPT", cwd)
        raise AssertionError("ModeAgentIndisponible aurait dû être levée")
    except watcher.ModeAgentIndisponible:
        pass

    with tempfile.TemporaryDirectory() as tmp:
        rep_travail = Path(tmp)
        ancien_cfg = watcher.CFG
        watcher.CFG = watcher.Config(
            nom="test761vibe", depot="AlainDelree/depot-inexistant-test761",
            rep_travail=rep_travail, topic_ntfy="test761vibe",
            max_essais=1, timeout_claude=15, notifier_local=False,
            agent="vibe",
        )
        try:
            succes, sortie = watcher.lancer_claude(
                9761, "titre", "body", dry_run=False, mode=watcher.MODE_LECTURE_ACTIVE,
                chemin_scratch=rep_travail / "scratch",
            )
        finally:
            watcher.CFG = ancien_cfg

        assert succes is False, "MODE_LECTURE_ACTIVE sous vibe doit échouer proprement"
        assert "indisponible" in sortie.lower(), f"message inattendu : {sortie}"

    return {"exception_levee": True, "echec_propre": True}


def _preparer_faux_claude(tmp_path: Path, script: str) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    claude_path = bin_dir / "claude"
    claude_path.write_text(script, encoding="utf-8")
    claude_path.chmod(claude_path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    gh_path = bin_dir / "gh"
    gh_path.write_text("#!/bin/bash\nexit 0\n", encoding="utf-8")
    gh_path.chmod(gh_path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return bin_dir


def _init_depot_git(rep: Path) -> None:
    subprocess.run(["git", "init", "-q", "-b", "master", str(rep)], check=True)
    (rep / "fichier.txt").write_text("original\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=rep, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=rep, check=True, capture_output=True)


def scenario_rapport_agent_ne_declenche_pas_erreur_bloquante():
    """Point 3 : un rapport d'agent (exit 0, sans marqueur ✅/❌ — reclassé en
    échec par le garde-fou #581) qui mentionne des mots ordinaires présents
    dans SIGNATURES_ERREUR_BLOQUANTE_CLAUDE ("invalid api key") ne doit PAS
    déclencher l'arrêt définitif : les deux tentatives prévues doivent être
    consommées normalement."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        rep_travail = tmp_path / "projet"
        rep_travail.mkdir()
        _init_depot_git(rep_travail)

        compteur = tmp_path / "compteur_appels"
        # La passe diagnostique (issue #124, déclenchée après épuisement des
        # tentatives par _gerer_abandon_max_essais) rappelle aussi `claude` —
        # reconnue ici à son prompt dédié ("diagnostic RAPIDE"), pour ne PAS
        # la compter comme une tentative normale.
        script_claude = f"""#!/bin/bash
for arg in "$@"; do
    if [[ "$arg" == *"diagnostic RAPIDE"* ]]; then
        echo "- piste de diagnostic 1"
        echo "- piste de diagnostic 2"
        exit 0
    fi
done
if [ "$#" -ge 2 ]; then
    echo x >> {compteur}
    echo "Analyse du correctif : le ticket décrit une 'invalid api key' et un souci de quota disque, sans rapport avec l'authentification CCL."
fi
exit 0
"""
        bin_dir = _preparer_faux_claude(tmp_path, script_claude)
        ancien_path = os.environ.get("PATH", "")
        os.environ["PATH"] = f"{bin_dir}{os.pathsep}{ancien_path}"
        try:
            verifier_faux_executables_actifs(bin_dir, ["claude", "gh"])
        except Exception:
            os.environ["PATH"] = ancien_path
            raise

        ancien_dossier_verrous = watcher.DOSSIER_VERROUS
        ancien_dossier_logs = watcher.DOSSIER_LOGS
        ancien_fichier_historique = watcher.FICHIER_HISTORIQUE
        ancien_fichier_etat_timeout = watcher.FICHIER_ETAT_TIMEOUT
        ancien_fichier_etat_ambiance = watcher.FICHIER_ETAT_AMBIANCE
        watcher.DOSSIER_VERROUS = tmp_path / "verrous"
        watcher.DOSSIER_LOGS = tmp_path / "logs"
        watcher.FICHIER_HISTORIQUE = watcher.DOSSIER_LOGS / "historique_durees.json"
        watcher.FICHIER_ETAT_TIMEOUT = watcher.DOSSIER_LOGS / "etat_timeout.json"
        watcher.FICHIER_ETAT_AMBIANCE = watcher.DOSSIER_LOGS / "etat_ambiance.json"

        ancien_cfg = watcher.CFG
        watcher.CFG = watcher.Config(
            nom="test761a", depot="AlainDelree/depot-inexistant-test761",
            rep_travail=rep_travail, topic_ntfy="test761a",
            max_essais=2, timeout_claude=15, notifier_local=False,
        )
        watcher.issues_en_cours.discard(9761)

        try:
            issue = _issue_minimale(9761, "Test #761 — rapport ordinaire", ["mode_scratch"])
            watcher.traiter_issue(issue, dry_run=False)
        finally:
            watcher.CFG = ancien_cfg
            if ancien_path:
                os.environ["PATH"] = ancien_path
            else:
                os.environ.pop("PATH", None)
            watcher.DOSSIER_VERROUS = ancien_dossier_verrous
            watcher.DOSSIER_LOGS = ancien_dossier_logs
            watcher.FICHIER_HISTORIQUE = ancien_fichier_historique
            watcher.FICHIER_ETAT_TIMEOUT = ancien_fichier_etat_timeout
            watcher.FICHIER_ETAT_AMBIANCE = ancien_fichier_etat_ambiance
            watcher.issues_en_cours.discard(9761)

        nb_appels = sum(1 for _ in compteur.read_text(encoding="utf-8").splitlines()) if compteur.exists() else 0
        assert nb_appels == 2, (
            "les 2 tentatives prévues (max_essais=2) auraient dû être consommées "
            f"(rapport ordinaire, pas une vraie erreur bloquante) — {nb_appels} appel(s) constaté(s)")

    return {"tentatives_consommees": nb_appels}


def scenario_vraie_erreur_stderr_declenche_arret_immediat():
    """Point 3 (contrôle) : un VRAI échec de process (code de retour non
    nul, signature dans stderr) doit toujours déclencher l'arrêt immédiat
    dès la première tentative, sans consommer les tentatives restantes."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        rep_travail = tmp_path / "projet"
        rep_travail.mkdir()
        _init_depot_git(rep_travail)

        compteur = tmp_path / "compteur_appels"
        script_claude = f"""#!/bin/bash
if [ "$#" -ge 2 ]; then
    echo x >> {compteur}
    echo "Error: invalid api key" >&2
    exit 1
fi
exit 0
"""
        bin_dir = _preparer_faux_claude(tmp_path, script_claude)
        ancien_path = os.environ.get("PATH", "")
        os.environ["PATH"] = f"{bin_dir}{os.pathsep}{ancien_path}"
        try:
            verifier_faux_executables_actifs(bin_dir, ["claude", "gh"])
        except Exception:
            os.environ["PATH"] = ancien_path
            raise

        ancien_dossier_verrous = watcher.DOSSIER_VERROUS
        ancien_dossier_logs = watcher.DOSSIER_LOGS
        ancien_fichier_historique = watcher.FICHIER_HISTORIQUE
        ancien_fichier_etat_timeout = watcher.FICHIER_ETAT_TIMEOUT
        ancien_fichier_etat_ambiance = watcher.FICHIER_ETAT_AMBIANCE
        watcher.DOSSIER_VERROUS = tmp_path / "verrous"
        watcher.DOSSIER_LOGS = tmp_path / "logs"
        watcher.FICHIER_HISTORIQUE = watcher.DOSSIER_LOGS / "historique_durees.json"
        watcher.FICHIER_ETAT_TIMEOUT = watcher.DOSSIER_LOGS / "etat_timeout.json"
        watcher.FICHIER_ETAT_AMBIANCE = watcher.DOSSIER_LOGS / "etat_ambiance.json"

        ancien_cfg = watcher.CFG
        watcher.CFG = watcher.Config(
            nom="test761b", depot="AlainDelree/depot-inexistant-test761",
            rep_travail=rep_travail, topic_ntfy="test761b",
            max_essais=5, timeout_claude=15, notifier_local=False,
        )
        watcher.issues_en_cours.discard(9762)

        try:
            issue = _issue_minimale(9762, "Test #761 — vraie erreur bloquante", ["mode_scratch"])
            watcher.traiter_issue(issue, dry_run=False)
        finally:
            watcher.CFG = ancien_cfg
            if ancien_path:
                os.environ["PATH"] = ancien_path
            else:
                os.environ.pop("PATH", None)
            watcher.DOSSIER_VERROUS = ancien_dossier_verrous
            watcher.DOSSIER_LOGS = ancien_dossier_logs
            watcher.FICHIER_HISTORIQUE = ancien_fichier_historique
            watcher.FICHIER_ETAT_TIMEOUT = ancien_fichier_etat_timeout
            watcher.FICHIER_ETAT_AMBIANCE = ancien_fichier_etat_ambiance
            watcher.issues_en_cours.discard(9762)

        nb_appels = sum(1 for _ in compteur.read_text(encoding="utf-8").splitlines()) if compteur.exists() else 0
        assert nb_appels == 1, (
            f"l'arrêt aurait dû être immédiat dès la 1re tentative (sur 5 prévues) — {nb_appels} appel(s) constaté(s)")

    return {"arret_immediat": True}


def main():
    if os.name == "nt":
        print("  (ignoré : ce test s'appuie sur bash/git POSIX, non applicable sous Windows)")
        return 0

    tests = [
        ("cwd transmis à construire_cmd (vibe --workdir, claude inchangé)",
         scenario_cwd_transmis_vibe_claude_inchange),
        ("MODE_LECTURE_ACTIVE indisponible pour vibe (échec propre, sans crash)",
         scenario_lecture_active_vibe_indisponible),
        ("rapport d'agent avec mots ordinaires → PAS d'arrêt définitif, tentatives consommées",
         scenario_rapport_agent_ne_declenche_pas_erreur_bloquante),
        ("vrai stderr de process avec signature → arrêt immédiat, sans consommer les tentatives",
         scenario_vraie_erreur_stderr_declenche_arret_immediat),
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
