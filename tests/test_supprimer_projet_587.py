#!/usr/bin/env python3
"""Test de `supprimer_projet.py` / `app/supprimer_projet.py` — issue #587
(flux de suppression de projet, côté CCL/local, symétrique à la création).

Aucun test ici ne touche au vrai `configs/` ni au vrai `BRIDGE_AGENT_DOC.md` :
`supprimer_projet.DOSSIER_CONFIGS` est monkeypatché vers un répertoire jetable
pour chaque scénario, et `regenerer_tableaux_projets.regenerer` (l'étape
Documentation) est remplacé par un faux compteur d'appels plutôt que d'écrire
réellement dans le dépôt — cohérent avec l'absence de test existant sur
`nouveau_projet.creer_projet()`/`mettre_a_jour_doc()`, pour la même raison.

Couvre :
- `previsualiser_suppression` : projet introuvable, projet présent (avec
  dépôt git local) — aperçu correct, AUCUNE écriture disque ;
- `supprimer_projet(dry_run=True)` : décrit les 4 cibles (dont les cases
  cochées côté serveur, issue #629), ne touche à rien (fichier .conf et
  répertoire de travail intacts après l'appel) ;
- `supprimer_projet(dry_run=False)` : chemin de succès — répertoire de
  travail (contenu + `.git`) et `.conf` supprimés, régénération de la doc et
  nettoyage des cases cochées (issue #629) déclenchés, dans cet ordre ;
- Arrêt propre si la suppression du répertoire échoue : `.conf` conservé,
  régénération de la doc jamais appelée ;
- Nom de projet vide → erreur, aucun appel ;
- Routes Flask (`app/supprimer_projet.py`) : dry-run 404 si absent, refus si
  la confirmation ne correspond pas au nom, succès sinon.

Exécution :  python3 tests/test_supprimer_projet_587.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import sys
import tempfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import flask  # noqa: E402

import supprimer_projet as sp  # noqa: E402
import etat_cases_cochees as ecc  # noqa: E402
from app import supprimer_projet as route_sp  # noqa: E402


def _isoler_cases_cochees(tmp: Path):
    """Redirige etat_cases_cochees.CHEMIN_ETAT/CHEMIN_VERROU vers `tmp`, pour
    qu'aucun scénario de ce fichier ne touche au vrai
    logs/etat_cases_cochees.json du dépôt. Retourne (ancien_chemin,
    ancien_verrou) à restaurer par l'appelant."""
    ancien_chemin, ancien_verrou = ecc.CHEMIN_ETAT, ecc.CHEMIN_VERROU
    ecc.CHEMIN_ETAT = tmp / "etat_cases_cochees.json"
    ecc.CHEMIN_VERROU = ecc.CHEMIN_ETAT.with_suffix(".lock")
    return ancien_chemin, ancien_verrou

APP_FLASK = flask.Flask(__name__)


def _ecrire_conf(dossier_configs: Path, nom: str, rep: Path) -> None:
    dossier_configs.mkdir(parents=True, exist_ok=True)
    (dossier_configs / f"{nom}.conf").write_text(
        f"NOM = {nom}\nDEPOT = AlainDelree/{nom}\nREP_TRAVAIL = {rep}\n",
        encoding="utf-8")


class _CompteurRegen:
    """Remplace regenerer_tableaux_projets.regenerer : compte les appels sans
    jamais toucher au vrai BRIDGE_AGENT_DOC.md."""

    def __init__(self):
        self.appels = 0

    def __call__(self, *a, **k):
        self.appels += 1
        return {"existe": True, "erreur": None, "modifie": True}


