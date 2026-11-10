#!/usr/bin/env python3
"""Test — issue #879 : la case « Dépôt public » du formulaire « Nouveau
projet » est cochée par défaut (dépôt public), ce qui est le bon
comportement pour l'installation d'Alain mais pas pour une copie non
propriétaire de l'outil (`COPIE_NON_PROPRIETAIRE = oui`, issue #869 — ex. ami
sur PC Windows seul) : sur une telle copie, le contenu d'un projet n'a pas à
devenir public par simple oubli.

Couvre :
1. `identite.depot_public_par_defaut()` — nouveau réglage facultatif
   `DEPOT_PRIVE_PAR_DEFAUT` de `identite_locale.conf`, qui PRIME sur
   `copie_non_proprietaire()` dans les deux sens :
     - absent, sans COPIE_NON_PROPRIETAIRE → public par défaut (True),
       comportement historique inchangé (installation d'Alain) ;
     - absent, avec COPIE_NON_PROPRIETAIRE → privé par défaut (False) ;
     - DEPOT_PRIVE_PAR_DEFAUT = oui → privé par défaut (False), même SANS
       COPIE_NON_PROPRIETAIRE (ex. Alain, sur SA PROPRE installation) ;
     - DEPOT_PRIVE_PAR_DEFAUT = non → public par défaut (True), même AVEC
       COPIE_NON_PROPRIETAIRE ;
     - valeur quelconque (ni oui ni non reconnu) → repli sur la règle
       COPIE_NON_PROPRIETAIRE, comme si le réglage était absent.
2. `nouveau_projet.creer_projet()` : le paramètre `public` omis (`None`) se
   résout en `identite.depot_public_par_defaut()`, jamais un `True` codé en
   dur ; un `public` explicite (reflet de la case du formulaire) PRIME
   toujours sur ce réglage. Le compte-rendu (étape « Dépôt GitHub ») et la
   clé `public` du résultat reflètent la valeur réellement appliquée.
3. Route Flask `POST /nouveau-projet` (`app/nouveau_projet.py`) : même règle
   de résolution du défaut quand la clé JSON "public" est absente — jamais
   un `True` codé en dur côté route non plus.
4. Rendu Jinja de `templates/fragments/modale_nouveau_projet.html` : la case
   est cochée/décochée et le libellé adapté selon `depot_public_par_defaut`,
   de façon à ce que le libellé affiché ne contredise jamais l'état réel de
   la case.

Comme tests/test_copie_non_proprietaire_869.py : aucun accès réseau réel
(`gh`/`git`), `creer_depot`/`committer_pousser_doc` sont des faux
enregistreurs d'appels, jamais les fonctions réelles.

Non couvert par ces tests automatiques (à vérifier à la main, voir
VERIFICATIONS_MANUELLES.md § Nouveau projet) : le rendu réel dans un
navigateur — notamment que `window.DEPOT_PUBLIC_PAR_DEFAUT`
(fragments/scripts.html) est bien repris par `ouvrirNouveauProjet()`
(static/js/app.js, fonction DOM non testée ici) à CHAQUE ouverture du modal,
pas seulement au premier chargement de la page.

Exécution :  python3 -m pytest tests/test_depot_prive_par_defaut_879.py
"""

import sys
import tempfile
from pathlib import Path
from unittest import mock

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import etat_configs_legitimes as ecl  # noqa: E402
import identite  # noqa: E402
import nouveau_projet as np_cli  # noqa: E402

try:
    import flask
except ImportError:
    flask = None

try:
    import jinja2
except ImportError:
    jinja2 = None


# ─── 1. identite.depot_public_par_defaut() ───────────────────────────────

def _avec_identite_locale(contenu: str):
    """Context manager minimal : écrit `contenu` dans un identite_locale.conf
    temporaire et fait pointer identite.FICHIER_IDENTITE_LOCALE dessus."""
    tmp = tempfile.TemporaryDirectory()
    chemin = Path(tmp.name) / "identite_locale.conf"
    if contenu is not None:
        chemin.write_text(contenu, encoding="utf-8")
    return tmp, mock.patch.object(identite, "FICHIER_IDENTITE_LOCALE", chemin)


def test_absent_sans_copie_non_proprietaire_public_par_defaut():
    tmp, patch = _avec_identite_locale(None)
    with tmp, patch:
        assert identite.depot_public_par_defaut() is True


def test_absent_avec_copie_non_proprietaire_prive_par_defaut():
    tmp, patch = _avec_identite_locale("COPIE_NON_PROPRIETAIRE = oui\n")
    with tmp, patch:
        assert identite.depot_public_par_defaut() is False


def test_reglage_oui_prive_meme_sans_copie_non_proprietaire():
    tmp, patch = _avec_identite_locale("DEPOT_PRIVE_PAR_DEFAUT = oui\n")
    with tmp, patch:
        assert identite.copie_non_proprietaire() is False
        assert identite.depot_public_par_defaut() is False


