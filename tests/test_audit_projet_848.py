#!/usr/bin/env python3
"""Tests — issue #848 : un template d'audit par projet (onglet Configuration)
+ bouton « Préparer l'audit » + sélecteur de complexité du formulaire web.

Couvre :
- `app.audit` : import d'un fichier valide (titre/corps/timeout/mode/
  complexité extraits via `scripts/watcher_issues_inbox.py::extraire_champs`,
  réutilisée telle quelle — pas de second parseur) ; import sans COMPLEXITE
  ou avec une valeur non reconnue (repli 'normal' + avertissement) ; import
  avec PROJET/REPO_CIBLE inattendus (avertissement, valeurs toujours
  ignorées) ; remplacement d'un template existant ; suppression ; lecture du
  template d'un projet sans audit (`existe: False`).
- `app.templates.CHAMPS_TEMPLATE_DEFAUTS` : `repo_cible`/`complexite` ont un
  défaut qui permet de relire un ANCIEN template (créé avant cette issue,
  sans ces deux clés) sans erreur.
- `app.issues.construire_body`/`construire_labels` : le sélecteur de
  complexité du formulaire web (`data["complexite"]`) produit la ligne
  `| COMPLEXITE | ... |` dans le body ET empêche la pose du label
  `sans-complexite` — sans lui (ancien template, champ absent), comportement
  inchangé (label posé comme avant l'issue #848).

Exécution :  python3 -m pytest tests/test_audit_projet_848.py
        ou : python3 tests/test_audit_projet_848.py
"""

import sys
import tempfile
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))
sys.path.insert(0, str(RACINE / "scripts"))

import flask  # noqa: E402

import app.audit as audit_mod  # noqa: E402
import app.issues as app_issues  # noqa: E402
import app.templates as app_templates  # noqa: E402
from watcher import LABEL_SANS_COMPLEXITE, NIVEAUX_COMPLEXITE  # noqa: E402

APP_FLASK = flask.Flask(__name__)
APP_FLASK.add_url_rule("/audit/<nom_projet>/importer", "audit_importer", audit_mod.audit_importer, methods=["POST"])


class Patch:
    """Remplace `getattr(module, nom)` par `valeur` ; restaure à la sortie du
    `with` — même utilitaire minimal que tests/test_repo_cible_creation_829.py."""

    def __init__(self, module, nom, valeur):
        self.module, self.nom, self.valeur = module, nom, valeur

    def __enter__(self):
        self.original = getattr(self.module, self.nom)
        setattr(self.module, self.nom, self.valeur)
        return self.valeur

    def __exit__(self, *exc):
        setattr(self.module, self.nom, self.original)


@pytest.fixture
def projet(tmp_path):
    """Config bidon + redirection du dossier de stockage des templates
    d'audit vers un répertoire temporaire — aucun vrai configs/*.json
    touché."""
    rep_travail = tmp_path / "rep_travail"
    rep_travail.mkdir()
    cfg = SimpleNamespace(nom="projet_test_848", rep_travail=rep_travail)
    with Patch(audit_mod, "DOSSIER_TEMPLATES", tmp_path), \
         Patch(audit_mod, "projet_par_nom", lambda nom: cfg if nom == cfg.nom else None):
        yield cfg


def _importer(nom_projet, contenu):
    """Poste `contenu` comme fichier audit.txt vers /audit/<nom>/importer,
    retourne le JSON de la réponse."""
    with APP_FLASK.test_client() as c:
        rep = c.post(
            f"/audit/{nom_projet}/importer",
            data={"fichier": (BytesIO(contenu.encode("utf-8")), "audit.txt")},
            content_type="multipart/form-data",
        )
        return rep.status_code, rep.get_json()


# ─── Import d'un fichier valide ────────────────────────────────────────────

