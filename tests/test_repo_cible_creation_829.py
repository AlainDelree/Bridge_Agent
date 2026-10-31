#!/usr/bin/env python3
"""Test de non-régression — issue #829 : transmission de `REPO_CIBLE` à la
CRÉATION d'une issue (fichier déposé dans `issues_inbox/` ET formulaire web),
avec refus d'un projet à périmètre dynamique sans ce champ, au lieu de créer
une issue qui échouerait forcément à l'exécution (watcher.py).

Avant cette issue, `REPO_CIBLE` n'était reconnu/validé qu'au chemin `RELANCE`
(issue #567) — `construire_body` (web et inbox) ne le réinsérait jamais dans
le corps créé, et aucune des deux validations n'imposait sa présence pour un
projet `PERIMETRE_DYNAMIQUE=true`.

Couvre :
- `app.issues.formater_entete` : sortie INCHANGÉE sans le nouveau paramètre
  `repo_cible` ; ligne `| REPO_CIBLE | <chemin> |` ajoutée seulement s'il est
  fourni.
- Aller-retour : le corps produit par `formater_entete`/`construire_body`
  (web et inbox) est relu par `watcher.extraire_repo_cible` et rend le même
  chemin.
- `scripts/watcher_issues_inbox.py::valider` : accepté avec `REPO_CIBLE` pour
  un projet dynamique, rejeté sans lui, rejeté avec lui pour un projet non
  dynamique, rejeté si le chemin est invalide ; chaque bloc d'un lot (#3.13)
  traité séparément via `decouper_corps_en_blocs` + `valider`.
- `app.issues.envoyer()` (formulaire web) : mêmes quatre cas, via
  `flask.test_request_context` (aucun appel réseau réel, `gh` substitué).
- Chemin `RELANCE` (issue #567) non régressé : toujours son propre
  validateur (`valider_relance`), inchangé.

Aucun accès réseau ni GitHub réel : tous les dépôts de test sont des dossiers
temporaires (`tempfile`), tous les appels `gh`/`subprocess` substitués.

Exécution :  python3 tests/test_repo_cible_creation_829.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))
sys.path.insert(0, str(RACINE / "scripts"))

import flask  # noqa: E402

import watcher_issues_inbox as w  # noqa: E402
import app.issues as ai  # noqa: E402
import app.watchers as aw  # noqa: E402
import app.notifications_poller as anp  # noqa: E402
import app.fin_issue as afi  # noqa: E402
from watcher import extraire_repo_cible  # noqa: E402

APP_FLASK = flask.Flask(__name__)


class Patch:
    """Remplace `getattr(module, nom)` par `valeur` ; restaure à la sortie du
    `with` — même utilitaire minimal que tests/test_creation_issue_enrichie_634.py."""

    def __init__(self, module, nom, valeur):
        self.module, self.nom, self.valeur = module, nom, valeur

    def __enter__(self):
        self.original = getattr(self.module, self.nom)
        setattr(self.module, self.nom, self.valeur)
        return self.valeur

    def __exit__(self, *exc):
        setattr(self.module, self.nom, self.original)


def _cfg_projet(depot="AlainDelree/ProjetTest829", nom="projet_test_829",
                 rep_travail=None, perimetre_dynamique=False):
    return SimpleNamespace(depot=depot, nom=nom, timeout_claude=300, timeout_chef=1200,
                            max_essais=3,
                            rep_travail=rep_travail or Path(tempfile.gettempdir()),
                            perimetre_dynamique=perimetre_dynamique)


def _preparer_config_bidon(tmp_dir: Path, projet="projet_test_829", perimetre_dynamique=False):
    """Même mécanisme que tests/test_champ_relance_516.py::_preparer_config_bidon
    — fait pointer DOSSIER_SCRIPT/charger_config de watcher_issues_inbox.py
    vers un projet bidon, sans dépendre d'un vrai configs/<projet>.conf."""
    (tmp_dir / "configs").mkdir(parents=True, exist_ok=True)
    (tmp_dir / "configs" / f"{projet}.conf").write_text("DEPOT=AlainDelree/ProjetTest829\n")
    w.DOSSIER_SCRIPT = tmp_dir
    w.charger_config = lambda chemin: _cfg_projet(nom=projet, rep_travail=tmp_dir,
                                                     perimetre_dynamique=perimetre_dynamique)


