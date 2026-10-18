#!/usr/bin/env python3
"""Test de non-régression — issue #766 : gestion du modèle de l'agent Vibe
(`~/.vibe/config.toml`) depuis l'interface web.

Couvre le versant SERVEUR (`app/vibe_modele.py`) :
- lecture (`GET /vibe-modele/etat`) : disponibilité, modèle actif, modèles
  déclarés, schéma introspecté — SANS liste de modèles figée dans le code ;
- absence du fichier / de l'outil : section inoffensive, aucune erreur ;
- écriture CHIRURGICALE (changer le modèle actif, ajouter, retirer) :
  préserve tout ce que l'interface ne gère pas (commentaires, réglages
  inconnus, autres blocs `[[models]]`) — point de vigilance explicite de
  l'issue ;
- refus de retirer le modèle actif, et refus de retirer le dernier modèle
  déclaré (jamais de fichier sans modèle actif) ;
- rejet d'un doublon d'alias au sein du fichier (collision certaine) et
  avertissement bloquant (confirmation requise) pour une collision avec un
  alias intégré connu (`mistral-medium-3.5`) ;
- une sauvegarde est écrite avant toute modification du fichier.

Exécution :  python3 tests/test_modele_vibe_766.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import sys
import tempfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import flask  # noqa: E402

import app.vibe_modele as vm  # noqa: E402

APP_FLASK = flask.Flask(__name__)

CONFIG_EXEMPLE = (
    "# commentaire de tête, à préserver\n"
    'active_model = "devstral2"\n'
    "reglage_inconnu_de_bridge = 42\n"
    "[[models]]\n"
    'name = "mistral-vibe-cli-latest"\n'
    'provider = "mistral"\n'
    'alias = "devstral2"\n'
    "input_price = 0.4\n"
    "output_price = 2.0\n"
    "[[models]]\n"
    'name = "autre-model"\n'
    'provider = "mistral"\n'
    'alias = "rapide"\n'
    "# commentaire niché dans le second bloc, à préserver aussi\n"
    "input_price = 0.1\n"
    "output_price = 0.5\n"
)


def _preparer(tmp: Path, contenu: str = CONFIG_EXEMPLE) -> Path:
    cfg = tmp / "config.toml"
    cfg.write_text(contenu, encoding="utf-8")
    vm.CHEMIN_VIBE_CONFIG = cfg
    vm.DOSSIER_SAUVEGARDES = tmp / "bridge_sauvegardes"
    # Isole aussi le journal des changements (issue #769) : sans ça, chaque
    # écriture réussie de ce fichier de test polluerait le vrai logs/ du dépôt.
    vm.DOSSIER_LOGS = tmp / "logs"
    vm.FICHIER_JOURNAL_MODELE = vm.DOSSIER_LOGS / "journal_modele_vibe.jsonl"
    return cfg


def _reponse(rep):
    """Normalise (reponse, statut) qu'il y ait eu tuple d'erreur ou non."""
    if isinstance(rep, tuple):
        return rep[0].get_json(), rep[1]
    return rep.get_json(), 200


def test_etat_sans_fichier_ni_outil_est_inoffensif():
    """Absence du fichier (et donc de tout projet utilisant Vibe) : pas
    d'erreur, section simplement indisponible."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        vm.CHEMIN_VIBE_CONFIG = tmp / "inexistant" / "config.toml"
        vm.DOSSIER_SAUVEGARDES = tmp / "bak"
        with APP_FLASK.test_request_context("/vibe-modele/etat"):
            rep = vm.etat_vibe_modele()
        corps, statut = _reponse(rep)
        assert statut == 200
        assert corps["disponible"] is False
        assert corps["fichier_existe"] is False
        assert corps["modeles"] == []
        assert "erreur" not in corps
    return {"disponible": corps["disponible"]}


def test_etat_liste_modeles_et_schema_sans_liste_figee():
    """Les modèles et le modèle actif viennent du fichier ; le schéma du
    formulaire d'ajout est introspecté (name/provider/alias ici, pas une
    constante du code qui se périmerait)."""
    with tempfile.TemporaryDirectory() as tmp:
        _preparer(Path(tmp))
        with APP_FLASK.test_request_context("/vibe-modele/etat"):
            rep = vm.etat_vibe_modele()
        corps, statut = _reponse(rep)
        assert statut == 200
        assert corps["disponible"] is True
        assert corps["modele_actif"] == "devstral2"
        aliases = {m["alias"]: m["actif"] for m in corps["modeles"]}
        assert aliases == {"devstral2": True, "rapide": False}
        # input_price/output_price ne servent qu'à l'affichage d'un coût
        # estimé côté Vibe, jamais à son fonctionnement : jamais promus en
        # requis même présents sur toutes les entrées existantes (#770).
        assert set(corps["schema"]["champs_requis"]) == {"name", "provider", "alias"}
        assert corps["schema"]["champs_connus"] == {"input_price": "nombre", "output_price": "nombre"}
    return {"aliases": aliases}


