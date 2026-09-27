#!/usr/bin/env python3
"""Test de non-régression — issue #662 : purge automatique des sidecars
`rejected/.motifs/<nom>.motif` orphelins, c'est-à-dire dont le fichier rejeté
associé (`rejected/<nom>`) a disparu (typiquement une suppression manuelle
depuis l'explorateur de fichiers, hors de tout mécanisme applicatif).

Couvre `scripts/watcher_issues_inbox.py::purger_motifs_orphelins` :
- un `.motif` sans fichier rejeté associé est supprimé ;
- un `.motif` dont le fichier rejeté existe toujours est conservé ;
- `rejected/.motifs/` absent ou vide ne fait pas planter la fonction.

Purement une purge de fichiers : aucun effet sur le comportement observable
de l'application (pas de log, pas de notification) — non testé ici, absence
volontaire.

Exécution :  python3 -m pytest tests/test_purge_motifs_orphelins_662.py
"""

import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))
sys.path.insert(0, str(RACINE / "scripts"))

import watcher_issues_inbox as w  # noqa: E402


def _cfg(tmp_path: Path) -> w.ConfigInbox:
    rejected_dir = tmp_path / "issues_inbox" / "rejected"
    rejected_dir.mkdir(parents=True)
    return w.ConfigInbox(rejected_dir=rejected_dir)


def test_motif_orphelin_supprime(tmp_path):
    cfg = _cfg(tmp_path)
    dossier_motifs = cfg.rejected_dir / w.DOSSIER_MOTIFS
    dossier_motifs.mkdir()
    chemin_motif = dossier_motifs / f"disparu.txt{w.SUFFIXE_MOTIF}"
    chemin_motif.write_text("motif du rejet", encoding="utf-8")
    # Pas de rejected_dir/disparu.txt : le fichier rejeté a été supprimé.

    nb = w.purger_motifs_orphelins(cfg)

    assert nb == 1
    assert not chemin_motif.exists()


def test_motif_avec_fichier_rejete_present_conserve(tmp_path):
    cfg = _cfg(tmp_path)
    (cfg.rejected_dir / "present.txt").write_text("contenu", encoding="utf-8")
    dossier_motifs = cfg.rejected_dir / w.DOSSIER_MOTIFS
    dossier_motifs.mkdir()
    chemin_motif = dossier_motifs / f"present.txt{w.SUFFIXE_MOTIF}"
    chemin_motif.write_text("motif du rejet", encoding="utf-8")

    nb = w.purger_motifs_orphelins(cfg)

    assert nb == 0
    assert chemin_motif.exists()


def test_dossier_motifs_absent_ne_plante_pas(tmp_path):
    cfg = _cfg(tmp_path)
    assert not (cfg.rejected_dir / w.DOSSIER_MOTIFS).exists()

    assert w.purger_motifs_orphelins(cfg) == 0


def test_dossier_motifs_vide_ne_plante_pas(tmp_path):
    cfg = _cfg(tmp_path)
    (cfg.rejected_dir / w.DOSSIER_MOTIFS).mkdir()

    assert w.purger_motifs_orphelins(cfg) == 0


def test_melange_orphelin_et_conserve(tmp_path):
    cfg = _cfg(tmp_path)
    (cfg.rejected_dir / "present.txt").write_text("contenu", encoding="utf-8")
    dossier_motifs = cfg.rejected_dir / w.DOSSIER_MOTIFS
    dossier_motifs.mkdir()
    motif_conserve = dossier_motifs / f"present.txt{w.SUFFIXE_MOTIF}"
    motif_conserve.write_text("motif", encoding="utf-8")
    motif_orphelin = dossier_motifs / f"disparu.txt{w.SUFFIXE_MOTIF}"
    motif_orphelin.write_text("motif", encoding="utf-8")

    nb = w.purger_motifs_orphelins(cfg)

    assert nb == 1
    assert motif_conserve.exists()
    assert not motif_orphelin.exists()


if __name__ == "__main__":
    sys.exit(__import__("pytest").main([__file__, "-v"]))