def test_import_fichier_valide(projet):
    contenu = (
        "| PROJET     | diagnostique_programme |\n"
        "| MODE       | écriture |\n"
        f"| REPO_CIBLE | {projet.rep_travail} |\n"
        "| COMPLEXITE | lourd |\n"
        "| TIMEOUT    | 1200 |\n"
        "\n"
        "#Titre: Audit complet du projet\n"
        "\n"
        "## Contexte\nTexte d'audit.\n"
    )
    statut, rep = _importer(projet.nom, contenu)
    assert statut == 200, rep
    assert rep["succes"] is True
    assert rep["audit"] == {
        "titre": "Audit complet du projet",
        "corps": "## Contexte\nTexte d'audit.",
        "timeout": "1200",
        "mode": "ecriture",
        "complexite": "lourd",
    }
    # PROJET/REPO_CIBLE cohérents avec l'usage attendu (diagnostique_programme,
    # REP_TRAVAIL du projet audité) : aucun avertissement.
    assert rep["avertissements"] == []
    # Relecture (GET) : même contenu, existe=True.
    lu = audit_mod._charger_audit(projet.nom)
    assert lu == rep["audit"]


def test_import_titre_absent_rejete(projet):
    statut, rep = _importer(projet.nom, "| COMPLEXITE | normal |\n\nPas de titre.\n")
    assert statut == 400
    assert rep["succes"] is False
    assert "Titre" in rep["erreur"]


def test_import_aucun_fichier_rejete(projet):
    with APP_FLASK.test_client() as c:
        rep = c.post(f"/audit/{projet.nom}/importer", data={}, content_type="multipart/form-data")
    assert rep.status_code == 400
    assert rep.get_json()["succes"] is False


def test_import_projet_introuvable():
    statut, rep = _importer("projet_inexistant_848", "#Titre: X\n")
    assert statut == 404
    assert rep["succes"] is False


# ─── COMPLEXITE absente ou non reconnue ────────────────────────────────────

def test_import_sans_complexite_replie_normal_avec_avertissement(projet):
    statut, rep = _importer(projet.nom, "#Titre: Audit sans complexite\n\nCorps.\n")
    assert statut == 200, rep
    assert rep["audit"]["complexite"] == "normal"
    assert any("COMPLEXITE" in a and "Aucune ligne" in a for a in rep["avertissements"]), rep["avertissements"]


def test_import_complexite_non_reconnue_replie_normal_avec_avertissement(projet):
    contenu = "| COMPLEXITE | moyen |\n\n#Titre: Audit complexite inconnue\n\nCorps.\n"
    statut, rep = _importer(projet.nom, contenu)
    assert statut == 200, rep
    assert rep["audit"]["complexite"] == "normal"
    assert any("moyen" in a and "non reconnue" in a for a in rep["avertissements"]), rep["avertissements"]


def test_import_complexite_valide_aucun_avertissement(projet):
    for niveau in NIVEAUX_COMPLEXITE:
        contenu = f"| COMPLEXITE | {niveau} |\n\n#Titre: Audit {niveau}\n\nCorps.\n"
        statut, rep = _importer(projet.nom, contenu)
        assert statut == 200, rep
        assert rep["audit"]["complexite"] == niveau
        assert not any("COMPLEXITE" in a for a in rep["avertissements"]), rep["avertissements"]


def test_import_ligne_complexite_retiree_du_corps_stocke(projet):
    """La ligne COMPLEXITE ne doit pas rester dans le corps stocké — sinon
    elle apparaîtrait EN DOUBLE dans l'issue d'audit créée (une fois via le
    sélecteur de complexité du formulaire, une fois comme texte brut)."""
    contenu = "| COMPLEXITE | lourd |\n\n#Titre: Audit\n\n## Contexte\nTexte.\n"
    _, rep = _importer(projet.nom, contenu)
    assert "COMPLEXITE" not in rep["audit"]["corps"]


# ─── PROJET / REPO_CIBLE inattendus : avertissement, valeurs ignorées ──────

def test_import_projet_inattendu_avertit_et_ignore(projet):
    contenu = "| PROJET | bridge_agent |\n| COMPLEXITE | normal |\n\n#Titre: Audit\n\nCorps.\n"
    statut, rep = _importer(projet.nom, contenu)
    assert statut == 200, rep
    assert any("PROJET" in a and "bridge_agent" in a for a in rep["avertissements"]), rep["avertissements"]
    # Le champ n'est enregistré nulle part dans le template stocké.
    assert "projet" not in rep["audit"]
    assert "bridge_agent" not in rep["audit"]["corps"]


