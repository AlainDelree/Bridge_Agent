#!/usr/bin/env python3
"""Test de non-régression — issue #769 : journal des changements de modèle
de l'agent Vibe effectués DEPUIS L'INTERFACE WEB (`app/vibe_modele.py`).

Couvre :
- un changement de modèle actif (`POST /vibe-modele/activer`) ajoute une
  entrée JSONL avec date, ancien et nouveau alias ;
- un changement vers le modèle déjà actif (no-op) n'ajoute AUCUNE entrée ;
- une déclaration (`/ajouter`) et un retrait (`/retirer`) sont journalisés
  avec le bon événement ;
- `GET /vibe-modele/etat` expose l'historique récent (plus récent en
  premier) sous la clé `journal` ;
- purge : au-delà de `NB_ENTREES_JOURNAL_CONSERVEES`, les entrées les plus
  anciennes sont perdues plutôt que de laisser le fichier grossir sans fin ;
- best-effort strict : un échec d'écriture du journal (dossier remplacé par
  un fichier, donc impossible à créer) ne fait PAS échouer le changement de
  modèle lui-même.

Exécution :  python3 tests/test_journal_modele_vibe_769.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import json
import sys
import tempfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import flask  # noqa: E402

import app.vibe_modele as vm  # noqa: E402

APP_FLASK = flask.Flask(__name__)

CONFIG_EXEMPLE = (
    'active_model = "devstral2"\n'
    "[[models]]\n"
    'name = "mistral-vibe-cli-latest"\n'
    'provider = "mistral"\n'
    'alias = "devstral2"\n'
    "[[models]]\n"
    'name = "autre-model"\n'
    'provider = "mistral"\n'
    'alias = "rapide"\n'
)


def _preparer(tmp: Path, contenu: str = CONFIG_EXEMPLE) -> Path:
    cfg = tmp / "config.toml"
    cfg.write_text(contenu, encoding="utf-8")
    vm.CHEMIN_VIBE_CONFIG = cfg
    vm.DOSSIER_SAUVEGARDES = tmp / "bridge_sauvegardes"
    vm.DOSSIER_LOGS = tmp / "logs"
    vm.FICHIER_JOURNAL_MODELE = vm.DOSSIER_LOGS / "journal_modele_vibe.jsonl"
    return cfg


def _lire_journal() -> list:
    if not vm.FICHIER_JOURNAL_MODELE.exists():
        return []
    return [json.loads(l) for l in vm.FICHIER_JOURNAL_MODELE.read_text(encoding="utf-8").splitlines()]


def _reponse(rep):
    if isinstance(rep, tuple):
        return rep[0].get_json(), rep[1]
    return rep.get_json(), 200


def test_changement_actif_journalise_ancien_et_nouveau():
    with tempfile.TemporaryDirectory() as tmp:
        _preparer(Path(tmp))
        with APP_FLASK.test_request_context("/vibe-modele/activer", json={"alias": "rapide"}):
            rep = vm.activer_vibe_modele()
        corps, statut = _reponse(rep)
        assert statut == 200, corps
        lignes = _lire_journal()
        assert len(lignes) == 1, lignes
        assert lignes[0]["evenement"] == "changement_actif"
        assert lignes[0]["ancien"] == "devstral2"
        assert lignes[0]["nouveau"] == "rapide"
        assert "date" in lignes[0] and lignes[0]["date"]
    return {"entree": lignes[0]}


def test_changement_vers_le_modele_deja_actif_nest_pas_journalise():
    """Un alias déjà actif est un no-op côté serveur (_definir_actif) —
    aucune entrée ne doit être ajoutée puisque rien n'a réellement changé."""
    with tempfile.TemporaryDirectory() as tmp:
        _preparer(Path(tmp))
        with APP_FLASK.test_request_context("/vibe-modele/activer", json={"alias": "devstral2"}):
            rep = vm.activer_vibe_modele()
        corps, statut = _reponse(rep)
        assert statut == 200, corps
        assert _lire_journal() == []
    return {"ok": True}


