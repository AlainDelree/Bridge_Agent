#!/usr/bin/env python3
"""Test de non-régression — issue #599 : champ d'en-tête optionnel
`| REDACTEUR | <projet> |` dans `issues_inbox/`, validé pour cohérence avec
`PROJET` AVANT toute création d'issue GitHub — filet de sécurité contre une
issue rédigée par Claude Chat dans le contexte d'un projet puis déposée sous
un `PROJET` différent (distraction, relecture insuffisante d'Alain).

Couvre : extraction du champ (`extraire_champs`), la fonction de validation
`valider_redacteur()` (les 3 règles : cohérence directe, exception canal CCW
for-windows, rejet), l'intégration dans `valider()`, et le chemin complet
`traiter_fichier()` (fichier déplacé vers `rejected/`, ligne journalisée dans
`issues_inbox.log`) pour les 4 scénarios de vérification demandés par
l'issue. Aucun accès réseau (`gh` jamais appelé dans les scénarios de rejet).

Exécution :  python3 tests/test_champ_redacteur_599.py
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
    return SimpleNamespace(depot=depot, nom=nom, timeout_claude=300, timeout_chef=1200,
                            rep_travail=Path(tempfile.gettempdir()), perimetre_dynamique=False)


def _preparer_config_bidon(tmp_dir: Path, projet="bridge_agent"):
    """Fait pointer DOSSIER_SCRIPT/charger_config vers un projet bidon —
    évite toute dépendance à un vrai configs/<projet>.conf (gitignoré,
    absent de ce worktree)."""
    (tmp_dir / "configs").mkdir(parents=True, exist_ok=True)
    (tmp_dir / "configs" / f"{projet}.conf").write_text("DEPOT=AlainDelree/Bridge_Agent\n")
    w.DOSSIER_SCRIPT = tmp_dir
    w.charger_config = lambda chemin: _cfg_projet(nom=projet)


def scenario_1_extraction_champ_redacteur():
    """REDACTEUR est reconnu comme les autres champs d'en-tête et retiré du
    corps restant."""
    contenu = (
        "| PROJET    | bridge_agent |\n"
        "| REDACTEUR | bridge_agent |\n"
        "\n"
        "#Titre: Une tâche.\n"
        "Corps de la tâche.\n"
    )
    champs = w.extraire_champs(contenu)
    assert champs["redacteur"] == "bridge_agent", champs["redacteur"]
    assert "REDACTEUR" not in champs["corps"], champs["corps"]
    return {"redacteur": champs["redacteur"]}


def scenario_2_extraction_redacteur_absent():
    """REDACTEUR absent → chaîne vide, jamais d'erreur d'extraction."""
    champs = w.extraire_champs("| PROJET | bridge_agent |\n\n#Titre: Une tâche.\nCorps.\n")
    assert champs["redacteur"] == "", repr(champs["redacteur"])
    return {}


def scenario_3_valider_redacteur_absent_ok():
    """Cas 4 attendu : REDACTEUR absent → rétrocompatibilité, aucune
    validation, traitement normal."""
    champs = {"redacteur": "", "projet": "scrabble", "labels_brut": None}
    ok, detail = w.valider_redacteur(champs)
    assert ok, detail
    assert detail == ""
    return {}


def scenario_4_valider_redacteur_egal_projet_ok():
    """Cas 1 attendu : REDACTEUR == PROJET → OK, traitement normal."""
    champs = {"redacteur": "scrabble", "projet": "scrabble", "labels_brut": None}
    ok, detail = w.valider_redacteur(champs)
    assert ok, detail
    return {}


def scenario_5_valider_redacteur_canal_ccw_for_windows_ok():
    """Cas 2 attendu : label for-windows + REDACTEUR == bridge_agent → OK,
    quel que soit le PROJET réellement ciblé (canal central CCW)."""
    champs = {"redacteur": "bridge_agent", "projet": "scrabble", "labels_brut": "for-windows"}
    ok, detail = w.valider_redacteur(champs)
    assert ok, detail
    return {}


def scenario_6_valider_redacteur_autre_projet_sans_for_windows_rejete():
    """Cas 3 attendu : REDACTEUR d'un autre projet, sans label for-windows →
    rejet avec message explicite de discordance."""
    champs = {"redacteur": "scrabble", "projet": "bridge_agent", "labels_brut": None}
    ok, detail = w.valider_redacteur(champs)
    assert not ok
    assert "REDACTEUR incohérent avec PROJET" in detail, detail
    assert "scrabble" in detail and "bridge_agent" in detail, detail
    return {"detail": detail}


def scenario_7_valider_redacteur_bridge_agent_sans_for_windows_rejete():
    """REDACTEUR == bridge_agent MAIS sans label for-windows (et PROJET
    différent) reste rejeté — l'exception canal CCW exige le label."""
    champs = {"redacteur": "bridge_agent", "projet": "scrabble", "labels_brut": None}
    ok, detail = w.valider_redacteur(champs)
    assert not ok
    assert "REDACTEUR incohérent avec PROJET" in detail, detail
    return {"detail": detail}