# ─── formater_entete : nouveau paramètre repo_cible ────────────────────────

def scenario_1_formater_entete_sans_repo_cible_inchange():
    """Sans le paramètre, la sortie reste identique à l'existante (aucune
    ligne REPO_CIBLE) — comportement STRICTEMENT inchangé pour tout appelant
    qui ne le fournit pas."""
    avant = ai.formater_entete("écriture", "normale", 300, "bridge_agent")
    apres = ai.formater_entete("écriture", "normale", 300, "bridge_agent", repo_cible=None)
    assert avant == apres, (avant, apres)
    assert "REPO_CIBLE" not in avant, avant
    return {}


def scenario_2_formater_entete_avec_repo_cible_ajoute_la_ligne():
    """Fourni, repo_cible ajoute UNE ligne « | REPO_CIBLE | <chemin> | »,
    dans le tableau principal — le reste de l'en-tête inchangé."""
    chemin = "/tmp/depot_dynamique_test"
    corps = ai.formater_entete("écriture", "normale", 300, "diagnostique_programme",
                                repo_cible=chemin)
    assert f"| REPO_CIBLE | {chemin} |" in corps, corps
    assert "| PROJET   | diagnostique_programme |" in corps, corps
    sans = ai.formater_entete("écriture", "normale", 300, "diagnostique_programme")
    assert "REPO_CIBLE" not in sans, sans
    return {"corps": corps}


def scenario_3_formater_entete_vide_naoute_rien():
    """Chaîne vide — comme pour `modele` — est traitée comme absente (`if
    modele:`/`if repo_cible:` sont tous deux falsy sur une chaîne vide)."""
    corps = ai.formater_entete("lecture", "normale", 300, "bridge_agent", repo_cible="")
    assert "REPO_CIBLE" not in corps, corps
    return {}


# ─── Aller-retour avec watcher.extraire_repo_cible ──────────────────────────

def scenario_4_aller_retour_formater_puis_extraire():
    """Le corps produit par formater_entete() est relu par
    watcher.extraire_repo_cible() et rend EXACTEMENT le même chemin."""
    chemin = "/home/alain/projets/diagnostique_programme_cible"
    corps = ai.formater_entete("écriture", "normale", 900, "diagnostique_programme",
                                repo_cible=chemin)
    assert extraire_repo_cible(corps) == chemin, extraire_repo_cible(corps)
    return {}


def scenario_5_aller_retour_construire_body_web():
    """app.issues.construire_body() (chemin formulaire web) : repo_cible lu
    depuis `data`, réinséré, relu par extraire_repo_cible()."""
    chemin = "/home/alain/projets/diagnostique_programme_cible"
    data = {"projet": "diagnostique_programme", "mode": "ecriture", "priorite": "normale",
            "timeout": "900", "corps": "## Contexte\nTest.", "repo_cible": chemin}
    body = ai.construire_body(data)
    assert extraire_repo_cible(body) == chemin, body
    return {"body_extrait": extraire_repo_cible(body)}


def scenario_6_aller_retour_construire_body_inbox(tmp_path_factory):
    """scripts/watcher_issues_inbox.py::construire_body() (chemin fichier
    déposé) : repo_cible_brut extrait par extraire_champs() est réinséré,
    relu par extraire_repo_cible()."""
    tmp_dir = tmp_path_factory()
    cfg_projet = _cfg_projet(nom="diagnostique_programme", perimetre_dynamique=True)
    chemin = str(tmp_dir / "cible")
    champs = w.extraire_champs(
        "| PROJET     | diagnostique_programme |\n"
        "| MODE       | écriture |\n"
        f"| REPO_CIBLE | {chemin} |\n"
        "\n"
        "#Titre: Diagnostiquer le programme X\n"
        "\n"
        "## Contexte\nTest.\n"
    )
    body, _info_timeout = w.construire_body(champs, cfg_projet)
    assert extraire_repo_cible(body) == chemin, body
    return {}


# ─── scripts/watcher_issues_inbox.py::valider — validation à la création ───

