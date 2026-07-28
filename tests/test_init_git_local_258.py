#!/usr/bin/env python3
"""Test de `initialiser_git()` (`nouveau_projet.py`) — issue #257, étendu #258.

L'issue #257 avait été vérifiée manuellement sur des répertoires jetables
sous `/tmp` (deux cas : répertoire neuf, déjà-git), puis ces répertoires
supprimés — rien n'était resté sous `tests/`. L'issue #258 ajoute un
troisième cas (répertoire non versionné avec contenu préexistant → pas de
push automatique) et demande de garder trace des trois : ce fichier
persiste désormais les trois scénarios.

Aucun vrai dépôt GitHub n'est créé ni contacté : `depot` pointe vers un
dépôt qui n'existe pas, si bien que `git push` échoue proprement (dépôt
distant introuvable) sans jamais sortir du réseau local — cohérent avec le
test #257 d'origine.

Exécution :  python3 tests/test_init_git_local_258.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import subprocess
import sys
import tempfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import nouveau_projet as np  # noqa: E402

DEPOT_INEXISTANT = "AlainDelree/depot-de-test-258-inexistant"


def scenario_repertoire_neuf_vide():
    """Répertoire vide : comportement inchangé depuis #257 — init + commit +
    tentative de push automatiques, aucun fichier préexistant détecté."""
    with tempfile.TemporaryDirectory() as tmp:
        rep = Path(tmp)
        res = np.initialiser_git(str(rep), DEPOT_INEXISTANT)

        assert res["ok"], f"l'initialisation aurait dû réussir : {res}"
        assert res["deja_git"] is False
        assert res["contenu_preexistant"] == [], (
            f"un répertoire vide ne doit signaler aucun contenu préexistant : {res}")
        assert (rep / ".git").exists(), "git init n'a pas créé .git"
        assert (rep / ".gitignore").exists(), ".gitignore minimal non écrit"

        branche = subprocess.run(
            ["git", "branch", "--show-current"], cwd=rep,
            capture_output=True, text=True).stdout.strip()
        assert branche == "master", f"branche inattendue : {branche!r}"

        remote = subprocess.run(
            ["git", "remote", "get-url", "origin"], cwd=rep,
            capture_output=True, text=True).stdout.strip()
        assert remote == f"https://github.com/{DEPOT_INEXISTANT}.git", (
            f"remote HTTPS inattendu : {remote!r}")

        # Dépôt distant inexistant → le push doit échouer proprement, sans
        # faire échouer l'étape (ok reste True), et fournir la commande
        # manuelle de relance.
        assert res["push_ok"] is False, f"push_ok attendu False (dépôt inexistant) : {res}"
        assert res["commande_manuelle"] == f"cd {rep} && git push -u origin master"

    return {"push_ok": res["push_ok"], "contenu_preexistant": res["contenu_preexistant"]}


def scenario_deja_git():
    """Répertoire déjà versionné : comportement strictement inchangé — rien
    n'est fait, aucun remote ajouté, le fichier existant reste intact."""
    with tempfile.TemporaryDirectory() as tmp:
        rep = Path(tmp)
        subprocess.run(["git", "init", "-b", "main"], cwd=rep,
                       capture_output=True, text=True, check=True)
        marqueur = rep / "deja_la.txt"
        marqueur.write_text("contenu d'origine", encoding="utf-8")

        res = np.initialiser_git(str(rep), DEPOT_INEXISTANT)

        assert res == {
            "ok": True, "deja_git": True, "push_ok": None,
            "contenu_preexistant": [], "detail": "déjà un dépôt git — inchangé.",
            "commande_manuelle": None,
        }, res
        assert marqueur.read_text(encoding="utf-8") == "contenu d'origine"
        remote = subprocess.run(
            ["git", "remote"], cwd=rep, capture_output=True, text=True).stdout.strip()
        assert remote == "", f"aucun remote ne devrait avoir été ajouté : {remote!r}"

    return {"deja_git": res["deja_git"]}


