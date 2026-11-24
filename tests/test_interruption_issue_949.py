#!/usr/bin/env python3
"""Test de non-régression — issue #949 (étude #939, point d'extension #948).

Contexte : jusqu'ici, interrompre une issue dans `new_issue.py` agissait au
niveau du WATCHER entier d'un projet (bouton « Interrompre », #323) — tuer
son arbre de process arrêtait aussi les AUTRES issues en cours du même
projet. Cette issue branche sur le point d'extension posé par #948
(`_verifier_demande_interruption`, appelé à chaque tour de
`_attendre_fin_claude`, ~3s) la détection d'un fichier-sentinelle PROPRE à
une issue (`watcher._chemin_demande_interruption`, sous
`logs/demandes_interruption/`) : SEULE cette issue est arrêtée, needs-human
posé avec un commentaire d'interruption (pas un échec — pas de retry, pas de
diagnostic automatique, pas de « Échec après N tentatives »), le verrou est
libéré et le fichier de demande supprimé. Les autres issues en cours ou en
file du même projet ne sont ni arrêtées ni retardées.

Vérifie :
1. Demande déposée pendant l'attente de claude → arrêt en ~1 tour, sans
   nouvelle tentative, sans commentaire d'échec, `needs-human` + commentaire
   d'interruption sur CETTE issue, verrou libéré, fichier de demande supprimé
   (scenario_interruption_mid_wait...).
2. Portée stricte par (projet, numéro) : une demande pour une autre issue ou
   un autre projet est invisible pour `_verifier_demande_interruption`
   (scenario_demande_scoped_par_projet_et_numero).
3. Deux issues en parallèle (MAX_WRITE_PARALLELE=2) : une seule interrompue,
   l'autre aboutit normalement, sans retard (scenario_deux_issues_paralleles...).
4. Demande périmée : purgée au DÉMARRAGE du traitement d'une issue (même si
   l'issue n'est alors pas interrompue) et à la RELANCE
   (app.interruption.relancer_issue) — scenario_purge_demande_perimee_*.
5. Priorité ABSOLUE sur l'arrêt dit « critique » : une issue de priorité
   critique interrompue reçoit needs-human, `alerte_critique` n'est JAMAIS
   appelée (scenario_priorite_sur_arret_critique).
6. Sans aucune demande, le comportement est STRICTEMENT inchangé (succès
   normal) — scenario_sans_demande_comportement_inchange.
7. Route de dépôt (POST /demander-interruption-issue, app.interruption) :
   issue en cours → déposée ; issue absente des issues en cours → refusée
   sans déposer ; projet inconnu → 404.
8. Point 5 de l'issue (processus détachés) : décision retenue = NE PAS
   tenter de les atteindre (risque de cibler un process d'un autre projet
   jugé trop élevé pour un gain incertain, voir le rapport et
   docs/contexte/interruption_issue.md) — ce scénario VERROUILLE cette
   limite connue par un test : un process détaché (`setsid`, même schéma que
   le `sleep` observé par Alain sur `testvibe`, rattaché à `systemd --user`,
   hors du groupe de process de `claude`) survit bel et bien au nettoyage.

`claude`, `gh` et `notify-send` sont remplacés par de faux exécutables (même
technique que tests/test_worktree_parallelisation_337.py et
tests/test_boucle_attente_claude_948.py) : aucun appel réseau réel.

Exécution :  python3 tests/test_interruption_issue_949.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import contextlib
import os
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import flask  # noqa: E402

import watcher  # noqa: E402
import app.interruption as interruption  # noqa: E402
import app.watchers as watchers_mod  # noqa: E402
from garde_fou_faux_executables import (  # noqa: E402
    verifier_dossier_sous_tmp,
    verifier_faux_executables_actifs,
)

APP_FLASK = flask.Flask(__name__)

# Faux `gh` — stateful sur `issue view --json comments` (même schéma que
# tests/test_worktree_parallelisation_337.py) : `commenter_resultat_avec_retry`
# (issue #237) relit le commentaire posté pour le confirmer — sans cet état,
# chaque succès déclencherait à tort des retries « commentaire introuvable »,
# hors sujet pour ces scénarios.
FAUX_GH = r"""#!/bin/bash
if [ "$1" = "issue" ] && [ "$2" = "comment" ]; then
    numero="$3"
    bodyfile=""
    prev=""
    for arg in "$@"; do
        if [ "$prev" = "--body-file" ]; then
            bodyfile="$arg"
        fi
        prev="$arg"
    done
    if [ -n "$bodyfile" ] && grep -q -- '<!-- bridge:resultat -->' "$bodyfile" 2>/dev/null; then
        touch "$TEST_949_DIR/marqueur-$numero"
    fi
    exit 0
