#!/usr/bin/env python3
"""Test de `etat_son_issue.py` / `app/son_issue.py` / `scripts/traitement_fin.py`
— issue #630 (son plat/cloche PAR ISSUE, backend seul).

Aucun test ici ne touche au vrai `logs/son_issues.json` ni au vrai
`scripts/son_actif.txt` : `etat_son_issue.CHEMIN_ETAT`/`CHEMIN_VERROU` et
`traitement_fin.FICHIER_SON_ACTIF` sont monkeypatchés vers des fichiers
jetables pour chaque scénario — même approche que
`tests/test_supprimer_projet_587.py` (monkeypatch de `DOSSIER_CONFIGS`).

Couvre :
- `son_choisi`/`definir_son` : absence de choix → None, écriture puis
  lecture, valeur invalide refusée, `son=None` retire le choix (retombe sur
  l'interrupteur global) ;
- `nettoyer_projet` : purge totale d'un projet, les autres projets intacts ;
- `nettoyer_entrees_perimees` : conserve les 50 dernières issues connues par
  PROJET (pas de fuite entre projets), purge celles ≤ max-50 ;
- `traitement_fin.son_a_jouer` : choix de l'issue prioritaire sur
  l'interrupteur global, repli sur l'interrupteur global sans choix propre
  ou sans projet/numéro fournis ;
- routes Flask `/son-issue/<projet>/<numero>` (GET/POST) : lecture, écriture,
  remise à zéro, numéro invalide → 400.

Exécution :  python3 tests/test_son_issue_630.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import sys
import tempfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))
sys.path.insert(0, str(RACINE / "scripts"))

import flask  # noqa: E402

import etat_son_issue  # noqa: E402
import traitement_fin  # noqa: E402
from app import son_issue as route_son_issue  # noqa: E402

APP_FLASK = flask.Flask(__name__)


class _Etat:
    """Monkeypatch de etat_son_issue.CHEMIN_ETAT/CHEMIN_VERROU vers un
    répertoire jetable, restauré à la sortie — un scénario par instance."""

    def __enter__(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._ancien_etat   = etat_son_issue.CHEMIN_ETAT
        self._ancien_verrou = etat_son_issue.CHEMIN_VERROU
        etat_son_issue.CHEMIN_ETAT   = Path(self._tmp.name) / "son_issues.json"
        etat_son_issue.CHEMIN_VERROU = etat_son_issue.CHEMIN_ETAT.with_suffix(".lock")
        return self

    def __exit__(self, *a):
        etat_son_issue.CHEMIN_ETAT   = self._ancien_etat
        etat_son_issue.CHEMIN_VERROU = self._ancien_verrou
        self._tmp.cleanup()


def test_son_choisi_absent_par_defaut():
    with _Etat():
        assert etat_son_issue.son_choisi("bridge_agent", 630) is None


def test_definir_puis_lire():
    with _Etat():
        ok, erreur = etat_son_issue.definir_son("bridge_agent", 630, "cloche")
        assert ok is True and erreur is None
        assert etat_son_issue.son_choisi("bridge_agent", 630) == "cloche"
        # Un autre projet/numéro n'est pas affecté.
        assert etat_son_issue.son_choisi("bridge_agent", 631) is None
        assert etat_son_issue.son_choisi("autre_projet", 630) is None


def test_definir_valeur_invalide_refusee():
    with _Etat():
        ok, erreur = etat_son_issue.definir_son("bridge_agent", 630, "trompette")
        assert ok is False
        assert erreur is not None
        assert etat_son_issue.son_choisi("bridge_agent", 630) is None


def test_definir_none_retire_le_choix():
    with _Etat():
        etat_son_issue.definir_son("bridge_agent", 630, "plat")
        assert etat_son_issue.son_choisi("bridge_agent", 630) == "plat"
        ok, erreur = etat_son_issue.definir_son("bridge_agent", 630, None)
        assert ok is True and erreur is None
        assert etat_son_issue.son_choisi("bridge_agent", 630) is None
        # Retirer un choix déjà absent est un no-op réussi (idempotent).
        ok2, _ = etat_son_issue.definir_son("bridge_agent", 630, None)
        assert ok2 is True


def test_nettoyer_projet_purge_tout_et_seulement_ce_projet():
    with _Etat():
        etat_son_issue.definir_son("bridge_agent", 1, "cloche")
        etat_son_issue.definir_son("bridge_agent", 2, "plat")
        etat_son_issue.definir_son("autre_projet", 1, "cloche")
        assert etat_son_issue.nettoyer_projet("bridge_agent") is True
        assert etat_son_issue.son_choisi("bridge_agent", 1) is None
        assert etat_son_issue.son_choisi("bridge_agent", 2) is None
        assert etat_son_issue.son_choisi("autre_projet", 1) == "cloche"
        # Projet déjà absent → no-op réussi.
        assert etat_son_issue.nettoyer_projet("bridge_agent") is True


def test_nettoyer_entrees_perimees_garde_les_50_dernieres_par_projet():
    with _Etat():
        # bridge_agent : plus grand numéro connu = 1000 → seuil = 950.
        # 949 et 950 (≤ seuil) purgés, 951 et 1000 conservés (> seuil).
        etat_son_issue.definir_son("bridge_agent", 949, "cloche")
        etat_son_issue.definir_son("bridge_agent", 950, "cloche")
        etat_son_issue.definir_son("bridge_agent", 951, "plat")
        etat_son_issue.definir_son("bridge_agent", 1000, "cloche")
        # autre_projet : plage basse, rien à purger (max - 50 < 0).
        etat_son_issue.definir_son("autre_projet", 3, "plat")

        retirees = etat_son_issue.nettoyer_entrees_perimees()

        assert retirees.get("bridge_agent") == 2
        assert "autre_projet" not in retirees
        assert etat_son_issue.son_choisi("bridge_agent", 949) is None
        assert etat_son_issue.son_choisi("bridge_agent", 950) is None
        assert etat_son_issue.son_choisi("bridge_agent", 951) == "plat"
        assert etat_son_issue.son_choisi("bridge_agent", 1000) == "cloche"
        assert etat_son_issue.son_choisi("autre_projet", 3) == "plat"


class _SonGlobal:
    """Monkeypatch de traitement_fin.FICHIER_SON_ACTIF vers un fichier
    jetable, restauré à la sortie."""

    def __init__(self, valeur: str):
        self._valeur = valeur

    def __enter__(self):
        self._tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8")
        self._tmp.write(self._valeur)
        self._tmp.close()
        self._ancien = traitement_fin.FICHIER_SON_ACTIF
        traitement_fin.FICHIER_SON_ACTIF = self._tmp.name
        return self

    def __exit__(self, *a):
        traitement_fin.FICHIER_SON_ACTIF = self._ancien
        Path(self._tmp.name).unlink(missing_ok=True)


def test_son_a_jouer_choix_issue_prioritaire_sur_global():
    with _Etat(), _SonGlobal("plat"):
        etat_son_issue.definir_son("bridge_agent", 630, "cloche")
        assert traitement_fin.son_a_jouer("bridge_agent", 630) == "cloche"


def test_son_a_jouer_repli_sur_global_sans_choix_propre():
    with _Etat(), _SonGlobal("cloche"):
        assert traitement_fin.son_a_jouer("bridge_agent", 630) == "cloche"


def test_son_a_jouer_repli_sur_global_sans_projet_ni_numero():
    with _Etat(), _SonGlobal("cloche"):
        etat_son_issue.definir_son("bridge_agent", 630, "plat")
        # Pas de projet/numéro transmis (ex. bip de test sans contexte
        # d'issue) → l'interrupteur global s'applique, jamais le choix
        # d'une issue au hasard.
        assert traitement_fin.son_a_jouer(None, None) == "cloche"


def test_route_get_son_issue_absent():
    with _Etat():
        with APP_FLASK.test_request_context():
            rep = route_son_issue.get_son_issue("bridge_agent", "630")
        assert rep.get_json() == {"son": None}


def test_route_post_puis_get_son_issue():
    with _Etat():
        with APP_FLASK.test_request_context(
                "/son-issue/bridge_agent/630", method="POST", json={"son": "cloche"}):
            rep_post = route_son_issue.post_son_issue("bridge_agent", "630")
        assert rep_post.get_json() == {"succes": True, "son": "cloche"}

        with APP_FLASK.test_request_context():
            rep_get = route_son_issue.get_son_issue("bridge_agent", "630")
        assert rep_get.get_json() == {"son": "cloche"}


def test_route_post_son_invalide_400():
    with _Etat():
        with APP_FLASK.test_request_context(
                "/son-issue/bridge_agent/630", method="POST", json={"son": "trompette"}):
            rep = route_son_issue.post_son_issue("bridge_agent", "630")
        assert rep[1] == 400


def test_route_numero_invalide_400():
    with _Etat():
        with APP_FLASK.test_request_context():
            rep = route_son_issue.get_son_issue("bridge_agent", "pas-un-numero")
        assert rep[1] == 400


def main() -> int:
    tests = [
        ("son_choisi — absent par défaut", test_son_choisi_absent_par_defaut),
        ("definir_son puis son_choisi — écriture/lecture isolées par projet+numéro", test_definir_puis_lire),
        ("definir_son — valeur invalide refusée", test_definir_valeur_invalide_refusee),
        ("definir_son(None) — retire le choix, idempotent", test_definir_none_retire_le_choix),
        ("nettoyer_projet — purge tout, un seul projet touché", test_nettoyer_projet_purge_tout_et_seulement_ce_projet),
        ("nettoyer_entrees_perimees — garde les 50 dernières par projet", test_nettoyer_entrees_perimees_garde_les_50_dernieres_par_projet),
        ("son_a_jouer — choix de l'issue prioritaire sur l'interrupteur global", test_son_a_jouer_choix_issue_prioritaire_sur_global),
        ("son_a_jouer — repli sur l'interrupteur global sans choix propre", test_son_a_jouer_repli_sur_global_sans_choix_propre),
        ("son_a_jouer — repli sur l'interrupteur global sans projet/numéro", test_son_a_jouer_repli_sur_global_sans_projet_ni_numero),
        ("route GET /son-issue — absent → son: null", test_route_get_son_issue_absent),
        ("route POST puis GET /son-issue — écriture puis lecture", test_route_post_puis_get_son_issue),
        ("route POST /son-issue — valeur invalide → 400", test_route_post_son_invalide_400),
        ("route GET /son-issue — numéro invalide → 400", test_route_numero_invalide_400),
    ]
    echecs = 0
    for nom, fn in tests:
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
    print("\n✅ Tous les scénarios passent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