def scenario_contenu_preexistant_pas_de_push():
    """Cœur de l'issue #258 : répertoire non versionné contenant déjà un
    fichier (ni CONTEXTE.md, ni Specs, ni .gitignore) → init/remote/commit
    faits normalement, mais AUCUNE tentative de push, et la commande
    manuelle de push renvoyée pour relecture avant publication (dépôt
    public)."""
    with tempfile.TemporaryDirectory() as tmp:
        rep = Path(tmp)
        fichier_prexistant = rep / "donnees_client.csv"
        fichier_prexistant.write_text("nom,montant\nDupont,42\n", encoding="utf-8")
        # Un CONTEXTE.md déjà là ne doit PAS compter comme contenu préexistant
        # (issue #258, point 2) : c'est un fichier que le script crée lui-même.
        (rep / "CONTEXTE.md").write_text("", encoding="utf-8")

        appels = []
        vrai_run = subprocess.run

        def run_espion(cmd, *args, **kwargs):
            appels.append(cmd)
            return vrai_run(cmd, *args, **kwargs)

        subprocess.run = run_espion
        try:
            res = np.initialiser_git(str(rep), DEPOT_INEXISTANT)
        finally:
            subprocess.run = vrai_run

        assert res["ok"], f"l'initialisation aurait dû réussir : {res}"
        assert res["deja_git"] is False
        assert res["push_ok"] is None, (
            f"push_ok doit rester None (retenue volontaire, pas un échec) : {res}")
        assert res["contenu_preexistant"] == ["donnees_client.csv"], (
            f"CONTEXTE.md ne doit pas apparaître, seul le fichier réellement "
            f"préexistant doit être signalé : {res['contenu_preexistant']}")
        assert res["commande_manuelle"] == f"cd {rep} && git push -u origin master"
        assert "public" in res["detail"] and "relu" in res["detail"], (
            f"le compte-rendu doit expliquer pourquoi (dépôt public, non relu) : {res['detail']}")

        assert (rep / ".git").exists(), "git init n'a pas créé .git malgré le contenu préexistant"
        commits = vrai_run(["git", "log", "--oneline"], cwd=rep,
                           capture_output=True, text=True).stdout.strip().splitlines()
        assert len(commits) == 1, f"un seul commit initial attendu : {commits}"

        # Aucune commande `git push` ne doit avoir été tentée.
        commandes_push = [c for c in appels if isinstance(c, list) and "push" in c]
        assert not commandes_push, (
            f"un push a été tenté malgré le contenu préexistant : {commandes_push}")

    return {"contenu_preexistant": res["contenu_preexistant"],
            "commande_manuelle": res["commande_manuelle"]}


def scenario_timeout_git_ne_fait_pas_echouer_la_creation():
    """Point 1 de l'issue #258 : un `git push` qui dépasse son timeout doit
    être traité comme un échec normal de l'étape (comme un push refusé par
    le réseau), jamais remonter comme une exception ni bloquer l'appelant.
    Un faux `git` (en tête de PATH) délègue tout au vrai binaire sauf
    `push`, qu'il fait dépasser volontairement le timeout en dormant."""
    import os
    import stat

    with tempfile.TemporaryDirectory() as tmp:
        rep = Path(tmp) / "projet"
        rep.mkdir()
        bin_dir = Path(tmp) / "bin"
        bin_dir.mkdir()
        faux_git = bin_dir / "git"
        vrai_git = subprocess.run(["which", "git"], capture_output=True,
                                  text=True).stdout.strip()
        faux_git.write_text(
            "#!/bin/bash\n"
            'if [ "$1" = "push" ]; then\n'
            "  sleep 2\n"
            "  exit 0\n"
            "fi\n"
            f'exec "{vrai_git}" "$@"\n',
            encoding="utf-8",
        )
        faux_git.chmod(faux_git.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

        ancien_path = os.environ.get("PATH", "")
        ancien_timeout_push = np.TIMEOUT_GIT_PUSH
        os.environ["PATH"] = f"{bin_dir}{os.pathsep}{ancien_path}"
        np.TIMEOUT_GIT_PUSH = 0.3
        try:
            res = np.initialiser_git(str(rep), DEPOT_INEXISTANT)
        finally:
            os.environ["PATH"] = ancien_path
            np.TIMEOUT_GIT_PUSH = ancien_timeout_push

        assert res["ok"], (
            f"un timeout de push ne doit PAS faire échouer la création : {res}")
        assert res["push_ok"] is False, f"push_ok attendu False après timeout : {res}"
        assert res["commande_manuelle"] == f"cd {rep} && git push -u origin master"

    return {"ok": res["ok"], "push_ok": res["push_ok"]}


def main():
    tests = [
        ("répertoire neuf vide → init + commit + tentative de push",
         scenario_repertoire_neuf_vide),
        ("déjà un dépôt git → strictement inchangé",
         scenario_deja_git),
        ("contenu préexistant (issue #258) → init/commit locaux, "
         "aucun push tenté, commande manuelle renvoyée",
         scenario_contenu_preexistant_pas_de_push),
        ("timeout de git push (issue #258) → échec normal de l'étape, "
         "pas d'exception, création non bloquée",
         scenario_timeout_git_ne_fait_pas_echouer_la_creation),
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