def test_reglage_non_public_meme_avec_copie_non_proprietaire():
    tmp, patch = _avec_identite_locale(
        "COPIE_NON_PROPRIETAIRE = oui\nDEPOT_PRIVE_PAR_DEFAUT = non\n")
    with tmp, patch:
        assert identite.copie_non_proprietaire() is True
        assert identite.depot_public_par_defaut() is True


def test_reglage_oui_et_copie_non_proprietaire_les_deux_accordes():
    tmp, patch = _avec_identite_locale(
        "COPIE_NON_PROPRIETAIRE = oui\nDEPOT_PRIVE_PAR_DEFAUT = oui\n")
    with tmp, patch:
        assert identite.depot_public_par_defaut() is False


def test_valeur_quelconque_retombe_sur_copie_non_proprietaire():
    tmp, patch = _avec_identite_locale("DEPOT_PRIVE_PAR_DEFAUT = peut-etre\n")
    with tmp, patch:
        assert identite.depot_public_par_defaut() is True  # pas de COPIE_NON_PROPRIETAIRE

    tmp2, patch2 = _avec_identite_locale(
        "COPIE_NON_PROPRIETAIRE = oui\nDEPOT_PRIVE_PAR_DEFAUT = peut-etre\n")
    with tmp2, patch2:
        assert identite.depot_public_par_defaut() is False


# ─── 2. nouveau_projet.creer_projet() ────────────────────────────────────

def _mocker_etapes_reseau_depot_absent(monkeypatch, configs: Path, appels_public: list):
    """Dépôt absent → creer_depot() est bien celui appelé (pas installation
    sur existant) ; capture la valeur de `public` qu'il reçoit réellement."""
    monkeypatch.setattr(np_cli, "DOSSIER_CONFIGS", configs)
    monkeypatch.setattr(np_cli, "depot_existe", lambda depot: False)
    # ecrire_conf() (appelée par creer_projet()) enregistre le .conf créé
    # dans etat_configs_legitimes (verrou + fichier JSON) — isolé ici du vrai
    # logs/configs_legitimes.json, comme test_copie_non_proprietaire_869.py.
    monkeypatch.setattr(ecl, "CHEMIN_ETAT", configs.parent / "configs_legitimes.json")
    monkeypatch.setattr(ecl, "CHEMIN_VERROU", (configs.parent / "configs_legitimes.json").with_suffix(".lock"))

    def _creer_depot(depot, nom, public=True):
        appels_public.append(public)
        return True, ""
    monkeypatch.setattr(np_cli, "creer_depot", _creer_depot)
    monkeypatch.setattr(np_cli, "creer_labels", lambda depot: [])
    monkeypatch.setattr(np_cli, "creer_fichiers_contexte",
                        lambda rep, avec_specs: {"crees": [], "existants": [], "rep_cree": False})
    monkeypatch.setattr(np_cli, "initialiser_git", lambda rep, depot: {
        "ok": True, "detail": "ignoré (test)", "deja_git": True, "push_ok": None,
        "contenu_preexistant": [], "commande_manuelle": None,
    })
    monkeypatch.setattr(np_cli, "mettre_a_jour_doc", lambda: {
        "existe": False, "ok2": False, "ok7": False, "ok_date": False, "erreur": None,
        "local": False, "fichier_local": None,
    })


def test_creer_projet_public_omis_suit_identite_public(monkeypatch, tmp_path):
    configs = tmp_path / "configs"
    configs.mkdir()
    appels = []
    _mocker_etapes_reseau_depot_absent(monkeypatch, configs, appels)
    monkeypatch.setattr(np_cli.identite, "depot_public_par_defaut", lambda: True)

    resultat = np_cli.creer_projet(
        nom="pub879a", depot="AlainDelree/Pub879a",
        rep=str(tmp_path / "rep"), perimetre=str(tmp_path / "rep"))

    assert resultat["succes"] is True
    assert appels == [True]
    assert resultat["public"] is True
    etape = next(e for e in resultat["etapes"] if e["etape"] == "Dépôt GitHub")
    assert "créé (public)" in etape["detail"]


def test_creer_projet_public_omis_suit_identite_prive(monkeypatch, tmp_path):
    configs = tmp_path / "configs"
    configs.mkdir()
    appels = []
    _mocker_etapes_reseau_depot_absent(monkeypatch, configs, appels)
    monkeypatch.setattr(np_cli.identite, "depot_public_par_defaut", lambda: False)

    resultat = np_cli.creer_projet(
        nom="pub879b", depot="AlainDelree/Pub879b",
        rep=str(tmp_path / "rep"), perimetre=str(tmp_path / "rep"))

    assert resultat["succes"] is True
    assert appels == [False]
    assert resultat["public"] is False
    etape = next(e for e in resultat["etapes"] if e["etape"] == "Dépôt GitHub")
    assert "créé (privé)" in etape["detail"]


