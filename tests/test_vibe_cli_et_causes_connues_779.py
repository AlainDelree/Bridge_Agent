#!/usr/bin/env python3
"""Test de non-régression — issue #779 : incident chesscoach #126, Vibe a
changé d'interface par défaut lors d'une mise à jour silencieuse et
n'acceptait plus les options construites par `_construire_cmd_vibe`.

Vérifie :
1. `lancer_claude` pose `VIBE_CLI=python` dans l'environnement du SEUL
   subprocess `vibe` qu'il lance (`AGENTS_CONNUS["vibe"]["env"]`), fusionné
   sur une copie de `os.environ` — jamais sur l'environnement du watcher
   lui-même, jamais pour l'agent `claude` (comportement historique inchangé).
2. `_detecter_cause_connue_echec_rapide` reconnaît la signature du message
   réel de Vibe annonçant sa nouvelle interface en préversion, et la
   signature générique « binaire introuvable » — sans rien reconnaître
   d'une sortie ordinaire (repli sur `None`, texte générique conservé côté
   appelant).
3. `_gerer_tentative_anormalement_rapide` affiche la cause reconnue (et son
   remède) à la place du texte générique pointant vers l'authentification,
   dans le commentaire de clôture posté sur l'issue.

Un VRAI `vibe` est installé sur cette machine (`uv tool`, agent Mistral) :
`verifier_faux_executables_actifs` est appelée avant tout lancement pour
garantir que seul le faux exécutable de ce test est atteint — jamais une
session Vibe réelle, facturée.

Exécution :  python3 tests/test_vibe_cli_et_causes_connues_779.py
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


def _ecrire_executable(chemin: Path, script: str) -> None:
    chemin.write_text(script, encoding="utf-8")
    chemin.chmod(chemin.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def scenario_variable_posee_pour_vibe_seul():
    """Point 1 : le subprocess `vibe` reçoit VIBE_CLI=python ; le subprocess
    `claude` ne le reçoit PAS ; l'environnement du watcher lui-même (os.environ)
    n'est jamais modifié par l'appel."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        rep_travail = tmp_path / "projet"
        rep_travail.mkdir()

        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        capture_vibe = tmp_path / "capture_vibe"
        capture_claude = tmp_path / "capture_claude"

        _ecrire_executable(bin_dir / "vibe", f"""#!/bin/bash
echo "VIBE_CLI=${{VIBE_CLI:-<absent>}}" > {capture_vibe}
exit 0
""")
        _ecrire_executable(bin_dir / "claude", f"""#!/bin/bash
echo "VIBE_CLI=${{VIBE_CLI:-<absent>}}" > {capture_claude}
exit 0
""")

        ancien_path = os.environ.get("PATH", "")
        os.environ["PATH"] = f"{bin_dir}{os.pathsep}{ancien_path}"
        assert "VIBE_CLI" not in os.environ, "précondition : VIBE_CLI ne doit pas déjà exister dans l'environnement du watcher"
        try:
            verifier_faux_executables_actifs(bin_dir, ["vibe", "claude"])

            ancien_cfg = watcher.CFG
            # Agent vibe : VIBE_CLI=python attendu dans le subprocess.
            watcher.CFG = watcher.Config(
                nom="test779vibe", depot="AlainDelree/depot-inexistant-test779",
                rep_travail=rep_travail, topic_ntfy="test779vibe",
                max_essais=1, timeout_claude=15, notifier_local=False,
                agent="vibe",
            )
            try:
                succes, _sortie = watcher.lancer_claude(
                    97791, "titre", "body", dry_run=False, mode=watcher.MODE_LECTURE,
                    cwd=rep_travail, timeout=15,
                )
            finally:
                watcher.CFG = ancien_cfg
            assert succes is True, "le faux exécutable vibe sort en code 0 : succès attendu"

            # Agent claude : comportement historique inchangé, pas de VIBE_CLI.
            watcher.CFG = watcher.Config(
                nom="test779claude", depot="AlainDelree/depot-inexistant-test779",
                rep_travail=rep_travail, topic_ntfy="test779claude",
                max_essais=1, timeout_claude=15, notifier_local=False,
                agent="claude",
            )
            try:
                succes, _sortie = watcher.lancer_claude(
                    97792, "titre", "body", dry_run=False, mode=watcher.MODE_LECTURE,
                    cwd=rep_travail, timeout=15,
                )
            finally:
                watcher.CFG = ancien_cfg
            assert succes is True, "le faux exécutable claude sort en code 0 : succès attendu"
        finally:
            if ancien_path:
                os.environ["PATH"] = ancien_path
            else:
                os.environ.pop("PATH", None)

        assert capture_vibe.read_text(encoding="utf-8").strip() == "VIBE_CLI=python", (
            f"le subprocess vibe aurait dû recevoir VIBE_CLI=python : {capture_vibe.read_text(encoding='utf-8')!r}")
        assert capture_claude.read_text(encoding="utf-8").strip() == "VIBE_CLI=<absent>", (
            f"le subprocess claude ne devrait PAS recevoir VIBE_CLI : {capture_claude.read_text(encoding='utf-8')!r}")
        assert "VIBE_CLI" not in os.environ, (
            "l'environnement du watcher lui-même ne doit JAMAIS porter VIBE_CLI après l'appel")

    return {"vibe_recoit_la_variable": True, "claude_inchange": True, "os_environ_watcher_intact": True}