class _FauxCommitDoc:
    """Remplace regenerer_tableaux_projets.committer_pousser_doc (issue #645) :
    enregistre les messages de commit reçus sans jamais toucher au vrai dépôt
    git — même raisonnement que _CompteurRegen ci-dessus pour `regenerer`.
    Statut "ok" (commité + poussé) par défaut ; configurable pour simuler un
    push en échec ou l'absence de changement réel."""

    def __init__(self, statut="ok"):
        self.statut = statut
        self.appels = []

    def __call__(self, message, **kwargs):
        self.appels.append(message)
        commande = None if self.statut in ("ok", "rien_a_faire") else "cd ~/Bridge_Agent\ngit push"
        return {"statut": self.statut,
                "detail": f"détail simulé ({self.statut})",
                "commande_manuelle": commande}


def test_previsualiser_projet_introuvable():
    with tempfile.TemporaryDirectory() as tmp:
        ancien = sp.DOSSIER_CONFIGS
        sp.DOSSIER_CONFIGS = Path(tmp) / "configs"
        try:
            apercu = sp.previsualiser_suppression("fantome")
        finally:
            sp.DOSSIER_CONFIGS = ancien
        assert apercu == {"existe": False, "nom": "fantome"}
    return {"existe": apercu["existe"]}


def test_previsualiser_projet_present():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        configs = tmp / "configs"
        rep = tmp / "travail" / "monprojet"
        rep.mkdir(parents=True)
        (rep / ".git").mkdir()
        (rep / "CONTEXTE.md").write_text("contexte", encoding="utf-8")
        _ecrire_conf(configs, "monprojet", rep)

        ancien = sp.DOSSIER_CONFIGS
        sp.DOSSIER_CONFIGS = configs
        try:
            apercu = sp.previsualiser_suppression("monprojet")
        finally:
            sp.DOSSIER_CONFIGS = ancien

        assert apercu["existe"] is True
        assert apercu["depot"] == "AlainDelree/monprojet"
        assert apercu["rep_existe"] is True
        assert apercu["git_local"] is True
        assert apercu["nb_fichiers"] >= 2, apercu
        # Aucune écriture : le .conf et le répertoire doivent être intacts.
        assert (configs / "monprojet.conf").exists()
        assert (rep / ".git").exists()
    return {"git_local": apercu["git_local"], "nb_fichiers": apercu["nb_fichiers"]}


def test_dry_run_ne_touche_a_rien():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        configs = tmp / "configs"
        rep = tmp / "travail" / "monprojet"
        rep.mkdir(parents=True)
        (rep / ".git").mkdir()
        _ecrire_conf(configs, "monprojet", rep)

        compteur = _CompteurRegen()
        faux_commit = _FauxCommitDoc()
        ancien_configs = sp.DOSSIER_CONFIGS
        ancien_regen = sp.regenerer_tableaux_projets.regenerer
        ancien_commit = sp.regenerer_tableaux_projets.committer_pousser_doc
        ancien_chemin, ancien_verrou = _isoler_cases_cochees(tmp)
        sp.DOSSIER_CONFIGS = configs
        sp.regenerer_tableaux_projets.regenerer = compteur
        sp.regenerer_tableaux_projets.committer_pousser_doc = faux_commit
        try:
            res = sp.supprimer_projet("monprojet", dry_run=True)
        finally:
            sp.DOSSIER_CONFIGS = ancien_configs
            sp.regenerer_tableaux_projets.regenerer = ancien_regen
            sp.regenerer_tableaux_projets.committer_pousser_doc = ancien_commit
            ecc.CHEMIN_ETAT, ecc.CHEMIN_VERROU = ancien_chemin, ancien_verrou

        assert res["succes"] is True
        assert res["dry_run"] is True
        assert len(res["etapes"]) == 4
        assert all(e["ok"] for e in res["etapes"])
        assert (configs / "monprojet.conf").exists(), "dry-run ne doit pas supprimer le .conf"
        assert (rep / ".git").exists(), "dry-run ne doit pas toucher au répertoire de travail"
        assert compteur.appels == 0, "dry-run ne doit jamais régénérer la doc"
        assert faux_commit.appels == [], "dry-run ne doit jamais committer la doc"
    return {"nb_etapes": len(res["etapes"])}


