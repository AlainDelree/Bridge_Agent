#!/usr/bin/env python3
"""Test de non-régression — issue #900 : mode interactif, étape 1.

Marqueur « interactif » (étude #888) posé par le label GitHub
`mode_interactif`, orthogonal aux labels de mode (`mode_write`/
`mode_scratch`) — la déduction du MODE (`_deduire_mode`) reste inchangée, à
trois valeurs. Cette étape ne change rien au lancement de CCL : elle pose
seulement le marqueur et exclut l'issue de la calibration automatique du
TIMEOUT (sa durée dépend d'Alain, pas de la tâche).

Couvre :
1. `labels_github.LABELS` provisionne désormais `mode_interactif` (même
   patron que `mode_scratch`/`sans-redacteur`, cf. issue #816) — sans cette
   entrée, un dépôt existant ne recevrait jamais ce label.
2. `watcher.est_interactif` : marqueur absent, retenu (écriture/lecture
   active), et les deux cas de repli décidés avec Alain — lecture seule et
   issue destinée à Windows (label `for-windows`) — jamais un rejet,
   toujours un avertissement informatif.
3. `watcher._deduire_mode_et_logguer` journalise l'avertissement de repli
   (log.warning), sans jamais changer le MODE réellement appliqué.
4. `scripts/watcher_issues_inbox.py::construire_labels` pose
   `mode_interactif` quand le champ d'en-tête `INTERACTIF` vaut exactement
   "oui", et seulement dans ce cas (valeur différente ou champ absent :
   issue automatique, sans rejet).
5. Exclusion de la calibration automatique du TIMEOUT : `_finaliser_succes`
   (clôture réussie) et `_tracer_tentative_expiree` (tentative expirée)
   n'appellent ni `enregistrer_duree` ni `maj_calibration_timeout` pour une
   issue interactive retenue — comportement inchangé sinon.

Exécution :  python3 -m pytest tests/test_mode_interactif_900.py
        ou : python3 tests/test_mode_interactif_900.py
"""

import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))
sys.path.insert(0, str(RACINE / "scripts"))

import pytest  # noqa: E402

import watcher  # noqa: E402
import watcher_issues_inbox as wii  # noqa: E402
import labels_github  # noqa: E402


# ─── 1. Label provisionné d'office sur tout dépôt (issue #816) ────────────

def test_label_mode_interactif_dans_labels_github():
    noms = [nom for nom, _couleur, _description in labels_github.LABELS]
    assert "mode_interactif" in noms, (
        f"'mode_interactif' absent de labels_github.LABELS — sans cette "
        f"entrée, aucun dépôt (nouveau ou existant) ne provisionne ce label, "
        f"et construire_labels() l'omettrait silencieusement (même cause "
        f"que #785/#816). Labels présents : {noms}"
    )


# ─── 2. est_interactif : marqueur absent, retenu, et les deux replis ──────

def test_est_interactif_absent():
    assert watcher.est_interactif([], watcher.MODE_LECTURE) == (False, "")
    assert watcher.est_interactif(["mode_write"], watcher.MODE_ECRITURE) == (False, "")


def test_est_interactif_retenu_en_ecriture():
    interactif, avertissement = watcher.est_interactif(
        ["mode_write", "mode_interactif"], watcher.MODE_ECRITURE)
    assert interactif is True
    assert avertissement == ""


def test_est_interactif_retenu_en_lecture_active():
    interactif, avertissement = watcher.est_interactif(
        ["mode_scratch", "mode_interactif"], watcher.MODE_LECTURE_ACTIVE)
    assert interactif is True
    assert avertissement == ""


def test_est_interactif_repli_lecture_seule():
    """Décision avec Alain : la lecture seule n'est JAMAIS interactive."""
    interactif, avertissement = watcher.est_interactif(
        ["mode_interactif"], watcher.MODE_LECTURE)
    assert interactif is False
    assert avertissement, "un avertissement informatif était attendu, pas un silence"
    assert "lecture seule" in avertissement


def test_est_interactif_repli_windows():
    """Décision avec Alain : le mode interactif ne concerne que le ThinkPad
    (CCL) — une issue destinée à Windows reste automatique même marquée."""
    interactif, avertissement = watcher.est_interactif(
        ["mode_write", "mode_interactif", "for-windows"], watcher.MODE_ECRITURE)
    assert interactif is False
    assert avertissement, "un avertissement informatif était attendu, pas un silence"
    assert "Windows" in avertissement


def test_est_interactif_ne_leve_jamais():
    """Aucune combinaison de labels/mode ne doit lever — même un mode
    inconnu (défensif, ne devrait pas arriver en pratique)."""
    watcher.est_interactif(["mode_interactif", "for-windows", "mode_scratch"], "mode_inconnu")