def test_creer_projet_public_explicite_prime_sur_identite(monkeypatch, tmp_path):
    """La case du formulaire (public explicite) l'emporte toujours sur le
    réglage d'installation, dans les deux sens."""
    configs = tmp_path / "configs"
    configs.mkdir()
    appels = []
    _mocker_etapes_reseau_depot_absent(monkeypatch, configs, appels)
    monkeypatch.setattr(np_cli.identite, "depot_public_par_defaut", lambda: False)

    resultat = np_cli.creer_projet(
        nom="pub879c", depot="AlainDelree/Pub879c",
        rep=str(tmp_path / "rep"), perimetre=str(tmp_path / "rep"),
        public=True)

    assert appels == [True]
    assert resultat["public"] is True

    appels.clear()
    monkeypatch.setattr(np_cli.identite, "depot_public_par_defaut", lambda: True)
    resultat2 = np_cli.creer_projet(
        nom="pub879d", depot="AlainDelree/Pub879d",
        rep=str(tmp_path / "rep"), perimetre=str(tmp_path / "rep"),
        public=False)

    assert appels == [False]
    assert resultat2["public"] is False
    etape2 = next(e for e in resultat2["etapes"] if e["etape"] == "Dépôt GitHub")
    assert "créé (privé)" in etape2["detail"]


# ─── 3. Route Flask POST /nouveau-projet ─────────────────────────────────

APP_FLASK = flask.Flask(__name__) if flask else None


def _route_appel(monkeypatch, json_payload: dict, depot_public_par_defaut: bool) -> list:
    """Appelle la route creer_nouveau_projet() avec ce payload JSON, capture
    la valeur de `public` transmise à creer_projet() (lui-même remplacé par
    un faux enregistreur — aucun accès réseau)."""
    from app import nouveau_projet as route_np
    appels = []
    monkeypatch.setattr(route_np.np_cli, "creer_projet",
                        lambda **kwargs: (appels.append(kwargs.get("public")),
                                          {"succes": True, "etapes": []})[1])
    monkeypatch.setattr(route_np.np_cli.identite, "depot_public_par_defaut",
                        lambda: depot_public_par_defaut)
    with APP_FLASK.test_request_context("/nouveau-projet", method="POST",
                                        json=json_payload):
        route_np.creer_nouveau_projet()
    return appels


def test_route_champ_public_absent_suit_identite_public(monkeypatch):
    if flask is None:
        print("  (ignoré : flask non installé)")
        return
    appels = _route_appel(monkeypatch, {"nom": "x"}, depot_public_par_defaut=True)
    assert appels == [True]


def test_route_champ_public_absent_suit_identite_prive(monkeypatch):
    if flask is None:
        print("  (ignoré : flask non installé)")
        return
    appels = _route_appel(monkeypatch, {"nom": "x"}, depot_public_par_defaut=False)
    assert appels == [False]


def test_route_champ_public_explicite_prime_sur_identite(monkeypatch):
    if flask is None:
        print("  (ignoré : flask non installé)")
        return
    appels = _route_appel(monkeypatch, {"nom": "x", "public": True},
                          depot_public_par_defaut=False)
    assert appels == [True]
    appels2 = _route_appel(monkeypatch, {"nom": "x", "public": False},
                           depot_public_par_defaut=True)
    assert appels2 == [False]


# ─── 4. Rendu Jinja — case + libellé cohérents avec le défaut ───────────

def _rendre(nom_fragment: str, **contexte) -> str:
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(str(RACINE / "templates")))
    return env.get_template(nom_fragment).render(**contexte)


def _bloc_case_public(rendu: str) -> str:
    return rendu.split('id="np-public-ligne"')[1].split("</label>")[0]


def test_case_publique_cochee_et_libelle_historique_quand_public_par_defaut():
    if jinja2 is None:
        print("  (ignoré : jinja2 non installé)")
        return
    bloc = _bloc_case_public(
        _rendre("fragments/modale_nouveau_projet.html", depot_public_par_defaut=True))
    assert 'id="np-public" checked' in bloc.replace("\n", " ")
    assert "décocher pour un dépôt privé" in bloc
    # Le sens de la case ne doit jamais être contraire au libellé : cochée
    # par défaut ⇒ le libellé ne doit pas annoncer "privé par défaut".
    assert "privé par défaut" not in bloc


def test_case_publique_decochee_et_libelle_adapte_quand_prive_par_defaut():
    if jinja2 is None:
        print("  (ignoré : jinja2 non installé)")
        return
    bloc = _bloc_case_public(
        _rendre("fragments/modale_nouveau_projet.html", depot_public_par_defaut=False))
    assert 'id="np-public" checked' not in bloc.replace("\n", " ")
    assert "cocher pour un dépôt public" in bloc
    assert "privé par défaut" in bloc
    # Inversement, décochée par défaut ⇒ pas le libellé historique qui
    # suggérerait à tort que la case est cochée.
    assert "décocher pour un dépôt privé" not in bloc


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
