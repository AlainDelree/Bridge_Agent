#!/usr/bin/env python3
"""Test — issue #869 : réglage `COPIE_NON_PROPRIETAIRE` (`identite_locale.conf`)
pour une copie de l'outil qui n'appartient pas à Alain (ex. ami sur PC
Windows seul, issue #868).

Constat d'origine : sur une telle copie, créer ou supprimer un projet
réécrivait BRIDGE_AGENT_DOC.md avec les seuls projets de la copie, créait un
commit local (divergence avec le dépôt d'Alain, `git pull --ff-only` cassé
ensuite) et tentait un push qui échouerait — ou écraserait la doc d'Alain si
les droits étaient accordés. Ce fichier vérifie que :

- par défaut (réglage absent), le comportement est STRICTEMENT inchangé :
  `regenerer()`/`committer_pousser_doc()` sont appelés comme avant, pour la
  création ET la suppression ;
- une fois le réglage actif, AUCUNE écriture sur `BRIDGE_AGENT_DOC.md`,
  AUCUN commit, AUCUN push — à la place, `PROJETS_LOCAUX.md` (fichier
  local, gitignoré) est régénéré, et l'étape « Documentation » l'annonce en
  une ligne, jamais comme une erreur.

Aucun test ici ne touche au vrai `configs/`, au vrai `BRIDGE_AGENT_DOC.md`
ni au vrai dépôt git (même discipline que test_supprimer_projet_587.py /
test_topic_ntfy_facultatif_667.py) : `committer_pousser_doc` est soit un
faux enregistreur d'appels, soit une fonction qui lève si invoquée — jamais
la fonction réelle (commit + push RÉELS, non tolérable depuis un test).

Exécution :  python3 -m pytest tests/test_copie_non_proprietaire_869.py
"""

import sys
import tempfile
from pathlib import Path
from unittest import mock

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import etat_cases_cochees as ecc  # noqa: E402
import etat_son_issue as esi  # noqa: E402
import etat_configs_legitimes as ecl  # noqa: E402
import identite  # noqa: E402
import nouveau_projet as np_cli  # noqa: E402
import regenerer_tableaux_projets as rtp  # noqa: E402
import supprimer_projet as sp_cli  # noqa: E402


def _conf(dossier: Path, nom: str, depot: str, rep) -> None:
    dossier.mkdir(parents=True, exist_ok=True)
    (dossier / f"{nom}.conf").write_text(
        f"NOM = {nom}\nDEPOT = {depot}\nREP_TRAVAIL = {rep}\n", encoding="utf-8")


def _preparer_projet(tmp_path: Path, nom: str):
    """configs/<nom>.conf + répertoire de travail avec un .git, comme un
    projet réellement créé — pour tester supprimer_projet() en conditions
    proches du réel, sans jamais toucher au vrai configs/."""
    configs = tmp_path / "configs"
    rep = tmp_path / "travail" / nom
    rep.mkdir(parents=True)
    (rep / ".git").mkdir()
    _conf(configs, nom, f"AlainDelree/{nom}", rep)
    return configs, rep


def _isoler_etats_json(monkeypatch, tmp_path: Path) -> None:
    """Redirige les 3 petits fichiers d'état JSON touchés par
    supprimer_projet() (cases cochées, choix de son, configs légitimes) vers
    `tmp_path` — aucun test de ce fichier ne doit toucher aux vrais
    logs/*.json du dépôt (même technique que test_supprimer_projet_587.py)."""
    monkeypatch.setattr(ecc, "CHEMIN_ETAT", tmp_path / "etat_cases_cochees.json")
    monkeypatch.setattr(ecc, "CHEMIN_VERROU", (tmp_path / "etat_cases_cochees.json").with_suffix(".lock"))
    monkeypatch.setattr(esi, "CHEMIN_ETAT", tmp_path / "son_issues.json")
    monkeypatch.setattr(esi, "CHEMIN_VERROU", (tmp_path / "son_issues.json").with_suffix(".lock"))
    monkeypatch.setattr(ecl, "CHEMIN_ETAT", tmp_path / "configs_legitimes.json")
    monkeypatch.setattr(ecl, "CHEMIN_VERROU", (tmp_path / "configs_legitimes.json").with_suffix(".lock"))


# ─── 1. identite.copie_non_proprietaire() ────────────────────────────────

def test_copie_non_proprietaire_absente_par_defaut():
    with tempfile.TemporaryDirectory() as tmp:
        chemin = Path(tmp) / "identite_locale.conf"  # n'existe pas
        with mock.patch.object(identite, "FICHIER_IDENTITE_LOCALE", chemin):
            assert identite.copie_non_proprietaire() is False