# ─── 3. _deduire_mode_et_logguer journalise l'avertissement de repli ──────

def test_deduire_mode_et_logguer_journalise_repli_interactif(caplog):
    ancien_cfg = watcher.CFG
    watcher.CFG = watcher.Config(nom="t900", depot="x/y", rep_travail=Path("/tmp"))
    try:
        body = "| PROJET | bridge_agent |\n| TIMEOUT | 300s |\n"
        with caplog.at_level("WARNING", logger=watcher.log.name):
            mode, _mode_txt, _priorite, _critique, _timeout, _modele, _avert_mode = (
                watcher._deduire_mode_et_logguer(9900, "Test #900", body, ["mode_interactif"], None)
            )
        assert mode == watcher.MODE_LECTURE, (
            "sans label mode_write/mode_scratch, le MODE réel reste lecture seule "
            "— rien ne change dans le lancement de CCL à cette étape")
        assert any("interactif" in rec.message and "lecture seule" in rec.message
                   for rec in caplog.records), (
            f"le repli (lecture seule) aurait dû être journalisé — messages : "
            f"{[rec.message for rec in caplog.records]}"
        )
    finally:
        watcher.CFG = ancien_cfg


def test_deduire_mode_et_logguer_silencieux_sans_marqueur(caplog):
    ancien_cfg = watcher.CFG
    watcher.CFG = watcher.Config(nom="t900b", depot="x/y", rep_travail=Path("/tmp"))
    try:
        body = "| PROJET | bridge_agent |\n| TIMEOUT | 300s |\n"
        with caplog.at_level("WARNING", logger=watcher.log.name):
            watcher._deduire_mode_et_logguer(9901, "Test #900 bis", body, [], None)
        assert not any("interactif" in rec.message for rec in caplog.records), (
            "aucun avertissement interactif attendu sans le label mode_interactif"
        )
    finally:
        watcher.CFG = ancien_cfg


# ─── 4. construire_labels (dépôt d'issues par fichier) ────────────────────

def _champs(interactif_brut=None, mode_brut="écriture"):
    return {
        "labels_brut": "", "mode_brut": mode_brut, "interactif_brut": interactif_brut,
        "redacteur": "bridge_agent", "corps": "| COMPLEXITE | normal |\n",
    }


def test_construire_labels_interactif_oui():
    labels = wii.construire_labels(_champs(interactif_brut="oui")).split(",")
    assert "mode_interactif" in labels


def test_construire_labels_interactif_absent():
    labels = wii.construire_labels(_champs(interactif_brut=None)).split(",")
    assert "mode_interactif" not in labels


def test_construire_labels_interactif_valeur_non_reconnue():
    """Valeur différente de "oui" (ex. faute de frappe) : issue automatique,
    sans rejet — même esprit que les champs optionnels voisins."""
    labels = wii.construire_labels(_champs(interactif_brut="non")).split(",")
    assert "mode_interactif" not in labels


def test_construire_labels_interactif_casse_et_espaces_tolerees():
    labels = wii.construire_labels(_champs(interactif_brut="  OUI  ")).split(",")
    assert "mode_interactif" in labels


def test_interactif_dans_champs_entete():
    assert "INTERACTIF" in wii.CHAMPS_ENTETE


def test_extraire_champs_lit_interactif():
    contenu = "| PROJET | bridge_agent |\n| INTERACTIF | oui |\n#Titre: Test\n\nCorps.\n"
    champs = wii.extraire_champs(contenu)
    assert champs["interactif_brut"] == "oui"
    # la ligne d'en-tête est retirée du corps, comme MODE/TIMEOUT/MODELE.
    assert "INTERACTIF" not in champs["corps"]


# ─── 5. Exclusion de la calibration automatique du TIMEOUT ────────────────

@pytest.fixture
def _compteurs_calibration(monkeypatch):
    appels = {"duree": 0, "calib": 0}
    monkeypatch.setattr(watcher, "enregistrer_duree",
                         lambda *a, **k: appels.__setitem__("duree", appels["duree"] + 1))
    monkeypatch.setattr(watcher, "maj_calibration_timeout",
                         lambda *a, **k: (appels.__setitem__("calib", appels["calib"] + 1), 100.0)[1])
    return appels