def test_import_repo_cible_inattendu_avertit_et_ignore(projet):
    contenu = ("| REPO_CIBLE | /tmp/ailleurs-848 |\n| COMPLEXITE | normal |\n\n"
               "#Titre: Audit\n\nCorps.\n")
    statut, rep = _importer(projet.nom, contenu)
    assert statut == 200, rep
    assert any("REPO_CIBLE" in a and "/tmp/ailleurs-848" in a for a in rep["avertissements"]), rep["avertissements"]
    assert "repo_cible" not in rep["audit"]


def test_import_repo_cible_correspondant_au_projet_audite_aucun_avertissement(projet):
    contenu = (f"| REPO_CIBLE | {projet.rep_travail} |\n| COMPLEXITE | normal |\n\n"
               "#Titre: Audit\n\nCorps.\n")
    statut, rep = _importer(projet.nom, contenu)
    assert statut == 200, rep
    assert not any("REPO_CIBLE" in a for a in rep["avertissements"]), rep["avertissements"]


def test_import_projet_diagnostique_programme_aucun_avertissement(projet):
    contenu = "| PROJET | diagnostique_programme |\n| COMPLEXITE | normal |\n\n#Titre: Audit\n\nCorps.\n"
    statut, rep = _importer(projet.nom, contenu)
    assert statut == 200, rep
    assert not any("PROJET" in a for a in rep["avertissements"]), rep["avertissements"]


# ─── Remplacement d'un template existant ───────────────────────────────────

def test_import_remplace_le_template_existant(projet):
    _importer(projet.nom, "| COMPLEXITE | rapide |\n\n#Titre: Premier\n\nCorps 1.\n")
    statut, rep = _importer(projet.nom, "| COMPLEXITE | lourd |\n\n#Titre: Second\n\nCorps 2.\n")
    assert statut == 200, rep
    lu = audit_mod._charger_audit(projet.nom)
    assert lu["titre"] == "Second"
    assert lu["complexite"] == "lourd"
    # Un seul template stocké (objet unique, pas une liste qui s'accumule).
    assert audit_mod._chemin_audit(projet.nom).read_text(encoding="utf-8").count('"titre"') == 1


# ─── Suppression ────────────────────────────────────────────────────────────

def test_suppression_template_existant(projet):
    _importer(projet.nom, "#Titre: Audit\n\nCorps.\n")
    assert audit_mod._charger_audit(projet.nom) is not None
    with APP_FLASK.test_request_context():
        rep = audit_mod.audit_supprimer(projet.nom)
    assert rep.get_json()["succes"] is True
    assert audit_mod._charger_audit(projet.nom) is None


def test_suppression_sans_template_404(projet):
    with APP_FLASK.test_request_context():
        rep = audit_mod.audit_supprimer(projet.nom)
    assert rep[1] == 404
    assert rep[0].get_json()["succes"] is False


def test_suppression_projet_introuvable():
    with APP_FLASK.test_request_context():
        rep = audit_mod.audit_supprimer("projet_inexistant_848")
    assert rep[1] == 404


# ─── Lecture du template d'audit d'un projet ───────────────────────────────

def test_lecture_projet_sans_audit_existe_false(projet):
    with APP_FLASK.test_request_context():
        rep = audit_mod.audit_lire(projet.nom)
    assert rep.get_json() == {"existe": False}


def test_lecture_projet_avec_audit_existe_true(projet):
    _importer(projet.nom, "| COMPLEXITE | court |\n\n#Titre: Audit\n\nCorps.\n")
    with APP_FLASK.test_request_context():
        rep = audit_mod.audit_lire(projet.nom)
    json_rep = rep.get_json()
    assert json_rep["existe"] is True
    assert json_rep["titre"] == "Audit"
    assert json_rep["complexite"] == "court"


def test_lecture_projet_introuvable_404():
    with APP_FLASK.test_request_context():
        rep = audit_mod.audit_lire("projet_inexistant_848")
    assert rep[1] == 404


# ─── app.templates — rétrocompatibilité des nouveaux champs ────────────────

def test_champs_template_defauts_retrocompatibles():
    """Un ANCIEN template enregistré avant l'issue #848 (sans `repo_cible` ni
    `complexite`) doit se relire avec les mêmes défauts que le reste du
    formulaire — comportement inchangé pour ces deux champs absents."""
    assert app_templates.CHAMPS_TEMPLATE_DEFAUTS["repo_cible"] == ""
    assert app_templates.CHAMPS_TEMPLATE_DEFAUTS["complexite"] == "normal"


