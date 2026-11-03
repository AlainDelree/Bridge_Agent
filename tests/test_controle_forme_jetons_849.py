#!/usr/bin/env python3
"""Test de non-régression — issue #849 : onglet CCW, contrôler la forme des
jetons (longueur, préfixe, espaces) avant de finaliser un projet.

Couvre, SANS AUCUN vrai SSH/nssm/PowerShell (même discipline que
tests/test_ccw_renouveler_un_seul_jeton_743.py) :

- `app.ccw._nettoyer_bords_jeton` : retrait des espaces/retours à la ligne
  de bord (fonction pure) ;
- `app.ccw._jeton_a_caractere_bloquant` : détection d'un espace ou d'un
  caractère de contrôle AU MILIEU du jeton nettoyé (collage abîmé) — jeton
  plausible non bloqué, jeton avec espace ou retour à la ligne final non
  bloqué (bords déjà retirés), jeton avec espace/caractère de contrôle au
  milieu bloqué ;
- `app.ccw.ccw_finaliser_projet` (route Flask, sans SSH réel — `_preparer`
  substitué) : refus clair si GH_TOKEN ou CLAUDE_CODE_OAUTH_TOKEN contient un
  espace/caractère de contrôle en son milieu, SANS appel SSH et SANS que la
  valeur du jeton n'apparaisse dans la réponse JSON ; un jeton avec un simple
  espace/retour à la ligne de bord (donc non abîmé une fois nettoyé) est
  accepté, nettoyé avant écriture dans le fichier de valeurs.

Exécution :  python3 tests/test_controle_forme_jetons_849.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import flask  # noqa: E402

import app.ccw as ccw  # noqa: E402

APP_FLASK = flask.Flask(__name__)


class FauxResultatSsh:
    """Même rôle que CompletedProcess pour les points d'appel SSH substitués
    ci-dessous (returncode/stdout/stderr) — jamais de vrai sous-processus."""

    def __init__(self, returncode, stdout="", stderr=""):
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr


class Patch:
    """Remplace `getattr(module, nom)` par `valeur` ; restaure à la sortie du
    `with`. Même utilitaire minimal que tests/test_ccw_renouveler_un_seul_jeton_743.py."""

    def __init__(self, module, nom, valeur):
        self.module, self.nom, self.valeur = module, nom, valeur

    def __enter__(self):
        self.original = getattr(self.module, self.nom)
        setattr(self.module, self.nom, self.valeur)
        return self.valeur

    def __exit__(self, *exc):
        setattr(self.module, self.nom, self.original)


def _appel_interdit(*_a, **_k):
    raise AssertionError("appel SSH inattendu — la route doit refuser avant tout aller-retour")


class _RequeteFactice:
    def __init__(self, donnees):
        self.json = donnees


def _appeler_finaliser(donnees, fichiers_copies):
    """Même pattern que test_ccw_renouveler_un_seul_jeton_743.py :
    `_preparer`/`_copier`/`_executer_ps` substitués, jamais de vrai SSH."""
    def _copier_facture(hote, utilisateur, cle_privee, source_local, timeout):
        contenu = None
        if Path(source_local).suffix == ".txt":
            contenu = Path(source_local).read_text(encoding="utf-8")
        fichiers_copies.append((Path(source_local).name, contenu))
        return FauxResultatSsh(0)

    def _executer_ps_facture(hote, utilisateur, cle_privee, nom_script, args_ps, timeout):
        return FauxResultatSsh(0, stdout="[finaliser-auto] OK\n")

    with APP_FLASK.test_request_context(), \
         Patch(ccw, "request", _RequeteFactice(donnees)), \
         Patch(ccw, "_preparer", lambda: (("192.168.1.50", "AlainW", "/chemin/cle"), None)), \
         Patch(ccw, "_copier", _copier_facture), \
         Patch(ccw, "_executer_ps", _executer_ps_facture):
        return ccw.ccw_finaliser_projet()


# ─── _nettoyer_bords_jeton ──────────────────────────────────────────────────

def test_nettoyer_bords_jeton_retire_espaces_et_retours_a_la_ligne():
    assert ccw._nettoyer_bords_jeton("  ghp_abcdef  ") == "ghp_abcdef"
    assert ccw._nettoyer_bords_jeton("ghp_abcdef\n") == "ghp_abcdef"
    assert ccw._nettoyer_bords_jeton("\nghp_abcdef\r\n") == "ghp_abcdef"
    return {}


def test_nettoyer_bords_jeton_sans_bord_inchange():
    assert ccw._nettoyer_bords_jeton("ghp_abcdef") == "ghp_abcdef"
    return {}


# ─── _jeton_a_caractere_bloquant ────────────────────────────────────────────

def test_jeton_bloquant_jeton_plausible_non_bloque():
    assert ccw._jeton_a_caractere_bloquant("ghp_" + "a" * 36) is False
    return {}


def test_jeton_bloquant_espace_au_milieu():
    assert ccw._jeton_a_caractere_bloquant("ghp_abc def") is True
    return {}


def test_jeton_bloquant_caractere_de_controle_au_milieu():
    assert ccw._jeton_a_caractere_bloquant("ghp_abc\tdef") is True
    assert ccw._jeton_a_caractere_bloquant("ghp_abc\ndef") is True
    return {}


def test_jeton_bloquant_retour_a_la_ligne_final_deja_retire_non_bloquant():
    """Un jeton dont les bords ont déjà été nettoyés par
    `_nettoyer_bords_jeton` (comme le fait la route) ne contient plus le
    retour à la ligne final — plus rien à bloquer."""
    nettoye = ccw._nettoyer_bords_jeton("ghp_abcdef\n")
    assert ccw._jeton_a_caractere_bloquant(nettoye) is False
    return {}


def test_jeton_bloquant_chaine_vide_non_bloquante():
    assert ccw._jeton_a_caractere_bloquant("") is False
    return {}


# ─── ccw_finaliser_projet (route Flask, sans SSH réel) ─────────────────────

def test_finaliser_gh_avec_espace_au_milieu_refuse_sans_appel_ssh_ni_fuite():
    with APP_FLASK.test_request_context(), \
         Patch(ccw, "request", _RequeteFactice(
             {"nom": "Scrabble", "topic": "", "gh_token": "ghp_abc def" + "x" * 29, "oauth_token": ""})), \
         Patch(ccw, "_preparer", _appel_interdit):
        rep = ccw.ccw_finaliser_projet()
    j = rep.get_json()
    assert j["succes"] is False, j
    assert "espace" in j["erreur"].lower() or "contrôle" in j["erreur"].lower(), j
    assert "ghp_abc" not in repr(j), "le jeton ne doit jamais apparaître dans la réponse JSON"
    return {}


def test_finaliser_oauth_avec_caractere_de_controle_au_milieu_refuse_sans_fuite():
    jeton_abime = "sk-ant-oat01" + "a" * 10 + "\t" + "b" * 10
    with APP_FLASK.test_request_context(), \
         Patch(ccw, "request", _RequeteFactice(
             {"nom": "Scrabble", "topic": "", "gh_token": "", "oauth_token": jeton_abime})), \
         Patch(ccw, "_preparer", _appel_interdit):
        rep = ccw.ccw_finaliser_projet()
    j = rep.get_json()
    assert j["succes"] is False, j
    assert "CLAUDE_CODE_OAUTH_TOKEN" in j["erreur"], j
    assert jeton_abime not in repr(j), "le jeton ne doit jamais apparaître dans la réponse JSON"
    return {}


def test_finaliser_gh_avec_espace_de_bord_seulement_accepte_et_nettoye():
    """Un jeton envoyé avec un espace/retour à la ligne de bord (ex. appel
    direct à la route, sans passer par le contrôle navigateur) n'est pas
    abîmé une fois nettoyé : accepté, et c'est la valeur NETTOYÉE qui est
    écrite dans le fichier de valeurs — jamais la version brute."""
    fichiers = []
    rep = _appeler_finaliser(
        {"nom": "Scrabble", "topic": "", "gh_token": "  ghp_nouveau\n", "oauth_token": ""},
        fichiers)
    j = rep.get_json()
    assert j["succes"] is True, j
    contenu = next(c for (_, c) in fichiers if c is not None)
    assert "GH_TOKEN=ghp_nouveau\n" in contenu, contenu
    return {}


def main() -> int:
    tests = [
        ("_nettoyer_bords_jeton : retire espaces et retours à la ligne de bord", test_nettoyer_bords_jeton_retire_espaces_et_retours_a_la_ligne),
        ("_nettoyer_bords_jeton : sans bord, inchangé", test_nettoyer_bords_jeton_sans_bord_inchange),
        ("_jeton_a_caractere_bloquant : jeton plausible → non bloqué", test_jeton_bloquant_jeton_plausible_non_bloque),
        ("_jeton_a_caractere_bloquant : espace au milieu → bloqué", test_jeton_bloquant_espace_au_milieu),
        ("_jeton_a_caractere_bloquant : caractère de contrôle au milieu → bloqué", test_jeton_bloquant_caractere_de_controle_au_milieu),
        ("_jeton_a_caractere_bloquant : retour à la ligne final déjà retiré → non bloquant", test_jeton_bloquant_retour_a_la_ligne_final_deja_retire_non_bloquant),
        ("_jeton_a_caractere_bloquant : chaîne vide → non bloquant", test_jeton_bloquant_chaine_vide_non_bloquante),
        ("ccw_finaliser_projet : GH_TOKEN avec espace au milieu → refus sans appel SSH ni fuite", test_finaliser_gh_avec_espace_au_milieu_refuse_sans_appel_ssh_ni_fuite),
        ("ccw_finaliser_projet : OAUTH avec caractère de contrôle au milieu → refus sans fuite", test_finaliser_oauth_avec_caractere_de_controle_au_milieu_refuse_sans_fuite),
        ("ccw_finaliser_projet : GH_TOKEN avec espace de bord seulement → accepté, nettoyé", test_finaliser_gh_avec_espace_de_bord_seulement_accepte_et_nettoye),
    ]
    echecs = 0
    for nom, fn in tests:
        try:
            rap = fn()
            print(f"  ✓ {nom}" + (f"  ({rap})" if rap else ""))
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
