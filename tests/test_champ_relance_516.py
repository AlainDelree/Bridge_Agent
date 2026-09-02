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


def _cfg_projet(depot="AlainDelree/Bridge_Agent", nom="bridge_agent"):
    return SimpleNamespace(depot=depot, nom=nom, timeout_claude=300, timeout_chef=1200)


def _preparer_config_bidon(tmp_dir: Path, projet="bridge_agent"):
    """Fait pointer DOSSIER_SCRIPT/charger_config vers un projet bidon —
    évite toute dépendance à un vrai configs/<projet>.conf (gitignoré,
    absent de ce worktree)."""
    (tmp_dir / "configs").mkdir(parents=True, exist_ok=True)
    (tmp_dir / "configs" / f"{projet}.conf").write_text("DEPOT=AlainDelree/Bridge_Agent\n")
    w.DOSSIER_SCRIPT = tmp_dir
    w.charger_config = lambda chemin: _cfg_projet()


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
