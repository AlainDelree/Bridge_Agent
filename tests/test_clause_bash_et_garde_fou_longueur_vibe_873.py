#!/usr/bin/env python3
"""Test de non-régression — issue #873 :

1. Clause de prompt « bash refusé » propre à Vibe (`_CLAUSE_BASH_VIBE`,
   `AGENTS_CONNUS["vibe"]["clause_bash"]`) : présente dans le prompt construit
   par `lancer_claude` pour l'agent "vibe" (point 5 des instructions, juste
   après la clause « sous-agents »), ABSENTE pour l'agent "claude" — ce
   dernier n'a pas ce problème (`--dangerously-skip-permissions` ne refuse
   aucune syntaxe shell). Contenu attendu : consigne d'utiliser write_file/
   edit plutôt que bash, interdiction de la substitution de commande et de
   la redirection, interdiction du `cd` vers le dossier de travail, et
   consigne de ne pas retenter une commande refusée sous la même forme.

2. Garde-fou de longueur (`PromptTropLong`, `LIMITE_CAR_PROMPT_VIBE_WINDOWS`)
   dans `_construire_cmd_vibe` : lève proprement au-delà de la limite,
   UNIQUEMENT sous Windows (`os.name == "nt"`, jamais sur CCL) ; capturée par
   `lancer_claude`, qui retourne un échec ordinaire (message clair) plutôt que
   de laisser l'exception remonter. `claude` (agent historique) n'a aucune
   limite équivalente : jamais affecté.

`vibe` n'est volontairement jamais invoqué réellement (consigne de l'issue
#873, comme #760/#761 : pas de session vibe réelle, facturée) — tous les
scénarios appellent directement les fonctions Python concernées, ou passent
par un faux `vibe`/`gh` (même technique que tests/test_lecture_active_327.py)
qui ne fait jamais de session réelle non plus.

Exécution :  python3 tests/test_clause_bash_et_garde_fou_longueur_vibe_873.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import os
import stat
import sys
import tempfile
from pathlib import Path
from unittest import mock

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import watcher  # noqa: E402
from garde_fou_faux_executables import verifier_faux_executables_actifs  # noqa: E402


def _ecrire_executable(chemin: Path, script: str) -> None:
    chemin.write_text(script, encoding="utf-8")
    chemin.chmod(chemin.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


# ─── Scénario 1 : la clause est bien déclarée pour vibe, absente pour claude ──

def scenario_clause_bash_declaree_pour_vibe_seulement():
    assert "clause_bash" in watcher.AGENTS_CONNUS["vibe"], (
        "AGENTS_CONNUS['vibe'] devrait déclarer une clause_bash (issue #873)")
    clause = watcher.AGENTS_CONNUS["vibe"]["clause_bash"]
    for motif in ("write_file", "edit", "substitution", "redirection", "cd",
                  "NE LA RETENTE PAS"):
        assert motif in clause, f"motif « {motif} » absent de la clause bash vibe : {clause}"

    assert watcher.AGENTS_CONNUS["claude"].get("clause_bash", "") == "", (
        "claude ne devrait avoir aucune clause_bash (problème propre à vibe)")
    return {"clause_declaree_vibe": True, "absente_claude": True}


# ─── Scénario 2 : la clause apparaît dans le prompt réellement construit ──────

def scenario_clause_bash_dans_le_prompt_construit():
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
                nom="test873vibe", depot="AlainDelree/depot-inexistant-test873",
                rep_travail=rep_travail, topic_ntfy="test873vibe",
                max_essais=1, timeout_claude=15, notifier_local=False,
                agent="vibe",
            )
            try:
                succes, _ = watcher.lancer_claude(
                    98731, "titre", "body", dry_run=False, mode=watcher.MODE_ECRITURE,
                    cwd=rep_travail, timeout=15,
                )
            finally:
                watcher.CFG = ancien_cfg
            assert succes is True
        finally:
            if ancien_path:
                os.environ["PATH"] = ancien_path
            else:
                os.environ.pop("PATH", None)

        # `printf '%s\n' "$@"` éclate chaque argument multi-ligne (le prompt
        # l'est) sur plusieurs lignes de capture_argv : on cherche les motifs
        # dans le fichier entier plutôt que de reconstruire un découpage par
        # argument, qui ne survivrait pas aux retours à la ligne internes.
        contenu = capture_argv.read_text(encoding="utf-8")
        assert "--prompt" in contenu, contenu
        for motif in ("write_file", "edit", "substitution", "redirection"):
            assert motif in contenu, (
                f"motif « {motif} » absent du prompt réellement transmis au subprocess vibe")

    return {"clause_presente_dans_prompt_reel": True}


# ─── Scénario 3 : _construire_cmd_vibe lève PromptTropLong sous Windows ──────

def scenario_garde_fou_longueur_leve_sous_windows_seulement():
    prompt_trop_long = "x" * (watcher.LIMITE_CAR_PROMPT_VIBE_WINDOWS + 1)
    prompt_normal = "prompt normal, bien sous la limite"

    with mock.patch.object(watcher.os, "name", "nt"):
        try:
            watcher._construire_cmd_vibe(
                watcher.MODE_ECRITURE, "", prompt_trop_long, Path("/tmp"))
            raise AssertionError("PromptTropLong attendue, aucune exception levée")
        except watcher.PromptTropLong as e:
            assert str(watcher.LIMITE_CAR_PROMPT_VIBE_WINDOWS) in str(e), str(e)

        # Un prompt sous la limite ne doit JAMAIS déclencher le garde-fou,
        # même sous Windows.
        cmd = watcher._construire_cmd_vibe(
            watcher.MODE_ECRITURE, "", prompt_normal, Path("/tmp"))
        assert prompt_normal in cmd, cmd

    # Linux (os.name réel de ce test) : jamais déclenché, même très au-dessus
    # de la limite — la limite est spécifique à Windows (ARG_MAX bien plus
    # large sous Linux).
    cmd = watcher._construire_cmd_vibe(
        watcher.MODE_ECRITURE, "", prompt_trop_long, Path("/tmp"))
    assert prompt_trop_long in cmd, "le garde-fou ne doit pas se déclencher sous Linux"

    return {"leve_sous_windows": True, "jamais_sous_linux": True, "prompt_normal_ok": True}


# ─── Scénario 4 : lancer_claude convertit PromptTropLong en échec propre ─────

def scenario_lancer_claude_capture_prompt_trop_long():
    with tempfile.TemporaryDirectory() as tmp:
        rep_travail = Path(tmp) / "projet"
        rep_travail.mkdir()

        ancien_cfg = watcher.CFG
        watcher.CFG = watcher.Config(
            nom="test873long", depot="AlainDelree/depot-inexistant-test873",
            rep_travail=rep_travail, topic_ntfy="test873long",
            max_essais=1, timeout_claude=15, notifier_local=False,
            agent="vibe",
        )
        prompt_trop_long = "x" * (watcher.LIMITE_CAR_PROMPT_VIBE_WINDOWS + 1)
        try:
            with mock.patch.object(watcher.os, "name", "nt"):
                succes, message = watcher.lancer_claude(
                    98741, "titre", "body", dry_run=False, mode=watcher.MODE_ECRITURE,
                    cwd=rep_travail, timeout=15,
                    prompt_perso=prompt_trop_long,
                )
        finally:
            watcher.CFG = ancien_cfg

        assert succes is False, "un prompt trop long doit être un échec propre, pas un crash"
        assert "trop long" in message.lower(), message
        assert str(watcher.LIMITE_CAR_PROMPT_VIBE_WINDOWS) in message, message

    return {"echec_propre_sans_crash": True}


def main():
    if os.name == "nt":
        print("  (ignoré : ce test s'appuie sur bash, non applicable sous Windows)")
        return 0

    tests = [
        ("clause_bash déclarée pour vibe, absente pour claude",
         scenario_clause_bash_declaree_pour_vibe_seulement),
        ("clause_bash présente dans le prompt réellement transmis au subprocess vibe",
         scenario_clause_bash_dans_le_prompt_construit),
        ("_construire_cmd_vibe lève PromptTropLong au-delà de la limite, Windows seulement",
         scenario_garde_fou_longueur_leve_sous_windows_seulement),
        ("lancer_claude convertit PromptTropLong en échec propre (pas de crash)",
         scenario_lancer_claude_capture_prompt_trop_long),
    ]

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
