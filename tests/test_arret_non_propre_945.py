#!/usr/bin/env python3
"""Test de non-régression — issue #945 : trace de la cause d'un arrêt du
watcher de projet + détection d'un arrêt non propre au démarrage suivant.

Couvre uniquement la logique PURE (aucun process réel, aucun vrai signal) :
1. formuler_avertissement_arret_non_propre : formulation du message, avec et
   sans PID connu.
2. detecter_arret_non_propre : ne journalise RIEN si le fichier PID est
   absent (sortie propre précédente, qui l'a retiré) ou si son PID est
   encore vivant (prudence — ne devrait pas arriver après le verrou #908) ;
   journalise un avertissement net s'il existe mais que son process est mort.
3. _nom_signal : résolution du nom lisible d'un signal connu, repli sur le
   numéro brut pour un numéro inconnu.
4. _gestionnaire_signal_arret : journalise le signal reçu, retire le fichier
   PID, puis sys.exit(0) — même arrêt propre que KeyboardInterrupt.

Exécution :  python3 tests/test_arret_non_propre_945.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import signal
import sys
import tempfile
from pathlib import Path
from unittest import mock

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import watcher  # noqa: E402


def test_formuler_avertissement_pid_connu():
    msg = watcher.formuler_avertissement_arret_non_propre(1234, "2026-11-23 17:45:44,000 [INFO] Tentative 1/3...")
    assert "pid 1234" in msg
    assert "arrêt précédent non propre" in msg.lower() or "Arrêt précédent non propre" in msg
    assert "17:45:44" in msg


def test_formuler_avertissement_pid_inconnu():
    msg = watcher.formuler_avertissement_arret_non_propre(None, "(journal vide)")
    assert "pid inconnu" in msg
    assert "(journal vide)" in msg


def test_derniere_ligne_journal_lit_la_derniere_ligne_non_vide():
    with tempfile.TemporaryDirectory() as d:
        fichier = Path(d) / "watcher-test.log"
        fichier.write_text(
            "2026-11-23 17:44:43,000 [INFO] Bridge watcher démarré\n"
            "2026-11-23 17:45:44,000 [INFO] Tentative 1/3...\n"
            "\n",  # ligne vide finale : ignorée
            encoding="utf-8",
        )
        assert watcher._derniere_ligne_journal(fichier) == "2026-11-23 17:45:44,000 [INFO] Tentative 1/3..."


def test_derniere_ligne_journal_fichier_absent():
    assert watcher._derniere_ligne_journal(Path("/chemin/inexistant/watcher-x.log")) == "(journal introuvable)"


def _config_minimal(tmp: Path) -> "watcher.Config":
    return watcher.Config(
        nom="test_945",
        depot="exemple/depot-test",
        rep_travail=tmp,
        topic_ntfy="test-topic",
    )


def test_detecter_arret_non_propre_aucun_fichier_pid():
    """Sortie propre précédente (ou toute première exécution) : pas de
    fichier PID → silence total, aucun log.warning."""
    with tempfile.TemporaryDirectory() as d:
        cfg = _config_minimal(Path(d))
        with mock.patch.object(watcher, "DOSSIER_LOGS", Path(d)), \
             mock.patch.object(watcher.log, "warning") as m_warn:
            watcher.detecter_arret_non_propre(cfg)
        m_warn.assert_not_called()


def test_detecter_arret_non_propre_pid_mort_journalise_avertissement():
    """Fichier PID présent, process mort (_pid_vivant renvoie False) : un seul
    avertissement net, avec le PID et la dernière ligne du journal."""
    with tempfile.TemporaryDirectory() as d:
        dossier = Path(d)
        cfg = _config_minimal(dossier)
        (dossier / "watcher-test_945.pid").write_text("999999")
        (dossier / "watcher-test_945.log").write_text(
            "2026-11-23 17:45:44,000 [INFO] Tentative 1/3...\n", encoding="utf-8"
        )
        with mock.patch.object(watcher, "DOSSIER_LOGS", dossier), \
             mock.patch.object(watcher, "_pid_vivant", return_value=False), \
             mock.patch.object(watcher.log, "warning") as m_warn:
            watcher.detecter_arret_non_propre(cfg)
        m_warn.assert_called_once()
        (texte,) = m_warn.call_args.args
        assert "999999" in texte
        assert "17:45:44" in texte


def test_detecter_arret_non_propre_pid_vivant_ne_journalise_rien():
    """Prudence (ne devrait pas arriver après acquerir_verrou_processus) :
    PID encore vivant → aucun avertissement, ce n'est pas un arrêt non
    propre."""
    with tempfile.TemporaryDirectory() as d:
        dossier = Path(d)
        cfg = _config_minimal(dossier)
        (dossier / "watcher-test_945.pid").write_text("1")
        with mock.patch.object(watcher, "DOSSIER_LOGS", dossier), \
             mock.patch.object(watcher, "_pid_vivant", return_value=True), \
             mock.patch.object(watcher.log, "warning") as m_warn:
            watcher.detecter_arret_non_propre(cfg)
        m_warn.assert_not_called()


def test_detecter_arret_non_propre_pid_illisible_journalise_quand_meme():
    """Fichier PID présent mais contenu corrompu (pas un entier) : traité
    comme PID inconnu, l'avertissement est tout de même émis (le fichier
    existe et n'a par construction pas pu être retiré proprement)."""
    with tempfile.TemporaryDirectory() as d:
        dossier = Path(d)
        cfg = _config_minimal(dossier)
        (dossier / "watcher-test_945.pid").write_text("pas-un-pid")
        with mock.patch.object(watcher, "DOSSIER_LOGS", dossier), \
             mock.patch.object(watcher.log, "warning") as m_warn:
            watcher.detecter_arret_non_propre(cfg)
        m_warn.assert_called_once()
        (texte,) = m_warn.call_args.args
        assert "pid inconnu" in texte


