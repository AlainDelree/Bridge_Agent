#!/usr/bin/env python3
"""Test de `app/projets.py` / `nouveau_projet.py` — issue #643 (refonte web,
étape 8 : retrait du réglage de son PAR PROJET — `SCRIPT_BIP`/`TONALITE_BIP`
— de l'onglet Configuration, décidé dès le début de la refonte au profit du
modèle à deux niveaux : interrupteur global + choix par issue, #630/#637).

Couvre :
- `CLES_EDITABLES` ne contient plus `SCRIPT_BIP` ni `TONALITE_BIP` : ces clés
  ne sont plus éditables depuis l'interface ;
- `get_config` sur un `.conf` existant qui porte encore ces clés (résidu
  d'avant #643, cf. l'ancien `chesscoach.conf`) ne lève aucune erreur et ne
  les expose plus dans sa réponse JSON ;
- `post_config` sur ce même `.conf` n'écrit ni ne touche ces clés (filtrées
  par `CLES_EDITABLES`), même si le front les soumettait encore par erreur ;
- le gabarit généré par `nouveau_projet.ecrire_conf` pour un NOUVEAU projet
  ne contient plus de ligne `SCRIPT_BIP` ni de commentaire `TONALITE_BIP`, ni
  aucune référence à `bip_Cloche.py` (fichier supprimé par #630).

Exécution :  python3 tests/test_retrait_son_par_projet_643.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import sys
import tempfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import flask  # noqa: E402

import app.projets as projets  # noqa: E402
import nouveau_projet as np_cli  # noqa: E402

APP_FLASK = flask.Flask(__name__)


def _ecrire_conf_avec_son_par_projet(dossier_configs: Path, nom: str, rep: Path) -> Path:
    """.conf minimal mais portant encore SCRIPT_BIP/TONALITE_BIP — le cas
    résiduel (ex. l'ancien chesscoach.conf) que #643 doit continuer à
    tolérer sans erreur ni écriture forcée."""
    dossier_configs.mkdir(parents=True, exist_ok=True)
    chemin = dossier_configs / f"{nom}.conf"
    chemin.write_text(
        f"NOM = {nom}\n"
        f"DEPOT = AlainDelree/{nom}\n"
        f"REP_TRAVAIL = {rep}\n"
        f"TOPIC_NTFY = topic-test\n"
        f"SCRIPT_BIP = /home/alain/Bridge_Agent/scripts/bip_Cloche.py\n"
        f"TONALITE_BIP = 5\n",
        encoding="utf-8")
    return chemin


def test_cles_editables_sans_son_par_projet():
    assert "SCRIPT_BIP" not in projets.CLES_EDITABLES
    assert "TONALITE_BIP" not in projets.CLES_EDITABLES
    return {"cles": sorted(projets.CLES_EDITABLES)}


def test_get_config_tolere_conf_existant_avec_anciennes_cles():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        configs = tmp / "configs"
        rep_travail = tmp / "travail" / "chesscoach"
        rep_travail.mkdir(parents=True)
        _ecrire_conf_avec_son_par_projet(configs, "chesscoach", rep_travail)

        ancien = projets.DOSSIER_SCRIPT
        projets.DOSSIER_SCRIPT = tmp
        try:
            with APP_FLASK.test_request_context("/config/chesscoach"):
                rep = projets.get_config("chesscoach")
        finally:
            projets.DOSSIER_SCRIPT = ancien

        # Pas de tuple (erreur, code) : réponse simple → succès, pas d'exception.
        assert not isinstance(rep, tuple), f"erreur inattendue : {rep}"
        corps = rep.get_json()
        assert "script_bip" not in corps
        assert "tonalite_bip" not in corps
    return {"cles_reponse": sorted(corps.keys())}


def test_post_config_ne_touche_pas_aux_anciennes_cles():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        configs = tmp / "configs"
        rep_travail = tmp / "travail" / "chesscoach"
        rep_travail.mkdir(parents=True)
        chemin = _ecrire_conf_avec_son_par_projet(configs, "chesscoach", rep_travail)
        avant = chemin.read_text(encoding="utf-8")

        ancien = projets.DOSSIER_SCRIPT
        projets.DOSSIER_SCRIPT = tmp
        try:
            with APP_FLASK.test_request_context(
                    "/config/chesscoach", method="POST",
                    json={"TOPIC_NTFY": "nouveau-topic",
                          "SCRIPT_BIP": "/tmp/devrait-etre-ignore.py",
                          "TONALITE_BIP": "9"}):
                rep = projets.post_config("chesscoach")
        finally:
            projets.DOSSIER_SCRIPT = ancien

        corps = rep.get_json()
        assert corps["succes"] is True
        apres = chemin.read_text(encoding="utf-8")
        # La clé éditable soumise a bien changé...
        assert "TOPIC_NTFY = nouveau-topic" in apres
        # ...mais les deux clés retirées de CLES_EDITABLES sont intactes
        # (ni modifiées avec la nouvelle valeur soumise, ni supprimées).
        assert "bip_Cloche.py" in apres
        assert "TONALITE_BIP = 5" in apres
        assert "devrait-etre-ignore" not in apres
        assert "TONALITE_BIP = 9" not in apres
        assert avant.count("SCRIPT_BIP") == apres.count("SCRIPT_BIP")
    return {"succes": corps["succes"]}


def test_gabarit_nouveau_projet_sans_son_par_projet():
    with tempfile.TemporaryDirectory() as tmp:
        configs = Path(tmp) / "configs"
        configs.mkdir()
        ancien = np_cli.DOSSIER_CONFIGS
        np_cli.DOSSIER_CONFIGS = configs
        try:
            chemin = np_cli.ecrire_conf(
                "monprojet", "AlainDelree/Monprojet", "/home/alain/Monprojet",
                "/home/alain/Monprojet")
        finally:
            np_cli.DOSSIER_CONFIGS = ancien

        contenu = chemin.read_text(encoding="utf-8")
        assert "SCRIPT_BIP" not in contenu
        assert "TONALITE_BIP" not in contenu
        assert "bip_Cloche.py" not in contenu
    return {"longueur_conf": len(contenu)}


def test_creer_projet_signature_sans_script_bip():
    """`creer_projet` n'accepte plus de paramètre `script_bip` (supprimé avec
    SCRIPT_BIP_DEFAUT) — un appel avec cet argument doit échouer explicitement
    plutôt que d'être silencieusement accepté puis ignoré."""
    import inspect
    params = inspect.signature(np_cli.creer_projet).parameters
    assert "script_bip" not in params
    assert not hasattr(np_cli, "SCRIPT_BIP_DEFAUT")
    return {"parametres": sorted(params.keys())}


def main() -> int:
    tests = [
        ("CLES_EDITABLES sans SCRIPT_BIP/TONALITE_BIP", test_cles_editables_sans_son_par_projet),
        ("get_config tolère un .conf existant avec ces clés, sans erreur, sans les exposer",
         test_get_config_tolere_conf_existant_avec_anciennes_cles),
        ("post_config ignore ces clés sans les modifier ni les supprimer",
         test_post_config_ne_touche_pas_aux_anciennes_cles),
        ("gabarit nouveau_projet.py sans SCRIPT_BIP/TONALITE_BIP/bip_Cloche.py",
         test_gabarit_nouveau_projet_sans_son_par_projet),
        ("creer_projet()/SCRIPT_BIP_DEFAUT n'existent plus", test_creer_projet_signature_sans_script_bip),
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
