#!/usr/bin/env python3
"""Test — issue #870 : copie de l'outil sur un poste seul, trois corrections.

1. Faux message d'échec de la doc — sur une copie non-propriétaire
   (`COPIE_NON_PROPRIETAIRE = oui`, issue #869), `creer_projet()`/
   `supprimer_projet()` ne tentent JAMAIS de commit/push sur
   `BRIDGE_AGENT_DOC.md` (voir tests/test_copie_non_proprietaire_869.py) ;
   mais `doc_commit_statut` valait `None` dans ce cas, interprété à tort
   comme un échec par les consommateurs (`afficherRappelGit` dans
   static/js/app.js, `messageStatutCommitDoc` dans static/js/config.js),
   qui affichaient alors un encadré « Action requise » / un message
   affirmant un commit/push automatique — alors qu'aucun commit n'a jamais
   été tenté. Corrigé en renvoyant un statut explicite `"non_applicable"`,
   géré par les deux consommateurs JS (voir static/js/tests/config.test.js
   pour messageStatutCommitDoc ; afficherRappelGit touche le DOM, vérifié à
   la main, cf. VERIFICATIONS_MANUELLES.md).

2. Encadré du hook de relecture (Relecture_Bridge, issue #578) — affiché
   SANS CONDITION jusqu'ici alors que cet outil n'existe que sur la machine
   d'Alain. `identite.relecture_disponible()` détecte sa présence
   (`~/Relecture_Bridge/installer.sh`) ; `creer_projet()` renvoie ce
   booléen (`relecture_disponible`), lu par static/js/app.js avant
   d'afficher l'encadré.

3. Réglage `MACHINE_SEULE` (`identite_locale.conf`, nom repris de la
   solution de fond déjà évoquée au §16.1 de BRIDGE_AGENT_DOC.md et au §4 de
   provisioning/windows/ROUTAGE_LABELS_POSTE_SEUL.md, issue #866/#867) —
   masque l'onglet « CCW » et la case « Projet CCW » du formulaire de
   nouveau projet (`identite.machine_seule()`, lu par `app/vues.py::index()`
   et consommé par les fragments Jinja `onglets.html` /
   `modale_nouveau_projet.html`). N'implémente PAS le routage des labels
   for-linux/for-windows décrit dans ces deux documents (hors périmètre).

Comme tests/test_copie_non_proprietaire_869.py : aucun accès au vrai
`configs/`, au vrai `BRIDGE_AGENT_DOC.md` ni au vrai dépôt git.

Exécution :  python3 -m pytest tests/test_poste_seul_870.py
         ou  python3 tests/test_poste_seul_870.py
"""

import sys
import tempfile
from pathlib import Path
from unittest import mock

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import identite  # noqa: E402
import nouveau_projet as np_cli  # noqa: E402
import supprimer_projet as sp_cli  # noqa: E402

try:
    import jinja2
except ImportError:
    jinja2 = None


# ─── 1. identite.machine_seule() ─────────────────────────────────────────

def test_machine_seule_absente_par_defaut():
    with tempfile.TemporaryDirectory() as tmp:
        chemin = Path(tmp) / "identite_locale.conf"  # n'existe pas
        with mock.patch.object(identite, "FICHIER_IDENTITE_LOCALE", chemin):
            assert identite.machine_seule() is False


def test_machine_seule_active_oui():
    with tempfile.TemporaryDirectory() as tmp:
        chemin = Path(tmp) / "identite_locale.conf"
        chemin.write_text("MACHINE_SEULE = oui\n", encoding="utf-8")
        with mock.patch.object(identite, "FICHIER_IDENTITE_LOCALE", chemin):
            assert identite.machine_seule() is True


def test_machine_seule_valeur_quelconque_reste_inactive():
    with tempfile.TemporaryDirectory() as tmp:
        chemin = Path(tmp) / "identite_locale.conf"
        chemin.write_text("MACHINE_SEULE = non\n", encoding="utf-8")
        with mock.patch.object(identite, "FICHIER_IDENTITE_LOCALE", chemin):
            assert identite.machine_seule() is False