def scenario_8_valider_redacteur_for_windows_mais_autre_redacteur_rejete():
    """Label for-windows présent mais REDACTEUR ni == PROJET ni ==
    bridge_agent → rejet (l'exception canal CCW ne couvre que
    REDACTEUR=bridge_agent)."""
    champs = {"redacteur": "relecture_bridge", "projet": "scrabble", "labels_brut": "for-windows"}
    ok, detail = w.valider_redacteur(champs)
    assert not ok
    return {"detail": detail}


def scenario_9_traiter_fichier_redacteur_egal_projet_traite_normalement(tmp_path_factory):
    """Chemin complet : REDACTEUR == PROJET → gh issue create appelé,
    fichier supprimé, ligne OK journalisée."""
    tmp_dir = tmp_path_factory()
    _preparer_config_bidon(tmp_dir)
    cfg = w.ConfigInbox(rep_travail=tmp_dir, inbox_dir=tmp_dir / "issues_inbox",
                         rejected_dir=tmp_dir / "issues_inbox" / "rejected")
    cfg.inbox_dir.mkdir(parents=True, exist_ok=True)
    cfg.rejected_dir.mkdir(parents=True, exist_ok=True)

    def _creer_issue(cfg_i, cfg_p, titre, labels, body):
        return True, "https://x/1"

    w._issue_ouverte_meme_titre = lambda cfg_p, titre: None
    w._creer_issue = _creer_issue
    w.demarrer_watcher = lambda cfg_p, forcer=False: (False, 1111)

    chemin = cfg.inbox_dir / "issue.txt"
    chemin.write_text(
        "| PROJET    | bridge_agent |\n"
        "| REDACTEUR | bridge_agent |\n"
        "\n"
        "#Titre: Tâche cohérente.\n"
        "Corps.\n"
    )
    import os, time
    os.utime(chemin, (time.time() - 5, time.time() - 5))

    w.traiter_fichier(cfg, chemin)

    assert not chemin.exists(), "le fichier traité avec succès doit être supprimé"
    lignes = cfg.fichier_log.read_text(encoding="utf-8").splitlines()
    assert lignes and " OK " in lignes[-1], lignes
    return {"derniere_ligne": lignes[-1] if lignes else ""}


def scenario_10_traiter_fichier_redacteur_autre_projet_rejete(tmp_path_factory):
    """Chemin complet : REDACTEUR d'un autre projet (non for-windows) → pas
    de gh issue create, fichier déplacé vers rejected/, ligne REJECTED
    journalisée avec le motif de discordance."""
    tmp_dir = tmp_path_factory()
    _preparer_config_bidon(tmp_dir)
    cfg = w.ConfigInbox(rep_travail=tmp_dir, inbox_dir=tmp_dir / "issues_inbox",
                         rejected_dir=tmp_dir / "issues_inbox" / "rejected")
    cfg.inbox_dir.mkdir(parents=True, exist_ok=True)
    cfg.rejected_dir.mkdir(parents=True, exist_ok=True)

    def _creer_issue_qui_ne_doit_jamais_etre_appelee(*a, **k):
        raise AssertionError("gh issue create ne doit pas être appelé pour un REDACTEUR incohérent")
    w._creer_issue = _creer_issue_qui_ne_doit_jamais_etre_appelee

    chemin = cfg.inbox_dir / "issue.txt"
    chemin.write_text(
        "| PROJET    | bridge_agent |\n"
        "| REDACTEUR | scrabble |\n"
        "\n"
        "#Titre: Tâche mal aiguillée.\n"
        "Corps.\n"
    )
    import os, time
    os.utime(chemin, (time.time() - 5, time.time() - 5))

    w.traiter_fichier(cfg, chemin)

    assert not chemin.exists()
    rejetes = list(cfg.rejected_dir.glob("*REJETE*"))
    assert len(rejetes) == 1, rejetes
    assert "redacteur" in rejetes[0].name.lower(), rejetes[0].name

    lignes = cfg.fichier_log.read_text(encoding="utf-8").splitlines()
    assert lignes and " REJECTED " in lignes[-1], lignes
    assert "REDACTEUR incohérent avec PROJET" in lignes[-1], lignes[-1]
    return {"derniere_ligne": lignes[-1]}