fi
if [ "$1" = "issue" ] && [ "$2" = "view" ]; then
    numero="$3"
    if [ -f "$TEST_949_DIR/marqueur-$numero" ]; then
        echo '{"comments":[{"body":"<!-- bridge:resultat -->\nfake"}]}'
    else
        echo '{"comments":[]}'
    fi
    exit 0
fi
exit 0
"""
FAUX_NOTIFY_SEND = "#!/bin/bash\nexit 0\n"

# Faux `claude` — issue #949. Écrit un marqueur « demarre-<numero> » dès le
# lancement (le test attend ce fichier avant de déposer la demande
# d'interruption, pour ne jamais la poser avant que claude ne tourne vraiment),
# dort une durée pilotée par un fichier « sleep-<numero> » (0.3s par défaut —
# assez pour laisser aboutir une issue NON ciblée), puis écrit un marqueur
# « fin-naturelle-<numero> » et un rapport de clôture normal. Si le process
# est tué pendant le sommeil (interruption), ce second marqueur n'apparaît
# jamais — c'est précisément ce que les scénarios vérifient.
FAUX_CLAUDE = r"""#!/bin/bash
if [ "$#" -ge 2 ]; then
    prompt="${@: -1}"
    numero=$(echo "$prompt" | grep -oE 'Issue #[0-9]+' | head -1 | grep -oE '[0-9]+')
    touch "$TEST_949_DIR/demarre-$numero"
    duree="0.3"
    if [ -f "$TEST_949_DIR/sleep-$numero" ]; then
        duree=$(cat "$TEST_949_DIR/sleep-$numero")
    fi
    sleep "$duree"
    touch "$TEST_949_DIR/fin-naturelle-$numero"
    echo "<!-- bridge:verdict:succes -->"
    echo "✅ Tâche terminée — test #949 numéro $numero"