def test_changer_modele_actif_preserve_contenu_non_gere():
    """Changer active_model ne touche QUE cette ligne — commentaires, réglage
    inconnu, et les DEUX blocs [[models]] (y compris le commentaire niché
    dans le second) ressortent identiques."""
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _preparer(Path(tmp))
        with APP_FLASK.test_request_context(
            "/vibe-modele/activer", method="POST", json={"alias": "rapide"}
        ):
            rep = vm.activer_vibe_modele()
        corps, statut = _reponse(rep)
        assert statut == 200 and corps["succes"] is True

        texte = cfg.read_text(encoding="utf-8")
        assert 'active_model = "rapide"' in texte
        assert "# commentaire de tête, à préserver" in texte
        assert "reglage_inconnu_de_bridge = 42" in texte
        assert "# commentaire niché dans le second bloc, à préserver aussi" in texte
        assert 'name = "mistral-vibe-cli-latest"' in texte
        assert 'name = "autre-model"' in texte
    return {"texte_final": texte}


def test_refuse_retirer_le_modele_actif():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _preparer(Path(tmp))
        texte_avant = cfg.read_text(encoding="utf-8")
        with APP_FLASK.test_request_context(
            "/vibe-modele/retirer", method="POST", json={"alias": "devstral2"}
        ):
            rep = vm.retirer_vibe_modele()
        corps, statut = _reponse(rep)
        assert statut == 400
        assert "actif" in corps["erreur"]
        # Rien écrit sur disque : refus avant toute modification.
        assert cfg.read_text(encoding="utf-8") == texte_avant
    return {"erreur": corps["erreur"]}


def test_refuse_retirer_le_dernier_modele_meme_si_inactif():
    """Ne jamais laisser le fichier sans AUCUN modèle — même lorsque le seul
    modèle restant n'est, par construction, pas actif (cas impossible en
    pratique mais le garde-fou sur le COMPTE doit tenir indépendamment de
    celui sur l'alias actif)."""
    with tempfile.TemporaryDirectory() as tmp:
        contenu_un_seul = (
            'active_model = "rapide"\n'
            "[[models]]\n"
            'name = "autre-model"\n'
            'provider = "mistral"\n'
            'alias = "rapide"\n'
        )
        _preparer(Path(tmp), contenu_un_seul)
        with APP_FLASK.test_request_context(
            "/vibe-modele/retirer", method="POST", json={"alias": "rapide"}
        ):
            rep = vm.retirer_vibe_modele()
        corps, statut = _reponse(rep)
        assert statut == 400
    return {"erreur": corps["erreur"]}


def test_retirer_modele_inactif_preserve_le_reste():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _preparer(Path(tmp))
        with APP_FLASK.test_request_context(
            "/vibe-modele/retirer", method="POST", json={"alias": "rapide"}
        ):
            rep = vm.retirer_vibe_modele()
        corps, statut = _reponse(rep)
        assert statut == 200 and corps["succes"] is True
        assert [m["alias"] for m in corps["modeles"]] == ["devstral2"]

        texte = cfg.read_text(encoding="utf-8")
        assert "# commentaire de tête, à préserver" in texte
        assert "reglage_inconnu_de_bridge = 42" in texte
        assert 'alias = "rapide"' not in texte
        assert 'active_model = "devstral2"' in texte
    return {"texte_final": texte}


def test_rejette_doublon_alias_dans_le_fichier():
    """Collision CERTAINE (même alias deux fois) : rejetée sans confirmation
    possible, contrairement à la collision avec un alias intégré."""
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _preparer(Path(tmp))
        texte_avant = cfg.read_text(encoding="utf-8")
        with APP_FLASK.test_request_context(
            "/vibe-modele/ajouter", method="POST",
            json={"champs": {"name": "x", "provider": "mistral", "alias": "rapide",
                              "input_price": 0, "output_price": 0},
                  "forcer": True},
        ):
            rep = vm.ajouter_vibe_modele()
        corps, statut = _reponse(rep)
        assert statut == 400
        assert "collision" in corps["erreur"]
        assert cfg.read_text(encoding="utf-8") == texte_avant
    return {"erreur": corps["erreur"]}