def scenario_7_valider_accepte_avec_repo_cible_projet_dynamique(tmp_path_factory):
    """Projet PERIMETRE_DYNAMIQUE=true avec REPO_CIBLE valide (absolu,
    existant) : accepté."""
    tmp_dir = tmp_path_factory()
    _preparer_config_bidon(tmp_dir, perimetre_dynamique=True)
    (tmp_dir / "cible_valide").mkdir(exist_ok=True)

    champs = w.extraire_champs(
        "| PROJET     | projet_test_829 |\n"
        f"| REPO_CIBLE | {tmp_dir / 'cible_valide'} |\n"
        "\n"
        "#Titre: Une tâche sur le dépôt cible\n"
    )
    ok, detail, cfg_projet = w.valider(champs)
    assert ok, detail
    return {"detail": detail}


def scenario_8_valider_rejette_projet_dynamique_sans_repo_cible(tmp_path_factory):
    """Projet PERIMETRE_DYNAMIQUE=true SANS REPO_CIBLE : rejeté — sans ce
    champ, watcher.py abandonnerait de toute façon l'issue à l'exécution,
    sans aucun repli (watcher.py ~ligne 5684)."""
    tmp_dir = tmp_path_factory()
    _preparer_config_bidon(tmp_dir, perimetre_dynamique=True)

    champs = w.extraire_champs(
        "| PROJET | projet_test_829 |\n"
        "\n"
        "#Titre: Une tâche sans dépôt cible\n"
    )
    ok, detail, cfg_projet = w.valider(champs)
    assert not ok
    assert "REPO_CIBLE" in detail, detail
    assert "périmètre dynamique" in detail, detail
    return {"detail": detail}


def scenario_9_valider_rejette_repo_cible_projet_non_dynamique(tmp_path_factory):
    """REPO_CIBLE fourni pour un projet qui n'est PAS à périmètre
    dynamique : rejeté (au lieu d'être ignoré en silence)."""
    tmp_dir = tmp_path_factory()
    _preparer_config_bidon(tmp_dir, perimetre_dynamique=False)

    champs = w.extraire_champs(
        "| PROJET     | projet_test_829 |\n"
        f"| REPO_CIBLE | {tmp_dir} |\n"
        "\n"
        "#Titre: Une tâche avec un champ superflu\n"
    )
    ok, detail, cfg_projet = w.valider(champs)
    assert not ok
    assert "REPO_CIBLE fourni" in detail, detail
    assert "PERIMETRE_DYNAMIQUE" in detail, detail
    return {"detail": detail}


def scenario_10_valider_rejette_chemin_invalide(tmp_path_factory):
    """REPO_CIBLE relatif (refusé par valider_repo_cible) reste rejeté même
    pour un projet à périmètre dynamique."""
    tmp_dir = tmp_path_factory()
    _preparer_config_bidon(tmp_dir, perimetre_dynamique=True)

    champs = w.extraire_champs(
        "| PROJET     | projet_test_829 |\n"
        "| REPO_CIBLE | chemin/relatif |\n"
        "\n"
        "#Titre: Une tâche avec un chemin invalide\n"
    )
    ok, detail, cfg_projet = w.valider(champs)
    assert not ok
    assert "REPO_CIBLE invalide" in detail, detail
    return {"detail": detail}


def scenario_11_valider_lot_chaque_bloc_separement(tmp_path_factory):
    """Lot (§3.13) : chaque bloc #Titre: est validé avec SON PROPRE
    REPO_CIBLE — un bloc valide et un bloc invalide dans le même fichier
    donnent des verdicts indépendants."""
    tmp_dir = tmp_path_factory()
    _preparer_config_bidon(tmp_dir, perimetre_dynamique=True)
    (tmp_dir / "bloc_1_valide").mkdir(exist_ok=True)

    contenu = (
        "#Titre: Bloc 1 — chemin valide\n"
        "| PROJET     | projet_test_829 |\n"
        f"| REPO_CIBLE | {tmp_dir / 'bloc_1_valide'} |\n"
        "\n"
        "#Titre: Bloc 2 — champ absent\n"
        "| PROJET | projet_test_829 |\n"
    )
    blocs = w.decouper_corps_en_blocs(contenu)
    assert len(blocs) == 2, blocs

    champs_1 = w.extraire_champs(blocs[0])
    ok_1, detail_1, _ = w.valider(champs_1)
    assert ok_1, detail_1

    champs_2 = w.extraire_champs(blocs[1])
    ok_2, detail_2, _ = w.valider(champs_2)
    assert not ok_2
    assert "REPO_CIBLE" in detail_2, detail_2
    return {"detail_1": detail_1, "detail_2": detail_2}