# ─── 2. identite.relecture_disponible() ──────────────────────────────────

def test_relecture_disponible_absente():
    with tempfile.TemporaryDirectory() as tmp:
        with mock.patch.object(Path, "home", return_value=Path(tmp)):
            assert identite.relecture_disponible() is False


def test_relecture_disponible_presente():
    with tempfile.TemporaryDirectory() as tmp:
        dossier = Path(tmp) / "Relecture_Bridge"
        dossier.mkdir()
        (dossier / "installer.sh").write_text("#!/bin/sh\n", encoding="utf-8")
        with mock.patch.object(Path, "home", return_value=Path(tmp)):
            assert identite.relecture_disponible() is True


# ─── 3. nouveau_projet.creer_projet() — doc_commit_statut + relecture ────

def _mocker_etapes_reseau_creation(monkeypatch, configs: Path, tmp_path: Path) -> None:
    monkeypatch.setattr(np_cli, "DOSSIER_CONFIGS", configs)
    monkeypatch.setattr(np_cli, "depot_existe", lambda depot: True)
    monkeypatch.setattr(np_cli, "creer_labels", lambda depot: [])
    monkeypatch.setattr(np_cli, "creer_fichiers_contexte",
                        lambda rep, avec_specs: {"crees": [], "existants": [], "rep_cree": False})
    monkeypatch.setattr(np_cli, "initialiser_git", lambda rep, depot: {
        "ok": True, "detail": "ignoré (test)", "deja_git": True, "push_ok": None,
        "contenu_preexistant": [], "commande_manuelle": None,
    })
    # ecrire_conf() (appelée par creer_projet()) écrit aussi dans
    # logs/configs_legitimes.json — isolé dans tmp_path, même technique que
    # _isoler_etats_json ci-dessous (sans quoi le verrou échoue si logs/
    # n'existe pas, comme ici dans un worktree neuf sans historique watcher).
    monkeypatch.setattr(np_cli.etat_configs_legitimes, "CHEMIN_ETAT",
                        tmp_path / "configs_legitimes.json")
    monkeypatch.setattr(np_cli.etat_configs_legitimes, "CHEMIN_VERROU",
                        (tmp_path / "configs_legitimes.json").with_suffix(".lock"))


def test_creer_projet_sans_copie_non_proprietaire_statut_ok(monkeypatch, tmp_path):
    """Comportement ACTUEL, inchangé : sans COPIE_NON_PROPRIETAIRE,
    doc_commit_statut reflète toujours le statut réel de committer_pousser_doc."""
    configs = tmp_path / "configs"
    configs.mkdir()
    _mocker_etapes_reseau_creation(monkeypatch, configs, tmp_path)
    monkeypatch.setattr(np_cli, "mettre_a_jour_doc", lambda: {
        "existe": True, "ok2": True, "ok7": True, "ok_date": True, "erreur": None,
        "local": False, "fichier_local": None,
    })
    monkeypatch.setattr(np_cli.regenerer_tableaux_projets, "committer_pousser_doc",
                        lambda message, **k: {"statut": "ok", "detail": "simulé",
                                               "commande_manuelle": None})

    resultat = np_cli.creer_projet(
        nom="defaut870", depot="AlainDelree/Defaut870",
        rep=str(tmp_path / "rep"), perimetre=str(tmp_path / "rep"))

    assert resultat["succes"] is True
    assert resultat["doc_commit_statut"] == "ok"


