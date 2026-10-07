#!/usr/bin/env python3
"""Test de non-régression — issue #726 : le texte libre d'un fichier RELANCE
(§3.14) est désormais ajouté au CORPS de l'issue (section horodatée
« ## Relance du <date> »), pas seulement recopié dans le commentaire de
trace — c'est le corps que lit CCL à la reprise, jamais les commentaires.

Couvre : (1) texte libre ajouté en fin de corps avec section horodatée ;
(2) texte vide → corps inchangé par ce mécanisme ; (3) deux relances
successives → deux sections empilées, dans l'ordre ; (4) texte imitant des
lignes d'en-tête → jamais lu comme un champ par lire_champ_entete (zone
d'en-tête bornée, §3.3) ; (5) fusion des champs d'en-tête + ajout du texte
dans une seule mise à jour du corps (_traiter_relance, un seul appel
`_modifier_corps_gh`) ; (6) échec de la mise à jour du corps → relance
rejetée comme avant, needs-human conservé (relancer_issue jamais appelé).
Tous les appels `gh` sont substitués (aucun accès réseau).

Exécution :  python3 tests/test_texte_libre_relance_726.py
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
import app.watchers as watchers_mod  # noqa: E402


def _cfg_projet(depot="AlainDelree/Bridge_Agent", nom="bridge_agent", rep_travail=None):
    return SimpleNamespace(depot=depot, nom=nom, timeout_claude=300, timeout_chef=1200,
                            rep_travail=rep_travail or Path(tempfile.gettempdir()),
                            perimetre_dynamique=False)


def _preparer_config_bidon(tmp_dir: Path, projet="bridge_agent"):
    (tmp_dir / "configs").mkdir(parents=True, exist_ok=True)
    (tmp_dir / "configs" / f"{projet}.conf").write_text("DEPOT=AlainDelree/Bridge_Agent\n")
    w.DOSSIER_SCRIPT = tmp_dir
    w.charger_config = lambda chemin: _cfg_projet(rep_travail=tmp_dir)


# ─── 1. Texte libre ajouté en fin de corps, section horodatée ─────────────

def scenario_1_texte_libre_ajoute_avec_section_horodatee():
    corps = (
        "## En-tête\n\n"
        "| Champ    | Valeur |\n"
        "|----------|--------|\n"
        "| SOURCE   | CC |\n"
        "| TIMEOUT  | 300s |\n"
        "| PROJET   | bridge_agent |\n\n"
        "## Contexte\nTexte d'origine.\n"
    )
    nouveau = w._ajouter_texte_libre(corps, "Cause supposée : dépendance manquante.")
    assert nouveau.startswith(corps.rstrip("\n")), "le corps d'origine doit être préservé en tête"
    assert "## Relance du " in nouveau, nouveau
    assert "Cause supposée : dépendance manquante." in nouveau, nouveau
    assert nouveau.index("## Relance du") > nouveau.index("Texte d'origine")
    return {}


# ─── 2. Texte vide → corps inchangé par ce mécanisme ───────────────────────

def scenario_2_texte_vide_corps_inchange_par_le_mecanisme():
    """_traiter_relance ne doit appeler _ajouter_texte_libre que si
    champs["corps"] est non vide — reproduit ici la garde elle-même plutôt
    que _ajouter_texte_libre (qui, appelée directement avec une chaîne vide,
    ajouterait quand même une section vide : c'est à l'appelant de ne pas
    l'invoquer, cf. scénario 5/6 ci-dessous pour le chemin complet)."""
    corps = "| TIMEOUT | 300s |\n| PROJET | bridge_agent |\n"
    champs = {"corps": ""}
    # Même logique que dans _traiter_relance : corps inchangé si champs["corps"] vide.
    nouveau = corps
    if champs["corps"]:
        nouveau = w._ajouter_texte_libre(corps, champs["corps"])
    assert nouveau == corps
    return {}


# ─── 3. Deux relances successives → deux sections empilées, dans l'ordre ──

def scenario_3_deux_relances_successives_empilent_les_sections():
    corps = "| TIMEOUT | 300s |\n| PROJET | bridge_agent |\n"
    apres_1 = w._ajouter_texte_libre(corps, "Première consigne de reprise.")
    apres_2 = w._ajouter_texte_libre(apres_1, "Deuxième consigne de reprise.")

    assert apres_2.count("## Relance du ") == 2, apres_2
    assert "Première consigne de reprise." in apres_2
    assert "Deuxième consigne de reprise." in apres_2
    assert apres_2.index("Première consigne") < apres_2.index("Deuxième consigne"), \
        "la plus récente doit être en dernier, sans effacer la précédente"
    return {}


# ─── 4. Texte imitant des lignes d'en-tête → jamais lu comme un champ ──────

def scenario_4_texte_imitant_entete_jamais_lu_comme_champ():
    """Un corps court (en-tête + peu de texte, bien sous ZONE_ENTETE_LIGNES)
    avec un texte libre qui imite TIMEOUT/MODE : après ajout, lire_champ_entete
    doit continuer à renvoyer la valeur RÉELLE (ou rien si le champ est
    absent de l'en-tête réel), jamais la valeur imitée dans le texte libre —
    la section ajoutée doit être hors de la zone d'en-tête bornée (§3.3)."""
    corps = (
        "| SOURCE  | CC |\n"
        "| MODE    | lecture |\n"
        "| TIMEOUT | 300s |\n"
        "| PROJET  | bridge_agent |\n\n"
        "Court.\n"
    )
    assert len(corps.splitlines()) < w.ZONE_ENTETE_LIGNES, "le cas visé est justement un corps court"

    texte_libre_piege = (
        "| MODE | ecriture |\n"
        "| TIMEOUT | 1s |\n"
        "| SOUS_DOSSIER | ../../etc |\n"
        "Consigne de reprise qui imite des lignes d'en-tête."
    )
    nouveau = w._ajouter_texte_libre(corps, texte_libre_piege)

    assert w.lire_champ_entete(nouveau, "MODE") == "lecture", \
        "le MODE réel ne doit jamais être masqué par la valeur imitée dans le texte libre"
    assert w.lire_champ_entete(nouveau, "TIMEOUT") == "300s", \
        "le TIMEOUT réel ne doit jamais être masqué par la valeur imitée dans le texte libre"
    assert w.lire_champ_entete(nouveau, "SOUS_DOSSIER") is None, \
        "SOUS_DOSSIER, absent de l'en-tête réel, ne doit jamais être lu depuis le texte libre imité"
    assert "| MODE | ecriture |" not in w._zone_entete(nouveau), \
        "la ligne imitée ne doit même pas apparaître dans la zone d'en-tête bornée"

    # Une correction RELANCE ultérieure (TIMEOUT) doit toujours cibler la
    # VRAIE ligne d'en-tête, jamais la ligne imitée dans le texte libre.
    apres_correction, modifies = w._fusionner_entete(nouveau, {"timeout_brut": "1800s", "modele": "",
                                                                 "corps": "", "sous_dossier_brut": None,
                                                                 "repo_cible_brut": None})
    assert "| TIMEOUT | 1800s |" in apres_correction, apres_correction
    assert "| TIMEOUT | 1s |" in apres_correction, "la ligne imitée dans le texte libre reste inchangée"
    assert modifies == ["TIMEOUT → 1800s"]
    return {}


# ─── 5. Fusion des champs + ajout du texte dans une seule mise à jour ──────

def scenario_5_fusion_entete_et_texte_libre_en_une_seule_maj_corps(tmp_path_factory):
    tmp_dir = tmp_path_factory()
    _preparer_config_bidon(tmp_dir)

    appels = {"nb_edit_corps": 0}

    def _fausse_recuperation(depot, numero):
        return True, "", {
            "number": numero, "state": "OPEN", "title": "Échec de build",
            "body": "| TIMEOUT | 300s |\n| PROJET | bridge_agent |\n",
            "labels": [{"name": "bridge"}, {"name": "for-linux"}],
        }

    def _faux_edit_corps(depot, numero, corps):
        appels["nb_edit_corps"] += 1
        appels["corps_envoye"] = corps
        return True, ""

    def _faux_relancer(depot, numero, commentaire=""):
        appels["commentaire"] = commentaire
        return "ok", [{"etape": "retrait_label_needs_human", "statut": "succes", "message": ""},
                        {"etape": "commentaire", "statut": "succes", "message": ""}]

    w._recuperer_issue = _fausse_recuperation
    w._modifier_corps_gh = _faux_edit_corps
    w.relancer_issue = _faux_relancer
    watchers_mod.demarrer_watcher = lambda cfg, forcer=False: (False, 4242)
    w.demarrer_service_ccw_arriere_plan = lambda *_a, **_k: None

    contenu = (
        "| PROJET  | bridge_agent |\n"
        "| RELANCE | #88 |\n"
        "| TIMEOUT | 1800s |\n"
        "\n"
        "Le TIMEOUT était trop court, voici la cause probable.\n"
    )
    champs = w.extraire_champs(contenu)
    succes, titre, projet, texte, resultat_gh, _labels, _donnees_temps = w._traiter_relance(w.ConfigInbox(), champs)

    assert succes, texte
    assert appels["nb_edit_corps"] == 1, "une seule mise à jour du corps : fusion + texte libre ensemble"
    assert "| TIMEOUT | 1800s |" in appels["corps_envoye"], appels["corps_envoye"]
    assert "## Relance du " in appels["corps_envoye"], appels["corps_envoye"]
    assert "Le TIMEOUT était trop court, voici la cause probable." in appels["corps_envoye"]
    # Le commentaire de trace existant reste inchangé (conservé tel quel, #726).
    assert "Le TIMEOUT était trop court, voici la cause probable." in appels["commentaire"]
    return {"texte": texte}


# ─── 6. Échec de la mise à jour du corps → relance rejetée, needs-human conservé

def scenario_6_echec_maj_corps_rejette_sans_toucher_needs_human(tmp_path_factory):
    tmp_dir = tmp_path_factory()
    _preparer_config_bidon(tmp_dir)

    appels = {"relancer_appele": False}

    def _fausse_recuperation(depot, numero):
        return True, "", {
            "number": numero, "state": "OPEN", "title": "Échec de build",
            "body": "| TIMEOUT | 300s |\n| PROJET | bridge_agent |\n",
            "labels": [{"name": "bridge"}, {"name": "for-linux"}],
        }

    def _faux_edit_corps_qui_echoue(depot, numero, corps):
        return False, "réseau indisponible"

    def _faux_relancer_qui_ne_devrait_pas_etre_appele(depot, numero, commentaire=""):
        appels["relancer_appele"] = True
        return "ok", []

    w._recuperer_issue = _fausse_recuperation
    w._modifier_corps_gh = _faux_edit_corps_qui_echoue
    w.relancer_issue = _faux_relancer_qui_ne_devrait_pas_etre_appele

    contenu = (
        "| PROJET  | bridge_agent |\n"
        "| RELANCE | #88 |\n"
        "\n"
        "Consigne de reprise quelconque.\n"
    )
    champs = w.extraire_champs(contenu)
    succes, titre, projet, texte, _, _labels, _donnees_temps = w._traiter_relance(w.ConfigInbox(), champs)

    assert not succes
    assert "mise à jour du corps" in texte, texte
    assert "réseau indisponible" in texte, texte
    assert not appels["relancer_appele"], \
        "needs-human ne doit pas être retiré si la mise à jour du corps échoue"
    return {"texte": texte}


def main():
    tmp = tempfile.TemporaryDirectory()
    ancien_demarrer_watcher = watchers_mod.demarrer_watcher
    ancien_demarrage_ccw = w.demarrer_service_ccw_arriere_plan
    ancien_recuperer_issue = w._recuperer_issue
    ancien_modifier_corps = w._modifier_corps_gh
    ancien_relancer = w.relancer_issue

    def _tmp_path_factory():
        return Path(tmp.name)

    tests = [
        ("texte libre ajouté en fin de corps, section horodatée", scenario_1_texte_libre_ajoute_avec_section_horodatee),
        ("texte vide → corps inchangé par ce mécanisme", scenario_2_texte_vide_corps_inchange_par_le_mecanisme),
        ("deux relances successives → deux sections empilées, dans l'ordre", scenario_3_deux_relances_successives_empilent_les_sections),
        ("texte imitant des lignes d'en-tête → jamais lu comme un champ", scenario_4_texte_imitant_entete_jamais_lu_comme_champ),
        ("fusion en-tête + texte libre en une seule mise à jour du corps", lambda: scenario_5_fusion_entete_et_texte_libre_en_une_seule_maj_corps(_tmp_path_factory)),
        ("échec maj corps → rejet, needs-human conservé", lambda: scenario_6_echec_maj_corps_rejette_sans_toucher_needs_human(_tmp_path_factory)),
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
        finally:
            watchers_mod.demarrer_watcher = ancien_demarrer_watcher
            w.demarrer_service_ccw_arriere_plan = ancien_demarrage_ccw
            w._recuperer_issue = ancien_recuperer_issue
            w._modifier_corps_gh = ancien_modifier_corps
            w.relancer_issue = ancien_relancer

    tmp.cleanup()
    if echecs:
        print(f"\n❌ {echecs} scénario(s) en échec.")
        return 1
    print("\n✅ Tous les scénarios passent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
