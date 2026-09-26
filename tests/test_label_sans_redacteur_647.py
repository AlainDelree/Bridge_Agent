#!/usr/bin/env python3
"""Test de non-régression — issue #647 : avertissement visible (non bloquant)
quand une issue arrive sans champ REDACTEUR.

Couvre le versant SERVEUR : la pose du label GitHub `sans-redacteur`
(watcher.LABEL_SANS_REDACTEUR) par `construire_labels()`
(scripts/watcher_issues_inbox.py) — présent UNIQUEMENT quand le champ REDACTEUR
est ABSENT de l'en-tête (cas déjà accepté par `valider_redacteur()`, qui
renvoie (True, "") pour ce cas — rétrocompatibilité, jamais de rejet).
REDACTEUR présent (cohérent avec PROJET ou non — l'incohérence a son propre
traitement, rejet vers rejected/, inchangé) → jamais posé. Complète le chemin
bout-en-bout via `traiter_fichier()`, comme test_champ_redacteur_599.py.

Le versant NAVIGATEUR (calcul du badge à partir du label) est couvert par
static/js/tests/resultats.test.js (`node --test`).

Exécution :  python3 -m pytest tests/test_label_sans_redacteur_647.py
        ou : python3 tests/test_label_sans_redacteur_647.py
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
from watcher import LABEL_SANS_REDACTEUR  # noqa: E402


def _champs(redacteur="", labels_brut=None, mode_brut=None):
    return {"redacteur": redacteur, "labels_brut": labels_brut, "mode_brut": mode_brut}


def test_construire_labels_redacteur_absent_pose_le_label():
    """REDACTEUR absent (chaîne vide, cas normal d'extraction) → label posé."""
    labels = w.construire_labels(_champs(redacteur="")).split(",")
    assert LABEL_SANS_REDACTEUR in labels, labels


def test_construire_labels_redacteur_egal_projet_ne_pose_rien():
    """REDACTEUR présent et cohérent avec PROJET → label absent."""
    labels = w.construire_labels(_champs(redacteur="bridge_agent")).split(",")
    assert LABEL_SANS_REDACTEUR not in labels, labels


def test_construire_labels_redacteur_incoherent_ne_pose_rien_non_plus():
    """REDACTEUR présent mais incohérent avec PROJET : ce n'est PAS le rôle
    de construire_labels() de le détecter (valider_redacteur() rejette déjà ce
    cas avant d'atteindre construire_labels(), cf. test_champ_redacteur_599.py)
    — mais la présence seule du champ suffit à ne jamais poser ce label-ci."""
    labels = w.construire_labels(_champs(redacteur="scrabble")).split(",")
    assert LABEL_SANS_REDACTEUR not in labels, labels


def test_construire_labels_redacteur_absent_pas_de_doublon_si_deja_dans_labels():
    """Un dépôt manuel du label via le champ LABELS de l'en-tête ne produit
    jamais de doublon (garde `not in labels`)."""
    labels = w.construire_labels(_champs(redacteur="", labels_brut="sans-redacteur")).split(",")
    assert labels.count(LABEL_SANS_REDACTEUR) == 1, labels


def _cfg_projet(depot="AlainDelree/Bridge_Agent", nom="bridge_agent"):
    return SimpleNamespace(depot=depot, nom=nom, timeout_claude=300, timeout_chef=1200,
                            max_essais=3, rep_travail=Path(tempfile.gettempdir()),
                            perimetre_dynamique=False)


def _preparer_config_bidon(tmp_dir: Path, projet="bridge_agent"):
    (tmp_dir / "configs").mkdir(parents=True, exist_ok=True)
    (tmp_dir / "configs" / f"{projet}.conf").write_text("DEPOT=AlainDelree/Bridge_Agent\n")
    w.DOSSIER_SCRIPT = tmp_dir
    w.charger_config = lambda chemin: _cfg_projet(nom=projet)


def _traiter_et_capturer_labels(tmp_path, contenu):
    """Fait passer `contenu` par traiter_fichier() en interceptant les labels
    réellement transmis à `gh issue create` — retourne la liste des labels,
    ou None si la création a été rejetée (aucun appel à _creer_issue)."""
    _preparer_config_bidon(tmp_path)
    cfg = w.ConfigInbox(rep_travail=tmp_path, inbox_dir=tmp_path / "issues_inbox",
                         rejected_dir=tmp_path / "issues_inbox" / "rejected")
    cfg.inbox_dir.mkdir(parents=True, exist_ok=True)
    cfg.rejected_dir.mkdir(parents=True, exist_ok=True)

    captures = {}

    def _creer_issue(cfg_i, cfg_p, titre, labels, body):
        captures["labels"] = labels
        return True, "https://x/1"

    w._issue_ouverte_meme_titre = lambda cfg_p, titre: None
    w._creer_issue = _creer_issue
    watchers_mod.demarrer_watcher = lambda cfg_p, forcer=False: (False, 1111)

    chemin = cfg.inbox_dir / "issue.txt"
    chemin.write_text(contenu)
    import os, time
    os.utime(chemin, (time.time() - 5, time.time() - 5))

    w.traiter_fichier(cfg, chemin)
    return captures.get("labels")


def test_traiter_fichier_sans_redacteur_pose_le_label(tmp_path):
    labels = _traiter_et_capturer_labels(
        tmp_path,
        "| PROJET | bridge_agent |\n\n#Titre: Tâche sans REDACTEUR.\nCorps.\n",
    )
    assert labels is not None, "l'issue aurait dû être créée"
    assert LABEL_SANS_REDACTEUR in labels.split(","), labels


def test_traiter_fichier_avec_redacteur_coherent_ne_pose_rien(tmp_path):
    labels = _traiter_et_capturer_labels(
        tmp_path,
        "| PROJET    | bridge_agent |\n"
        "| REDACTEUR | bridge_agent |\n"
        "\n"
        "#Titre: Tâche cohérente.\nCorps.\n",
    )
    assert labels is not None, "l'issue aurait dû être créée"
    assert LABEL_SANS_REDACTEUR not in labels.split(","), labels


def main() -> int:
    tests = [
        ("construire_labels : REDACTEUR absent → label posé",
         test_construire_labels_redacteur_absent_pose_le_label),
        ("construire_labels : REDACTEUR == PROJET → rien posé",
         test_construire_labels_redacteur_egal_projet_ne_pose_rien),
        ("construire_labels : REDACTEUR incohérent → rien posé (ici)",
         test_construire_labels_redacteur_incoherent_ne_pose_rien_non_plus),
        ("construire_labels : pas de doublon si déjà dans LABELS",
         test_construire_labels_redacteur_absent_pas_de_doublon_si_deja_dans_labels),
    ]
    echecs = 0
    for nom, fn in tests:
        try:
            fn()
            print(f"  ✓ {nom}")
        except AssertionError as e:
            echecs += 1
            print(f"  ✗ {nom}\n      {e}")

    tmp = tempfile.TemporaryDirectory()
    for nom, fn in [
        ("traiter_fichier : sans REDACTEUR → label posé",
         test_traiter_fichier_sans_redacteur_pose_le_label),
        ("traiter_fichier : REDACTEUR cohérent → rien posé",
         test_traiter_fichier_avec_redacteur_coherent_ne_pose_rien),
    ]:
        try:
            fn(Path(tmp.name))
            print(f"  ✓ {nom}")
        except AssertionError as e:
            echecs += 1
            print(f"  ✗ {nom}\n      {e}")
    tmp.cleanup()

    if echecs:
        print(f"\n❌ {echecs} scénario(s) en échec.")
        return 1
    print("\n✅ Tous les scénarios passent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
