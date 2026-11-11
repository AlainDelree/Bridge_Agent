#!/usr/bin/env python3
"""Test — issue #882 : l'avertissement « Dépôt privé : GH_TOKEN doit avoir
les permissions nécessaires… » (`modale_nouveau_projet.html`, issue #529)
s'affichait SANS CONDITION dès qu'un dépôt privé était choisi, même sur une
installation où `gh` est authentifié par son propre trousseau
(`gh auth login`, sans la moindre variable d'environnement `GH_TOKEN` ni
`GITHUB_TOKEN`) — où la création d'un dépôt privé réussit sans que cet
avertissement ait le moindre sens : il décrit un mécanisme (un jeton fourni
par variable d'environnement) qui n'est pas utilisé sur cette installation.

Règle retenue (voir le docstring de `identite.token_github_env_present()`) :
l'avertissement ne doit s'afficher QUE si `GH_TOKEN` ou `GITHUB_TOKEN` est
effectivement présent dans l'environnement du PROCESSUS de l'interface — un
FAIT lu directement dans `os.environ`, jamais une supposition sur le mode
d'authentification de `gh`. `gh` donne TOUJOURS la priorité à ces deux
variables sur son authentification de trousseau dès qu'elles sont présentes
(comportement documenté de `gh`), donc leur présence est le signal fiable
que l'avertissement s'applique. Sur l'installation d'Alain (où `GH_TOKEN`
est exporté dans l'environnement de `new_issue.py`), rien ne change :
l'avertissement reste affiché, texte inchangé.

Couvre :
1. `identite.token_github_env_present()` — présence de GH_TOKEN seul,
   GITHUB_TOKEN seul, les deux, ni l'un ni l'autre, valeurs vides/blanches
   (traitées comme absentes).
2. `app/vues.py::index()` transmet bien `gh_token_env_present` au gabarit,
   depuis `identite.token_github_env_present()` (pas une valeur codée en
   dur) — vérifié par lecture du source, comme
   `tests/test_retrait_bandeaux_historiques_746.py`.
3. Rendu Jinja de `fragments/scripts.html` : `window.GH_TOKEN_ENV_PRESENT`
   reflète fidèlement True/False — c'est cette variable que
   `npMajAvertissementPrive()` (static/js/app.js, voir
   static/js/tests/nouveau_projet_verif_depot_882.test.js) lit pour décider
   d'afficher ou non l'avertissement.

Non couvert par ces tests automatiques (à vérifier à la main, voir
VERIFICATIONS_MANUELLES.md § issue #882) : le rendu réel dans un navigateur,
notamment qu'ouvrir le formulaire avec et sans `GH_TOKEN` exporté change
effectivement la visibilité de l'avertissement une fois le dépôt privé
sélectionné.

Exécution :  python3 -m pytest tests/test_avertissement_gh_token_882.py
         ou  python3 tests/test_avertissement_gh_token_882.py
"""

import sys
from pathlib import Path
from unittest import mock

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import identite  # noqa: E402

try:
    import jinja2
except ImportError:
    jinja2 = None


# ─── 1. identite.token_github_env_present() ──────────────────────────────

def test_absent_des_deux_variables():
    with mock.patch.dict("os.environ", {}, clear=True):
        assert identite.token_github_env_present() is False


def test_gh_token_seul_present():
    with mock.patch.dict("os.environ", {"GH_TOKEN": "ghp_xxx"}, clear=True):
        assert identite.token_github_env_present() is True


def test_github_token_seul_present():
    with mock.patch.dict("os.environ", {"GITHUB_TOKEN": "ghp_yyy"}, clear=True):
        assert identite.token_github_env_present() is True


def test_les_deux_presentes():
    with mock.patch.dict("os.environ", {"GH_TOKEN": "a", "GITHUB_TOKEN": "b"}, clear=True):
        assert identite.token_github_env_present() is True


def test_valeur_vide_traitee_comme_absente():
    with mock.patch.dict("os.environ", {"GH_TOKEN": ""}, clear=True):
        assert identite.token_github_env_present() is False


def test_valeur_blanche_traitee_comme_absente():
    with mock.patch.dict("os.environ", {"GH_TOKEN": "   "}, clear=True):
        assert identite.token_github_env_present() is False


def test_github_token_vide_mais_gh_token_present():
    with mock.patch.dict("os.environ", {"GH_TOKEN": "ghp_xxx", "GITHUB_TOKEN": ""}, clear=True):
        assert identite.token_github_env_present() is True


# ─── 2. app/vues.py::index() transmet le fait, pas une valeur codée en dur ──

def test_vues_transmet_gh_token_env_present_depuis_identite():
    contenu = (RACINE / "app" / "vues.py").read_text(encoding="utf-8")
    assert "gh_token_env_present=identite.token_github_env_present()" in contenu, (
        "app/vues.py::index() doit transmettre gh_token_env_present au gabarit "
        "depuis identite.token_github_env_present() (issue #882)")


# ─── 3. Rendu Jinja de fragments/scripts.html ────────────────────────────

def _rendre_scripts(gh_token_env_present: bool) -> str:
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(str(RACINE / "templates")))
    env.globals["url_statique"] = lambda chemin: "/static/" + chemin
    env.globals["importmap_socle"] = lambda: "{}"
    return env.get_template("fragments/scripts.html").render(
        projets=[], formats_image={"mimes": []},
        depot_public_par_defaut=True, diagnostic_copie=False,
        gh_token_env_present=gh_token_env_present)


def test_scripts_html_window_gh_token_env_present_true():
    if jinja2 is None:
        print("  (ignoré : jinja2 non installé)")
        return
    rendu = _rendre_scripts(True)
    assert "window.GH_TOKEN_ENV_PRESENT = true;" in rendu


def test_scripts_html_window_gh_token_env_present_false():
    if jinja2 is None:
        print("  (ignoré : jinja2 non installé)")
        return
    rendu = _rendre_scripts(False)
    assert "window.GH_TOKEN_ENV_PRESENT = false;" in rendu


def main() -> int:
    import inspect
    import types
    tests = [(n, f) for n, f in globals().items()
             if n.startswith("test_") and isinstance(f, types.FunctionType)]
    echecs = 0
    for nom, fn in tests:
        params = inspect.signature(fn).parameters
        if "tmp_path" in params or "monkeypatch" in params:
            print(f"  · {nom} (ignoré hors pytest — nécessite un fixture)")
            continue
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
    print("\n✅ Tous les scénarios directement exécutables passent (lancer pytest pour la couverture complète).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
