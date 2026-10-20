#!/usr/bin/env python3
"""Test de non-régression — issue #781 (incident chesscoach #127) :

1. Plafonds de session explicites pour l'agent vibe (--max-turns/--max-price/
   --max-tokens, centralisés dans `AGENTS_CONNUS["vibe"]["plafonds_session"]`)
   — transmis sur la ligne de commande réellement construite par
   `_construire_cmd_vibe`, pour les deux modes qui l'utilisent (MODE_LECTURE,
   MODE_ECRITURE), et de bout en bout via `lancer_claude` + un faux `vibe` qui
   capture ses arguments. `--time-limit` (délai) volontairement ABSENT : déjà
   géré par le watcher lui-même (timeout de `proc.communicate`), pas dupliqué
   ici. L'agent `claude` (historique) reste inchangé (aucun de ces drapeaux).

2. Code de retour et taille de la sortie capturée, tracés dans le journal à
   CHAQUE tentative (`lancer_claude`), succès comme échec — avant cette
   issue, seul l'échec loggait le code de retour, et aucune taille n'était
   jamais journalisée.

3. Message corrigé de `_gerer_verdict_illisible_avec_commits` (garde-fou
   d'arrêt sur commits présents, issue #777) : ne reprend plus l'hypothèse
   de l'issue #581 (réponse tardive d'un sous-agent ayant écrasé le rapport,
   qui orientait la relecture dans la mauvaise direction sur l'incident
   chesscoach #127 — rien ne prouvait un sous-agent en retard, et le process
   semble simplement s'être arrêté avant d'écrire son rapport). Le nouveau
   message dit ce qui est constaté (rapport non atteint, travail probable,
   à vérifier) et conserve la fin brute de la sortie capturée comme seul
   élément factuel repris de l'ancien message.

Exécution :  python3 tests/test_plafonds_vibe_et_message_commits_781.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import logging
import os
import stat
import sys
import tempfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import watcher  # noqa: E402
from garde_fou_faux_executables import verifier_faux_executables_actifs  # noqa: E402


def _ecrire_executable(chemin: Path, script: str) -> None:
    chemin.write_text(script, encoding="utf-8")
    chemin.chmod(chemin.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


# ─── Scénario 1 : plafonds dans la commande construite (fonction pure) ────────

def scenario_construire_cmd_vibe_pose_les_plafonds():
    plafonds = watcher.AGENTS_CONNUS["vibe"]["plafonds_session"]
    for mode in (watcher.MODE_LECTURE, watcher.MODE_ECRITURE):
        cmd = watcher._construire_cmd_vibe(mode, "", "mon prompt", Path("/tmp"))
        assert "--max-turns" in cmd, f"mode {mode} : --max-turns absent de {cmd}"
        i = cmd.index("--max-turns")
        assert cmd[i + 1] == str(plafonds["max_turns"]), cmd
        assert "--max-price" in cmd, f"mode {mode} : --max-price absent de {cmd}"
        i = cmd.index("--max-price")
        assert cmd[i + 1] == str(plafonds["max_price_dollars"]), cmd
        assert "--max-tokens" in cmd, f"mode {mode} : --max-tokens absent de {cmd}"
        i = cmd.index("--max-tokens")
        assert cmd[i + 1] == str(plafonds["max_tokens"]), cmd
        assert "--time-limit" not in cmd, (
            f"mode {mode} : --time-limit ne doit PAS être posé (déjà géré par "
            f"le watcher, voir lancer_claude) : {cmd}")
    return {"plafonds_presents_tous_modes": True, "time_limit_absent": True}


def scenario_claude_historique_sans_plafond():
    """`claude` (agent historique) ne doit recevoir AUCUN de ces drapeaux —
    comportement inchangé par cette issue."""
    cmd = watcher._construire_cmd_claude(watcher.MODE_ECRITURE, "", "mon prompt", Path("/tmp"))
    for drapeau in ("--max-turns", "--max-price", "--max-tokens", "--time-limit"):
        assert drapeau not in cmd, f"{drapeau} ne devrait jamais apparaître pour claude : {cmd}"
    return {"claude_inchange": True}


# ─── Scénario 2 : plafonds de bout en bout via lancer_claude ──────────────────

def scenario_plafonds_transmis_au_vrai_subprocess_vibe():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        rep_travail = tmp_path / "projet"
        rep_travail.mkdir()
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        capture_argv = tmp_path / "capture_argv"

        _ecrire_executable(bin_dir / "vibe", f"""#!/bin/bash
