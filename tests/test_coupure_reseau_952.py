#!/usr/bin/env python3
"""Test de non-régression — issue #952.

Contexte : coupure internet réelle du 24/11/2026 (~14:10-14:35) ayant
laissé trois issues bancales sur trois projets (rummikub #265, alchess
#383, diagnostique_programme #115) — voir ARCHITECTURE.md §17 pour le
détail des trois mécanismes vérifiés ici :

1. `lister_issues()` distingue désormais son propre échec (`None`) d'une
   liste vide (`[]`) — scenario_liste_en_echec_distincte_de_liste_vide.
2. toute publication GitHub (commentaire, label, fermeture) qui échoue
   après ses tentatives immédiates est mise en attente durable puis
   rejouée, dans l'ordre, sans jamais être republiée deux fois —
   scenario_publication_mise_en_attente_puis_rejouee_sans_doublon.
3. un watcher redémarré alors que des publications restent en attente les
   rejoue à son prochain démarrage, AVANT le premier cycle —
   scenario_rejeu_au_demarrage.
4. une tentative `claude` dont l'échec coïncide avec une coupure réseau
   détectée n'est PAS comptée, et est refaite à l'identique au retour du
   réseau — scenario_tentative_pendant_panne_non_comptee.
5. une panne plus longue que le maximum d'attente entraîne un abandon
   NORMAL (pas un blocage indéfini), publication en attente comprise —
   scenario_panne_plus_longue_que_le_maximum.
6. un vrai échec avec réseau disponible garde EXACTEMENT le comportement
   d'avant l'issue #952 (le garde-fou réseau ne change rien hors panne) —
   scenario_echec_reel_reseau_disponible_comportement_inchange.

`gh` et `claude` sont remplacés par de faux exécutables (même technique que
tests/test_interruption_issue_949.py et tests/test_premier_marqueur_et_
arret_rapide_763.py) : aucun appel réseau réel. `_reseau_disponible` est
monkeypatché pour les scénarios 4/5/6 (jamais de vraie sonde TCP dans ce
fichier) ; les durées d'attente (`INTERVALLE_SONDAGE_RESEAU_S`,
`DUREE_MAX_ATTENTE_RESEAU_S`) sont raccourcies pour la durée des scénarios
qui en ont besoin, puis restaurées.

Non automatisable (nécessite une vraie coupure réseau de la machine) : voir
VERIFICATIONS_MANUELLES.md, section « Résistance à une coupure réseau
(issue #952) ».

Exécution :  python3 tests/test_coupure_reseau_952.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import contextlib
import json
import os
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest import mock

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import watcher  # noqa: E402
from garde_fou_faux_executables import verifier_faux_executables_actifs  # noqa: E402


class StopLoop(Exception):
    """Sentinelle : rompt la boucle infinie de main() sans tuer le process
    de test (même patron que test_auto_extinction_217.py)."""


# Faux `gh` partagé, stateful via `$CONTROL_DIR` (même esprit que
# tests/test_interruption_issue_949.py) — gère `issue comment` (vérifie la
# présence effective à la relecture, comme le vrai `gh issue view`),
# `close` et `edit --add-label`, chacun contrôlable en échec via un fichier
# `$CONTROL_DIR/mode_<action>` ("ok" par défaut, "fail" pour simuler une
# panne). Réutilisé par tous les scénarios de ce fichier qui ont besoin
# d'un `gh` réaliste (pas seulement « toujours 0 »).
_FAUX_GH_SCRIPT = r"""#!/bin/bash
mode_file() { cat "$CONTROL_DIR/$1" 2>/dev/null || echo ok; }
if [ "$1" = "issue" ] && [ "$2" = "list" ]; then
    echo '[]'
    exit 0
fi
if [ "$1" = "issue" ] && [ "$2" = "comment" ]; then
    numero="$3"
    bodyfile=""
    prev=""
    for arg in "$@"; do
        if [ "$prev" = "--body-file" ]; then bodyfile="$arg"; fi
        prev="$arg"
    done
    if [ "$(mode_file mode_comment)" = "fail" ]; then
        echo "erreur simulee commentaire" >&2
        exit 1
    fi
    mkdir -p "$CONTROL_DIR/comments_$numero"
    n=$(ls "$CONTROL_DIR/comments_$numero" 2>/dev/null | wc -l)
    cp "$bodyfile" "$CONTROL_DIR/comments_$numero/$((n+1)).txt"
    exit 0