def scenario_11_traiter_fichier_canal_ccw_for_windows_traite_normalement(tmp_path_factory):
    """Chemin complet : label for-windows + REDACTEUR == bridge_agent →
    traité normalement même si PROJET vise un autre projet."""
    tmp_dir = tmp_path_factory()
    _preparer_config_bidon(tmp_dir, projet="scrabble")
    cfg = w.ConfigInbox(rep_travail=tmp_dir, inbox_dir=tmp_dir / "issues_inbox",
                         rejected_dir=tmp_dir / "issues_inbox" / "rejected")
    cfg.inbox_dir.mkdir(parents=True, exist_ok=True)
    cfg.rejected_dir.mkdir(parents=True, exist_ok=True)

    w._issue_ouverte_meme_titre = lambda cfg_p, titre: None
    w._creer_issue = lambda cfg_i, cfg_p, titre, labels, body: (True, "https://x/2")
    w.demarrer_watcher = lambda cfg_p, forcer=False: (False, 2222)

    chemin = cfg.inbox_dir / "issue.txt"
    chemin.write_text(
        "| PROJET    | scrabble |\n"
        "| REDACTEUR | bridge_agent |\n"
        "| LABELS    | for-windows |\n"
        "\n"
        "#Titre: Build Windows Scrabble.\n"
        "Corps.\n"
    )
    import os, time
    os.utime(chemin, (time.time() - 5, time.time() - 5))

    w.traiter_fichier(cfg, chemin)

    assert not chemin.exists(), "le fichier traité avec succès doit être supprimé"
    lignes = cfg.fichier_log.read_text(encoding="utf-8").splitlines()
    assert lignes and " OK " in lignes[-1], lignes
    return {"derniere_ligne": lignes[-1] if lignes else ""}


def scenario_12_traiter_fichier_sans_redacteur_traite_normalement(tmp_path_factory):
    """Chemin complet : REDACTEUR absent → rétrocompatibilité, traité
    normalement comme avant l'issue #599."""
    tmp_dir = tmp_path_factory()
    _preparer_config_bidon(tmp_dir)
    cfg = w.ConfigInbox(rep_travail=tmp_dir, inbox_dir=tmp_dir / "issues_inbox",
                         rejected_dir=tmp_dir / "issues_inbox" / "rejected")
    cfg.inbox_dir.mkdir(parents=True, exist_ok=True)
    cfg.rejected_dir.mkdir(parents=True, exist_ok=True)

    w._issue_ouverte_meme_titre = lambda cfg_p, titre: None
    w._creer_issue = lambda cfg_i, cfg_p, titre, labels, body: (True, "https://x/3")
    w.demarrer_watcher = lambda cfg_p, forcer=False: (False, 3333)

    chemin = cfg.inbox_dir / "issue.txt"
    chemin.write_text("| PROJET | bridge_agent |\n\n#Titre: Tâche sans REDACTEUR.\nCorps.\n")
    import os, time
    os.utime(chemin, (time.time() - 5, time.time() - 5))

    w.traiter_fichier(cfg, chemin)

    assert not chemin.exists(), "le fichier traité avec succès doit être supprimé"
    lignes = cfg.fichier_log.read_text(encoding="utf-8").splitlines()
    assert lignes and " OK " in lignes[-1], lignes
    return {"derniere_ligne": lignes[-1] if lignes else ""}


def main():
    tmp = tempfile.TemporaryDirectory()

    def _tmp_path_factory():
        return Path(tmp.name)

    tests = [
        ("champ REDACTEUR extrait et retiré du corps", scenario_1_extraction_champ_redacteur),
        ("REDACTEUR absent → chaîne vide, pas d'erreur", scenario_2_extraction_redacteur_absent),
        ("valider_redacteur : absent → OK (rétrocompat)", scenario_3_valider_redacteur_absent_ok),
        ("valider_redacteur : REDACTEUR == PROJET → OK", scenario_4_valider_redacteur_egal_projet_ok),
        ("valider_redacteur : for-windows + bridge_agent → OK", scenario_5_valider_redacteur_canal_ccw_for_windows_ok),
        ("valider_redacteur : autre projet sans for-windows → rejet", scenario_6_valider_redacteur_autre_projet_sans_for_windows_rejete),
        ("valider_redacteur : bridge_agent sans for-windows → rejet", scenario_7_valider_redacteur_bridge_agent_sans_for_windows_rejete),
        ("valider_redacteur : for-windows mais REDACTEUR tiers → rejet", scenario_8_valider_redacteur_for_windows_mais_autre_redacteur_rejete),
        ("traiter_fichier : REDACTEUR == PROJET → traité normalement",
         lambda: scenario_9_traiter_fichier_redacteur_egal_projet_traite_normalement(_tmp_path_factory)),
        ("traiter_fichier : REDACTEUR autre projet → rejeté + loggé",
         lambda: scenario_10_traiter_fichier_redacteur_autre_projet_rejete(_tmp_path_factory)),
        ("traiter_fichier : canal CCW for-windows → traité normalement",
         lambda: scenario_11_traiter_fichier_canal_ccw_for_windows_traite_normalement(_tmp_path_factory)),
        ("traiter_fichier : sans REDACTEUR → traité normalement (rétrocompat)",
         lambda: scenario_12_traiter_fichier_sans_redacteur_traite_normalement(_tmp_path_factory)),
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