printf '%s\\n' "$@" > {capture_argv}
echo "sortie de test"
exit 0
""")
        _ecrire_executable(bin_dir / "gh", "#!/bin/bash\nexit 0\n")

        ancien_path = os.environ.get("PATH", "")
        os.environ["PATH"] = f"{bin_dir}{os.pathsep}{ancien_path}"
        try:
            verifier_faux_executables_actifs(bin_dir, ["vibe", "gh"])

            ancien_cfg = watcher.CFG
            watcher.CFG = watcher.Config(
                nom="test781vibe", depot="AlainDelree/depot-inexistant-test781",
                rep_travail=rep_travail, topic_ntfy="test781vibe",
                max_essais=1, timeout_claude=15, notifier_local=False,
                agent="vibe",
            )
            try:
                succes, sortie = watcher.lancer_claude(
                    97811, "titre", "body", dry_run=False, mode=watcher.MODE_ECRITURE,
                    cwd=rep_travail, timeout=15,
                )
            finally:
                watcher.CFG = ancien_cfg
            assert succes is True, f"le faux vibe sort en code 0 : succès attendu, obtenu : {sortie}"
        finally:
            if ancien_path:
                os.environ["PATH"] = ancien_path
            else:
                os.environ.pop("PATH", None)

        lignes = capture_argv.read_text(encoding="utf-8").splitlines()
        plafonds = watcher.AGENTS_CONNUS["vibe"]["plafonds_session"]
        for drapeau, valeur in (
            ("--max-turns", str(plafonds["max_turns"])),
            ("--max-price", str(plafonds["max_price_dollars"])),
            ("--max-tokens", str(plafonds["max_tokens"])),
        ):
            assert drapeau in lignes, f"{drapeau} absent de la commande réellement lancée : {lignes}"
            i = lignes.index(drapeau)
            assert lignes[i + 1] == valeur, f"valeur de {drapeau} inattendue : {lignes}"
        assert "--time-limit" not in lignes, f"--time-limit n'aurait pas dû être transmis : {lignes}"

    return {"plafonds_recus_par_le_vrai_subprocess": True}


# ─── Scénario 3 : code de retour + taille de sortie tracés à chaque tentative ──

class _CaptureLog(logging.Handler):
    def __init__(self):
        super().__init__()
        self.messages = []

    def emit(self, record):
        self.messages.append(record.getMessage())


def scenario_succes_et_echec_journalisent_code_retour_et_taille():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        rep_travail = tmp_path / "projet"
        rep_travail.mkdir()
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()

        _ecrire_executable(bin_dir / "claude", """#!/bin/bash
for arg in "$@"; do
    if [[ "$arg" == *"MARQUEUR_ECHEC_781"* ]]; then
        echo "erreur fatale" >&2
        exit 7
    fi