def test_suppression_reelle_succes():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        configs = tmp / "configs"
        rep = tmp / "travail" / "monprojet"
        rep.mkdir(parents=True)
        (rep / ".git").mkdir()
        (rep / "CONTEXTE.md").write_text("contexte", encoding="utf-8")
        _ecrire_conf(configs, "monprojet", rep)

        compteur = _CompteurRegen()
        faux_commit = _FauxCommitDoc()
        ancien_configs = sp.DOSSIER_CONFIGS
        ancien_regen = sp.regenerer_tableaux_projets.regenerer
        ancien_commit = sp.regenerer_tableaux_projets.committer_pousser_doc
        ancien_chemin, ancien_verrou = _isoler_cases_cochees(tmp)
        sp.DOSSIER_CONFIGS = configs
        sp.regenerer_tableaux_projets.regenerer = compteur
        sp.regenerer_tableaux_projets.committer_pousser_doc = faux_commit
        ecc.cocher_issue("monprojet", 12)
        try:
            res = sp.supprimer_projet("monprojet", dry_run=False)
        finally:
            sp.DOSSIER_CONFIGS = ancien_configs
            sp.regenerer_tableaux_projets.regenerer = ancien_regen
            sp.regenerer_tableaux_projets.committer_pousser_doc = ancien_commit
            ecc.CHEMIN_ETAT, ecc.CHEMIN_VERROU = ancien_chemin, ancien_verrou

        assert res["succes"] is True, res
        assert not rep.exists(), "répertoire de travail (+ dépôt git local) non supprimé"
        assert not (configs / "monprojet.conf").exists(), ".conf non supprimé"
        assert compteur.appels == 1, "la doc doit être régénérée exactement une fois"
        noms_etapes = [e["etape"] for e in res["etapes"]]
        assert noms_etapes == [
            "Répertoire de travail (contenu + dépôt git local)",
            "Fichier .conf",
            "Documentation",
            "Commit doc Bridge_Agent",
            "Cases cochées (état serveur, issue #629)",
        ], noms_etapes
        assert all(e["ok"] for e in res["etapes"]), res["etapes"]
        # Issue #645 : le commit/push automatique de la doc est bien déclenché
        # une seule fois, avec un message clair mentionnant le projet retiré.
        assert faux_commit.appels == ["Retrait du projet monprojet (§2)"], faux_commit.appels
        assert res["doc_commit_statut"] == "ok"
        assert res["doc_commit_commande_manuelle"] is None
    return {"succes": res["succes"], "appels_regen": compteur.appels,
            "doc_commit_statut": res["doc_commit_statut"]}