def test_sauvegarde_template_memorise_repo_cible_et_complexite(tmp_path, monkeypatch):
    monkeypatch.setattr(app_templates, "DOSSIER_TEMPLATES", tmp_path)
    cfg = SimpleNamespace(nom="projet_test_848_tpl")
    monkeypatch.setattr(app_templates, "projet_par_nom", lambda nom: cfg if nom == cfg.nom else None)

    flaskapp = flask.Flask(__name__)
    data = {
        "projet": cfg.nom, "nom": "Mon template", "titre": "T", "corps": "C",
        "repo_cible": "/home/alain/MonProjet", "complexite": "lourd",
    }
    with flaskapp.test_request_context("/templates", method="POST", json=data):
        rep = app_templates.templates_sauvegarder()
    json_rep = rep.get_json()
    assert json_rep["succes"] is True
    assert json_rep["template"]["repo_cible"] == "/home/alain/MonProjet"
    assert json_rep["template"]["complexite"] == "lourd"


def test_chargement_ancien_template_sans_nouveaux_champs_ne_plante_pas(tmp_path, monkeypatch):
    """Un fichier templates_<projet>.json écrit avant l'issue #848 (sans les
    clés repo_cible/complexite) doit rester lisible — aucune KeyError."""
    monkeypatch.setattr(app_templates, "DOSSIER_TEMPLATES", tmp_path)
    ancien = [{
        "id": "abcd1234", "nom": "Ancien template", "projet": "projet_test_848_old",
        "titre": "T", "corps": "C", "priorite": "normale", "timeout": "300",
        "mode": "lecture", "notifs": [],
    }]
    (tmp_path / "templates_projet_test_848_old.json").write_text(
        __import__("json").dumps(ancien), encoding="utf-8")
    templates = app_templates._charger_templates("projet_test_848_old")
    assert templates == ancien
    assert "repo_cible" not in templates[0]
    assert "complexite" not in templates[0]


# ─── app.issues — sélecteur de complexité du formulaire web ───────────────

def test_construire_body_avec_complexite_ajoute_la_ligne():
    data = {"projet": "diagnostique_programme", "mode": "ecriture", "priorite": "normale",
            "timeout": "1200", "corps": "## Contexte\nAudit.", "complexite": "lourd"}
    body = app_issues.construire_body(data)
    assert "| COMPLEXITE | lourd |" in body, body


def test_construire_body_sans_complexite_inchange():
    data = {"projet": "bridge_agent", "mode": "lecture", "priorite": "normale",
            "timeout": "300", "corps": "Corps."}
    body = app_issues.construire_body(data)
    assert "COMPLEXITE" not in body, body


def test_construire_body_complexite_invalide_omise():
    """Une valeur hors des quatre niveaux (ancien template sans ce champ,
    valeur corrompue) est omise plutôt que d'écrire une ligne invalide."""
    data = {"projet": "bridge_agent", "mode": "lecture", "priorite": "normale",
            "timeout": "300", "corps": "Corps.", "complexite": "pas-un-niveau"}
    body = app_issues.construire_body(data)
    assert "COMPLEXITE" not in body, body


def test_construire_labels_avec_complexite_valide_pas_de_label_sans_complexite():
    for niveau in NIVEAUX_COMPLEXITE:
        data = {"corps": "Corps.", "complexite": niveau}
        labels = app_issues.construire_labels(data).split(",")
        assert LABEL_SANS_COMPLEXITE not in labels, (niveau, labels)


def test_construire_labels_sans_complexite_pose_le_label_comme_avant_848():
    """Comportement de l'issue #844 inchangé : un ancien template sans le
    champ `complexite` (et un corps sans ligne COMPLEXITE) reçoit toujours
    le label informatif."""
    data = {"corps": "Corps sans ligne COMPLEXITE."}
    labels = app_issues.construire_labels(data).split(",")
    assert LABEL_SANS_COMPLEXITE in labels, labels


def test_construire_labels_complexite_invalide_pose_le_label():
    data = {"corps": "Corps.", "complexite": "pas-un-niveau"}
    labels = app_issues.construire_labels(data).split(",")
    assert LABEL_SANS_COMPLEXITE in labels, labels


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