fi
exit 0
"""

# Faux `claude` — point 5 de l'issue #949. Détache un `sleep` via `setsid`
# (nouvelle session ET nouveau pgid, exactement comme le `sleep 120` observé
# par Alain sur testvibe, rattaché à `systemd --user`), note son PID, puis
# termine immédiatement — reproduit le schéma « claude revient, le process
# détaché survit, HORS du groupe de process que _nettoyer_arbre_claude peut
# atteindre (os.killpg sur le pgid de claude) ».
FAUX_CLAUDE_DETACHE = r"""#!/bin/bash
setsid sleep 30 < /dev/null > /dev/null 2>&1 &
echo $! > "$TEST_PIDFILE_DETACHE_949"
exit 0
"""


def _preparer_bin(tmp_path: Path, claude_script: str = FAUX_CLAUDE) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    for nom, contenu in (("claude", claude_script), ("gh", FAUX_GH), ("notify-send", FAUX_NOTIFY_SEND)):
        chemin = bin_dir / nom
        chemin.write_text(contenu, encoding="utf-8")
        chemin.chmod(chemin.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return bin_dir


def _init_depot_git(rep: Path) -> None:
    subprocess.run(["git", "init", "-q", "-b", "master", str(rep)], check=True)
    (rep / "fichier.txt").write_text("original\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=rep, check=True, capture_output=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                     "commit", "-q", "-m", "initial"], cwd=rep, check=True, capture_output=True)


def _issue_minimale(numero: int, titre: str, priorite: str = "normale") -> dict:
    return {
        "number": numero,
        "title": titre,
        "body": f"| PRIORITE | {priorite} |\n| TIMEOUT | 30s |\n",
        "labels": [{"name": "mode_write"}],
    }


@contextlib.contextmanager
def _intervalle_sondage_reduit(valeur: float):
    ancien = watcher.INTERVALLE_SONDAGE_CLAUDE_S
    watcher.INTERVALLE_SONDAGE_CLAUDE_S = valeur
    try:
        yield
    finally:
        watcher.INTERVALLE_SONDAGE_CLAUDE_S = ancien


@contextlib.contextmanager
def _contexte_isole(tmp_path: Path, **kwargs_config):
    """Isole tout l'état global mutable de watcher.py pertinent pour ces
    scénarios — même esprit que `_contexte_watcher_isole` de
    tests/test_worktree_parallelisation_337.py, complété par
    `DOSSIER_DEMANDES_INTERRUPTION` (issue #949, constante résolue une seule
    fois à l'import, donc jamais dérivée automatiquement d'une
    DOSSIER_LOGS redirigée — même pattern que DOSSIER_VERROUS)."""
    ancien_cfg                     = watcher.CFG
    ancien_dossier_verrous         = watcher.DOSSIER_VERROUS
    ancien_dossier_demandes        = watcher.DOSSIER_DEMANDES_INTERRUPTION
    ancien_dossier_logs            = watcher.DOSSIER_LOGS
    ancien_fichier_historique      = watcher.FICHIER_HISTORIQUE
    ancien_fichier_etat_timeout    = watcher.FICHIER_ETAT_TIMEOUT
    ancien_fichier_etat_ambiance   = watcher.FICHIER_ETAT_AMBIANCE
    ancien_dossier_worktrees_dedie = watcher.DOSSIER_WORKTREES_DEDIE
    ancien_threads                 = list(watcher._threads_ecriture)
    ancien_issues_en_cours         = set(watcher.issues_en_cours)
    ancien_bloquees                = set(watcher._issues_write_bloquees_needs_human)

    watcher.DOSSIER_VERROUS = tmp_path / "verrous"
    watcher.DOSSIER_DEMANDES_INTERRUPTION = tmp_path / "demandes_interruption"
    watcher.DOSSIER_LOGS = tmp_path / "logs"
    watcher.FICHIER_HISTORIQUE = watcher.DOSSIER_LOGS / "historique_durees.json"
    watcher.FICHIER_ETAT_TIMEOUT = watcher.DOSSIER_LOGS / "etat_timeout.json"
    watcher.FICHIER_ETAT_AMBIANCE = watcher.DOSSIER_LOGS / "etat_ambiance.json"
    watcher.DOSSIER_WORKTREES_DEDIE = tmp_path / "worktrees_dedies"
    verifier_dossier_sous_tmp(watcher.DOSSIER_WORKTREES_DEDIE, "DOSSIER_WORKTREES_DEDIE")
    watcher._threads_ecriture.clear()
    watcher.issues_en_cours.clear()
    watcher._issues_write_bloquees_needs_human.clear()
    watcher.CFG = watcher.Config(**kwargs_config)
    try:
        yield
    finally:
        watcher.CFG = ancien_cfg
        watcher.DOSSIER_VERROUS = ancien_dossier_verrous
        watcher.DOSSIER_DEMANDES_INTERRUPTION = ancien_dossier_demandes
        watcher.DOSSIER_LOGS = ancien_dossier_logs
        watcher.FICHIER_HISTORIQUE = ancien_fichier_historique
        watcher.FICHIER_ETAT_TIMEOUT = ancien_fichier_etat_timeout
        watcher.FICHIER_ETAT_AMBIANCE = ancien_fichier_etat_ambiance
        watcher.DOSSIER_WORKTREES_DEDIE = ancien_dossier_worktrees_dedie
        watcher._threads_ecriture.clear()
        watcher._threads_ecriture.extend(ancien_threads)
        watcher.issues_en_cours.clear()
        watcher.issues_en_cours.update(ancien_issues_en_cours)
        watcher._issues_write_bloquees_needs_human.clear()
        watcher._issues_write_bloquees_needs_human.update(ancien_bloquees)


@contextlib.contextmanager
def _capturer_compte_rendu():
    """Enregistre chaque appel à commenter_issue/ajouter_label/alerte_critique
    SANS remplacer leur effet réel (contrairement à
    tests/test_arret_verdict_illisible_commits_777.py) : plusieurs scénarios
    ci-dessous exercent le chemin de SUCCÈS normal
    (`commenter_resultat_avec_retry`, issue #237), qui relit le commentaire
    posté via un VRAI appel `gh issue view` — le remplacer purement et
    simplement ferait disparaître le marqueur que le faux `gh` stateful
    (FAUX_GH) a besoin de voir pour répondre « trouvé », et déclencherait des
    retries hors sujet pour ces tests."""
    commentaires, labels_poses, appels_alerte_critique = [], [], []
    ancien_commenter = watcher.commenter_issue
    ancien_ajouter_label = watcher.ajouter_label
    ancien_notifier = watcher.notifier
    ancien_notifier_fin_sse = watcher.notifier_fin_sse
    ancien_alerte_critique = watcher.alerte_critique

    def _commenter(num, msg):
        commentaires.append((num, msg))
        return ancien_commenter(num, msg)

    def _ajouter_label(num, lab):
        labels_poses.append((num, lab))
        return ancien_ajouter_label(num, lab)

    watcher.commenter_issue = _commenter
    watcher.ajouter_label = _ajouter_label
    watcher.notifier = lambda *a, **k: None
    watcher.notifier_fin_sse = lambda *a, **k: None
    watcher.alerte_critique = lambda *a, **k: appels_alerte_critique.append((a, k))
    try:
        yield commentaires, labels_poses, appels_alerte_critique
    finally:
        watcher.commenter_issue = ancien_commenter
        watcher.ajouter_label = ancien_ajouter_label
        watcher.notifier = ancien_notifier
        watcher.notifier_fin_sse = ancien_notifier_fin_sse
        watcher.alerte_critique = ancien_alerte_critique


@contextlib.contextmanager
def _path_et_test_dir(bin_dir: Path, test_dir: Path):
    ancien_path = os.environ.get("PATH", "")
    os.environ["PATH"] = f"{bin_dir}{os.pathsep}{ancien_path}"
    os.environ["TEST_949_DIR"] = str(test_dir)
    try:
        verifier_faux_executables_actifs(bin_dir, ["claude", "gh", "notify-send"])
    except Exception:
        os.environ["PATH"] = ancien_path
        raise
    try:
        yield
    finally:
        if ancien_path:
            os.environ["PATH"] = ancien_path
        else:
            os.environ.pop("PATH", None)
        os.environ.pop("TEST_949_DIR", None)


# ─── Scénario 1 : demande déposée pendant l'attente → arrêt, needs-human ───

def scenario_interruption_mid_wait_arrete_sans_echec():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        rep_travail = tmp_path / "projet"
        rep_travail.mkdir()
        _init_depot_git(rep_travail)
        test_dir = tmp_path / "etat"
        test_dir.mkdir()
        bin_dir = _preparer_bin(tmp_path)
        numero = 94901

        with _contexte_isole(
            tmp_path, nom="test949a", depot="AlainDelree/depot-test949a",
            rep_travail=rep_travail, topic_ntfy="test949a",
            max_essais=3, timeout_claude=30, max_write_parallele=1,
        ), _intervalle_sondage_reduit(0.2), \
             _path_et_test_dir(bin_dir, test_dir), \
             _capturer_compte_rendu() as (commentaires, labels_poses, _alertes):

            (test_dir / f"sleep-{numero}").write_text("10", encoding="utf-8")
            issue = _issue_minimale(numero, "Test #949 — interruption en cours d'attente")

            debut = time.monotonic()
            thread = threading.Thread(target=watcher.traiter_issue, args=(issue, False))
            thread.start()

            fin_attente = time.monotonic() + 10
            while not (test_dir / f"demarre-{numero}").exists() and time.monotonic() < fin_attente:
                time.sleep(0.05)
            assert (test_dir / f"demarre-{numero}").exists(), "claude n'a jamais démarré"

            chemin_demande = watcher._chemin_demande_interruption("test949a", numero)
            chemin_demande.parent.mkdir(parents=True, exist_ok=True)
            chemin_demande.write_text("heure=test origine=test949\n", encoding="utf-8")

            thread.join(timeout=10)
            duree = time.monotonic() - debut
            assert not thread.is_alive(), "le traitement n'a jamais rendu la main"

        assert not (test_dir / f"fin-naturelle-{numero}").exists(), (
            "claude a eu le temps de terminer naturellement (sleep 10s) — "
            "l'interruption n'a pas arrêté le process à temps"
        )
        assert duree < 5, f"l'arrêt a pris trop longtemps ({duree:.2f}s) pour ~1 tour de 0.2s"

        msgs_num = [m for n, m in commentaires if n == numero]
        msgs_interruption = [m for m in msgs_num if "Interrompue sur demande" in m]
        assert len(msgs_interruption) == 1, (
            f"un seul commentaire d'interruption attendu sur cette issue, obtenu : {msgs_num}"
        )
        assert not any("Échec après" in m for m in msgs_num), msgs_num

        labs_num = [l for n, l in labels_poses if n == numero]
        assert labs_num == [watcher.LABEL_ECHEC], f"needs-human attendu une seule fois : {labs_num}"

        assert not chemin_demande.exists(), "le fichier de demande aurait dû être supprimé une fois traitée"

        verrou = watcher._chemin_verrou(rep_travail)
        assert not verrou.exists(), "le verrou de REP_TRAVAIL aurait dû être libéré"
    return {"duree": round(duree, 2)}


# ─── Scénario 2 : portée stricte (projet, numéro) ──────────────────────────

def scenario_demande_scoped_par_projet_et_numero():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        with _contexte_isole(
            tmp_path, nom="projetA949", depot="AlainDelree/depot-a949",
            rep_travail=tmp_path, topic_ntfy="projetA949",
        ):
            def _poser(projet, numero):
                chemin = watcher._chemin_demande_interruption(projet, numero)
                chemin.parent.mkdir(parents=True, exist_ok=True)
                chemin.write_text("x", encoding="utf-8")

            # Autre ISSUE du même projet : ignorée.
            _poser("projetA949", 999)
            assert watcher._verifier_demande_interruption(123) is False

            # Même numéro, AUTRE projet : ignorée.
            _poser("projetB949", 123)
            assert watcher._verifier_demande_interruption(123) is False

            # Ce projet, cette issue précisément : détectée.
            _poser("projetA949", 123)
            assert watcher._verifier_demande_interruption(123) is True
    return {}


# ─── Scénario 3 : deux issues en parallèle, une seule interrompue ──────────

def scenario_deux_issues_paralleles_une_seule_interrompue():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        rep_travail = tmp_path / "projet"
        rep_travail.mkdir()
        _init_depot_git(rep_travail)
        test_dir = tmp_path / "etat"
        test_dir.mkdir()
        bin_dir = _preparer_bin(tmp_path)
        numero_ok, numero_interrompu = 94911, 94912

        with _contexte_isole(
            tmp_path, nom="test949par", depot="AlainDelree/depot-test949par",
            rep_travail=rep_travail, topic_ntfy="test949par",
            max_essais=3, timeout_claude=30, max_write_parallele=2,
        ), _intervalle_sondage_reduit(0.2), \
             _path_et_test_dir(bin_dir, test_dir), \
             _capturer_compte_rendu() as (commentaires, labels_poses, _alertes):

            (test_dir / f"sleep-{numero_ok}").write_text("0.3", encoding="utf-8")
            (test_dir / f"sleep-{numero_interrompu}").write_text("10", encoding="utf-8")

            issue_ok = _issue_minimale(numero_ok, "Test #949 — issue non ciblée")
            issue_interrompu = _issue_minimale(numero_interrompu, "Test #949 — issue interrompue")

            watcher.traiter_issue(issue_ok, dry_run=False)
            watcher.traiter_issue(issue_interrompu, dry_run=False)
            actifs = watcher._threads_ecriture_actifs()
            assert len(actifs) == 2, f"les deux issues auraient dû être dispatchées en thread : {actifs}"

            fin_attente = time.monotonic() + 10
            while not (test_dir / f"demarre-{numero_interrompu}").exists() and time.monotonic() < fin_attente:
                time.sleep(0.05)
            assert (test_dir / f"demarre-{numero_interrompu}").exists()

            chemin_demande = watcher._chemin_demande_interruption("test949par", numero_interrompu)
            chemin_demande.parent.mkdir(parents=True, exist_ok=True)
            chemin_demande.write_text("heure=test origine=test949\n", encoding="utf-8")

            for entree in actifs:
                entree["thread"].join(timeout=15)
                assert not entree["thread"].is_alive(), f"thread #{entree['numero']} toujours actif après 15s"

        # L'issue NON ciblée a abouti normalement, sans retard ni effet de bord.
        assert (test_dir / f"fin-naturelle-{numero_ok}").exists(), (
            "l'issue NON ciblée par la demande aurait dû aboutir normalement"
        )
        assert not any(n == numero_ok for n, _ in labels_poses if _ == watcher.LABEL_ECHEC), (
            "l'issue non ciblée n'aurait jamais dû recevoir needs-human"
        )

        # L'issue CIBLÉE a été interrompue : pas de fin naturelle, needs-human.
        assert not (test_dir / f"fin-naturelle-{numero_interrompu}").exists(), (
            "l'issue ciblée aurait dû être arrêtée avant la fin de son sommeil (10s)"
        )
        msgs_cible = [m for n, m in commentaires if n == numero_interrompu]
        assert msgs_cible and "Interrompue sur demande" in msgs_cible[-1], msgs_cible
        labs_cible = [l for n, l in labels_poses if n == numero_interrompu]
        assert watcher.LABEL_ECHEC in labs_cible, labs_cible
    return {}


# ─── Scénario 4 : demandes périmées purgées (démarrage / relance) ─────────

def scenario_purge_demande_perimee_au_demarrage():
    """Une demande déjà présente AVANT que le traitement d'une issue ne
    démarre (watcher éteint quand elle a été déposée, ou exécution
    précédente non terminée) ne doit JAMAIS interrompre ce NOUVEAU
    traitement — purgée en tout premier, avant toute tentative."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        rep_travail = tmp_path / "projet"
        rep_travail.mkdir()
        _init_depot_git(rep_travail)
        test_dir = tmp_path / "etat"
        test_dir.mkdir()
        bin_dir = _preparer_bin(tmp_path)
        numero = 94921

        with _contexte_isole(
            tmp_path, nom="test949d", depot="AlainDelree/depot-test949d",
            rep_travail=rep_travail, topic_ntfy="test949d",
            max_essais=3, timeout_claude=30, max_write_parallele=1,
        ), _path_et_test_dir(bin_dir, test_dir), \
             _capturer_compte_rendu() as (commentaires, labels_poses, _alertes):

            chemin_demande = watcher._chemin_demande_interruption("test949d", numero)
            chemin_demande.parent.mkdir(parents=True, exist_ok=True)
            chemin_demande.write_text("heure=perimee origine=test949\n", encoding="utf-8")

            issue = _issue_minimale(numero, "Test #949 — demande périmée purgée au démarrage")
            watcher.traiter_issue(issue, dry_run=False)

        assert (test_dir / f"fin-naturelle-{numero}").exists(), (
            "l'issue aurait dû aboutir normalement malgré la demande périmée présente avant son démarrage"
        )
        assert not chemin_demande.exists(), "la demande périmée aurait dû être purgée au démarrage"
        assert not any(l == watcher.LABEL_ECHEC for _n, l in labels_poses), labels_poses
        assert not any("Interrompue sur demande" in m for _n, m in commentaires), commentaires
    return {}


def scenario_purge_demande_perimee_a_la_relance():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        ancien_dossier = watcher.DOSSIER_DEMANDES_INTERRUPTION
        watcher.DOSSIER_DEMANDES_INTERRUPTION = tmp_path / "demandes_interruption"
        cfg = SimpleNamespace(nom="projetRelance949", depot="AlainDelree/depot-relance949")
        chemin_demande = watcher._chemin_demande_interruption(cfg.nom, 555)
        chemin_demande.parent.mkdir(parents=True, exist_ok=True)
        chemin_demande.write_text("heure=perimee origine=test949\n", encoding="utf-8")
        try:
            with mock.patch.object(interruption, "projet_par_depot", lambda d: cfg), \
                 mock.patch.object(interruption, "_retirer_label_gh", lambda d, n, l: ("succes", "ok")), \
                 mock.patch.object(interruption, "_commenter_gh", lambda d, n, m: ("succes", "ok")), \
                 mock.patch.object(interruption.github_status, "signaler_resultat_gh", lambda *a, **k: None):
                statut, etapes = interruption.relancer_issue(cfg.depot, 555)
            assert statut == "ok", etapes
            assert not chemin_demande.exists(), "la demande périmée aurait dû être purgée à la relance"
        finally:
            watcher.DOSSIER_DEMANDES_INTERRUPTION = ancien_dossier
    return {}


# ─── Scénario 5 : priorité sur l'arrêt dit « critique » ────────────────────

def scenario_priorite_sur_arret_critique():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        rep_travail = tmp_path / "projet"
        rep_travail.mkdir()
        _init_depot_git(rep_travail)
        test_dir = tmp_path / "etat"
        test_dir.mkdir()
        bin_dir = _preparer_bin(tmp_path)
        numero = 94931

        with _contexte_isole(
            tmp_path, nom="test949e", depot="AlainDelree/depot-test949e",
            rep_travail=rep_travail, topic_ntfy="test949e",
            max_essais=1, timeout_claude=30, max_write_parallele=1,
        ), _intervalle_sondage_reduit(0.2), \
             _path_et_test_dir(bin_dir, test_dir), \
             _capturer_compte_rendu() as (commentaires, labels_poses, appels_alerte_critique):

            (test_dir / f"sleep-{numero}").write_text("10", encoding="utf-8")
            issue = _issue_minimale(numero, "Test #949 — priorité sur arrêt critique", priorite="critique")

            thread = threading.Thread(target=watcher.traiter_issue, args=(issue, False))
            thread.start()
            fin_attente = time.monotonic() + 10
            while not (test_dir / f"demarre-{numero}").exists() and time.monotonic() < fin_attente:
                time.sleep(0.05)
            assert (test_dir / f"demarre-{numero}").exists()

            chemin_demande = watcher._chemin_demande_interruption("test949e", numero)
            chemin_demande.parent.mkdir(parents=True, exist_ok=True)
            chemin_demande.write_text("heure=test origine=test949\n", encoding="utf-8")

            thread.join(timeout=10)
            assert not thread.is_alive()

        assert not appels_alerte_critique, (
            f"l'arrêt dit « critique » (retry infini, jamais needs-human) n'aurait "
            f"jamais dû se déclencher — l'interruption explicite a priorité "
            f"absolue : appels={appels_alerte_critique}"
        )
        labs_num = [l for n, l in labels_poses if n == numero]
        assert watcher.LABEL_ECHEC in labs_num, (
            f"needs-human attendu malgré la priorité 'critique' de l'issue : {labs_num}"
        )
    return {}


# ─── Scénario 6 : sans demande, comportement strictement inchangé ─────────

def scenario_sans_demande_comportement_inchange():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        rep_travail = tmp_path / "projet"
        rep_travail.mkdir()
        _init_depot_git(rep_travail)
        test_dir = tmp_path / "etat"
        test_dir.mkdir()
        bin_dir = _preparer_bin(tmp_path)
        numero = 94941

        with _contexte_isole(
            tmp_path, nom="test949f", depot="AlainDelree/depot-test949f",
            rep_travail=rep_travail, topic_ntfy="test949f",
            max_essais=3, timeout_claude=30, max_write_parallele=1,
        ), _path_et_test_dir(bin_dir, test_dir), \
             _capturer_compte_rendu() as (commentaires, labels_poses, appels_alerte_critique):

            (test_dir / f"sleep-{numero}").write_text("0.3", encoding="utf-8")
            issue = _issue_minimale(numero, "Test #949 — aucune demande, contrôle")
            watcher.traiter_issue(issue, dry_run=False)

        assert (test_dir / f"fin-naturelle-{numero}").exists(), "l'issue aurait dû aboutir normalement"
        assert not any(l == watcher.LABEL_ECHEC for _n, l in labels_poses), labels_poses
        assert not appels_alerte_critique
    return {}


# ─── Scénario 7 : route de dépôt (/demander-interruption-issue) ───────────

def _appeler_route_demande(payload: dict):
    with APP_FLASK.test_request_context("/demander-interruption-issue", json=payload):
        resp = interruption.route_demander_interruption()
    if isinstance(resp, tuple):
        body, code = resp
    else:
        body, code = resp, 200
    return body.get_json(), code


def scenario_route_depot_issue_en_cours_est_deposee():
    cfg = SimpleNamespace(nom="projetRoute949a", depot="AlainDelree/depot-route949a")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        ancien_dossier = watcher.DOSSIER_DEMANDES_INTERRUPTION
        watcher.DOSSIER_DEMANDES_INTERRUPTION = tmp_path / "demandes_interruption"
        try:
            with mock.patch.object(interruption, "projet_par_depot", lambda d: cfg), \
                 mock.patch.object(watchers_mod, "tache_en_cours",
                                    lambda c: [{"numero": 777, "mode": "ecriture", "rep": "x"}]):
                corps, code = _appeler_route_demande({"depot": cfg.depot, "numero": 777})
            assert code == 200, corps
            assert corps["succes"] is True and corps["deposee"] is True, corps
            assert watcher._chemin_demande_interruption(cfg.nom, 777).exists()
        finally:
            watcher.DOSSIER_DEMANDES_INTERRUPTION = ancien_dossier
    return {}


def scenario_route_depot_issue_absente_est_refusee():
    cfg = SimpleNamespace(nom="projetRoute949b", depot="AlainDelree/depot-route949b")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        ancien_dossier = watcher.DOSSIER_DEMANDES_INTERRUPTION
        watcher.DOSSIER_DEMANDES_INTERRUPTION = tmp_path / "demandes_interruption"
        try:
            with mock.patch.object(interruption, "projet_par_depot", lambda d: cfg), \
                 mock.patch.object(watchers_mod, "tache_en_cours", lambda c: []):
                corps, code = _appeler_route_demande({"depot": cfg.depot, "numero": 888})
            assert code == 200, corps
            assert corps["succes"] is True and corps["deposee"] is False, corps
            assert not watcher._chemin_demande_interruption(cfg.nom, 888).exists()
        finally:
            watcher.DOSSIER_DEMANDES_INTERRUPTION = ancien_dossier
    return {}


def scenario_route_depot_projet_inconnu_404():
    with mock.patch.object(interruption, "projet_par_depot", lambda d: None):
        corps, code = _appeler_route_demande({"depot": "AlainDelree/inconnu949", "numero": 1})
    assert code == 404, corps
    assert corps["succes"] is False, corps
    return {}


# ─── Scénario 8 : point 5 — processus détachés, limite connue verrouillée ─

def attendre_mort(pid: int, delai_max: float = 2.0) -> bool:
    fin = time.monotonic() + delai_max
    while time.monotonic() < fin:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        time.sleep(0.05)
    return False


def scenario_processus_detache_survit_limite_connue():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        watcher.CFG = watcher.Config(
            nom="test949detache", depot="AlainDelree/depot-test949detache",
            rep_travail=tmp_path, topic_ntfy="test949detache",
        )
        pidfile = tmp_path / "pid_detache"
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        fake_claude = bin_dir / "claude"
        fake_claude.write_text(FAUX_CLAUDE_DETACHE, encoding="utf-8")
        fake_claude.chmod(fake_claude.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

        ancien_path = os.environ.get("PATH", "")
        os.environ["PATH"] = f"{bin_dir}{os.pathsep}{ancien_path}"
        os.environ["TEST_PIDFILE_DETACHE_949"] = str(pidfile)
        try:
            verifier_faux_executables_actifs(bin_dir, ["claude"])
            succes, _sortie = watcher.lancer_claude(
                numero=94951, titre="Test #949 — process détaché", body="Corps",
                dry_run=False, mode=watcher.MODE_LECTURE,
                timeout=15, cwd=tmp_path,
            )
        finally:
            if ancien_path:
                os.environ["PATH"] = ancien_path
            else:
                os.environ.pop("PATH", None)
            os.environ.pop("TEST_PIDFILE_DETACHE_949", None)

        assert succes, "le faux claude lui-même devait réussir (exit 0)"
        assert pidfile.exists(), "le faux claude n'a pas écrit le PID du process détaché"
        pid_detache = int(pidfile.read_text().strip())
        try:
            # Limite CONNUE et ACCEPTÉE (issue #949, point 5, rapport) : un
            # process détaché (nouveau pgid/session) survit au nettoyage,
            # qui ne cible QUE le pgid de claude — jamais par nom, jamais en
            # dehors de ce groupe.
            assert not attendre_mort(pid_detache, delai_max=1.0), (
                "le process détaché a été tué — la limite documentée par le "
                "rapport #949 ne serait alors plus exacte, à corriger"
            )
        finally:
            try:
                os.kill(pid_detache, signal.SIGKILL)
            except ProcessLookupError:
                pass
    return {"pid_detache": pid_detache}


def main():
    if os.name == "nt":
        print("  (ignoré : ce test s'appuie sur bash/git POSIX, non applicable sous Windows)")
        return 0

    tests = [
        ("interruption pendant l'attente → arrêt ~1 tour, needs-human, sans échec",
         scenario_interruption_mid_wait_arrete_sans_echec),
        ("portée stricte (projet, numéro) : autre issue/projet ignoré",
         scenario_demande_scoped_par_projet_et_numero),
        ("deux issues en parallèle : une seule interrompue, l'autre aboutit",
         scenario_deux_issues_paralleles_une_seule_interrompue),
        ("demande périmée purgée au démarrage du traitement",
         scenario_purge_demande_perimee_au_demarrage),
        ("demande périmée purgée à la relance (app.interruption.relancer_issue)",
         scenario_purge_demande_perimee_a_la_relance),
        ("priorité absolue sur l'arrêt dit « critique »",
         scenario_priorite_sur_arret_critique),
        ("sans demande : comportement strictement inchangé",
         scenario_sans_demande_comportement_inchange),
        ("route /demander-interruption-issue : issue en cours → déposée",
         scenario_route_depot_issue_en_cours_est_deposee),
        ("route /demander-interruption-issue : issue absente → refusée",
         scenario_route_depot_issue_absente_est_refusee),
        ("route /demander-interruption-issue : projet inconnu → 404",
         scenario_route_depot_projet_inconnu_404),
        ("point 5 : process détaché (setsid) survit — limite connue verrouillée",
         scenario_processus_detache_survit_limite_connue),
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

    if echecs:
        print(f"\n❌ {echecs} scénario(s) en échec.")
        return 1
    print("\n✅ Tous les scénarios passent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