def test_copie_non_proprietaire_active_oui():
    with tempfile.TemporaryDirectory() as tmp:
        chemin = Path(tmp) / "identite_locale.conf"
        chemin.write_text("COPIE_NON_PROPRIETAIRE = oui\n", encoding="utf-8")
        with mock.patch.object(identite, "FICHIER_IDENTITE_LOCALE", chemin):
            assert identite.copie_non_proprietaire() is True


def test_copie_non_proprietaire_valeur_quelconque_reste_inactive():
    with tempfile.TemporaryDirectory() as tmp:
        chemin = Path(tmp) / "identite_locale.conf"
        chemin.write_text("COPIE_NON_PROPRIETAIRE = non\n", encoding="utf-8")
        with mock.patch.object(identite, "FICHIER_IDENTITE_LOCALE", chemin):
            assert identite.copie_non_proprietaire() is False


# ─── 2. regenerer_tableaux_projets.regenerer_local() ─────────────────────

def test_regenerer_local_cree_le_squelette_et_les_tableaux(tmp_path):
    configs = tmp_path / "configs"
    _conf(configs, "monprojet", "AlainDelree/MonProjet", "/home/x/MonProjet")
    cible = tmp_path / "PROJETS_LOCAUX.md"
    assert not cible.exists()

    res = rtp.regenerer_local(doc_path=cible, dossier_configs=configs)

    assert res["existe"] is True
    assert res["erreur"] is None
    assert res["n_projets"] == 1
    assert cible.exists()
    contenu = cible.read_text(encoding="utf-8")
    assert "monprojet" in contenu
    assert "AlainDelree/MonProjet" in contenu


def test_regenerer_local_defaut_distinct_du_doc_de_loutil():
    """FICHIER_PROJETS_LOCAUX (défaut de doc_path pour regenerer_local()) et
    DOC (défaut de regenerer()) sont deux chemins distincts — garantit que
    les appelants qui se contentent des paramètres par défaut (CLI
    interactif, regenerer_tableaux_projets.main()) n'écrivent jamais au même
    endroit selon la branche prise."""
    assert rtp.FICHIER_PROJETS_LOCAUX != rtp.DOC
    assert rtp.FICHIER_PROJETS_LOCAUX.name == "PROJETS_LOCAUX.md"
    assert rtp.regenerer_local.__defaults__[0] == rtp.FICHIER_PROJETS_LOCAUX


# ─── 3. nouveau_projet.mettre_a_jour_doc() ───────────────────────────────

def test_np_mettre_a_jour_doc_sans_reglage_appelle_regenerer(monkeypatch):
    appels_regen, appels_local = [], []
    monkeypatch.setattr(np_cli.identite, "copie_non_proprietaire", lambda: False)
    monkeypatch.setattr(np_cli.regenerer_tableaux_projets, "regenerer",
                        lambda *a, **k: (appels_regen.append(1),
                                         {"existe": True, "erreur": None, "modifie": True})[1])
    monkeypatch.setattr(np_cli.regenerer_tableaux_projets, "regenerer_local",
                        lambda *a, **k: (appels_local.append(1), {})[1])

    resultat = np_cli.mettre_a_jour_doc()

    assert appels_regen == [1]
    assert appels_local == []
    assert resultat["local"] is False
    assert resultat["fichier_local"] is None


def test_np_mettre_a_jour_doc_avec_reglage_appelle_regenerer_local(monkeypatch):
    appels_regen, appels_local = [], []
    monkeypatch.setattr(np_cli.identite, "copie_non_proprietaire", lambda: True)
    monkeypatch.setattr(np_cli.regenerer_tableaux_projets, "regenerer",
                        lambda *a, **k: (appels_regen.append(1), {})[1])
    monkeypatch.setattr(np_cli.regenerer_tableaux_projets, "regenerer_local",
                        lambda *a, **k: (appels_local.append(1),
                                         {"existe": True, "erreur": None, "modifie": True})[1])

    resultat = np_cli.mettre_a_jour_doc()

    assert appels_local == [1]
    assert appels_regen == []
    assert resultat["local"] is True
    assert resultat["fichier_local"] == str(rtp.FICHIER_PROJETS_LOCAUX)


# ─── 4. supprimer_projet.mettre_a_jour_doc() ─────────────────────────────