# ─── app.issues.envoyer() — formulaire web, mêmes quatre cas ───────────────

def _envoyer_avec(data: dict, cfg):
    """Appelle ai.envoyer() dans un contexte Flask minimal, avec gh/réseau
    substitués — même mécanisme que
    tests/test_creation_issue_enrichie_634.py::test_envoyer_enrichit_creation_issue_sans_appel_gh_supplementaire,
    mais ici seul le résultat JSON de la validation importe (gh ne doit même
    pas être appelé dans les trois cas de rejet)."""
    appels_gh = []

    def faux_run(cmd, **kwargs):
        appels_gh.append(cmd)
        class FauxResultat:
            returncode, stdout, stderr = 0, "https://github.com/AlainDelree/ProjetTest829/issues/1\n", ""
        return FauxResultat()

    with Patch(ai, "projet_par_nom", lambda nom: cfg if nom == cfg.nom else None), \
         Patch(ai, "_issue_ouverte_meme_titre", lambda c, titre: None), \
         Patch(ai.subprocess, "run", faux_run), \
         Patch(ai, "maj_rate_limit", lambda origine: None), \
         Patch(aw, "redemarrer_si_eteint", lambda c: (False, None, "")), \
         Patch(anp, "ajouter_issue_surveillee", lambda depot, numero, labels: None), \
         Patch(afi, "emettre_creation_issue", lambda *a, **k: None):
        with APP_FLASK.test_request_context("/envoyer", method="POST", json=data):
            rep = ai.envoyer()
        return rep.get_json(), appels_gh


def scenario_12_envoyer_rejette_projet_dynamique_sans_repo_cible():
    """Formulaire web : projet PERIMETRE_DYNAMIQUE=true, champ repo_cible
    vide → rejet SANS appel gh (rien n'est créé)."""
    cfg = _cfg_projet(nom="projet_test_829_web", perimetre_dynamique=True)
    json_rep, appels_gh = _envoyer_avec(
        {"projet": cfg.nom, "titre": "Tâche sans dépôt cible", "mode": "ecriture",
         "priorite": "normale", "timeout": "300", "corps": "", "repo_cible": ""},
        cfg,
    )
    assert json_rep["succes"] is False, json_rep
    assert "obligatoire" in json_rep["erreur"], json_rep["erreur"]
    assert appels_gh == [], appels_gh
    return {"erreur": json_rep["erreur"]}


def scenario_13_envoyer_rejette_repo_cible_projet_non_dynamique():
    """Formulaire web : repo_cible fourni pour un projet SANS
    PERIMETRE_DYNAMIQUE=true → rejet SANS appel gh."""
    cfg = _cfg_projet(nom="projet_test_829_web2", perimetre_dynamique=False)
    json_rep, appels_gh = _envoyer_avec(
        {"projet": cfg.nom, "titre": "Tâche avec champ superflu", "mode": "lecture",
         "priorite": "normale", "timeout": "300", "corps": "", "repo_cible": "/tmp/quelconque"},
        cfg,
    )
    assert json_rep["succes"] is False, json_rep
    assert "PERIMETRE_DYNAMIQUE" in json_rep["erreur"], json_rep["erreur"]
    assert appels_gh == [], appels_gh
    return {"erreur": json_rep["erreur"]}


def scenario_14_envoyer_rejette_chemin_invalide():
    """Formulaire web : projet dynamique, repo_cible relatif (invalide) →
    rejet avec la raison, SANS appel gh."""
    cfg = _cfg_projet(nom="projet_test_829_web3", perimetre_dynamique=True)
    json_rep, appels_gh = _envoyer_avec(
        {"projet": cfg.nom, "titre": "Tâche avec chemin invalide", "mode": "ecriture",
         "priorite": "normale", "timeout": "300", "corps": "", "repo_cible": "chemin/relatif"},
        cfg,
    )
    assert json_rep["succes"] is False, json_rep
    assert "invalide" in json_rep["erreur"], json_rep["erreur"]
    assert appels_gh == [], appels_gh
    return {"erreur": json_rep["erreur"]}