def test_echec_repertoire_arrete_tout():
    """Si la suppression du répertoire échoue, le .conf est conservé et la doc
    n'est jamais régénérée — pas de continuation aveugle."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        configs = tmp / "configs"
        rep = tmp / "travail" / "monprojet"
        rep.mkdir(parents=True)
        _ecrire_conf(configs, "monprojet", rep)

        def rmtree_qui_echoue(*a, **k):
            raise OSError("permission refusée (simulée)")

        compteur = _CompteurRegen()
        ancien_configs = sp.DOSSIER_CONFIGS
        ancien_regen = sp.regenerer_tableaux_projets.regenerer
        ancien_rmtree = sp.shutil.rmtree
        sp.DOSSIER_CONFIGS = configs
        sp.regenerer_tableaux_projets.regenerer = compteur
        sp.shutil.rmtree = rmtree_qui_echoue
        try:
            res = sp.supprimer_projet("monprojet", dry_run=False)
        finally:
            sp.DOSSIER_CONFIGS = ancien_configs
            sp.regenerer_tableaux_projets.regenerer = ancien_regen
            sp.shutil.rmtree = ancien_rmtree

        assert res["succes"] is False
        assert (configs / "monprojet.conf").exists(), \
            ".conf ne doit pas être supprimé si le répertoire a échoué"
        assert compteur.appels == 0, "la doc ne doit pas être régénérée après un échec"
        assert res["etapes"][0]["ok"] is False
        assert len(res["etapes"]) == 1, "arrêt immédiat, pas d'étapes suivantes"
    return {"succes": res["succes"]}


def test_nom_vide():
    res = sp.supprimer_projet("   ", dry_run=False)
    assert res["succes"] is False
    assert res["etapes"] == []
    return {"erreur": res["erreur"]}


def test_route_verifier_projet_absent():
    with tempfile.TemporaryDirectory() as tmp:
        ancien = sp.DOSSIER_CONFIGS
        sp.DOSSIER_CONFIGS = Path(tmp) / "configs"
        try:
            with APP_FLASK.test_request_context("/supprimer-projet/verifier/fantome"):
                rep = route_sp.verifier_supprimer_projet("fantome")
        finally:
            sp.DOSSIER_CONFIGS = ancien
        assert rep[1] == 404
        assert rep[0].get_json()["existe"] is False
    return {"status": rep[1]}


def test_route_executer_confirmation_incorrecte():
    with APP_FLASK.test_request_context(
            "/supprimer-projet", method="POST",
            json={"nom": "monprojet", "confirmation": "autrechose"}):
        rep = route_sp.executer_supprimer_projet()
    assert rep[1] == 400
    assert rep[0].get_json()["succes"] is False
    return {"status": rep[1]}


def test_route_executer_succes():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        configs = tmp / "configs"
        rep_travail = tmp / "travail" / "monprojet"
        rep_travail.mkdir(parents=True)
        _ecrire_conf(configs, "monprojet", rep_travail)

        compteur = _CompteurRegen()
        faux_commit = _FauxCommitDoc()
        ancien_configs = sp.DOSSIER_CONFIGS
        ancien_regen = sp.regenerer_tableaux_projets.regenerer
        ancien_commit = sp.regenerer_tableaux_projets.committer_pousser_doc
        ancien_chemin, ancien_verrou = _isoler_cases_cochees(tmp)
        sp.DOSSIER_CONFIGS = configs
        sp.regenerer_tableaux_projets.regenerer = compteur
        sp.regenerer_tableaux_projets.committer_pousser_doc = faux_commit
        try:
            with APP_FLASK.test_request_context(
                    "/supprimer-projet", method="POST",
                    json={"nom": "MonProjet", "confirmation": "monprojet"}):
                rep = route_sp.executer_supprimer_projet()
        finally:
            sp.DOSSIER_CONFIGS = ancien_configs
            sp.regenerer_tableaux_projets.regenerer = ancien_regen
            sp.regenerer_tableaux_projets.committer_pousser_doc = ancien_commit
            ecc.CHEMIN_ETAT, ecc.CHEMIN_VERROU = ancien_chemin, ancien_verrou

        assert rep[1] == 200, rep[0].get_json()
        corps = rep[0].get_json()
        assert corps["succes"] is True
        assert not (configs / "monprojet.conf").exists()
    return {"status": rep[1]}


def main() -> int:
    tests = [
        ("previsualiser_suppression — projet introuvable", test_previsualiser_projet_introuvable),
        ("previsualiser_suppression — projet présent, aucune écriture", test_previsualiser_projet_present),
        ("supprimer_projet(dry_run=True) — ne touche à rien", test_dry_run_ne_touche_a_rien),
        ("supprimer_projet(dry_run=False) — succès, ordre des étapes", test_suppression_reelle_succes),
        ("échec suppression répertoire — arrêt propre, .conf conservé", test_echec_repertoire_arrete_tout),
        ("nom vide — erreur, aucune étape", test_nom_vide),
        ("route GET verifier — 404 si projet absent", test_route_verifier_projet_absent),
        ("route POST — confirmation ne correspondant pas au nom → 400", test_route_executer_confirmation_incorrecte),
        ("route POST — succès (nom normalisé, confirmation correcte)", test_route_executer_succes),
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