def test_sp_mettre_a_jour_doc_sans_reglage_appelle_regenerer(monkeypatch):
    appels_regen, appels_local = [], []
    monkeypatch.setattr(sp_cli.identite, "copie_non_proprietaire", lambda: False)
    monkeypatch.setattr(sp_cli.regenerer_tableaux_projets, "regenerer",
                        lambda *a, **k: (appels_regen.append(1),
                                         {"existe": True, "erreur": None, "modifie": True})[1])
    monkeypatch.setattr(sp_cli.regenerer_tableaux_projets, "regenerer_local",
                        lambda *a, **k: (appels_local.append(1), {})[1])

    resultat = sp_cli.mettre_a_jour_doc()

    assert appels_regen == [1]
    assert appels_local == []
    assert resultat["local"] is False
    assert resultat["fichier_local"] is None


def test_sp_mettre_a_jour_doc_avec_reglage_appelle_regenerer_local(monkeypatch):
    appels_regen, appels_local = [], []
    monkeypatch.setattr(sp_cli.identite, "copie_non_proprietaire", lambda: True)
    monkeypatch.setattr(sp_cli.regenerer_tableaux_projets, "regenerer",
                        lambda *a, **k: (appels_regen.append(1), {})[1])
    monkeypatch.setattr(sp_cli.regenerer_tableaux_projets, "regenerer_local",
                        lambda *a, **k: (appels_local.append(1),
                                         {"existe": True, "erreur": None, "modifie": True})[1])

    resultat = sp_cli.mettre_a_jour_doc()

    assert appels_local == [1]
    assert appels_regen == []
    assert resultat["local"] is True
    assert resultat["fichier_local"] == str(rtp.FICHIER_PROJETS_LOCAUX)


# ─── 5. nouveau_projet.creer_projet() — étapes + gating du commit/push ───

def _mocker_etapes_reseau_creation(monkeypatch, configs: Path) -> None:
    """Court-circuite les étapes réseau (gh/git) de creer_projet(), comme
    test_creer_projet_topic_vide_reste_vide (issue #667) — seule la branche
    Documentation/Commit nous intéresse ici."""
    monkeypatch.setattr(np_cli, "DOSSIER_CONFIGS", configs)
    monkeypatch.setattr(np_cli, "depot_existe", lambda depot: True)
    monkeypatch.setattr(np_cli, "creer_labels", lambda depot: [])
    monkeypatch.setattr(np_cli, "creer_fichiers_contexte",
                        lambda rep, avec_specs: {"crees": [], "existants": [], "rep_cree": False})
    monkeypatch.setattr(np_cli, "initialiser_git", lambda rep, depot: {
        "ok": True, "detail": "ignoré (test)", "deja_git": True, "push_ok": None,
        "contenu_preexistant": [], "commande_manuelle": None,
    })


def test_creer_projet_sans_reglage_committer_pousser_doc_appele(monkeypatch, tmp_path):
    """Comportement ACTUEL, inchangé : sans le réglage, la création d'un
    projet appelle bien committer_pousser_doc (commit + push automatique,
    issue #645) — confirme qu'on ne régresse pas l'installation d'Alain."""
    configs = tmp_path / "configs"
    configs.mkdir()
    _mocker_etapes_reseau_creation(monkeypatch, configs)
    monkeypatch.setattr(np_cli, "mettre_a_jour_doc", lambda: {
        "existe": True, "ok2": True, "ok7": True, "ok_date": True, "erreur": None,
        "local": False, "fichier_local": None,
    })
    appels_commit = []
    monkeypatch.setattr(np_cli.regenerer_tableaux_projets, "committer_pousser_doc",
                        lambda message, **k: (appels_commit.append(message),
                                              {"statut": "ok", "detail": "simulé",
                                               "commande_manuelle": None})[1])

    resultat = np_cli.creer_projet(
        nom="defaut869", depot="AlainDelree/Defaut869",
        rep=str(tmp_path / "rep"), perimetre=str(tmp_path / "rep"))

    assert resultat["succes"] is True
    assert appels_commit == ["Ajout du projet defaut869 (§2)"]
    assert "Commit doc Bridge_Agent" in [e["etape"] for e in resultat["etapes"]]


def test_creer_projet_avec_reglage_aucun_commit_aucun_push(monkeypatch, tmp_path):
    """Réglage actif : committer_pousser_doc ne doit JAMAIS être appelé (le
    stub lève si invoqué), et l'étape « Documentation » annonce clairement
    le fichier local — sans jamais parler d'échec ni de push."""
    configs = tmp_path / "configs"
    configs.mkdir()
    _mocker_etapes_reseau_creation(monkeypatch, configs)
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
        nom="actif869", depot="AlainDelree/Actif869",
        rep=str(tmp_path / "rep"), perimetre=str(tmp_path / "rep"))

    assert resultat["succes"] is True
    etapes_noms = [e["etape"] for e in resultat["etapes"]]
    assert "Commit doc Bridge_Agent" not in etapes_noms
    etape_doc = next(e for e in resultat["etapes"] if e["etape"] == "Documentation")
    assert etape_doc["ok"] is True
    assert "PROJETS_LOCAUX.md" in etape_doc["detail"]
    assert "COPIE_NON_PROPRIETAIRE" in etape_doc["detail"]
    assert "échec" not in etape_doc["detail"].lower()
    assert "push" not in etape_doc["detail"].lower()