def scenario_reconnaissance_signature_interface_vibe():
    """Point 2 : la signature du message RÉEL de Vibe (confirmé en lisant le
    binaire installé — "Please report this error ... To switch back to the
    classic TUI, set VIBE_CLI=python.") est reconnue, de même que la
    signature générique "binaire introuvable" ; une sortie ordinaire ne
    déclenche aucune reconnaissance (repli sur None)."""
    ancien_cfg = watcher.CFG
    watcher.CFG = watcher.Config(
        nom="test779sig", depot="AlainDelree/depot-inexistant-test779",
        rep_travail=Path("/tmp"), topic_ntfy="test779sig",
        agent="vibe",
    )
    try:
        sortie_preview = (
            "WARNING: You are using the new Vibe TUI, currently in preview. "
            "Please report this error at https://github.com/mistralai/mistral-vibe/issues. "
            "To switch back to the classic TUI, set VIBE_CLI=python."
        )
        resultat = watcher._detecter_cause_connue_echec_rapide(sortie_preview)
        assert resultat is not None, "la signature de la nouvelle interface Vibe aurait dû être reconnue"
        cause, remede = resultat
        assert "préversion" in cause.lower() or "interface" in cause.lower(), f"cause inattendue : {cause}"
        assert "vibe_cli" in remede.lower(), f"remède inattendu (devrait mentionner VIBE_CLI) : {remede}"

        resultat_introuvable = watcher._detecter_cause_connue_echec_rapide(
            watcher.AGENTS_CONNUS["vibe"]["msg_binaire_introuvable"])
        assert resultat_introuvable is not None, "la signature « binaire introuvable » aurait dû être reconnue"
        assert resultat_introuvable[0] == "binaire introuvable", f"cause inattendue : {resultat_introuvable}"

        resultat_ordinaire = watcher._detecter_cause_connue_echec_rapide(
            "Error: unexpected end of stream")
        assert resultat_ordinaire is None, f"aucune signature ne devrait matcher une sortie ordinaire : {resultat_ordinaire}"
    finally:
        watcher.CFG = ancien_cfg

    return {"signature_preview_reconnue": True, "signature_introuvable_reconnue": True, "repli_none_ok": True}


def scenario_message_cloture_mentionne_cause_reconnue_pas_authentif():
    """Point 3 : bout en bout via `traiter_issue` — un faux `vibe` qui échoue
    instantanément en reproduisant le message réel de la nouvelle interface
    doit produire un commentaire de clôture citant cette cause précise
    (préversion / VIBE_CLI), PAS le texte générique d'authentification."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        rep_travail = tmp_path / "projet"
        rep_travail.mkdir()
        subprocess.run(["git", "init", "-q", "-b", "master", str(rep_travail)], check=True)
        (rep_travail / "fichier.txt").write_text("original\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=rep_travail, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=rep_travail, check=True, capture_output=True)

        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        compteur = tmp_path / "compteur_appels"
        _ecrire_executable(bin_dir / "vibe", f"""#!/bin/bash
if [ "$#" -ge 2 ]; then
    echo x >> {compteur}
    echo "WARNING: You are using the new Vibe TUI, currently in preview. Please report this error at https://github.com/mistralai/mistral-vibe/issues. To switch back to the classic TUI, set VIBE_CLI=python." >&2
    exit 2
fi
exit 0
""")
        _ecrire_executable(bin_dir / "gh", "#!/bin/bash\nexit 0\n")

        ancien_path = os.environ.get("PATH", "")
        os.environ["PATH"] = f"{bin_dir}{os.pathsep}{ancien_path}"
        try:
            verifier_faux_executables_actifs(bin_dir, ["vibe", "gh"])
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
            nom="test779cloture", depot="AlainDelree/depot-inexistant-test779",
            rep_travail=rep_travail, topic_ntfy="test779cloture",
            max_essais=5, timeout_claude=15, notifier_local=False,
            agent="vibe",
        )
        watcher.issues_en_cours.discard(97793)

        commentaires = []
        labels_poses = []
        ancien_commenter = watcher.commenter_issue
        ancien_ajouter_label = watcher.ajouter_label
        watcher.commenter_issue = lambda num, message: commentaires.append(message)
        watcher.ajouter_label = lambda num, label: labels_poses.append(label)

        try:
            issue = _issue_minimale(97793, "Test #779 — nouvelle interface Vibe", [])
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
            watcher.issues_en_cours.discard(97793)

        nb_appels = sum(1 for _ in compteur.read_text(encoding="utf-8").splitlines()) if compteur.exists() else 0
        assert nb_appels == 1, (
            f"l'arrêt aurait dû être immédiat dès la 1re tentative (sur 5 prévues) — {nb_appels} appel(s) constaté(s)")
        assert "needs-human" in labels_poses, f"label needs-human attendu, labels posés : {labels_poses}"
        assert commentaires, "un commentaire de clôture était attendu"
        message = commentaires[-1]
        assert "vibe_cli" in message.lower(), f"le message devrait citer la cause reconnue (VIBE_CLI) : {message}"
        assert "authentifié sur cette machine" not in message, (
            f"le texte générique d'authentification n'aurait pas dû être affiché ici : {message}")

    return {"tentatives_consommees": nb_appels, "labels": labels_poses}


def main():
    if os.name == "nt":
        print("  (ignoré : ce test s'appuie sur bash/git POSIX, non applicable sous Windows)")
        return 0

    tests = [
        ("VIBE_CLI=python posé pour le subprocess vibe seul, claude et os.environ du watcher inchangés",
         scenario_variable_posee_pour_vibe_seul),
        ("reconnaissance des signatures (nouvelle interface Vibe, binaire introuvable, repli None)",
         scenario_reconnaissance_signature_interface_vibe),
        ("message de clôture : cause reconnue citée, texte générique d'authentification absent",
         scenario_message_cloture_mentionne_cause_reconnue_pas_authentif),
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
