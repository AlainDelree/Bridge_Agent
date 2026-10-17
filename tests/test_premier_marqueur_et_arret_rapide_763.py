#!/usr/bin/env python3
"""Test de non-régression — issue #763 : deux correctifs indépendants.

Vérifie :
1. `_verdict_final` retient le PREMIER marqueur ✅/❌ en tête de ligne, plus la
   dernière occurrence (corrige #757) — scénario exact de l'incident #56
   d'apiselect : un rapport qui annonce ✅ en première ligne, puis contient
   plus loin, dans une section « lacunes de tests », une puce portant le
   marqueur ❌. Le verdict retenu doit être ✅, pas ❌.
2. Une tentative dont le PROCESS échoue anormalement vite (moins de
   `SEUIL_DUREE_TENTATIVE_ANORMALE_S`, issue #763, incident #762) déclenche
   un arrêt immédiat (même mécanisme que `_gerer_erreur_bloquante`, issue
   #760) : label `needs-human`, commentaire explicite invitant à vérifier
   l'authentification/le binaire, et les tentatives restantes NE sont PAS
   consommées.
3. Non-régression : un rapport d'agent reclassé en échec après coup par le
   garde-fou #581 (sans marqueur ✅/❌) et produit quasi instantanément par le
   faux exécutable de test ne doit JAMAIS être traité comme une tentative
   anormalement rapide — seul un échec constaté au niveau du PROCESS (stderr
   réel, code de retour non nul) y est exposé (voir `_duree_tentative_anormale`,
   restreinte comme `_detecter_erreur_bloquante`, issue #761). Les deux
   tentatives prévues doivent être consommées normalement.

`gh` et `claude` sont remplacés par de faux exécutables (même technique que
tests/test_corrections_erreurs_bloquantes_761.py) : aucun appel réseau réel.

Exécution :  python3 tests/test_premier_marqueur_et_arret_rapide_763.py
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


def scenario_premier_marqueur_retenu_malgre_puce_echec_plus_loin():
    """Point 1 : rapport apiselect #56 reconstitué — ✅ en tête, ❌ dans une
    puce de la section « lacunes de tests » plus loin dans le texte. Le
    verdict retenu doit être le PREMIER marqueur (✅), pas le dernier (❌)."""
    rapport = (
        "✅ Tâche terminée — ajout des tests manquants pour /api/select\n\n"
        "<details>\n<summary>Détails complets</summary>\n\n"
        "## Lacunes de tests restantes\n\n"
        "- ❌ cas limite : filtre vide non couvert\n"
        "- ❌ cas limite : pagination négative non couverte\n\n"
        "</details>\n"
    )
    verdict = watcher._verdict_final(rapport)
    assert verdict == "✅", f"verdict attendu ✅ (première ligne), obtenu {verdict!r}"

    # Contrôle inverse : un vrai échec annoncé en tête reste bien détecté
    # comme tel même si une puce ultérieure porte le marqueur ✅ (ex. liste de
    # critères déjà remplis avant l'échec final).
    rapport_echec = (
        "❌ Tâche échouée — permission refusée sur le dépôt cible\n\n"
        "- ✅ lecture du code effectuée\n- ✅ diagnostic posé\n"
    )
    verdict_echec = watcher._verdict_final(rapport_echec)
    assert verdict_echec == "❌", f"verdict attendu ❌ (première ligne), obtenu {verdict_echec!r}"

    return {"verdict_succes": verdict, "verdict_echec": verdict_echec}


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


def _lancer_avec_contexte_isole(tmp_path: Path, rep_travail: Path, bin_dir: Path,
                                 nom_cfg: str, max_essais: int, numero: int, titre: str):
    """Isolation commune aux scénarios 2 et 3 : PATH, dossiers de logs/verrous
    et Config temporaires, restaurés dans tous les cas (même esprit que
    tests/test_corrections_erreurs_bloquantes_761.py)."""
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
        nom=nom_cfg, depot="AlainDelree/depot-inexistant-test763",
        rep_travail=rep_travail, topic_ntfy=nom_cfg,
        max_essais=max_essais, timeout_claude=15, notifier_local=False,
    )
    watcher.issues_en_cours.discard(numero)

    commentaires = []
    labels_poses = []
    ancien_commenter = watcher.commenter_issue
    ancien_ajouter_label = watcher.ajouter_label

    def _faux_commenter(num, message):
        commentaires.append(message)

    def _faux_ajouter_label(num, label):
        labels_poses.append(label)

    watcher.commenter_issue = _faux_commenter
    watcher.ajouter_label = _faux_ajouter_label

    try:
        issue = _issue_minimale(numero, titre, ["mode_scratch"])
        watcher.traiter_issue(issue, dry_run=False)
    finally:
        watcher.CFG = ancien_cfg
        watcher.commenter_issue = ancien_commenter
        watcher.ajouter_label = ancien_ajouter_label
        if ancien_path:
            os.environ["PATH"] = ancien_path
        else:
            os.environ.pop("PATH", None)
        watcher.DOSSIER_VERROUS = ancien_dossier_verrous
        watcher.DOSSIER_LOGS = ancien_dossier_logs
        watcher.FICHIER_HISTORIQUE = ancien_fichier_historique
        watcher.FICHIER_ETAT_TIMEOUT = ancien_fichier_etat_timeout
        watcher.FICHIER_ETAT_AMBIANCE = ancien_fichier_etat_ambiance
        watcher.issues_en_cours.discard(numero)

    return commentaires, labels_poses


def scenario_tentative_anormalement_rapide_arrete_immediatement():
    """Point 2 : un VRAI échec de process (code de retour non nul, quasi
    instantané — bien sous SEUIL_DUREE_TENTATIVE_ANORMALE_S) doit arrêter le
    traitement dès la première tentative, label needs-human posé, message
    invitant à vérifier authentification/binaire, SANS consommer les 5
    tentatives prévues."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        rep_travail = tmp_path / "projet"
        rep_travail.mkdir()
        _init_depot_git(rep_travail)

        compteur = tmp_path / "compteur_appels"
        # Échec immédiat, SANS signature reconnue par
        # SIGNATURES_ERREUR_BLOQUANTE_CLAUDE (sinon #760 déclencherait
        # l'arrêt avant même d'atteindre ce nouveau garde-fou de durée) —
        # message technique générique, comme le "No messages returned from
        # query" réellement constaté sur #762 pour une authentification
        # absente.
        script_claude = f"""#!/bin/bash
if [ "$#" -ge 2 ]; then
    echo x >> {compteur}
    echo "Error: unexpected end of stream" >&2
    exit 1
fi
exit 0
"""
        bin_dir = _preparer_faux_claude(tmp_path, script_claude)
        commentaires, labels_poses = _lancer_avec_contexte_isole(
            tmp_path, rep_travail, bin_dir, "test763rapide", max_essais=5,
            numero=97631, titre="Test #763 — tentative anormalement rapide")

        nb_appels = sum(1 for _ in compteur.read_text(encoding="utf-8").splitlines()) if compteur.exists() else 0
        assert nb_appels == 1, (
            f"l'arrêt aurait dû être immédiat dès la 1re tentative (sur 5 prévues) — {nb_appels} appel(s) constaté(s)")
        assert "needs-human" in labels_poses, f"label needs-human attendu, labels posés : {labels_poses}"
        assert commentaires, "un commentaire de clôture était attendu"
        message = commentaires[-1]
        assert "authentif" in message.lower(), f"le message devrait inviter à vérifier l'authentification : {message}"
        assert "binaire" in message.lower(), f"le message devrait inviter à vérifier le binaire : {message}"

    return {"tentatives_consommees": nb_appels, "labels": labels_poses}


