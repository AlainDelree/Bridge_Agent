#!/usr/bin/env python3
"""Test de non-régression — issue #844 : label informatif (non bloquant)
« sans-complexite » + badge dédié quand une issue arrive sans ligne
COMPLEXITE reconnue — même mécanisme que « sans-redacteur » (issue #647),
mais appliqué aux DEUX chemins de création (fichier déposé dans
issues_inbox/ ET formulaire web), conformément à la demande de l'issue.

Couvre le versant SERVEUR :
- `watcher.complexite_reconnue()` — même reconnaissance EXACTE que
  `watcher.extraire_complexite()` (calibration TIMEOUT, issue #434/#221) :
  quatre niveaux (rapide/court/normal/lourd), insensible à la casse/espaces.
  Absente ou valeur hors de ces quatre niveaux (ex. « moyen ») → False.
- La pose du label GitHub `sans-complexite` (watcher.LABEL_SANS_COMPLEXITE)
  par `construire_labels()` côté `scripts/watcher_issues_inbox.py` (chemin
  fichier) ET côté `app/issues.py` (chemin formulaire web) — jamais de rejet,
  l'issue est toujours créée normalement.
- Le chemin bout-en-bout via `traiter_fichier()`, comme
  test_label_sans_redacteur_647.py.

Le versant NAVIGATEUR (calcul du badge à partir du label) est couvert par
static/js/tests/resultats.test.js (`node --test`).

Exécution :  python3 -m pytest tests/test_label_sans_complexite_844.py
        ou : python3 tests/test_label_sans_complexite_844.py
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
import app.issues as app_issues  # noqa: E402
from watcher import LABEL_SANS_COMPLEXITE, complexite_reconnue  # noqa: E402


# ─── watcher.complexite_reconnue — même reconnaissance qu'extraire_complexite
def test_complexite_reconnue_absente():
    assert complexite_reconnue("## En-tête\n\n| PROJET | bridge_agent |\n") is False


def test_complexite_reconnue_valeur_inconnue():
    assert complexite_reconnue("| COMPLEXITE | moyen |\n") is False


def test_complexite_reconnue_valeur_valide():
    for niveau in ("rapide", "court", "normal", "lourd"):
        assert complexite_reconnue(f"| COMPLEXITE | {niveau} |\n") is True, niveau


def test_complexite_reconnue_insensible_casse_et_espaces():
    assert complexite_reconnue("| COMPLEXITE |  LOURD  |\n") is True


# ─── construire_labels() côté fichier déposé (scripts/watcher_issues_inbox.py)
def _champs(corps="", redacteur="bridge_agent", labels_brut=None, mode_brut=None):
    return {"corps": corps, "redacteur": redacteur, "labels_brut": labels_brut,
            "mode_brut": mode_brut}


def test_inbox_construire_labels_complexite_absente_pose_le_label():
    labels = w.construire_labels(_champs(corps="Corps sans ligne COMPLEXITE.")).split(",")
    assert LABEL_SANS_COMPLEXITE in labels, labels


def test_inbox_construire_labels_complexite_inconnue_pose_le_label():
    labels = w.construire_labels(_champs(corps="| COMPLEXITE | moyen |\n\nCorps.")).split(",")
    assert LABEL_SANS_COMPLEXITE in labels, labels


def test_inbox_construire_labels_complexite_valide_ne_pose_rien():
    labels = w.construire_labels(_champs(corps="| COMPLEXITE | lourd |\n\nCorps.")).split(",")
    assert LABEL_SANS_COMPLEXITE not in labels, labels


def test_inbox_construire_labels_complexite_absente_pas_de_doublon_si_deja_dans_labels():
    labels = w.construire_labels(
        _champs(corps="Corps.", labels_brut="sans-complexite")
    ).split(",")
    assert labels.count(LABEL_SANS_COMPLEXITE) == 1, labels


# ─── construire_labels() côté formulaire web (app/issues.py)
def test_web_construire_labels_complexite_absente_pose_le_label():
    labels = app_issues.construire_labels({"corps": "Corps sans ligne COMPLEXITE."}).split(",")
    assert LABEL_SANS_COMPLEXITE in labels, labels


def test_web_construire_labels_complexite_inconnue_pose_le_label():
    labels = app_issues.construire_labels({"corps": "| COMPLEXITE | moyen |\n\nCorps."}).split(",")
    assert LABEL_SANS_COMPLEXITE in labels, labels


def test_web_construire_labels_complexite_valide_ne_pose_rien():
    labels = app_issues.construire_labels({"corps": "| COMPLEXITE | lourd |\n\nCorps."}).split(",")
    assert LABEL_SANS_COMPLEXITE not in labels, labels


# ─── Chemin complet via traiter_fichier() (fichier déposé) ─────────────────
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
    _preparer_config_bidon(tmp_path)
    cfg = w.ConfigInbox(rep_travail=tmp_path, inbox_dir=tmp_path / "issues_inbox",
                         rejected_dir=tmp_path / "issues_inbox" / "rejected")
    cfg.inbox_dir.mkdir(parents=True, exist_ok=True)
    cfg.rejected_dir.mkdir(parents=True, exist_ok=True)

    captures = {}

    def _creer_issue(cfg_i, cfg_p, titre, labels, body):
        captures["labels"] = labels
        return True, "https://x/1", []

    w._issue_ouverte_meme_titre = lambda cfg_p, titre: None
    w._creer_issue = _creer_issue
    watchers_mod.demarrer_watcher = lambda cfg_p, forcer=False: (False, 2222)

    chemin = cfg.inbox_dir / "issue.txt"
    chemin.write_text(contenu)
    import os, time
    os.utime(chemin, (time.time() - 5, time.time() - 5))

    w.traiter_fichier(cfg, chemin)
    return captures.get("labels")


def test_traiter_fichier_sans_complexite_pose_le_label(tmp_path):
    labels = _traiter_et_capturer_labels(
        tmp_path,
        "| PROJET | bridge_agent |\n\n#Titre: Tâche sans COMPLEXITE.\nCorps.\n",
    )
    assert labels is not None, "l'issue aurait dû être créée"
    assert LABEL_SANS_COMPLEXITE in labels.split(","), labels


def test_traiter_fichier_avec_complexite_valide_ne_pose_rien(tmp_path):
    labels = _traiter_et_capturer_labels(
        tmp_path,
        "| PROJET | bridge_agent |\n\n#Titre: Tâche avec COMPLEXITE.\n"
        "| COMPLEXITE | lourd |\n\nCorps.\n",
    )
    assert labels is not None, "l'issue aurait dû être créée"
    assert LABEL_SANS_COMPLEXITE not in labels.split(","), labels


def main() -> int:
    tests = [
        ("complexite_reconnue : absente → False",
         test_complexite_reconnue_absente),
        ("complexite_reconnue : valeur inconnue → False",
         test_complexite_reconnue_valeur_inconnue),
        ("complexite_reconnue : valeur valide → True",
         test_complexite_reconnue_valeur_valide),
        ("complexite_reconnue : insensible casse/espaces",
         test_complexite_reconnue_insensible_casse_et_espaces),
        ("inbox construire_labels : absente → label posé",
         test_inbox_construire_labels_complexite_absente_pose_le_label),
        ("inbox construire_labels : inconnue → label posé",
         test_inbox_construire_labels_complexite_inconnue_pose_le_label),
        ("inbox construire_labels : valide → rien posé",
         test_inbox_construire_labels_complexite_valide_ne_pose_rien),
        ("inbox construire_labels : pas de doublon si déjà dans LABELS",
         test_inbox_construire_labels_complexite_absente_pas_de_doublon_si_deja_dans_labels),
        ("web construire_labels : absente → label posé",
         test_web_construire_labels_complexite_absente_pose_le_label),
        ("web construire_labels : inconnue → label posé",
         test_web_construire_labels_complexite_inconnue_pose_le_label),
        ("web construire_labels : valide → rien posé",
         test_web_construire_labels_complexite_valide_ne_pose_rien),
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
        ("traiter_fichier : sans COMPLEXITE → label posé",
         test_traiter_fichier_sans_complexite_pose_le_label),
        ("traiter_fichier : COMPLEXITE valide → rien posé",
         test_traiter_fichier_avec_complexite_valide_ne_pose_rien),
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