def test_finaliser_succes_interactif_exclut_calibration(monkeypatch, tmp_path, _compteurs_calibration):
    monkeypatch.setattr(watcher, "commenter_resultat_avec_retry", lambda numero, message: True)
    monkeypatch.setattr(watcher, "fermer_issue", lambda numero: True)
    monkeypatch.setattr(watcher, "editer_dernier_commentaire", lambda numero, message: True)
    monkeypatch.setattr(watcher, "notifier", lambda *a, **k: None)
    monkeypatch.setattr(watcher, "notifier_fin_sse", lambda numero: None)

    ancien_cfg = watcher.CFG
    watcher.CFG = watcher.Config(nom="t900c", depot="AlainDelree/x", rep_travail=tmp_path)
    try:
        watcher._finaliser_succes(
            9902, "Titre", "", labels=["mode_write", "mode_interactif"],
            mode=watcher.MODE_ECRITURE, timeout=300,
            avertissement_conflit="", avertissement_worktree_deja_pris="",
            avertissement_worktree_repris="",
            sortie="<!-- bridge:verdict:succes -->\n✅ OK\n",
            debut_traitement=0.0, nb_projets_actifs_debut=1, est_relance=False,
            dry_run=False, cwd_effectif=tmp_path, tete_avant_traitement=None,
            tentative=1, timeout_suggere_lancement=None, estimation_lancement={},
        )
    finally:
        watcher.CFG = ancien_cfg

    assert _compteurs_calibration == {"duree": 0, "calib": 0}, (
        "une issue interactive ne doit rien enregistrer dans l'historique des "
        "durées ni dans la calibration du TIMEOUT"
    )


def test_finaliser_succes_normal_alimente_calibration(monkeypatch, tmp_path, _compteurs_calibration):
    """Non-régression : sans le label mode_interactif, le comportement
    existant (enregistrement + calibration) reste inchangé."""
    monkeypatch.setattr(watcher, "commenter_resultat_avec_retry", lambda numero, message: True)
    monkeypatch.setattr(watcher, "fermer_issue", lambda numero: True)
    monkeypatch.setattr(watcher, "editer_dernier_commentaire", lambda numero, message: True)
    monkeypatch.setattr(watcher, "notifier", lambda *a, **k: None)
    monkeypatch.setattr(watcher, "notifier_fin_sse", lambda numero: None)

    ancien_cfg = watcher.CFG
    watcher.CFG = watcher.Config(nom="t900d", depot="AlainDelree/x", rep_travail=tmp_path)
    try:
        watcher._finaliser_succes(
            9903, "Titre", "", labels=["mode_write"],
            mode=watcher.MODE_ECRITURE, timeout=300,
            avertissement_conflit="", avertissement_worktree_deja_pris="",
            avertissement_worktree_repris="",
            sortie="<!-- bridge:verdict:succes -->\n✅ OK\n",
            debut_traitement=0.0, nb_projets_actifs_debut=1, est_relance=False,
            dry_run=False, cwd_effectif=tmp_path, tete_avant_traitement=None,
            tentative=1, timeout_suggere_lancement=None, estimation_lancement={},
        )
    finally:
        watcher.CFG = ancien_cfg

    assert _compteurs_calibration == {"duree": 1, "calib": 1}


def test_tracer_tentative_expiree_interactif_exclut_calibration(tmp_path, _compteurs_calibration):
    ancien_cfg = watcher.CFG
    watcher.CFG = watcher.Config(nom="t900e", depot="AlainDelree/x", rep_travail=tmp_path)
    try:
        watcher._tracer_tentative_expiree(
            9904, "Titre", "", ["mode_write", "mode_interactif"], watcher.MODE_ECRITURE,
            debut_traitement=0.0, nb_projets_actifs_debut=1,
            tentative=1, timeout=300, timeout_suggere_lancement=None, estimation_lancement={},
        )
    finally:
        watcher.CFG = ancien_cfg

    assert _compteurs_calibration == {"duree": 0, "calib": 0}


def test_tracer_tentative_expiree_normal_alimente_calibration(tmp_path, _compteurs_calibration):
    """Non-régression : sans le label mode_interactif, comportement inchangé."""
    ancien_cfg = watcher.CFG
    watcher.CFG = watcher.Config(nom="t900f", depot="AlainDelree/x", rep_travail=tmp_path)
    try:
        watcher._tracer_tentative_expiree(
            9905, "Titre", "", ["mode_write"], watcher.MODE_ECRITURE,
            debut_traitement=0.0, nb_projets_actifs_debut=1,
            tentative=1, timeout=300, timeout_suggere_lancement=None, estimation_lancement={},
        )
    finally:
        watcher.CFG = ancien_cfg

    assert _compteurs_calibration == {"duree": 1, "calib": 1}


def main() -> int:
    return pytest.main([str(Path(__file__)), "-q"])


if __name__ == "__main__":
    sys.exit(main())
