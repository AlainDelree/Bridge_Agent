#!/usr/bin/env python3
"""Test de non-régression — issue #785 : le mode « lecture active » déclaré
dans l'en-tête d'une issue n'était jamais réellement armé.

Cause établie : `mode_scratch` (label GitHub qui arme la lecture active,
issue #327) manquait de `nouveau_projet.LABELS` — exactement la même
régression que `sans-redacteur` (#648) et `agent-claude`/`agent-vibe`
(#768) : un nouveau projet ne provisionnait jamais ce label sur son dépôt
GitHub, si bien que `creer_issue_gh` (app/issues.py, comportement #648)
l'omettait silencieusement faute d'exister — une issue déclarant
`| MODE | lecture active |` dans son en-tête s'exécutait alors en lecture
seule, sans qu'aucune erreur ni avertissement ne le signale.

Couvre :
- `nouveau_projet.LABELS` contient désormais `mode_scratch` (comme
  `mode_write`) — c'est l'absence de cette entrée qui a causé #785.
- `extraire_mode_entete` reconnaît le MODE déclaré dans l'en-tête de façon
  tolérante (accents/casse/synonymes), sans jamais le confondre avec le
  champ voisin `MODELE`, et renvoie None si le champ est absent.
- `_texte_ecart_mode` détecte un écart entre le MODE déclaré dans l'en-tête
  et le MODE réellement retenu (déduit des labels) — reproduit exactement
  le scénario #785 (en-tête « lecture active », aucun label de mode posé) —
  et reste silencieux quand les deux coïncident ou que le champ est absent.
- `_deduire_mode_et_logguer` journalise cet écart (log.warning) ET le
  retourne pour insertion dans le commentaire de clôture — sans jamais
  changer le MODE réellement appliqué (toujours celui des labels, seul
  mécanisme sous contrôle d'accès).

Exécution :  python3 tests/test_ecart_mode_entete_785.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import logging
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import watcher  # noqa: E402
import nouveau_projet as np  # noqa: E402


def scenario_labels_nouveau_projet_contient_mode_scratch():
    """Régression directe de #785 : tout nouveau projet doit désormais
    provisionner `mode_scratch` d'office sur son dépôt GitHub, comme
    `mode_write` — c'est l'oubli de cette entrée qui a causé le bug."""
    noms = [nom for nom, _couleur, _description in np.LABELS]
    assert "mode_write" in noms, noms
    assert "mode_scratch" in noms, (
        f"'mode_scratch' absent de nouveau_projet.LABELS — régression #785 : "
        f"sans cette entrée, aucun nouveau dépôt ne provisionne ce label, et "
        f"creer_issue_gh() l'omet silencieusement à chaque création d'issue "
        f"en lecture active. Labels présents : {noms}"
    )
    return {"labels": noms}


def scenario_extraire_mode_entete():
    """Reconnaissance tolérante du champ `| MODE | ... |`, sans confusion
    avec `MODELE`, et None si le champ est absent."""
    assert watcher.extraire_mode_entete("| MODE | écriture |\n") == watcher.MODE_ECRITURE
    assert watcher.extraire_mode_entete("| mode | ECRITURE |\n") == watcher.MODE_ECRITURE
    assert watcher.extraire_mode_entete("| MODE | write |\n") == watcher.MODE_ECRITURE
    assert watcher.extraire_mode_entete("| MODE | lecture active |\n") == watcher.MODE_LECTURE_ACTIVE
    assert watcher.extraire_mode_entete("| MODE | scratch |\n") == watcher.MODE_LECTURE_ACTIVE
    assert watcher.extraire_mode_entete("| MODE | lecture seule |\n") == watcher.MODE_LECTURE
    assert watcher.extraire_mode_entete("| MODE | lecture |\n") == watcher.MODE_LECTURE
    # « lecture active » ne doit jamais être absorbé par « lecture » seul —
    # même piège que reconnaitreModeTexte (static/js/creation.js) et
    # reconnaitre_mode (scripts/watcher_issues_inbox.py).
    assert watcher.extraire_mode_entete("| MODE | Lecture Active (scratch) |\n") == watcher.MODE_LECTURE_ACTIVE
    # Jamais confondu avec le champ voisin MODELE.
    assert watcher.extraire_mode_entete("| MODELE | claude-opus-4-8 |\n| MODE | écriture |\n") == watcher.MODE_ECRITURE
    assert watcher.extraire_mode_entete("| MODELE | claude-opus-4-8 |\n") is None
    # Champ absent ou valeur non reconnue.
    assert watcher.extraire_mode_entete("| PROJET | chesscoach |\n") is None
    assert watcher.extraire_mode_entete("") is None
    return {}


def scenario_texte_ecart_mode():
    """`_texte_ecart_mode` reproduit le scénario exact de #785 : en-tête
    déclarant « lecture active », mais AUCUN label de mode posé (donc
    `_deduire_mode([])` retombe sur `MODE_LECTURE`) → avertissement non vide.
    Reste silencieux quand les deux coïncident, ou quand l'en-tête ne
    déclare aucun MODE."""
    body_lecture_active = "| PROJET | chesscoach |\n| MODE | lecture active |\n| TIMEOUT | 900s |\n"
    body_ecriture = "| PROJET | chesscoach |\n| MODE | écriture |\n"
    body_sans_mode = "| PROJET | chesscoach |\n| TIMEOUT | 300s |\n"

    # Reproduction de #785 : label mode_scratch absent du dépôt → mode
    # réellement déduit = lecture, malgré l'en-tête.
    texte = watcher._texte_ecart_mode(body_lecture_active, watcher.MODE_LECTURE)
    assert texte, "un écart aurait dû être détecté (en-tête 'lecture active' vs mode réel 'lecture')"
    assert "lecture active" in texte and "lecture seule" in texte, texte

    # Cohérent (label bien posé, comme pour mode_write qui fonctionne) : pas
    # d'avertissement.
    assert watcher._texte_ecart_mode(body_lecture_active, watcher.MODE_LECTURE_ACTIVE) == ""
    assert watcher._texte_ecart_mode(body_ecriture, watcher.MODE_ECRITURE) == ""

    # Champ MODE absent de l'en-tête : rien à comparer, jamais d'avertissement
    # (une issue sans MODE explicite retombe légitimement sur lecture seule).
    assert watcher._texte_ecart_mode(body_sans_mode, watcher.MODE_LECTURE) == ""
    return {"texte": texte}


def scenario_deduire_mode_et_logguer_journalise_et_retourne_ecart():
    """`_deduire_mode_et_logguer` (point d'entrée réel, appelé par
    `_traiter_issue_synchrone` au lancement) journalise l'écart (log.warning,
    issue #785 point 3) ET le retourne comme dernier élément du tuple, sans
    changer le MODE réellement appliqué (toujours celui des labels)."""
    ancien_cfg = watcher.CFG
    watcher.CFG = watcher.Config(nom="t785", depot="x/y", rep_travail=Path("/tmp"))
    try:
        enregistrements = []
        gestionnaire = logging.Handler()
        gestionnaire.emit = lambda rec: enregistrements.append(rec.getMessage())
        watcher.log.addHandler(gestionnaire)
        try:
            body = "| PROJET | chesscoach |\n| MODE | lecture active |\n| TIMEOUT | 900s |\n"
            # Aucun label de mode posé — reproduction de #785 : creer_issue_gh
            # aurait silencieusement omis 'mode_scratch', absent du dépôt.
            mode, _mode_txt, _priorite, _critique, _timeout, _modele, avertissement = (
                watcher._deduire_mode_et_logguer(9785, "Test #785", body, [], None)
            )
        finally:
            watcher.log.removeHandler(gestionnaire)

        assert mode == watcher.MODE_LECTURE, (
            "le MODE réellement appliqué doit rester celui des labels (lecture, "
            "aucun label posé) — jamais corrigé à la volée depuis le texte de l'en-tête")
        assert avertissement, "l'écart MODE déclaré/retenu aurait dû être retourné pour le commentaire de clôture"
        assert "Écart de MODE" in avertissement, avertissement
        assert any("écart MODE" in msg for msg in enregistrements), (
            f"l'écart aurait dû être journalisé (log.warning) — messages capturés : {enregistrements}")

        # Cas sain (label mode_write bien posé, comme pour une issue en
        # écriture qui fonctionne) : aucun avertissement, rien à journaliser.
        enregistrements.clear()
        gestionnaire2 = logging.Handler()
        gestionnaire2.emit = lambda rec: enregistrements.append(rec.getMessage())
        watcher.log.addHandler(gestionnaire2)
        try:
            body_ok = "| PROJET | chesscoach |\n| MODE | écriture |\n| TIMEOUT | 900s |\n"
            mode_ok, _mt, _pr, _cr, _to, _md, avertissement_ok = (
                watcher._deduire_mode_et_logguer(9786, "Test #785 bis", body_ok, ["mode_write"], None)
            )
        finally:
            watcher.log.removeHandler(gestionnaire2)
        assert mode_ok == watcher.MODE_ECRITURE
        assert avertissement_ok == ""
        assert not any("écart MODE" in msg for msg in enregistrements), enregistrements
    finally:
        watcher.CFG = ancien_cfg
    return {}


def main():
    tests = [
        ("nouveau_projet.LABELS contient mode_scratch (cause #785)",
         scenario_labels_nouveau_projet_contient_mode_scratch),
        ("extraire_mode_entete : reconnaissance tolérante + distinction MODELE",
         scenario_extraire_mode_entete),
        ("_texte_ecart_mode : détecte l'écart lecture active déclarée / lecture réelle",
         scenario_texte_ecart_mode),
        ("_deduire_mode_et_logguer : journalise et retourne l'écart sans changer le MODE réel",
         scenario_deduire_mode_et_logguer_journalise_et_retourne_ecart),
    ]

    logging.getLogger().addHandler(logging.NullHandler())
    watcher.log.setLevel(logging.WARNING)  # assez bas pour que les scénarios capturent le log.warning attendu

    echecs = 0
    for nom, fn in tests:
        try:
            fn()
            print(f"  ✓ {nom}")
        except AssertionError as e:
            echecs += 1
            print(f"  ✗ {nom}\n      {e}")
        except Exception as e:
            echecs += 1
            print(f"  ✗ {nom} — exception inattendue : {e!r}")

    if echecs:
        print(f"\n❌ {echecs} scénario(s) en échec.")
        return 1
    print("\n✅ Tous les scénarios passent.")
    return 0


if __name__ == "__main__":
    import sys as _sys
    _sys.exit(main())
