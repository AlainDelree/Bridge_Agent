#!/usr/bin/env python3
"""Test de non-régression — issue #786 : un label absent du dépôt était
retiré silencieusement à la création d'une issue, quel que soit ce qu'il
pilotait. Le dernier incident en date : `mode_scratch` (ARME la lecture
active) manquait de la liste provisionnée d'office — l'issue s'est exécutée
en lecture seule pendant une heure, sans la moindre trace.

Couvre le changement de comportement de `app.issues.creer_issue_gh` /
`LABELS_CRITIQUES` (issue #786) :
- un label CRITIQUE absent (`for-linux`, `for-windows`, `mode_write`,
  `mode_scratch` — ce qui pilote la destination ou le mode d'exécution)
  fait désormais ÉCHOUER la création, avec un message nommant la cause et la
  commande de correction (`gh label create`), SANS boucler ;
- un label de CONFORT absent (notification, traçabilité…) continue d'être
  omis en best-effort comme avant (#648), toujours journalisé.

Aucun appel réseau réel : `subprocess.run` est monkeypatché dans
`app.issues`.

Exécution :  python3 -m pytest tests/test_label_critique_786.py
"""

import sys
from pathlib import Path
from types import SimpleNamespace

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import app.issues as issues  # noqa: E402


def _resultat(returncode, stdout="", stderr=""):
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


def _labels_de_la_commande(commande):
    if "--label" not in commande:
        return []
    return commande[commande.index("--label") + 1].split(",")


def test_labels_critiques_sont_bien_mode_et_destination():
    """La répartition (issue #786) : critiques = ce qui pilote le mode
    d'exécution ou la destination de l'issue — rien d'autre."""
    assert issues.LABELS_CRITIQUES == {"for-linux", "for-windows", "mode_write", "mode_scratch"}


def test_creer_issue_gh_refuse_si_mode_scratch_absent(monkeypatch, tmp_path):
    """Reproduit l'incident #786 : `mode_scratch` absent du dépôt. La
    création doit être REFUSÉE (pas créée en lecture seule à l'insu de
    tous), en un seul appel gh (pas de boucle de réessai sur un label
    critique), avec un message nommant la cause ET la commande de
    correction."""
    appels = []

    def faux_run(commande, **kwargs):
        appels.append(commande)
        if "mode_scratch" in _labels_de_la_commande(commande):
            return _resultat(1, stderr="could not add label: 'mode_scratch' not found")
        return _resultat(0, stdout="https://github.com/AlainDelree/x/issues/9\n")

    monkeypatch.setattr(issues.subprocess, "run", faux_run)
    chemin_body = tmp_path / "body.md"
    chemin_body.write_text("corps", encoding="utf-8")

    succes, resultat, labels_eff, labels_omis = issues.creer_issue_gh(
        "AlainDelree/VieuxDepot", "titre lecture active",
        "bridge,for-linux,mode_scratch", str(chemin_body),
    )

    assert not succes
    assert "mode_scratch" in resultat, resultat
    assert "AlainDelree/VieuxDepot" in resultat, resultat
    assert "gh label create" in resultat, resultat
    assert labels_omis == [], labels_omis
    assert len(appels) == 1, "aucune boucle : un label critique absent doit refuser immédiatement"


def test_creer_issue_gh_refuse_si_for_linux_absent(monkeypatch, tmp_path):
    """Même garde pour la destination : `for-linux` absent ne doit jamais
    faire créer une issue qu'aucun watcher ne verra jamais."""

    def faux_run(commande, **kwargs):
        if "for-linux" in _labels_de_la_commande(commande):
            return _resultat(1, stderr="could not add label: 'for-linux' not found")
        return _resultat(0, stdout="https://github.com/AlainDelree/x/issues/10\n")

    monkeypatch.setattr(issues.subprocess, "run", faux_run)
    chemin_body = tmp_path / "body.md"
    chemin_body.write_text("corps", encoding="utf-8")

    succes, resultat, _labels_eff, labels_omis = issues.creer_issue_gh(
        "AlainDelree/VieuxDepot", "titre", "bridge,for-linux", str(chemin_body),
    )

    assert not succes
    assert "for-linux" in resultat, resultat
    assert labels_omis == [], labels_omis


def test_creer_issue_gh_label_confort_absent_continue_comme_avant(monkeypatch, tmp_path):
    """Non-régression #648 : un label de CONFORT absent (ex. sans-redacteur)
    ne doit PAS bloquer la création, même quand un label critique est
    présent et correctement posé à côté."""
    appels = []

    def faux_run(commande, **kwargs):
        appels.append(commande)
        if "sans-redacteur" in _labels_de_la_commande(commande):
            return _resultat(1, stderr="could not add label: 'sans-redacteur' not found")
        return _resultat(0, stdout="https://github.com/AlainDelree/x/issues/11\n")

    monkeypatch.setattr(issues.subprocess, "run", faux_run)
    chemin_body = tmp_path / "body.md"
    chemin_body.write_text("corps", encoding="utf-8")

    succes, resultat, labels_eff, labels_omis = issues.creer_issue_gh(
        "AlainDelree/Bridge_Agent", "titre",
        "bridge,for-linux,mode_write,sans-redacteur", str(chemin_body),
    )

    assert succes, resultat
    assert "sans-redacteur" not in labels_eff, labels_eff
    assert labels_omis == ["sans-redacteur"], labels_omis
    assert len(appels) == 2


def test_creer_issue_gh_refuse_meme_si_decouvert_apres_un_label_confort(monkeypatch, tmp_path):
    """Un label de confort ET un label critique manquent tous deux : gh ne
    rapporte qu'un nom à la fois (toujours le confort ici, listé en premier
    par cette fausse commande) — le label critique découvert à l'itération
    suivante doit tout de même déclencher le refus, pas une 3e boucle qui
    finirait par créer l'issue sans lui."""
    appels = []

    def faux_run(commande, **kwargs):
        appels.append(commande)
        labels = _labels_de_la_commande(commande)
        if "sans-redacteur" in labels:
            return _resultat(1, stderr="could not add label: 'sans-redacteur' not found")
        if "mode_write" in labels:
            return _resultat(1, stderr="could not add label: 'mode_write' not found")
        return _resultat(0, stdout="https://github.com/AlainDelree/x/issues/12\n")

    monkeypatch.setattr(issues.subprocess, "run", faux_run)
    chemin_body = tmp_path / "body.md"
    chemin_body.write_text("corps", encoding="utf-8")

    succes, resultat, _labels_eff, labels_omis = issues.creer_issue_gh(
        "AlainDelree/VieuxDepot", "titre",
        "bridge,mode_write,sans-redacteur", str(chemin_body),
    )

    assert not succes
    assert "mode_write" in resultat, resultat
    assert labels_omis == ["sans-redacteur"], (
        "le label de confort retiré avant la découverte du critique reste "
        "journalisé dans labels_omis, même si la création finit refusée"
    )
    assert len(appels) == 2


def test_message_label_critique_absent_nomme_la_cause_et_le_correctif():
    msg = issues._message_label_critique_absent("mode_scratch", "AlainDelree/VieuxDepot")
    assert "mode_scratch" in msg
    assert "AlainDelree/VieuxDepot" in msg
    assert 'gh label create "mode_scratch" --repo AlainDelree/VieuxDepot' in msg


def main() -> int:
    tests = [
        ("LABELS_CRITIQUES == mode + destination",
         test_labels_critiques_sont_bien_mode_et_destination, ()),
        ("_message_label_critique_absent nomme cause + correctif",
         test_message_label_critique_absent_nomme_la_cause_et_le_correctif, ()),
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
