#!/usr/bin/env python3
"""Test de non-régression — issue #648 (régression #647) : le label
`sans-redacteur` posé par `construire_labels()` (scripts/watcher_issues_inbox.py,
issue #647) n'avait été ajouté à AUCUN dépôt existant (`LABELS` de
`nouveau_projet.py` non mis à jour), faisant échouer intégralement `gh issue
create` — et donc rejeter le fichier entier — pour toute issue sans REDACTEUR.

Couvre :
- `nouveau_projet.LABELS` contient désormais `sans-redacteur` (tout nouveau
  projet le provisionne d'office) ;
- `app.issues.creer_issue_gh()` — point d'appel commun de `gh issue create`
  utilisé par `app/issues.py::envoyer()` (formulaire web) et
  `scripts/watcher_issues_inbox.py::_creer_issue()` (dépôt de fichier par
  Claude Chat) — retire automatiquement un label ABSENT du dépôt plutôt que
  de faire échouer toute la création, journalise l'anomalie (charge à
  l'appelant), et boucle correctement si PLUSIEURS labels sont
  successivement manquants (gh ne rapporte qu'un nom à la fois). Une erreur
  gh d'un autre type (dépôt inconnu, etc.) échoue normalement, sans boucler.

Aucun appel réseau réel : `subprocess.run` est monkeypatché dans
`app.issues`.

Exécution :  python3 -m pytest tests/test_label_manquant_648.py
"""

import sys
from pathlib import Path
from types import SimpleNamespace

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import nouveau_projet as np  # noqa: E402
import app.issues as issues  # noqa: E402


def _resultat(returncode, stdout="", stderr=""):
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


def _labels_de_la_commande(commande):
    """Extrait la valeur de --label d'une commande gh simulée (liste vide si
    l'option est absente, cas où plus aucun label n'est à poser)."""
    if "--label" not in commande:
        return []
    return commande[commande.index("--label") + 1].split(",")


def test_labels_contient_sans_redacteur():
    """Tout nouveau projet doit désormais provisionner ce label d'office —
    c'est l'absence de cette entrée qui a causé la régression #648."""
    noms = [nom for nom, _couleur, _description in np.LABELS]
    assert "sans-redacteur" in noms, noms


def test_creer_issue_gh_omet_le_label_manquant_et_reussit(monkeypatch, tmp_path):
    """Reproduit le bug #648 : gh refuse tant que `sans-redacteur` est demandé
    et absent du dépôt. creer_issue_gh() doit réessayer sans ce label, PAS
    rejeter toute la création."""
    appels = []

    def faux_run(commande, **kwargs):
        appels.append(commande)
        if "sans-redacteur" in _labels_de_la_commande(commande):
            return _resultat(1, stderr="could not add label: 'sans-redacteur' not found")
        return _resultat(0, stdout="https://github.com/AlainDelree/x/issues/1\n")

    monkeypatch.setattr(issues.subprocess, "run", faux_run)
    chemin_body = tmp_path / "body.md"
    chemin_body.write_text("corps", encoding="utf-8")

    succes, resultat, labels_eff, labels_omis = issues.creer_issue_gh(
        "AlainDelree/Bridge_Agent", "titre test",
        "bridge,for-linux,sans-redacteur", str(chemin_body),
    )

    assert succes, resultat
    assert resultat == "https://github.com/AlainDelree/x/issues/1"
    assert "sans-redacteur" not in labels_eff, labels_eff
    assert labels_omis == ["sans-redacteur"], labels_omis
    assert len(appels) == 2, "un seul réessai attendu (un seul label fautif)"


def test_creer_issue_gh_plusieurs_labels_manquants_successifs(monkeypatch, tmp_path):
    """gh ne rapporte qu'UN label manquant à la fois : si deux labels sont
    absents du dépôt, la boucle doit les retirer l'un après l'autre jusqu'au
    succès, sans jamais recréer l'issue en double (chaque échec gh est
    atomique — aucune issue créée avant l'ajout des labels)."""

    def faux_run(commande, **kwargs):
        labels = _labels_de_la_commande(commande)
        if "aaa-manquant" in labels:
            return _resultat(1, stderr="could not add label: 'aaa-manquant' not found")
        if "bbb-manquant" in labels:
            return _resultat(1, stderr="could not add label: 'bbb-manquant' not found")
        return _resultat(0, stdout="https://github.com/AlainDelree/x/issues/2\n")

    monkeypatch.setattr(issues.subprocess, "run", faux_run)
    chemin_body = tmp_path / "body.md"
    chemin_body.write_text("corps", encoding="utf-8")

    succes, resultat, labels_eff, labels_omis = issues.creer_issue_gh(
        "AlainDelree/Bridge_Agent", "titre",
        "bridge,aaa-manquant,bbb-manquant", str(chemin_body),
    )

    assert succes, resultat
    assert labels_omis == ["aaa-manquant", "bbb-manquant"], labels_omis
    assert labels_eff == ["bridge"], labels_eff


def test_creer_issue_gh_autre_erreur_gh_ne_boucle_pas(monkeypatch, tmp_path):
    """Une erreur gh qui n'est pas « label introuvable » (dépôt inconnu,
    réseau…) doit échouer normalement, sans tenter de retirer un label."""
    appels = []

    def faux_run(commande, **kwargs):
        appels.append(commande)
        return _resultat(1, stderr="GraphQL: Could not resolve to a Repository")

    monkeypatch.setattr(issues.subprocess, "run", faux_run)
    chemin_body = tmp_path / "body.md"
    chemin_body.write_text("corps", encoding="utf-8")

    succes, resultat, labels_eff, labels_omis = issues.creer_issue_gh(
        "AlainDelree/Inexistant", "titre", "bridge,for-linux", str(chemin_body),
    )

    assert not succes
    assert "Could not resolve" in resultat
    assert labels_omis == []
    assert len(appels) == 1, "aucune boucle : ce n'est pas un label manquant"


def main() -> int:
    tests = [
        ("nouveau_projet.LABELS contient sans-redacteur",
         test_labels_contient_sans_redacteur, ()),
    ]
    echecs = 0
    for nom, fn, args in tests:
        try:
            fn(*args)
            print(f"  ✓ {nom}")
        except AssertionError as e:
            echecs += 1
            print(f"  ✗ {nom}\n      {e}")
    print("\nAutres scénarios (monkeypatch/tmp_path) : exécuter via pytest.")
    if echecs:
        print(f"\n❌ {echecs} scénario(s) en échec.")
        return 1
    print("\n✅ Tous les scénarios exécutables sans pytest passent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