def test_creer_projet_avec_copie_non_proprietaire_statut_non_applicable(monkeypatch, tmp_path):
    """Avant #870 : doc_commit_statut valait None ici, interprété à tort
    comme un échec par les consommateurs JS. Doit désormais valoir
    "non_applicable" — un statut explicite, jamais un échec."""
    configs = tmp_path / "configs"
    configs.mkdir()
    _mocker_etapes_reseau_creation(monkeypatch, configs, tmp_path)
    fichier_local = tmp_path / "PROJETS_LOCAUX.md"
    monkeypatch.setattr(np_cli, "mettre_a_jour_doc", lambda: {
        "existe": True, "ok2": True, "ok7": True, "ok_date": True, "erreur": None,
        "local": True, "fichier_local": str(fichier_local),
    })

    def _commit_interdit(*a, **k):
        raise AssertionError("committer_pousser_doc ne doit jamais être appelé "
                              "quand COPIE_NON_PROPRIETAIRE est actif")
    monkeypatch.setattr(np_cli.regenerer_tableaux_projets, "committer_pousser_doc", _commit_interdit)

    resultat = np_cli.creer_projet(
        nom="actif870", depot="AlainDelree/Actif870",
        rep=str(tmp_path / "rep"), perimetre=str(tmp_path / "rep"))

    assert resultat["succes"] is True
    assert resultat["doc_commit_statut"] == "non_applicable"
    assert resultat["doc_commit_statut"] not in ("echec", "push_echoue")


def test_creer_projet_relecture_disponible_transmis(monkeypatch, tmp_path):
    """creer_projet() transmet identite.relecture_disponible() tel quel
    (True ET False) — c'est ce booléen que static/js/app.js lit avant
    d'afficher l'encadré du hook de relecture."""
    configs = tmp_path / "configs"
    configs.mkdir()
    _mocker_etapes_reseau_creation(monkeypatch, configs, tmp_path)
    monkeypatch.setattr(np_cli, "mettre_a_jour_doc", lambda: {
        "existe": True, "ok2": True, "ok7": True, "ok_date": True, "erreur": None,
        "local": True, "fichier_local": str(tmp_path / "PROJETS_LOCAUX.md"),
    })

    monkeypatch.setattr(np_cli.identite, "relecture_disponible", lambda: True)
    resultat_dispo = np_cli.creer_projet(
        nom="relecturea870", depot="AlainDelree/RelectureA870",
        rep=str(tmp_path / "rep1"), perimetre=str(tmp_path / "rep1"))
    assert resultat_dispo["relecture_disponible"] is True

    monkeypatch.setattr(np_cli.identite, "relecture_disponible", lambda: False)
    resultat_absente = np_cli.creer_projet(
        nom="relectureb870", depot="AlainDelree/RelectureB870",
        rep=str(tmp_path / "rep2"), perimetre=str(tmp_path / "rep2"))
    assert resultat_absente["relecture_disponible"] is False


# ─── 4. supprimer_projet.supprimer_projet() — doc_commit_statut ─────────

def _preparer_projet(tmp_path: Path, nom: str):
    configs = tmp_path / "configs"
    rep = tmp_path / "travail" / nom
    rep.mkdir(parents=True)
    (rep / ".git").mkdir()
    configs.mkdir(parents=True, exist_ok=True)
    (configs / f"{nom}.conf").write_text(
        f"NOM = {nom}\nDEPOT = AlainDelree/{nom}\nREP_TRAVAIL = {rep}\n", encoding="utf-8")
    return configs, rep


def _isoler_etats_json(monkeypatch, tmp_path: Path) -> None:
    import etat_cases_cochees as ecc
    import etat_son_issue as esi
    import etat_configs_legitimes as ecl
    monkeypatch.setattr(ecc, "CHEMIN_ETAT", tmp_path / "etat_cases_cochees.json")
    monkeypatch.setattr(ecc, "CHEMIN_VERROU", (tmp_path / "etat_cases_cochees.json").with_suffix(".lock"))
    monkeypatch.setattr(esi, "CHEMIN_ETAT", tmp_path / "son_issues.json")
    monkeypatch.setattr(esi, "CHEMIN_VERROU", (tmp_path / "son_issues.json").with_suffix(".lock"))
    monkeypatch.setattr(ecl, "CHEMIN_ETAT", tmp_path / "configs_legitimes.json")
    monkeypatch.setattr(ecl, "CHEMIN_VERROU", (tmp_path / "configs_legitimes.json").with_suffix(".lock"))