def test_nom_signal_connu_et_inconnu():
    assert watcher._nom_signal(signal.SIGTERM) == "SIGTERM"
    assert watcher._nom_signal(signal.SIGINT) == "SIGINT"
    assert watcher._nom_signal(999999) == "999999"


def test_gestionnaire_signal_arret_journalise_nettoie_et_sort():
    """Le gestionnaire SIGTERM journalise le nom du signal, retire le fichier
    PID de CFG.nom, puis sys.exit(0) — même arrêt propre que l'auto-extinction
    et KeyboardInterrupt (issue #945 point 1)."""
    with tempfile.TemporaryDirectory() as d:
        dossier = Path(d)
        pid_file = dossier / "watcher-test_945_sig.pid"
        pid_file.write_text(str(watcher.os.getpid()))
        cfg = watcher.Config(nom="test_945_sig", depot="exemple/depot-test",
                              rep_travail=dossier, topic_ntfy="t")
        with mock.patch.object(watcher, "DOSSIER_LOGS", dossier), \
             mock.patch.object(watcher, "CFG", cfg), \
             mock.patch.object(watcher.log, "info") as m_info:
            try:
                watcher._gestionnaire_signal_arret(signal.SIGTERM, None)
                raise AssertionError("sys.exit(0) attendu, jamais atteint")
            except SystemExit as e:
                assert e.code == 0
        assert not pid_file.exists(), "le fichier PID doit être retiré par l'arrêt propre"
        m_info.assert_called_once()
        (texte,) = m_info.call_args.args
        assert "SIGTERM" in texte


def main():
    tests = [
        ("formuler_avertissement_arret_non_propre : PID connu", test_formuler_avertissement_pid_connu),
        ("formuler_avertissement_arret_non_propre : PID inconnu", test_formuler_avertissement_pid_inconnu),
        ("_derniere_ligne_journal : dernière ligne non vide", test_derniere_ligne_journal_lit_la_derniere_ligne_non_vide),
        ("_derniere_ligne_journal : fichier absent", test_derniere_ligne_journal_fichier_absent),
        ("detecter_arret_non_propre : aucun fichier PID → silence", test_detecter_arret_non_propre_aucun_fichier_pid),
        ("detecter_arret_non_propre : PID mort → avertissement", test_detecter_arret_non_propre_pid_mort_journalise_avertissement),
        ("detecter_arret_non_propre : PID vivant → silence", test_detecter_arret_non_propre_pid_vivant_ne_journalise_rien),
        ("detecter_arret_non_propre : PID illisible → avertissement quand même", test_detecter_arret_non_propre_pid_illisible_journalise_quand_meme),
        ("_nom_signal : connu et inconnu", test_nom_signal_connu_et_inconnu),
        ("_gestionnaire_signal_arret : log + nettoyage + sortie 0", test_gestionnaire_signal_arret_journalise_nettoie_et_sort),
    ]
    echecs = 0
    for nom, fn in tests:
        try:
            fn()
            print(f"  ✓ {nom}")
        except AssertionError as e:
            echecs += 1
            print(f"  ✗ {nom}\n      {e}")
        except Exception as e:  # noqa: BLE001
            echecs += 1
            print(f"  ✗ {nom} — erreur inattendue : {type(e).__name__}: {e}")

    if echecs:
        print(f"\n❌ {echecs} scénario(s) en échec.")
        return 1
    print("\n✅ Tous les scénarios passent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