# ─── 6. supprimer_projet.supprimer_projet() — étapes + gating ────────────

def test_supprimer_projet_sans_reglage_committer_pousser_doc_appele(monkeypatch, tmp_path):
    nom = "suppdefaut869"
    configs, rep = _preparer_projet(tmp_path, nom)
    monkeypatch.setattr(sp_cli, "DOSSIER_CONFIGS", configs)
    _isoler_etats_json(monkeypatch, tmp_path)
    monkeypatch.setattr(sp_cli, "mettre_a_jour_doc", lambda: {
        "existe": True, "ok": True, "modifie": True, "erreur": None,
        "local": False, "fichier_local": None,
    })
    appels_commit = []
    monkeypatch.setattr(sp_cli.regenerer_tableaux_projets, "committer_pousser_doc",
                        lambda message, **k: (appels_commit.append(message),
                                              {"statut": "ok", "detail": "simulé",
                                               "commande_manuelle": None})[1])

    resultat = sp_cli.supprimer_projet(nom, dry_run=False)

    assert resultat["succes"] is True
    assert appels_commit == [f"Retrait du projet {nom} (§2)"]
    assert not (configs / f"{nom}.conf").exists()
    assert not rep.exists()


def test_supprimer_projet_avec_reglage_aucun_commit_aucun_push(monkeypatch, tmp_path):
    nom = "suppactif869"
    configs, rep = _preparer_projet(tmp_path, nom)
    monkeypatch.setattr(sp_cli, "DOSSIER_CONFIGS", configs)
    _isoler_etats_json(monkeypatch, tmp_path)
    fichier_local = tmp_path / "PROJETS_LOCAUX.md"
    monkeypatch.setattr(sp_cli, "mettre_a_jour_doc", lambda: {
        "existe": True, "ok": True, "modifie": True, "erreur": None,
        "local": True, "fichier_local": str(fichier_local),
    })

    def _commit_interdit(*a, **k):
        raise AssertionError("committer_pousser_doc ne doit jamais être appelé "
                              "quand COPIE_NON_PROPRIETAIRE est actif")
    monkeypatch.setattr(sp_cli.regenerer_tableaux_projets, "committer_pousser_doc", _commit_interdit)

    resultat = sp_cli.supprimer_projet(nom, dry_run=False)

    assert resultat["succes"] is True
    etapes_noms = [e["etape"] for e in resultat["etapes"]]
    assert "Commit doc Bridge_Agent" not in etapes_noms
    etape_doc = next(e for e in resultat["etapes"] if e["etape"] == "Documentation")
    assert etape_doc["ok"] is True
    assert "PROJETS_LOCAUX.md" in etape_doc["detail"]
    assert "échec" not in etape_doc["detail"].lower()
    assert "push" not in etape_doc["detail"].lower()
    assert not (configs / f"{nom}.conf").exists()
    assert not rep.exists()


def test_supprimer_projet_dry_run_message_selon_reglage(monkeypatch, tmp_path):
    """L'aperçu à blanc (dry-run) doit lui aussi refléter le réglage, sans
    jamais toucher au disque dans les deux cas."""
    nom = "suppdry869"
    configs, rep = _preparer_projet(tmp_path, nom)
    monkeypatch.setattr(sp_cli, "DOSSIER_CONFIGS", configs)

    monkeypatch.setattr(sp_cli.identite, "copie_non_proprietaire", lambda: False)
    resultat_defaut = sp_cli.supprimer_projet(nom, dry_run=True)
    etape_doc_defaut = next(e for e in resultat_defaut["etapes"] if e["etape"] == "Documentation")
    assert "commités/poussés" in etape_doc_defaut["detail"]

    monkeypatch.setattr(sp_cli.identite, "copie_non_proprietaire", lambda: True)
    resultat_actif = sp_cli.supprimer_projet(nom, dry_run=True)
    etape_doc_actif = next(e for e in resultat_actif["etapes"] if e["etape"] == "Documentation")
    assert "PROJETS_LOCAUX.md" in etape_doc_actif["detail"]
    assert "COPIE_NON_PROPRIETAIRE" in etape_doc_actif["detail"]

    # dry-run : rien ne doit avoir été touché dans les deux cas.
    assert (configs / f"{nom}.conf").exists()
    assert rep.exists()


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