def test_supprimer_projet_sans_copie_non_proprietaire_statut_ok(monkeypatch, tmp_path):
    nom = "suppdefaut870"
    configs, rep = _preparer_projet(tmp_path, nom)
    monkeypatch.setattr(sp_cli, "DOSSIER_CONFIGS", configs)
    _isoler_etats_json(monkeypatch, tmp_path)
    monkeypatch.setattr(sp_cli, "mettre_a_jour_doc", lambda: {
        "existe": True, "ok": True, "modifie": True, "erreur": None,
        "local": False, "fichier_local": None,
    })
    monkeypatch.setattr(sp_cli.regenerer_tableaux_projets, "committer_pousser_doc",
                        lambda message, **k: {"statut": "ok", "detail": "simulé",
                                               "commande_manuelle": None})

    resultat = sp_cli.supprimer_projet(nom, dry_run=False)

    assert resultat["succes"] is True
    assert resultat["doc_commit_statut"] == "ok"


def test_supprimer_projet_avec_copie_non_proprietaire_statut_non_applicable(monkeypatch, tmp_path):
    nom = "suppactif870"
    configs, rep = _preparer_projet(tmp_path, nom)
    monkeypatch.setattr(sp_cli, "DOSSIER_CONFIGS", configs)
    _isoler_etats_json(monkeypatch, tmp_path)
    monkeypatch.setattr(sp_cli, "mettre_a_jour_doc", lambda: {
        "existe": True, "ok": True, "modifie": True, "erreur": None,
        "local": True, "fichier_local": str(tmp_path / "PROJETS_LOCAUX.md"),
    })

    def _commit_interdit(*a, **k):
        raise AssertionError("committer_pousser_doc ne doit jamais être appelé "
                              "quand COPIE_NON_PROPRIETAIRE est actif")
    monkeypatch.setattr(sp_cli.regenerer_tableaux_projets, "committer_pousser_doc", _commit_interdit)

    resultat = sp_cli.supprimer_projet(nom, dry_run=False)

    assert resultat["succes"] is True
    assert resultat["doc_commit_statut"] == "non_applicable"
    assert resultat["doc_commit_statut"] not in ("echec", "push_echoue")


# ─── 5. Rendu Jinja — onglet CCW + case « Projet CCW » masqués ───────────

def _rendre(nom_fragment: str, **contexte) -> str:
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(str(RACINE / "templates")))
    return env.get_template(nom_fragment).render(**contexte)


def test_onglet_ccw_visible_sans_reglage():
    if jinja2 is None:
        print("  (ignoré : jinja2 non installé)")
        return
    rendu = _rendre("fragments/onglets.html", machine_seule=False)
    assert 'data-onglet="ccw" >' in rendu or 'data-onglet="ccw">' in rendu, rendu
    assert "display:none" not in rendu.split('data-onglet="ccw"')[1].split(">")[0]


def test_onglet_ccw_masque_avec_machine_seule():
    if jinja2 is None:
        print("  (ignoré : jinja2 non installé)")
        return
    rendu = _rendre("fragments/onglets.html", machine_seule=True)
    bloc = rendu.split('data-onglet="ccw"')[1].split(">")[0]
    assert "display:none" in bloc, rendu


def test_case_projet_ccw_visible_sans_reglage():
    if jinja2 is None:
        print("  (ignoré : jinja2 non installé)")
        return
    rendu = _rendre("fragments/modale_nouveau_projet.html", machine_seule=False)
    bloc = rendu.split('id="np-ccw"')[0].rsplit("<label", 1)[1]
    assert "display:block" in bloc, rendu


def test_case_projet_ccw_masquee_avec_machine_seule():
    if jinja2 is None:
        print("  (ignoré : jinja2 non installé)")
        return
    rendu = _rendre("fragments/modale_nouveau_projet.html", machine_seule=True)
    bloc = rendu.split('id="np-ccw"')[0].rsplit("<label", 1)[1]
    assert "display:none" in bloc, rendu
    # L'élément reste dans le DOM (pas retiré) — app.js le référence par
    # getElementById sans vérifier son existence (voir le commentaire HTML
    # du template).
    assert 'id="np-ccw"' in rendu


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