def scenario_rapport_instantane_sans_marqueur_ne_declenche_pas_arret_rapide():
    """Point 3 (contrôle) : un rapport d'agent reclassé en échec par le
    garde-fou #581 (sans ✅/❌, exit 0) et produit quasi instantanément par le
    faux exécutable NE DOIT PAS être traité comme une tentative anormalement
    rapide — seul un échec de PROCESS (stderr réel) est concerné. Les 2
    tentatives prévues doivent être consommées normalement, comme avant
    #763."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        rep_travail = tmp_path / "projet"
        rep_travail.mkdir()
        _init_depot_git(rep_travail)

        compteur = tmp_path / "compteur_appels"
        script_claude = f"""#!/bin/bash
for arg in "$@"; do
    if [[ "$arg" == *"diagnostic RAPIDE"* ]]; then
        echo "- piste de diagnostic 1"
        exit 0
    fi
done
if [ "$#" -ge 2 ]; then
    echo x >> {compteur}
    echo "Rapport sans marqueur de clôture attendu."
fi
exit 0
"""
        bin_dir = _preparer_faux_claude(tmp_path, script_claude)
        commentaires, labels_poses = _lancer_avec_contexte_isole(
            tmp_path, rep_travail, bin_dir, "test763lent", max_essais=2,
            numero=97632, titre="Test #763 — rapport reclassé #581")

        nb_appels = sum(1 for _ in compteur.read_text(encoding="utf-8").splitlines()) if compteur.exists() else 0
        assert nb_appels == 2, (
            "les 2 tentatives prévues (max_essais=2) auraient dû être consommées "
            f"(reclassification #581, pas un échec de process) — {nb_appels} appel(s) constaté(s)")

    return {"tentatives_consommees": nb_appels}


def main():
    if os.name == "nt":
        print("  (ignoré : ce test s'appuie sur bash/git POSIX, non applicable sous Windows)")
        return 0

    tests = [
        ("premier marqueur ✅/❌ retenu (corrige #757, scénario apiselect #56)",
         scenario_premier_marqueur_retenu_malgre_puce_echec_plus_loin),
        ("tentative anormalement rapide → arrêt immédiat, needs-human, message authentification/binaire",
         scenario_tentative_anormalement_rapide_arrete_immediatement),
        ("rapport #581 instantané sans marqueur → PAS d'arrêt rapide, tentatives consommées",
         scenario_rapport_instantane_sans_marqueur_ne_declenche_pas_arret_rapide),
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
