#!/usr/bin/env python3
"""Test de non-régression — issue #516 : champ d'en-tête `| RELANCE | #N |`
dans `issues_inbox/`, pour corriger/relancer une issue `needs-human` sans
repasser par une édition manuelle sur GitHub.

Couvre : extraction du champ (`extraire_champs`), parsing du numéro
(`_numero_relance`), fusion des champs corrigibles dans le corps GitHub
existant (`_fusionner_entete`/`_maj_ligne_entete` — jamais d'insertion d'une
ligne absente), et le chemin complet `_traiter_relance` (anti-doublon
court-circuité, validation dépôt/état, réutilisation de
`app.interruption.relancer_issue`, coeur du bouton « 🔄 Relancer » #460).
Tous les appels `gh` sont substitués (aucun accès réseau).

Exécution :  python3 tests/test_champ_relance_516.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))
sys.path.insert(0, str(RACINE / "scripts"))

import watcher_issues_inbox as w  # noqa: E402


def _cfg_projet(depot="AlainDelree/Bridge_Agent", nom="bridge_agent", rep_travail=None, perimetre_dynamique=False):
    return SimpleNamespace(depot=depot, nom=nom, timeout_claude=300, timeout_chef=1200,
                            rep_travail=rep_travail or Path(tempfile.gettempdir()),
                            perimetre_dynamique=perimetre_dynamique)


def _preparer_config_bidon(tmp_dir: Path, projet="bridge_agent", perimetre_dynamique=False):
    """Fait pointer DOSSIER_SCRIPT/charger_config vers un projet bidon —
    évite toute dépendance à un vrai configs/<projet>.conf (gitignoré,
    absent de ce worktree). `rep_travail` du projet bidon pointe sur
    `tmp_dir` (issue #567) : nécessaire à `valider_sous_dossier`, appelée par
    `valider_relance` pour la correction SOUS_DOSSIER."""
    (tmp_dir / "configs").mkdir(parents=True, exist_ok=True)
    (tmp_dir / "configs" / f"{projet}.conf").write_text("DEPOT=AlainDelree/Bridge_Agent\n")
    w.DOSSIER_SCRIPT = tmp_dir
    w.charger_config = lambda chemin: _cfg_projet(rep_travail=tmp_dir, perimetre_dynamique=perimetre_dynamique)


def scenario_1_extraction_champ_relance():
    """Le champ RELANCE est reconnu comme les autres champs d'en-tête et
    retiré du corps restant."""
    contenu = (
        "| PROJET  | bridge_agent |\n"
        "| RELANCE | #77 |\n"
        "| TIMEOUT | 1800s |\n"
        "\n"
        "Le TIMEOUT était trop court, la tâche a échoué par dépassement.\n"
    )
    champs = w.extraire_champs(contenu)
    assert champs["relance_brut"] == "#77", champs["relance_brut"]
    assert champs["timeout_brut"] == "1800s", champs["timeout_brut"]
    assert "RELANCE" not in champs["corps"], champs["corps"]
    return {"relance_brut": champs["relance_brut"]}


def scenario_2_numero_relance_formats():
    """_numero_relance tolère « #N », « N », les espaces ; rejette le reste."""
    assert w._numero_relance("#42") == 42
    assert w._numero_relance("42") == 42
    assert w._numero_relance("  # 7 ") == 7  # espaces autour du # et du nombre tolérés
    assert w._numero_relance("#7") == 7
    assert w._numero_relance("abc") is None
    assert w._numero_relance(None) is None
    assert w._numero_relance("") is None
    return {}


def scenario_3_fusion_entete_corrige_champ_existant():
    """TIMEOUT/MODELE déjà présents dans le corps GitHub existant sont
    corrigés ; un champ absent (MODELE ici) n'est jamais inséré."""
    corps_existant = (
        "## En-tête\n\n"
        "| Champ    | Valeur |\n"
        "|----------|--------|\n"
        "| SOURCE   | CC |\n"
        "| TIMEOUT  | 300s |\n"
        "| PROJET   | bridge_agent |\n\n"
        "## Contexte\nTexte.\n"
    )
    champs = {"timeout_brut": "1800s", "modele": "claude-opus-4-8", "corps": ""}
    nouveau, modifies = w._fusionner_entete(corps_existant, champs)
    assert "| TIMEOUT  | 1800s |" in nouveau, nouveau
    assert "300s" not in nouveau, nouveau
    assert "MODELE" not in nouveau, "MODELE absent du corps cible ne doit jamais être inséré"
    assert modifies == ["TIMEOUT → 1800s"], modifies
    return {"modifies": modifies}


def scenario_4_fusion_entete_rien_a_corriger():
    """Aucun champ TIMEOUT/MODELE fourni → corps inchangé, liste vide."""
    corps_existant = "| TIMEOUT | 300s |\n"
    nouveau, modifies = w._fusionner_entete(corps_existant, {"timeout_brut": None, "modele": "", "corps": ""})
    assert nouveau == corps_existant
    assert modifies == []
    return {}


def scenario_5_traiter_relance_chemin_complet_succes(tmp_path_factory):
    """Chemin complet : issue ouverte du bon dépôt, corps mis à jour, puis
    relancer_issue() (réutilisée telle quelle, pas dupliquée) retire
    needs-human + poste le commentaire de trace."""
    tmp_dir = tmp_path_factory()
    _preparer_config_bidon(tmp_dir)

    appels = {}

    def _fausse_recuperation(depot, numero):
        appels["depot_view"] = depot
        appels["numero_view"] = numero
        return True, "", {
            "number": numero, "state": "OPEN", "title": "TIMEOUT trop court",
            "body": "| TIMEOUT | 300s |\n| PROJET | bridge_agent |\n",
        }

    def _faux_edit_corps(depot, numero, corps):
        appels["corps_envoye"] = corps
        return True, ""

    def _faux_relancer(depot, numero, commentaire=""):
        appels["commentaire"] = commentaire
        appels["depot_relance"] = depot
        appels["numero_relance"] = numero
        return "ok", [{"etape": "retrait_label_needs_human", "statut": "succes", "message": ""},
                        {"etape": "commentaire", "statut": "succes", "message": ""}]

    w._recuperer_issue = _fausse_recuperation
    w._modifier_corps_gh = _faux_edit_corps
    w.relancer_issue = _faux_relancer

    contenu = (
        "| PROJET  | bridge_agent |\n"
        "| RELANCE | #77 |\n"
        "| TIMEOUT | 1800s |\n"
        "\n"
        "Le précédent essai a échoué par dépassement de délai.\n"
    )
    champs = w.extraire_champs(contenu)
    succes, titre, projet, texte, resultat_gh = w._traiter_relance(w.ConfigInbox(), champs)

    assert succes, texte
    assert titre == "TIMEOUT trop court", titre
    assert projet == "bridge_agent", projet
    assert resultat_gh == ""
    assert "#77" in texte, texte
    assert appels["depot_view"] == "AlainDelree/Bridge_Agent"
    assert appels["numero_view"] == 77
    assert "| TIMEOUT | 1800s |" in appels["corps_envoye"], appels["corps_envoye"]
    assert "TIMEOUT → 1800s" in appels["commentaire"], appels["commentaire"]
    assert "échoué par dépassement" in appels["commentaire"], appels["commentaire"]
    assert appels["numero_relance"] == 77
    return {"texte": texte}


def scenario_6_traiter_relance_issue_fermee_rejetee():
    """Une issue fermée est rejetée avec un motif clair — pas de modification
    tentée."""
    def _fausse_recuperation(depot, numero):
        return True, "", {"number": numero, "state": "CLOSED", "title": "Ancienne tâche", "body": ""}

    w._recuperer_issue = _fausse_recuperation

    contenu = "| PROJET | bridge_agent |\n| RELANCE | #99 |\n"
    champs = w.extraire_champs(contenu)
    succes, titre, projet, texte, _ = w._traiter_relance(w.ConfigInbox(), champs)
    assert not succes
    assert "n'est pas ouverte" in texte, texte
    return {"texte": texte}


def scenario_7_traiter_relance_numero_invalide_rejete():
    """RELANCE avec une valeur non numérique est rejeté avant tout appel gh."""
    contenu = "| PROJET | bridge_agent |\n| RELANCE | pas-un-numero |\n"
    champs = w.extraire_champs(contenu)
    succes, titre, projet, texte, _ = w._traiter_relance(w.ConfigInbox(), champs)
    assert not succes
    assert "RELANCE invalide" in texte, texte
    return {"texte": texte}


# ─── Issue #567 : extension de RELANCE à SOUS_DOSSIER et REPO_CIBLE ─────────

def scenario_8_extraction_champs_sous_dossier_repo_cible():
    """SOUS_DOSSIER et REPO_CIBLE sont reconnus comme TIMEOUT/MODELE et
    retirés du corps restant."""
    contenu = (
        "| PROJET       | bridge_agent |\n"
        "| RELANCE      | #77 |\n"
        "| SOUS_DOSSIER | CCW/gestionmail |\n"
        "| REPO_CIBLE   | /home/alain/Autre_Projet |\n"
        "\n"
        "Le chemin visé était incorrect, d'où la correction.\n"
    )
    champs = w.extraire_champs(contenu)
    assert champs["sous_dossier_brut"] == "CCW/gestionmail", champs["sous_dossier_brut"]
    assert champs["repo_cible_brut"] == "/home/alain/Autre_Projet", champs["repo_cible_brut"]
    assert "SOUS_DOSSIER" not in champs["corps"], champs["corps"]
    assert "REPO_CIBLE" not in champs["corps"], champs["corps"]
    return {"sous_dossier_brut": champs["sous_dossier_brut"], "repo_cible_brut": champs["repo_cible_brut"]}


def scenario_9_fusion_entete_corrige_sous_dossier_et_repo_cible():
    """SOUS_DOSSIER/REPO_CIBLE déjà présents dans le corps GitHub existant
    sont corrigés ; un champ absent n'est jamais inséré."""
    corps_existant = (
        "## En-tête\n\n"
        "| Champ        | Valeur |\n"
        "|--------------|--------|\n"
        "| SOURCE       | CC |\n"
        "| SOUS_DOSSIER | ancien/chemin |\n"
        "| PROJET       | bridge_agent |\n\n"
        "## Contexte\nTexte.\n"
    )
    champs = {"timeout_brut": None, "modele": "", "corps": "",
              "sous_dossier_brut": "nouveau/chemin", "repo_cible_brut": "/repo/absent/du/corps"}
    nouveau, modifies = w._fusionner_entete(corps_existant, champs)
    assert "| SOUS_DOSSIER | nouveau/chemin |" in nouveau, nouveau
    assert "ancien/chemin" not in nouveau, nouveau
    assert "REPO_CIBLE" not in nouveau, "REPO_CIBLE absent du corps cible ne doit jamais être inséré"
    assert modifies == ["SOUS_DOSSIER → nouveau/chemin"], modifies
    return {"modifies": modifies}


def scenario_10_valider_relance_sous_dossier_valide(tmp_path_factory):
    """SOUS_DOSSIER valide (relatif, existe sous REP_TRAVAIL du projet) est
    accepté par valider_relance — réutilise valider_sous_dossier telle
    quelle."""
    tmp_dir = tmp_path_factory()
    _preparer_config_bidon(tmp_dir)
    (tmp_dir / "souscode").mkdir(exist_ok=True)

    champs = w.extraire_champs(
        "| PROJET       | bridge_agent |\n"
        "| RELANCE      | #77 |\n"
        "| SOUS_DOSSIER | souscode |\n"
    )
    ok, detail, cfg_projet, numero = w.valider_relance(champs)
    assert ok, detail
    assert numero == 77
    return {"detail": detail}


def scenario_11_valider_relance_sous_dossier_invalide_rejete(tmp_path_factory):
    """SOUS_DOSSIER pointant vers un dossier inexistant est rejeté — même
    validateur, même exigence qu'à la création."""
    tmp_dir = tmp_path_factory()
    _preparer_config_bidon(tmp_dir)

    champs = w.extraire_champs(
        "| PROJET       | bridge_agent |\n"
        "| RELANCE      | #77 |\n"
        "| SOUS_DOSSIER | dossier/qui/nexiste/pas |\n"
    )
    ok, detail, cfg_projet, numero = w.valider_relance(champs)
    assert not ok
    assert "SOUS_DOSSIER invalide" in detail, detail
    return {"detail": detail}


def scenario_12_valider_relance_repo_cible_necessite_perimetre_dynamique(tmp_path_factory):
    """REPO_CIBLE fourni via RELANCE mais projet SANS PERIMETRE_DYNAMIQUE=true
    est rejeté — le garde-fou de #125 reste vérifié à la relance, pas
    seulement à la création (issue #567)."""
    tmp_dir = tmp_path_factory()
    _preparer_config_bidon(tmp_dir, perimetre_dynamique=False)

    champs = w.extraire_champs(
        "| PROJET     | bridge_agent |\n"
        "| RELANCE    | #77 |\n"
        f"| REPO_CIBLE | {tmp_dir} |\n"
    )
    ok, detail, cfg_projet, numero = w.valider_relance(champs)
    assert not ok
    assert "PERIMETRE_DYNAMIQUE" in detail, detail
    return {"detail": detail}


def scenario_13_valider_relance_repo_cible_valide_avec_perimetre_dynamique(tmp_path_factory):
    """REPO_CIBLE valide (absolu, existant, PERIMETRE_DYNAMIQUE=true) est
    accepté par valider_relance — réutilise valider_repo_cible telle
    quelle."""
    tmp_dir = tmp_path_factory()
    _preparer_config_bidon(tmp_dir, perimetre_dynamique=True)

    champs = w.extraire_champs(
        "| PROJET     | bridge_agent |\n"
        "| RELANCE    | #77 |\n"
        f"| REPO_CIBLE | {tmp_dir} |\n"
    )
    ok, detail, cfg_projet, numero = w.valider_relance(champs)
    assert ok, detail
    return {"detail": detail}


def scenario_14_valider_relance_repo_cible_invalide_rejete(tmp_path_factory):
    """REPO_CIBLE relatif (invalide selon valider_repo_cible) reste rejeté
    même avec PERIMETRE_DYNAMIQUE=true — le garde-fou n'accepte pas
    n'importe quel chemin pour autant."""
    tmp_dir = tmp_path_factory()
    _preparer_config_bidon(tmp_dir, perimetre_dynamique=True)

    champs = w.extraire_champs(
        "| PROJET     | bridge_agent |\n"
        "| RELANCE    | #77 |\n"
        "| REPO_CIBLE | chemin/relatif |\n"
    )
    ok, detail, cfg_projet, numero = w.valider_relance(champs)
    assert not ok
    assert "REPO_CIBLE invalide" in detail, detail
    return {"detail": detail}


def scenario_15_traiter_relance_sous_dossier_chemin_complet_succes(tmp_path_factory):
    """Chemin complet _traiter_relance avec correction SOUS_DOSSIER : corps
    mis à jour, retrait needs-human + commentaire de trace inchangés."""
    tmp_dir = tmp_path_factory()
    _preparer_config_bidon(tmp_dir)
    (tmp_dir / "bonchemin").mkdir(exist_ok=True)

    appels = {}

    def _fausse_recuperation(depot, numero):
        return True, "", {
            "number": numero, "state": "OPEN", "title": "SOUS_DOSSIER incorrect",
            "body": "| SOUS_DOSSIER | mauvais/chemin |\n| PROJET | bridge_agent |\n",
        }

    def _faux_edit_corps(depot, numero, corps):
        appels["corps_envoye"] = corps
        return True, ""

    def _faux_relancer(depot, numero, commentaire=""):
        appels["commentaire"] = commentaire
        return "ok", [{"etape": "retrait_label_needs_human", "statut": "succes", "message": ""},
                        {"etape": "commentaire", "statut": "succes", "message": ""}]

    w._recuperer_issue = _fausse_recuperation
    w._modifier_corps_gh = _faux_edit_corps
    w.relancer_issue = _faux_relancer

    champs = w.extraire_champs(
        "| PROJET       | bridge_agent |\n"
        "| RELANCE      | #77 |\n"
        "| SOUS_DOSSIER | bonchemin |\n"
        "\n"
        "Le SOUS_DOSSIER pointait au mauvais endroit.\n"
    )
    succes, titre, projet, texte, resultat_gh = w._traiter_relance(w.ConfigInbox(), champs)

    assert succes, texte
    assert "| SOUS_DOSSIER | bonchemin |" in appels["corps_envoye"], appels["corps_envoye"]
    assert "SOUS_DOSSIER → bonchemin" in appels["commentaire"], appels["commentaire"]
    return {"texte": texte}


def main():
    tmp = tempfile.TemporaryDirectory()

    def _tmp_path_factory():
        return Path(tmp.name)

    tests = [
        ("champ RELANCE extrait et retiré du corps", scenario_1_extraction_champ_relance),
        ("_numero_relance tolère #N/N, rejette le reste", scenario_2_numero_relance_formats),
        ("_fusionner_entete corrige un champ existant, n'en insère jamais", scenario_3_fusion_entete_corrige_champ_existant),
        ("_fusionner_entete : rien à corriger → corps inchangé", scenario_4_fusion_entete_rien_a_corriger),
        ("_traiter_relance : chemin complet, succès", lambda: scenario_5_traiter_relance_chemin_complet_succes(_tmp_path_factory)),
        ("_traiter_relance : issue fermée → rejet", scenario_6_traiter_relance_issue_fermee_rejetee),
        ("_traiter_relance : RELANCE non numérique → rejet", scenario_7_traiter_relance_numero_invalide_rejete),
        ("champs SOUS_DOSSIER/REPO_CIBLE extraits et retirés du corps (#567)", scenario_8_extraction_champs_sous_dossier_repo_cible),
        ("_fusionner_entete corrige SOUS_DOSSIER/REPO_CIBLE, n'en insère jamais (#567)", scenario_9_fusion_entete_corrige_sous_dossier_et_repo_cible),
        ("valider_relance : SOUS_DOSSIER valide accepté (#567)", lambda: scenario_10_valider_relance_sous_dossier_valide(_tmp_path_factory)),
        ("valider_relance : SOUS_DOSSIER invalide rejeté (#567)", lambda: scenario_11_valider_relance_sous_dossier_invalide_rejete(_tmp_path_factory)),
        ("valider_relance : REPO_CIBLE sans PERIMETRE_DYNAMIQUE rejeté (#567)", lambda: scenario_12_valider_relance_repo_cible_necessite_perimetre_dynamique(_tmp_path_factory)),
        ("valider_relance : REPO_CIBLE valide accepté avec PERIMETRE_DYNAMIQUE (#567)", lambda: scenario_13_valider_relance_repo_cible_valide_avec_perimetre_dynamique(_tmp_path_factory)),
        ("valider_relance : REPO_CIBLE invalide rejeté même avec PERIMETRE_DYNAMIQUE (#567)", lambda: scenario_14_valider_relance_repo_cible_invalide_rejete(_tmp_path_factory)),
        ("_traiter_relance : chemin complet SOUS_DOSSIER, succès (#567)", lambda: scenario_15_traiter_relance_sous_dossier_chemin_complet_succes(_tmp_path_factory)),
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