def test_avertit_collision_alias_integre_et_bloque_sans_confirmation():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _preparer(Path(tmp))
        texte_avant = cfg.read_text(encoding="utf-8")
        champs = {"name": "x", "provider": "mistral", "alias": "mistral-medium-3.5",
                  "input_price": 0, "output_price": 0}

        with APP_FLASK.test_request_context(
            "/vibe-modele/ajouter", method="POST", json={"champs": champs}
        ):
            rep = vm.ajouter_vibe_modele()
        corps, statut = _reponse(rep)
        assert statut == 409
        assert corps.get("necessite_confirmation") is True
        assert cfg.read_text(encoding="utf-8") == texte_avant, "aucune écriture avant confirmation"

        with APP_FLASK.test_request_context(
            "/vibe-modele/ajouter", method="POST",
            json={"champs": champs, "forcer": True},
        ):
            rep = vm.ajouter_vibe_modele()
        corps, statut = _reponse(rep)
        assert statut == 200 and corps["succes"] is True
        assert "mistral-medium-3.5" in {m["alias"] for m in corps["modeles"]}
    return {"modeles": [m["alias"] for m in corps["modeles"]]}


def test_ajouter_modele_preserve_contenu_et_sauvegarde_avant_ecriture():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        cfg = _preparer(tmp)
        with APP_FLASK.test_request_context(
            "/vibe-modele/ajouter", method="POST",
            json={"champs": {"name": "nouveau-modele", "provider": "mistral",
                              "alias": "nouveau", "input_price": 1.0, "output_price": 3.0}},
        ):
            rep = vm.ajouter_vibe_modele()
        corps, statut = _reponse(rep)
        assert statut == 200 and corps["succes"] is True
        assert {m["alias"] for m in corps["modeles"]} == {"devstral2", "rapide", "nouveau"}

        texte = cfg.read_text(encoding="utf-8")
        assert "# commentaire de tête, à préserver" in texte
        assert "# commentaire niché dans le second bloc, à préserver aussi" in texte

        sauvegardes = list(vm.DOSSIER_SAUVEGARDES.glob("config-*.toml"))
        assert len(sauvegardes) == 1
        assert sauvegardes[0].read_text(encoding="utf-8") == CONFIG_EXEMPLE
    return {"sauvegardes": [p.name for p in sauvegardes]}


def test_champ_requis_manquant_rejete_sans_ecrire():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _preparer(Path(tmp))
        texte_avant = cfg.read_text(encoding="utf-8")
        with APP_FLASK.test_request_context(
            "/vibe-modele/ajouter", method="POST",
            json={"champs": {"alias": "incomplet"}},
        ):
            rep = vm.ajouter_vibe_modele()
        corps, statut = _reponse(rep)
        assert statut == 400
        assert "requis" in corps["erreur"]
        assert cfg.read_text(encoding="utf-8") == texte_avant
    return {"erreur": corps["erreur"]}


def test_fichier_toml_invalide_signale_sans_planter():
    with tempfile.TemporaryDirectory() as tmp:
        _preparer(Path(tmp), "ceci n'est pas du toml valide [[[")
        with APP_FLASK.test_request_context("/vibe-modele/etat"):
            rep = vm.etat_vibe_modele()
        corps, statut = _reponse(rep)
        assert statut == 200
        assert corps["disponible"] is False
        assert "erreur" in corps
    return {"erreur": corps["erreur"]}


def main() -> int:
    tests = [
        ("GET /vibe-modele/etat : fichier/outil absents → section inoffensive, pas d'erreur",
         test_etat_sans_fichier_ni_outil_est_inoffensif),
        ("GET /vibe-modele/etat : modèles + schéma lus depuis le fichier (rien de figé en dur)",
         test_etat_liste_modeles_et_schema_sans_liste_figee),
        ("POST /vibe-modele/activer : préserve commentaires/réglages inconnus/autres blocs",
         test_changer_modele_actif_preserve_contenu_non_gere),
        ("POST /vibe-modele/retirer : refuse de retirer le modèle actif",
         test_refuse_retirer_le_modele_actif),
        ("POST /vibe-modele/retirer : refuse de retirer le dernier modèle restant",
         test_refuse_retirer_le_dernier_modele_meme_si_inactif),
        ("POST /vibe-modele/retirer : un modèle inactif part, le reste est préservé",
         test_retirer_modele_inactif_preserve_le_reste),
        ("POST /vibe-modele/ajouter : doublon d'alias dans le fichier → rejeté (collision certaine)",
         test_rejette_doublon_alias_dans_le_fichier),
        ("POST /vibe-modele/ajouter : alias intégré connu → 409 bloquant puis accepté si forcer=true",
         test_avertit_collision_alias_integre_et_bloque_sans_confirmation),
        ("POST /vibe-modele/ajouter : préserve le contenu existant + sauvegarde écrite avant écriture",
         test_ajouter_modele_preserve_contenu_et_sauvegarde_avant_ecriture),
        ("POST /vibe-modele/ajouter : champ requis manquant → rejeté sans écrire",
         test_champ_requis_manquant_rejete_sans_ecrire),
        ("GET /vibe-modele/etat : TOML invalide → signalé proprement, jamais une exception",
         test_fichier_toml_invalide_signale_sans_planter),
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