fi
if [ "$1" = "issue" ] && [ "$2" = "view" ]; then
    numero="$3"
    dossier="$CONTROL_DIR/comments_$numero"
    if [ -d "$dossier" ] && [ -n "$(ls -A "$dossier" 2>/dev/null)" ]; then
        corps=$(cat "$dossier"/*.txt | python3 -c "import json,sys;print(json.dumps(sys.stdin.read()))")
        echo "{\"comments\":[{\"body\":$corps}]}"
    else
        echo '{"comments":[]}'
    fi
    exit 0
fi
if [ "$1" = "issue" ] && [ "$2" = "close" ]; then
    if [ "$(mode_file mode_close)" = "fail" ]; then
        echo "erreur simulee close" >&2
        exit 1
    fi
    echo "$3" >> "$CONTROL_DIR/closed.txt"
    exit 0
fi
if [ "$1" = "issue" ] && [ "$2" = "edit" ]; then
    numero="$3"
    label=""
    prev=""
    for arg in "$@"; do
        if [ "$prev" = "--add-label" ]; then label="$arg"; fi
        prev="$arg"
    done
    if [ "$(mode_file mode_label)" = "fail" ]; then
        echo "erreur simulee label" >&2
        exit 1
    fi
    echo "$numero:$label" >> "$CONTROL_DIR/labels.txt"
    exit 0
fi
exit 0
"""


def _ecrire_executable(chemin: Path, script: str) -> None:
    chemin.write_text(script, encoding="utf-8")
    chemin.chmod(chemin.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


# ─── Scénario 1 : liste en échec distincte d'une liste vide ────────────────

def _ecrire_conf(rep_travail: Path, nom: str) -> Path:
    conf = tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False, encoding="utf-8")
    conf.write(
        f"NOM = {nom}\n"
        "DEPOT = exemple/depot-test\n"
        f"REP_TRAVAIL = {rep_travail}\n"
        f"TOPIC_NTFY = {nom}\n"
        "INTERVALLE = 1\n"
        "DELAI_INACTIVITE_MIN = 20\n"
    )
    conf.close()
    return Path(conf.name)


def _executer_main_scripte(nom_cfg, lister_plan, sleeps, cap=10, extra_patches=None):
    """Pilote le VRAI watcher.main() avec horloge mockée et `lister_issues`
    scripté — même patron que test_auto_extinction_217.py, étendu pour
    espionner `_reconcilier_issues_en_cours_fermees` et
    `rejouer_publications_en_attente` (issue #952)."""
    horloge = {"t": 0.0}
    compteur = {"lister": 0}
    etat = {
        "exited": False, "cycles_avant_exit": None,
        "reconcilier_appels": 0, "rejoue_appels": 0,
    }

    def fake_monotonic():
        return horloge["t"]

    def fake_sleep(_):
        i = min(compteur["lister"] - 1, len(sleeps) - 1)
        horloge["t"] += sleeps[i] if sleeps else 1.0

    def fake_lister():
        i = compteur["lister"]
        compteur["lister"] += 1
        if compteur["lister"] > cap:
            raise StopLoop()
        return lister_plan[i] if i < len(lister_plan) else []

    def fake_reconcilier(issues):
        etat["reconcilier_appels"] += 1

    def fake_rejoue(nom_projet=None):
        etat["rejoue_appels"] += 1

    def fake_exit(code=0):
        etat["exited"] = True
        etat["cycles_avant_exit"] = compteur["lister"]
        raise StopLoop()

    rep_travail = Path(tempfile.mkdtemp(prefix=f"rep_{nom_cfg}_"))
    conf = _ecrire_conf(rep_travail, nom_cfg)
    argv = ["watcher.py", "--config", str(conf)]

    patches = [
        mock.patch.object(watcher.time, "monotonic", fake_monotonic),
        mock.patch.object(watcher.time, "sleep", fake_sleep),
        mock.patch.object(watcher, "lister_issues", fake_lister),
        mock.patch.object(watcher, "traiter_issue", lambda *a, **k: None),
        mock.patch.object(watcher, "_reconcilier_issues_en_cours_fermees", fake_reconcilier),
        mock.patch.object(watcher, "rejouer_publications_en_attente", fake_rejoue),
        mock.patch.object(watcher, "nb_publications_en_attente", lambda *a, **k: 0),
        mock.patch.object(watcher, "rafraichir_depot", lambda *a, **k: None),
        mock.patch.object(watcher, "verifier_accumulation_worktrees", lambda: None),
        mock.patch.object(watcher, "verifier_plafond_max_write_parallele", lambda: None),
        mock.patch.object(watcher.sys, "exit", fake_exit),
        mock.patch.object(watcher.sys, "argv", argv),
    ]
    for nom_patch, valeur in (extra_patches or {}).items():
        patches.append(mock.patch.object(watcher, nom_patch, valeur))

    with contextlib.ExitStack() as pile:
        for p in patches:
            pile.enter_context(p)
        try:
            watcher.main()
        except StopLoop:
            pass

    conf.unlink(missing_ok=True)
    # Nettoyage best-effort du marqueur de panne réseau réel (issue #952) :
    # écrit/retiré par watcher.py sous le VRAI logs/ du dépôt (DOSSIER_LOGS
    # n'est pas isolé dans ce scénario, comme déjà le cas pour le fichier PID
    # dans test_auto_extinction_217.py) — jamais laissé traîner après le test.
    (watcher.DOSSIER_LOGS / f"watcher-{nom_cfg}.reseau_panne").unlink(missing_ok=True)
    (watcher.DOSSIER_LOGS / f"watcher-{nom_cfg}.pid").unlink(missing_ok=True)
    return etat


def scenario_liste_en_echec_distincte_de_liste_vide():
    """Deux cycles où `lister_issues()` échoue (`None`, panne réseau/GitHub)
    PUIS un cycle où elle réussit (liste vide) : pendant la panne,
    `_reconcilier_issues_en_cours_fermees` (qui déclare les issues
    `needs-human` disparues) n'est JAMAIS appelée, l'auto-extinction (20 min)
    ne se déclenche PAS malgré un temps écoulé largement supérieur au délai
    pendant la panne — elle attend la durée RÉELLE d'inactivité après le
    retour du réseau (le temps de panne est suspendu, pas remis à zéro)."""
    # 3 cycles à 1300s d'écart : SANS la correction, le watcher aurait conclu
    # à de l'inactivité (1300s > 1200s = 20 min) dès le 2e passage en tête de
    # boucle (avant même le 2e appel à lister_issues) — cycles_avant_exit
    # vaudrait alors 1, pas 3.
    etat = _executer_main_scripte(
        "test_952_liste_panne",
        lister_plan=[None, None, []],
        sleeps=[1300.0, 1300.0, 1300.0],
        cap=10,
    )
    assert etat["exited"], "Le watcher aurait dû finir par s'éteindre une fois la vraie inactivité écoulée."
    assert etat["cycles_avant_exit"] == 3, (
        f"Auto-extinction déclenchée après {etat['cycles_avant_exit']} appel(s) à "
        f"lister_issues() — la panne (2 premiers appels) n'a pas été correctement "
        f"suspendue (attendu : 3, le temps de panne ne devait pas compter)."
    )
    assert etat["reconcilier_appels"] == 1, (
        f"_reconcilier_issues_en_cours_fermees appelée {etat['reconcilier_appels']} fois "
        f"— devrait l'être UNIQUEMENT lors du cycle où la liste a réussi (1), jamais "
        f"pendant une panne (aucune issue ne doit être déclarée disparue pendant une panne)."
    )
    assert etat["rejoue_appels"] == 1, (
        f"rejouer_publications_en_attente appelée {etat['rejoue_appels']} fois — "
        f"devrait l'être UNIQUEMENT après un gh issue list réussi (1 ici)."
    )
    return etat


def scenario_rejeu_au_demarrage():
    """Publications en attente présentes au démarrage (watcher arrêté
    pendant une panne) : rejouées AVANT le premier cycle, pas après.

    `fake_sleep` (et non `fake_lister`) est ce qui arrête la boucle : le
    `time.sleep(intervalle)` de fin de cycle est APRÈS le `try/except
    Exception` de `main()`, contrairement à un `raise` déclenché DEPUIS
    `lister_issues()` (DANS ce `try`) — qui serait silencieusement avalé par
    `except Exception`, laissant la boucle tourner indéfiniment (piège déjà
    présent, mais jamais exercé, dans le lanceur de scénario de
    test_auto_extinction_217.py)."""
    ordre = []

    def fake_rejoue(nom_projet=None):
        ordre.append("rejeu")

    def fake_lister():
        ordre.append("lister")
        return []

    def fake_sleep(_):
        raise StopLoop()

    rep_travail = Path(tempfile.mkdtemp(prefix="rep_test_952_demarrage_"))
    conf = _ecrire_conf(rep_travail, "test_952_demarrage")
    argv = ["watcher.py", "--config", str(conf)]
    try:
        with mock.patch.object(watcher, "rejouer_publications_en_attente", fake_rejoue), \
             mock.patch.object(watcher, "nb_publications_en_attente", lambda *a, **k: 1), \
             mock.patch.object(watcher, "lister_issues", fake_lister), \
             mock.patch.object(watcher, "_reconcilier_issues_en_cours_fermees", lambda *a, **k: None), \
             mock.patch.object(watcher, "rafraichir_depot", lambda *a, **k: None), \
             mock.patch.object(watcher, "verifier_accumulation_worktrees", lambda: None), \
             mock.patch.object(watcher, "verifier_plafond_max_write_parallele", lambda: None), \
             mock.patch.object(watcher.time, "sleep", fake_sleep), \
             mock.patch.object(watcher.sys, "argv", argv):
            try:
                watcher.main()
            except StopLoop:
                pass
    finally:
        conf.unlink(missing_ok=True)
        (watcher.DOSSIER_LOGS / "watcher-test_952_demarrage.pid").unlink(missing_ok=True)

    assert ordre[:2] == ["rejeu", "lister"], (
        f"Ordre inattendu au démarrage : {ordre} — le rejeu des publications en "
        f"attente doit précéder le premier cycle (premier appel à lister_issues)."
    )
    return {"ordre": ordre}


# ─── Scénarios 2 : publications en attente (mise en attente + rejeu) ──────

@contextlib.contextmanager
def _isolation_publications(tmp_path: Path, nom_cfg: str):
    """Isole CFG + les dossiers dépendants pour les scénarios de publication
    en attente (issue #952) — même patron que les autres tests watcher.py
    (ex. tests/test_premier_marqueur_et_arret_rapide_763.py)."""
    ancien_cfg = watcher.CFG
    ancien_dossier_logs = watcher.DOSSIER_LOGS
    ancien_dossier_publications = watcher.DOSSIER_PUBLICATIONS_EN_ATTENTE
    watcher.DOSSIER_LOGS = tmp_path / "logs"
    watcher.DOSSIER_PUBLICATIONS_EN_ATTENTE = watcher.DOSSIER_LOGS / "publications_en_attente"
    watcher.CFG = watcher.Config(
        nom=nom_cfg, depot="exemple/depot-test",
        rep_travail=tmp_path, topic_ntfy=nom_cfg,
    )
    try:
        yield
    finally:
        watcher.CFG = ancien_cfg
        watcher.DOSSIER_LOGS = ancien_dossier_logs
        watcher.DOSSIER_PUBLICATIONS_EN_ATTENTE = ancien_dossier_publications


def scenario_publication_mise_en_attente_puis_rejouee_sans_doublon():
    """`commenter_resultat_avec_retry` épuise ses 4 tentatives (`gh`
    simulé en échec) : le texte COMPLET est mis en attente durable, jamais
    perdu. Tant que `gh` échoue encore, le rejeu ne consomme rien. Dès que
    `gh` répond de nouveau : rejeu réussi, UNE SEULE fois (fichier supprimé),
    l'issue est fermée (fermer_issue déclenchée par le rejeu) — un second
    rejeu ne republie RIEN de plus (pas de doublon)."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        control_dir = tmp_path / "control"
        control_dir.mkdir()
        (control_dir / "mode_comment").write_text("fail")

        _ecrire_executable(bin_dir / "gh", _FAUX_GH_SCRIPT)

        ancien_path = os.environ.get("PATH", "")
        ancien_control = os.environ.get("CONTROL_DIR")
        os.environ["PATH"] = f"{bin_dir}{os.pathsep}{ancien_path}"
        os.environ["CONTROL_DIR"] = str(control_dir)
        try:
            verifier_faux_executables_actifs(bin_dir, ["gh"])

            ancien_delais = watcher.DELAIS_RETRY_RESULTAT
            watcher.DELAIS_RETRY_RESULTAT = (0, 0, 0)  # test rapide : pas de vraie attente
            try:
                with _isolation_publications(tmp_path, "test_952_publication"):
                    numero = 265
                    texte = f"{watcher.MARQUEUR_RESULTAT}\n## Résultat\n\nTravail déjà fait (rummikub #265)."

                    ok = watcher.commenter_resultat_avec_retry(numero, texte)
                    assert ok is False, "gh simulé en échec : commenter_resultat_avec_retry aurait dû échouer."

                    fichiers = watcher._lister_publications_en_attente("test_952_publication")
                    assert len(fichiers) == 1, f"attendu 1 publication en attente, trouvé {len(fichiers)}"
                    contenu = json.loads(fichiers[0].read_text(encoding="utf-8"))
                    assert contenu["action"] == "commentaire_resultat"
                    assert contenu["numero"] == numero
                    assert contenu["texte"] == texte, "Le texte COMPLET du rapport doit être conservé tel quel (incident rummikub #265)."
                    assert not (control_dir / f"comments_{numero}").exists(), "Aucun commentaire ne doit avoir été réellement posté (gh en échec)."

                    # Réseau toujours coupé : le rejeu ne doit RIEN consommer.
                    watcher.rejouer_publications_en_attente("test_952_publication")
                    fichiers = watcher._lister_publications_en_attente("test_952_publication")
                    assert len(fichiers) == 1, "La publication en attente ne doit pas disparaître tant que gh échoue encore."

                    # Le réseau revient : rejeu réussi.
                    (control_dir / "mode_comment").write_text("ok")
                    watcher.rejouer_publications_en_attente("test_952_publication")
                    fichiers = watcher._lister_publications_en_attente("test_952_publication")
                    assert len(fichiers) == 0, "La publication rejouée avec succès doit être retirée de la file."
                    assert (control_dir / f"comments_{numero}" / "1.txt").read_text(encoding="utf-8") == texte
                    assert not (control_dir / f"comments_{numero}" / "2.txt").exists(), "Un seul commentaire doit avoir été posté."
                    assert (control_dir / "closed.txt").read_text(encoding="utf-8").strip() == str(numero), (
                        "Le commentaire republié avec succès doit entraîner la fermeture de l'issue."
                    )

                    # Rejeu supplémentaire : plus rien en attente, aucun nouveau commentaire/fermeture.
                    watcher.rejouer_publications_en_attente("test_952_publication")
                    assert not (control_dir / f"comments_{numero}" / "2.txt").exists()
                    assert len(
                        [l for l in (control_dir / "closed.txt").read_text(encoding="utf-8").splitlines() if l.strip()]
                    ) == 1, "Aucun doublon de fermeture après un rejeu alors que la file est déjà vide."
            finally:
                watcher.DELAIS_RETRY_RESULTAT = ancien_delais
        finally:
            os.environ["PATH"] = ancien_path
            if ancien_control is None:
                os.environ.pop("CONTROL_DIR", None)
            else:
                os.environ["CONTROL_DIR"] = ancien_control

    return {"ok": True}


# ─── Scénarios 3 : tentative pendant une panne réseau (boucle de retry) ───

def _issue_minimale(numero: int, titre: str, labels: list[str]) -> dict:
    return {
        "number": numero,
        "title": titre,
        "body": "| PRIORITE | normale |\n| TIMEOUT | 30s |\n",
        "labels": [{"name": lab} for lab in labels],
    }


def _init_depot_git(rep: Path) -> None:
    subprocess.run(["git", "init", "-q", "-b", "master", str(rep)], check=True)
    (rep / "fichier.txt").write_text("original\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=rep, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=rep, check=True, capture_output=True)


@contextlib.contextmanager
def _isolation_tentative(tmp_path: Path, nom_cfg: str, numero: int, max_essais: int,
                          claude_script: str):
    """Isole CFG + dossiers dépendants pour un scénario qui passe par
    `traiter_issue` (boucle de tentatives) — `commenter_issue`/
    `ajouter_label` sont remplacés pour capturer les échecs DÉFINITIFS
    (needs-human), mais `commenter_resultat_avec_retry`/`fermer_issue`
    restent les VRAIES fonctions, qui appellent un `gh` factice STATEFUL
    (`_FAUX_GH_SCRIPT`, nécessaire pour que `_commentaire_marque_present`
    confirme réellement un succès, pas un simple « exit 0 » muet)."""
    rep_travail = tmp_path / "projet"
    rep_travail.mkdir()
    _init_depot_git(rep_travail)

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _ecrire_executable(bin_dir / "claude", claude_script)
    _ecrire_executable(bin_dir / "gh", _FAUX_GH_SCRIPT)
    control_dir = tmp_path / "control"
    control_dir.mkdir()

    ancien_path = os.environ.get("PATH", "")
    ancien_control = os.environ.get("CONTROL_DIR")
    os.environ["PATH"] = f"{bin_dir}{os.pathsep}{ancien_path}"
    os.environ["CONTROL_DIR"] = str(control_dir)
    verifier_faux_executables_actifs(bin_dir, ["claude", "gh"])

    ancien_dossier_verrous = watcher.DOSSIER_VERROUS
    ancien_dossier_logs = watcher.DOSSIER_LOGS
    ancien_dossier_publications = watcher.DOSSIER_PUBLICATIONS_EN_ATTENTE
    ancien_fichier_historique = watcher.FICHIER_HISTORIQUE
    ancien_fichier_etat_timeout = watcher.FICHIER_ETAT_TIMEOUT
    ancien_fichier_etat_ambiance = watcher.FICHIER_ETAT_AMBIANCE
    watcher.DOSSIER_LOGS = tmp_path / "logs"
    watcher.DOSSIER_VERROUS = watcher.DOSSIER_LOGS / "verrous"
    watcher.DOSSIER_PUBLICATIONS_EN_ATTENTE = watcher.DOSSIER_LOGS / "publications_en_attente"
    watcher.FICHIER_HISTORIQUE = watcher.DOSSIER_LOGS / "historique_durees.json"
    watcher.FICHIER_ETAT_TIMEOUT = watcher.DOSSIER_LOGS / "etat_timeout.json"
    watcher.FICHIER_ETAT_AMBIANCE = watcher.DOSSIER_LOGS / "etat_ambiance.json"

    ancien_cfg = watcher.CFG
    watcher.CFG = watcher.Config(
        nom=nom_cfg, depot="exemple/depot-test",
        rep_travail=rep_travail, topic_ntfy=nom_cfg,
        max_essais=max_essais, timeout_claude=15, notifier_local=False,
    )
    watcher.issues_en_cours.discard(numero)

    commentaires = []
    labels_poses = []
    ancien_commenter = watcher.commenter_issue
    ancien_ajouter_label = watcher.ajouter_label

    def _faux_commenter(num, message):
        commentaires.append(message)
        return True

    def _faux_ajouter_label(num, label):
        labels_poses.append(label)

    watcher.commenter_issue = _faux_commenter
    watcher.ajouter_label = _faux_ajouter_label

    try:
        yield commentaires, labels_poses, control_dir
    finally:
        watcher.CFG = ancien_cfg
        watcher.commenter_issue = ancien_commenter
        watcher.ajouter_label = ancien_ajouter_label
        if ancien_path:
            os.environ["PATH"] = ancien_path
        else:
            os.environ.pop("PATH", None)
        if ancien_control is None:
            os.environ.pop("CONTROL_DIR", None)
        else:
            os.environ["CONTROL_DIR"] = ancien_control
        watcher.DOSSIER_VERROUS = ancien_dossier_verrous
        watcher.DOSSIER_LOGS = ancien_dossier_logs
        watcher.DOSSIER_PUBLICATIONS_EN_ATTENTE = ancien_dossier_publications
        watcher.FICHIER_HISTORIQUE = ancien_fichier_historique
        watcher.FICHIER_ETAT_TIMEOUT = ancien_fichier_etat_timeout
        watcher.FICHIER_ETAT_AMBIANCE = ancien_fichier_etat_ambiance
        watcher.issues_en_cours.discard(numero)


def scenario_tentative_pendant_panne_non_comptee():
    """`claude` échoue vite (comme alchess #383 / diagnostique_programme
    #115, code 1 quasi instantané) AU MOMENT où le réseau est détecté
    coupé : cette tentative ne doit PAS être comptée — avec `MAX_ESSAIS=1`,
    si la tentative avait compté, l'issue serait abandonnée (needs-human)
    après ce seul échec. Le réseau revient dès le premier sondage : la même
    tentative est refaite et réussit, SANS needs-human."""
    numero = 383
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        compteur = tmp_path / "compteur_claude"
        claude_script = f"""#!/bin/bash
if [ "$#" -le 2 ]; then
    exit 0
fi
echo x >> {compteur}
n=$(wc -l < {compteur})
if [ "$n" -eq "1" ]; then
    echo "connexion impossible" >&2
    exit 1
fi
cat <<'RAP'
<!-- bridge:verdict:succes -->
✅ Succes test reseau 952
Commits (dans /tmp) : aucun (lecture seule)
py_compile : N/A — push : aucun
RAP
exit 0
"""
        with _isolation_tentative(tmp_path, "test_952_tentative", numero, max_essais=1,
                                   claude_script=claude_script) as (commentaires, labels_poses, control_dir):
            appels_reseau = {"n": 0}

            def fake_reseau_disponible():
                appels_reseau["n"] += 1
                return appels_reseau["n"] > 1  # 1er appel (juste après l'échec) : coupé ; ensuite : revenu

            ancien_intervalle = watcher.INTERVALLE_SONDAGE_RESEAU_S
            watcher.INTERVALLE_SONDAGE_RESEAU_S = 0.01
            try:
                with mock.patch.object(watcher, "_reseau_disponible", fake_reseau_disponible):
                    issue = _issue_minimale(numero, "test réseau 952", ["mode_scratch"])
                    watcher.traiter_issue(issue, dry_run=False)
            finally:
                watcher.INTERVALLE_SONDAGE_RESEAU_S = ancien_intervalle

        assert compteur.read_text().count("x") == 2, (
            "claude aurait dû être invoqué exactement 2 fois (1 échec pendant la "
            f"panne, non compté, puis 1 reprise réussie) : {compteur.read_text().count('x')}."
        )
        assert watcher.LABEL_ECHEC not in labels_poses, (
            f"needs-human ne devait PAS être posé (succès final, la tentative "
            f"pendant la panne ne devait pas être comptée) : {labels_poses}"
        )
    return {"appels_claude": 2}


def scenario_panne_plus_longue_que_le_maximum():
    """Le réseau ne revient JAMAIS (`_reseau_disponible` toujours faux) :
    au-delà du délai maximal d'attente (raccourci pour le test), le watcher
    abandonne NORMALEMENT (comme si `max_essais` était atteint) — claude
    n'est PAS réinvoqué en boucle pendant l'attente (seule la passe
    diagnostique, best-effort, s'ajoute à la tentative initiale)."""
    numero = 115
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        compteur = tmp_path / "compteur_claude"
        claude_script = f"""#!/bin/bash
if [ "$#" -le 2 ]; then
    exit 0
fi
echo x >> {compteur}
echo "connexion impossible" >&2
exit 1
"""
        with _isolation_tentative(tmp_path, "test_952_panne_longue", numero, max_essais=3,
                                   claude_script=claude_script) as (commentaires, labels_poses, control_dir):
            ancien_intervalle = watcher.INTERVALLE_SONDAGE_RESEAU_S
            ancien_max_attente = watcher.DUREE_MAX_ATTENTE_RESEAU_S
            watcher.INTERVALLE_SONDAGE_RESEAU_S = 0.01
            watcher.DUREE_MAX_ATTENTE_RESEAU_S = 0.05
            try:
                with mock.patch.object(watcher, "_reseau_disponible", lambda: False):
                    issue = _issue_minimale(numero, "test panne longue 952", ["mode_scratch"])
                    watcher.traiter_issue(issue, dry_run=False)
            finally:
                watcher.INTERVALLE_SONDAGE_RESEAU_S = ancien_intervalle
                watcher.DUREE_MAX_ATTENTE_RESEAU_S = ancien_max_attente

        nb_appels = compteur.read_text().count("x")
        # 1 tentative réelle + au plus 1 passe diagnostique best-effort —
        # JAMAIS réessayé une 2e/3e fois pendant que le réseau reste coupé :
        # sans la correction, un `MAX_ESSAIS=3` aurait fait tourner
        # jusqu'à 3 tentatives + 1 diagnostic.
        assert nb_appels <= 2, (
            f"claude n'aurait dû être invoqué qu'1 ou 2 fois (tentative + "
            f"diagnostic best-effort), pas réessayé pendant l'attente réseau "
            f"persistante : {nb_appels} appels."
        )
        # Issue abandonnée (needs-human), via le chemin normal d'abandon —
        # ici gh RÉPOND (commenter_issue/ajouter_label sont remplacés pour
        # capturer, voir _isolation_tentative), donc pas de mise en attente
        # à vérifier ICI : voir le scénario séparé ci-dessous pour ce volet.
        assert labels_poses == [watcher.LABEL_ECHEC], (
            f"needs-human attendu après abandon normal (panne trop longue) : {labels_poses}"
        )
        assert any("coupure réseau prolongée" in c for c in commentaires), (
            f"Le commentaire d'échec devrait mentionner la coupure réseau prolongée : {commentaires}"
        )

    # Volet « mise en attente » du point 2 de l'issue #952, séparément : les
    # VRAIES primitives publiques (commenter_issue/ajouter_label, jamais
    # remplacées ici), avec un gh RÉELLEMENT en échec cette fois.
    with tempfile.TemporaryDirectory() as tmp2:
        tmp_path2 = Path(tmp2)
        bin_dir2 = tmp_path2 / "bin"
        bin_dir2.mkdir()
        gh_path2 = bin_dir2 / "gh"
        gh_path2.write_text("#!/bin/bash\nexit 1\n", encoding="utf-8")
        gh_path2.chmod(gh_path2.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        ancien_path = os.environ.get("PATH", "")
        os.environ["PATH"] = f"{bin_dir2}{os.pathsep}{ancien_path}"
        try:
            verifier_faux_executables_actifs(bin_dir2, ["gh"])
            with _isolation_publications(tmp_path2, "test_952_panne_longue_mel"):
                watcher.commenter_issue(numero, "❌ Échec après 3 tentatives (après une coupure réseau prolongée).")
                watcher.ajouter_label(numero, watcher.LABEL_ECHEC)
                fichiers = watcher._lister_publications_en_attente("test_952_panne_longue_mel")
                actions = sorted(json.loads(f.read_text(encoding="utf-8"))["action"] for f in fichiers)
        finally:
            os.environ["PATH"] = ancien_path

    assert actions == ["commentaire", "label"], (
        f"Le commentaire d'échec ET le label needs-human, eux-mêmes en échec, "
        f"devraient être mis en attente : {actions}"
    )
    return {"nb_appels_claude": nb_appels, "actions_en_attente": actions}


def scenario_echec_reel_reseau_disponible_comportement_inchange():
    """Même scénario qu'avant l'issue #952 (cf.
    tests/test_premier_marqueur_et_arret_rapide_763.py) : un VRAI échec de
    process, quasi instantané, AVEC un réseau disponible — le nouveau
    garde-fou ne doit RIEN changer : arrêt immédiat, `needs-human`, UNE
    SEULE tentative consommée."""
    numero = 9521
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        compteur = tmp_path / "compteur_claude"
        claude_script = f"""#!/bin/bash
if [ "$#" -le 2 ]; then
    exit 0
fi
echo x >> {compteur}
echo "Error: unexpected end of stream" >&2
exit 1
"""
        with _isolation_tentative(tmp_path, "test_952_reseau_ok", numero, max_essais=5,
                                   claude_script=claude_script) as (commentaires, labels_poses, control_dir):
            with mock.patch.object(watcher, "_reseau_disponible", lambda: True):
                issue = _issue_minimale(numero, "test reseau disponible 952", ["mode_scratch"])
                watcher.traiter_issue(issue, dry_run=False)

        assert compteur.read_text().count("x") == 1, (
            "Une seule tentative aurait dû être consommée (réseau disponible — "
            "comportement inchangé de l'issue #763)."
        )
        assert labels_poses == [watcher.LABEL_ECHEC], (
            f"needs-human attendu immédiatement : {labels_poses}"
        )
    return {"labels_poses": labels_poses}


def main():
    tests = [
        ("1a. liste en échec distincte d'une liste vide (auto-extinction suspendue)",
         scenario_liste_en_echec_distincte_de_liste_vide),
        ("1b. rejeu des publications en attente AU DÉMARRAGE",
         scenario_rejeu_au_demarrage),
        ("2. publication mise en attente puis rejouée, sans doublon",
         scenario_publication_mise_en_attente_puis_rejouee_sans_doublon),
        ("3. tentative échouée pendant une panne : non comptée, refaite",
         scenario_tentative_pendant_panne_non_comptee),
        ("4. panne plus longue que le maximum : abandon normal + mise en attente",
         scenario_panne_plus_longue_que_le_maximum),
        ("5. échec réel, réseau disponible : comportement inchangé (#763)",
         scenario_echec_reel_reseau_disponible_comportement_inchange),
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