done
printf '%s' "0123456789"
exit 0
""")

        ancien_path = os.environ.get("PATH", "")
        os.environ["PATH"] = f"{bin_dir}{os.pathsep}{ancien_path}"
        capture = _CaptureLog()
        watcher.log.addHandler(capture)
        ancien_niveau = watcher.log.level
        watcher.log.setLevel(logging.INFO)
        try:
            verifier_faux_executables_actifs(bin_dir, ["claude"])

            ancien_cfg = watcher.CFG
            watcher.CFG = watcher.Config(
                nom="test781log", depot="AlainDelree/depot-inexistant-test781",
                rep_travail=rep_travail, topic_ntfy="test781log",
                max_essais=1, timeout_claude=15, notifier_local=False,
                agent="claude",
            )
            try:
                succes_ok, sortie_ok = watcher.lancer_claude(
                    97821, "titre", "corps normal", dry_run=False, mode=watcher.MODE_LECTURE,
                    cwd=rep_travail, timeout=15, tentative=1,
                )
                succes_ko, sortie_ko = watcher.lancer_claude(
                    97822, "titre", "MARQUEUR_ECHEC_781", dry_run=False, mode=watcher.MODE_LECTURE,
                    cwd=rep_travail, timeout=15, tentative=1,
                )
            finally:
                watcher.CFG = ancien_cfg
        finally:
            watcher.log.removeHandler(capture)
            watcher.log.setLevel(ancien_niveau)
            if ancien_path:
                os.environ["PATH"] = ancien_path
            else:
                os.environ.pop("PATH", None)

        assert succes_ok is True, sortie_ok
        assert succes_ko is False, sortie_ko

        lignes_succes = [m for m in capture.messages if "#97821" in m and "code retour" in m]
        assert lignes_succes, f"aucune ligne de journal avec le code de retour pour la tentative réussie : {capture.messages}"
        assert "code retour 0" in lignes_succes[0], lignes_succes[0]
        assert "10 car." in lignes_succes[0], (
            f"taille de stdout (10 caractères, '0123456789\\n'.strip()) attendue dans le journal : {lignes_succes[0]}")

        lignes_echec = [m for m in capture.messages if "#97822" in m and "code retour" in m]
        assert lignes_echec, f"aucune ligne de journal avec le code de retour pour la tentative échouée : {capture.messages}"
        assert "code retour 7" in lignes_echec[0], lignes_echec[0]

    return {"succes_trace": True, "echec_trace": True}


# ─── Scénario 4 : message corrigé (plus d'hypothèse #581 sur commits présents) ─

def scenario_message_commits_ne_reprend_plus_hypothese_581():
    sortie_type_581 = (
        "Sortie de claude sans aucune ligne de verdict de clôture "
        "attendue (ni succès ni échec) — probablement une réponse "
        "tardive émise après la fin réelle du traitement (ex. "
        "notification d'un sous-agent en arrière-plan terminé après le "
        "rapport final), qui a écrasé la vraie réponse dans la sortie "
        f"capturée (issue #581). {watcher._MARQUEUR_FIN_BRUTE_SORTIE}"
        "annonce la production du rapport..."
    )

    ancien_cfg = watcher.CFG
    watcher.CFG = watcher.Config(
        nom="test781msg", depot="AlainDelree/depot-inexistant-test781",
        rep_travail=Path("/tmp"), topic_ntfy="test781msg",
    )
    commentaires, labels_poses, notifs = [], [], []
    ancien_commenter = watcher.commenter_issue
    ancien_ajouter_label = watcher.ajouter_label
    ancien_notifier = watcher.notifier
    ancien_notifier_fin_sse = watcher.notifier_fin_sse
    watcher.commenter_issue = lambda num, msg: commentaires.append(msg)
    watcher.ajouter_label = lambda num, lab: labels_poses.append(lab)
    watcher.notifier = lambda *a, **k: notifs.append((a, k))
    watcher.notifier_fin_sse = lambda *a, **k: None
    try:
        watcher._gerer_verdict_illisible_avec_commits(
            97831, "titre", "corps", [], watcher.MODE_LECTURE, sortie_type_581,
            ["abc1234 fix-781-simulation"], "", "")
    finally:
        watcher.CFG = ancien_cfg
        watcher.commenter_issue = ancien_commenter
        watcher.ajouter_label = ancien_ajouter_label
        watcher.notifier = ancien_notifier
        watcher.notifier_fin_sse = ancien_notifier_fin_sse

    assert commentaires, "un commentaire de clôture était attendu"
    message = commentaires[-1]

    for texte_proscrit in ("réponse tardive", "sous-agent", "issue #581"):
        assert texte_proscrit not in message, (
            f"l'hypothèse #581 ne devrait plus apparaître dans ce message "
            f"(commits présents, cause différente) — trouvé « {texte_proscrit} » : {message}")

    assert "ne s'est pas rendu jusqu'à son rapport" in message, (
        f"le message devrait dire ce qui est constaté (rapport non atteint) : {message}")
    assert "vérifier" in message.lower(), message
    assert "fix-781-simulation" in message, f"le commit devrait rester listé : {message}"
    assert "annonce la production du rapport" in message, (
        f"la fin brute de la sortie capturée devrait rester utile au diagnostic : {message}")
    assert "needs-human" in labels_poses

    return {"hypothese_581_absente": True, "faits_constates_presents": True}


def main():
    if os.name == "nt":
        print("  (ignoré : ce test s'appuie sur bash, non applicable sous Windows)")
        return 0

    tests = [
        ("_construire_cmd_vibe pose les plafonds (max-turns/max-price/max-tokens), pas --time-limit",
         scenario_construire_cmd_vibe_pose_les_plafonds),
        ("_construire_cmd_claude (agent historique) ne pose aucun de ces plafonds",
         scenario_claude_historique_sans_plafond),
        ("bout en bout : le vrai subprocess vibe reçoit bien les plafonds",
         scenario_plafonds_transmis_au_vrai_subprocess_vibe),
        ("lancer_claude journalise code de retour + taille de sortie, succès et échec",
         scenario_succes_et_echec_journalisent_code_retour_et_taille),
        ("message d'arrêt sur commits présents : hypothèse #581 retirée, faits constatés affichés",
         scenario_message_commits_ne_reprend_plus_hypothese_581),
    ]

    logging.getLogger().addHandler(logging.NullHandler())

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