def test_declaration_et_retrait_journalises():
    with tempfile.TemporaryDirectory() as tmp:
        _preparer(Path(tmp))
        champs = {"name": "troisieme", "provider": "mistral", "alias": "turbo"}
        with APP_FLASK.test_request_context("/vibe-modele/ajouter", json={"champs": champs}):
            rep = vm.ajouter_vibe_modele()
        corps, statut = _reponse(rep)
        assert statut == 200, corps

        with APP_FLASK.test_request_context("/vibe-modele/retirer", json={"alias": "turbo"}):
            rep = vm.retirer_vibe_modele()
        corps, statut = _reponse(rep)
        assert statut == 200, corps

        lignes = _lire_journal()
        assert [l["evenement"] for l in lignes] == ["declaration", "retrait"]
        assert lignes[0]["nouveau"] == "turbo" and lignes[0]["ancien"] is None
        assert lignes[1]["ancien"] == "turbo" and lignes[1]["nouveau"] is None
    return {"evenements": [l["evenement"] for l in lignes]}


def test_etat_expose_le_journal_recent_plus_recent_en_premier():
    with tempfile.TemporaryDirectory() as tmp:
        _preparer(Path(tmp))
        with APP_FLASK.test_request_context("/vibe-modele/activer", json={"alias": "rapide"}):
            vm.activer_vibe_modele()
        with APP_FLASK.test_request_context("/vibe-modele/activer", json={"alias": "devstral2"}):
            vm.activer_vibe_modele()

        with APP_FLASK.test_request_context("/vibe-modele/etat"):
            rep = vm.etat_vibe_modele()
        corps, statut = _reponse(rep)
        assert statut == 200
        journal = corps["journal"]
        assert len(journal) == 2
        # Plus récent en premier : le second changement (→ devstral2) avant le premier (→ rapide).
        assert journal[0]["nouveau"] == "devstral2"
        assert journal[1]["nouveau"] == "rapide"
    return {"journal": journal}


def test_journal_purge_au_dela_du_plafond():
    with tempfile.TemporaryDirectory() as tmp:
        _preparer(Path(tmp))
        vm.NB_ENTREES_JOURNAL_CONSERVEES_SAUVEGARDE = vm.NB_ENTREES_JOURNAL_CONSERVEES
        vm.NB_ENTREES_JOURNAL_CONSERVEES = 3
        try:
            for alias in ["rapide", "devstral2", "rapide", "devstral2", "rapide"]:
                vm._journaliser_modele("changement_actif", ancien=None, nouveau=alias)
            lignes = _lire_journal()
            assert len(lignes) == 3, lignes
            assert [l["nouveau"] for l in lignes] == ["rapide", "devstral2", "rapide"]
        finally:
            vm.NB_ENTREES_JOURNAL_CONSERVEES = vm.NB_ENTREES_JOURNAL_CONSERVEES_SAUVEGARDE
    return {"nb_conserve": len(lignes)}


def test_echec_ecriture_journal_nempeche_pas_le_changement_de_modele():
    """Le dossier de logs est remplacé par un FICHIER (donc .mkdir() lève) :
    _journaliser_modele doit avaler l'erreur sans jamais la laisser remonter,
    et le changement de modèle lui-même doit malgré tout réussir (point de
    vigilance explicite de l'issue #769)."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        _preparer(tmp)
        bloque = tmp / "bloque"
        bloque.write_text("je suis un fichier, pas un dossier", encoding="utf-8")
        vm.DOSSIER_LOGS = bloque / "logs"  # .mkdir(parents=True) lèvera NotADirectoryError
        vm.FICHIER_JOURNAL_MODELE = vm.DOSSIER_LOGS / "journal_modele_vibe.jsonl"
        with APP_FLASK.test_request_context("/vibe-modele/activer", json={"alias": "rapide"}):
            rep = vm.activer_vibe_modele()
        corps, statut = _reponse(rep)
        assert statut == 200, corps
        assert corps["modele_actif"] == "rapide"
    return {"ok": True}


def main() -> int:
    tests = [
        ("POST /vibe-modele/activer : journalise ancien et nouveau alias",
         test_changement_actif_journalise_ancien_et_nouveau),
        ("POST /vibe-modele/activer vers le modèle déjà actif : aucune entrée (no-op)",
         test_changement_vers_le_modele_deja_actif_nest_pas_journalise),
        ("POST /vibe-modele/ajouter puis /retirer : événements declaration puis retrait",
         test_declaration_et_retrait_journalises),
        ("GET /vibe-modele/etat : expose le journal récent, plus récent en premier",
         test_etat_expose_le_journal_recent_plus_recent_en_premier),
        ("Journal : purge des entrées les plus anciennes au-delà du plafond",
         test_journal_purge_au_dela_du_plafond),
        ("Échec d'écriture du journal : n'empêche jamais le changement de modèle",
         test_echec_ecriture_journal_nempeche_pas_le_changement_de_modele),
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