def scenario_15_envoyer_accepte_projet_dynamique_avec_repo_cible_valide(tmp_path_factory):
    """Formulaire web : projet dynamique, repo_cible valide (absolu,
    existant) → création acceptée (un seul appel gh)."""
    tmp_dir = tmp_path_factory()
    cible = tmp_dir / "depot_valide"
    cible.mkdir(exist_ok=True)
    cfg = _cfg_projet(nom="projet_test_829_web4", perimetre_dynamique=True)
    json_rep, appels_gh = _envoyer_avec(
        {"projet": cfg.nom, "titre": "Tâche avec dépôt cible valide", "mode": "ecriture",
         "priorite": "normale", "timeout": "300", "corps": "", "repo_cible": str(cible)},
        cfg,
    )
    assert json_rep["succes"] is True, json_rep
    assert len(appels_gh) == 1, appels_gh
    return {}


# ─── Compatibilité : chemin RELANCE non régressé (issue #567) ─────────────

def scenario_16_relance_non_regresse(tmp_path_factory):
    """valider_relance (chemin RELANCE, #567) garde son propre
    comportement : REPO_CIBLE y reste seulement CORRIGIBLE, jamais rendu
    obligatoire par la modification de valider() — une issue RELANCE sans
    REPO_CIBLE (projet dynamique ou pas) reste acceptée."""
    tmp_dir = tmp_path_factory()
    _preparer_config_bidon(tmp_dir, perimetre_dynamique=True)

    champs = w.extraire_champs("| PROJET | projet_test_829 |\n| RELANCE | #1 |\n")
    ok, detail, cfg_projet, numero = w.valider_relance(champs)
    assert ok, detail
    assert numero == 1
    return {"detail": detail}


def main() -> int:
    tmp = tempfile.TemporaryDirectory()

    def _tmp_path_factory():
        return Path(tmp.name)

    tests = [
        ("formater_entete : sortie inchangée sans repo_cible", scenario_1_formater_entete_sans_repo_cible_inchange),
        ("formater_entete : avec repo_cible, une ligne ajoutée", scenario_2_formater_entete_avec_repo_cible_ajoute_la_ligne),
        ("formater_entete : repo_cible vide → rien ajouté", scenario_3_formater_entete_vide_naoute_rien),
        ("aller-retour formater_entete → extraire_repo_cible", scenario_4_aller_retour_formater_puis_extraire),
        ("aller-retour construire_body (web) → extraire_repo_cible", scenario_5_aller_retour_construire_body_web),
        ("aller-retour construire_body (inbox) → extraire_repo_cible", lambda: scenario_6_aller_retour_construire_body_inbox(_tmp_path_factory)),
        ("valider() : accepté, projet dynamique + REPO_CIBLE valide", lambda: scenario_7_valider_accepte_avec_repo_cible_projet_dynamique(_tmp_path_factory)),
        ("valider() : rejeté, projet dynamique SANS REPO_CIBLE", lambda: scenario_8_valider_rejette_projet_dynamique_sans_repo_cible(_tmp_path_factory)),
        ("valider() : rejeté, REPO_CIBLE pour projet non dynamique", lambda: scenario_9_valider_rejette_repo_cible_projet_non_dynamique(_tmp_path_factory)),
        ("valider() : rejeté, chemin invalide", lambda: scenario_10_valider_rejette_chemin_invalide(_tmp_path_factory)),
        ("valider() : lot — chaque bloc traité séparément", lambda: scenario_11_valider_lot_chaque_bloc_separement(_tmp_path_factory)),
        ("envoyer() (web) : rejeté, projet dynamique SANS repo_cible", scenario_12_envoyer_rejette_projet_dynamique_sans_repo_cible),
        ("envoyer() (web) : rejeté, repo_cible pour projet non dynamique", scenario_13_envoyer_rejette_repo_cible_projet_non_dynamique),
        ("envoyer() (web) : rejeté, chemin invalide", scenario_14_envoyer_rejette_chemin_invalide),
        ("envoyer() (web) : accepté, projet dynamique + chemin valide", lambda: scenario_15_envoyer_accepte_projet_dynamique_avec_repo_cible_valide(_tmp_path_factory)),
        ("valider_relance() : non régressé, REPO_CIBLE reste optionnel", lambda: scenario_16_relance_non_regresse(_tmp_path_factory)),
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

    tmp.cleanup()
    if echecs:
        print(f"\n❌ {echecs} scénario(s) en échec.")
        return 1
    print("\n✅ Tous les scénarios passent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
