#!/usr/bin/env python3
"""Test de non-régression — issue #816 : créer automatiquement les labels
GitHub manquants au démarrage des watchers, et rattraper les dépôts
existants.

Cause établie : `LABELS`/`creer_labels` (désormais `labels_github.py`,
extrait de `nouveau_projet.py`) n'étaient appliqués qu'à la création d'un
projet. Tout label ajouté au code restait absent de chaque dépôt déjà
provisionné jusqu'à un `gh label create` manuel — quatre incidents
(`sans-redacteur` #647/#648, `agent-claude`/`agent-vibe` #768, `mode_scratch`
#785), dont un sans la moindre erreur visible.

Couvre :
- `labels_github.creer_labels` : tous les labels déjà présents (rien n'est
  créé) ; certains manquants (seuls ceux-là sont créés) ; comparaison
  insensible à la casse ; liste illisible côté `gh` et création qui échoue
  (statut "echec" détaillé, jamais d'exception).
- `watcher.verifier_labels_demarrage` : résumé + détail journalisés, et
  jamais bloquant même si l'appel sous-jacent lève une exception.
- `rattraper_labels.py` : filtre `configs/*.conf` (hors `ccw.conf` et tout
  fichier sans `DEPOT`) et traite plusieurs projets d'un coup.

Aucun appel réseau réel : `labels_github._gh` (et les fonctions qui en
dépendent) sont monkeypatchées à la main, sans pytest.

Exécution :  python3 tests/test_labels_auto_watcher_816.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import logging
import sys
import tempfile
from io import StringIO
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import labels_github  # noqa: E402
import watcher  # noqa: E402
import rattraper_labels  # noqa: E402


def _resultat(returncode, stdout="", stderr=""):
    import subprocess
    return subprocess.CompletedProcess(["gh"], returncode, stdout=stdout, stderr=stderr)


def _patch_gh(fonction):
    """Remplace labels_github._gh pour la durée de l'appelant, restaure
    ensuite — valable pour tout code qui appelle creer_labels (watcher,
    rattraper_labels), puisque _gh est résolu dans l'espace de noms de
    labels_github à chaque appel, quel que soit le module qui a importé
    creer_labels."""
    original = labels_github._gh
    labels_github._gh = fonction
    return original


def scenario_tous_labels_presents_rien_cree():
    noms_existants = "\n".join(f"{nom}\tdeadbeef\tdesc" for nom, _c, _d in labels_github.LABELS)
    appels = []

    def faux_gh(*args):
        appels.append(args)
        if args[:2] == ("label", "list"):
            return _resultat(0, stdout=noms_existants)
        raise AssertionError(f"aucune création attendue : {args}")

    original = _patch_gh(faux_gh)
    try:
        resultats = labels_github.creer_labels("AlainDelree/X")
    finally:
        labels_github._gh = original

    assert len(resultats) == len(labels_github.LABELS)
    assert all(statut == "deja" for _n, statut, _d in resultats), resultats
    appels_creation = [a for a in appels if a[:2] == ("label", "create")]
    assert appels_creation == [], f"aucune création attendue, obtenu : {appels_creation}"


def scenario_certains_manquants_seuls_ceux_la_crees():
    presents = [n for n, _c, _d in labels_github.LABELS[:-2]]
    manquants = [n for n, _c, _d in labels_github.LABELS[-2:]]
    noms_existants = "\n".join(f"{nom}\tdeadbeef\tdesc" for nom in presents)
    crees = []

    def faux_gh(*args):
        if args[:2] == ("label", "list"):
            return _resultat(0, stdout=noms_existants)
        if args[:2] == ("label", "create"):
            crees.append(args[2])
            return _resultat(0)
        raise AssertionError(f"appel gh inattendu : {args}")

    original = _patch_gh(faux_gh)
    try:
        resultats = labels_github.creer_labels("AlainDelree/X")
    finally:
        labels_github._gh = original

    statuts = {n: s for n, s, _d in resultats}
    for nom in presents:
        assert statuts[nom] == "deja", (nom, statuts[nom])
    for nom in manquants:
        assert statuts[nom] == "cree", (nom, statuts[nom])
    assert sorted(crees) == sorted(manquants), (crees, manquants)


def scenario_comparaison_insensible_a_la_casse():
    """Un label existant avec une casse différente (ex. "Bridge" au lieu de
    "bridge") doit être reconnu comme déjà présent, pas recréé en double."""
    noms_existants = "\n".join(
        f"{nom.upper()}\tdeadbeef\tdesc" for nom, _c, _d in labels_github.LABELS
    )
    appels_creation = []

    def faux_gh(*args):
        if args[:2] == ("label", "list"):
            return _resultat(0, stdout=noms_existants)
        if args[:2] == ("label", "create"):
            appels_creation.append(args[2])
            return _resultat(0)
        raise AssertionError(f"appel gh inattendu : {args}")

    original = _patch_gh(faux_gh)
    try:
        resultats = labels_github.creer_labels("AlainDelree/X")
    finally:
        labels_github._gh = original

    assert all(statut == "deja" for _n, statut, _d in resultats), resultats
    assert appels_creation == []


def scenario_liste_illisible_et_creations_en_echec():
    """`gh label list` échoue (réseau/droits/dépôt inaccessible) : la liste
    des existants reste vide, donc chaque label est tenté — et chaque
    tentative échoue à son tour ici (dépôt inaccessible). Aucune exception
    ne doit sortir de creer_labels, et chaque échec porte un détail."""
    def faux_gh(*args):
        if args[:2] == ("label", "list"):
            return _resultat(1, stderr="GraphQL: Could not resolve to a Repository")
        if args[:2] == ("label", "create"):
            return _resultat(1, stderr="GraphQL: Could not resolve to a Repository")
        raise AssertionError(f"appel gh inattendu : {args}")

    original = _patch_gh(faux_gh)
    try:
        resultats = labels_github.creer_labels("AlainDelree/Inexistant")
    finally:
        labels_github._gh = original

    assert len(resultats) == len(labels_github.LABELS)
    assert all(statut == "echec" for _n, statut, _d in resultats), resultats
    assert all(detail for _n, _s, detail in resultats), "chaque échec doit porter un détail"


def _ajouter_capteur_log():
    enregistrements = []
    gestionnaire = logging.Handler()
    gestionnaire.emit = lambda rec: enregistrements.append(rec.getMessage())
    watcher.log.addHandler(gestionnaire)
    watcher.log.setLevel(logging.INFO)
    return gestionnaire, enregistrements


def scenario_watcher_verifier_labels_resume_et_detail():
    """verifier_labels_demarrage journalise une ligne de résumé (présents/
    créés/échoués) et une ligne par label créé ou en échec."""
    cfg = watcher.Config(nom="t816", depot="AlainDelree/T816", rep_travail=Path("/tmp"))
    resultats_canned = [
        ("for-linux", "deja", ""),
        ("for-windows", "cree", ""),
        ("bridge", "echec", "could not create label: already_exists"),
    ]
    original = watcher._creer_labels_gh
    watcher._creer_labels_gh = lambda depot: resultats_canned
    gestionnaire, enregistrements = _ajouter_capteur_log()
    try:
        watcher.verifier_labels_demarrage(cfg)
    finally:
        watcher._creer_labels_gh = original
        watcher.log.removeHandler(gestionnaire)

    resume = [m for m in enregistrements if "1 présent" in m and "AlainDelree/T816" in m]
    assert resume, enregistrements
    assert any("for-windows" in m and "créé" in m for m in enregistrements), enregistrements
    assert any("bridge" in m and "already_exists" in m for m in enregistrements), enregistrements


def scenario_watcher_verifier_labels_jamais_bloquant():
    """Si l'appel sous-jacent lève (réseau, gh absent...), le démarrage ne
    doit JAMAIS être interrompu : un avertissement précis est journalisé,
    aucune exception ne remonte."""
    cfg = watcher.Config(nom="t816b", depot="AlainDelree/T816B", rep_travail=Path("/tmp"))
    original = watcher._creer_labels_gh

    def leve(depot):
        raise OSError("gh introuvable")

    watcher._creer_labels_gh = leve
    gestionnaire, enregistrements = _ajouter_capteur_log()
    try:
        watcher.verifier_labels_demarrage(cfg)  # ne doit pas lever
    finally:
        watcher._creer_labels_gh = original
        watcher.log.removeHandler(gestionnaire)

    assert any("AlainDelree/T816B" in m and "gh introuvable" in m for m in enregistrements), enregistrements


def scenario_rattrapage_filtre_ccw_et_sans_depot():
    with tempfile.TemporaryDirectory() as tmp:
        dossier = Path(tmp)
        (dossier / "projA.conf").write_text(
            "NOM = projA\nDEPOT = AlainDelree/ProjA\nREP_TRAVAIL = /tmp/a\n", encoding="utf-8")
        (dossier / "projB.conf").write_text(
            "NOM = projB\nDEPOT = AlainDelree/ProjB\nREP_TRAVAIL = /tmp/b\n", encoding="utf-8")
        (dossier / "ccw.conf").write_text("TOPIC_NTFY = x\n", encoding="utf-8")
        (dossier / "ccw_ssh.conf").write_text("HOST = y\n", encoding="utf-8")

        projets = rattraper_labels.lister_projets_a_rattraper(dossier)

    noms = sorted(nom for nom, _d in projets)
    assert noms == ["projA", "projB"], projets
    depots = {nom: depot for nom, depot in projets}
    assert depots["projA"] == "AlainDelree/ProjA"
    assert depots["projB"] == "AlainDelree/ProjB"


def scenario_rattrapage_plusieurs_projets():
    """L'outil applique creer_labels à chaque projet déclaré et affiche un
    tableau par projet, sans jamais toucher à un .conf."""
    appels_depots = []

    def faux_creer_labels(depot):
        appels_depots.append(depot)
        if depot == "AlainDelree/ProjA":
            return [("for-linux", "deja", ""), ("mode_scratch", "cree", "")]
        return [("for-linux", "echec", "network down")]

    original_creer_labels = rattraper_labels.creer_labels
    rattraper_labels.creer_labels = faux_creer_labels

    with tempfile.TemporaryDirectory() as tmp:
        dossier = Path(tmp)
        conf_a = dossier / "projA.conf"
        conf_b = dossier / "projB.conf"
        conf_a.write_text("NOM = projA\nDEPOT = AlainDelree/ProjA\nREP_TRAVAIL = /tmp/a\n", encoding="utf-8")
        conf_b.write_text("NOM = projB\nDEPOT = AlainDelree/ProjB\nREP_TRAVAIL = /tmp/b\n", encoding="utf-8")
        original_dossier = rattraper_labels.DOSSIER_CONFIGS
        rattraper_labels.DOSSIER_CONFIGS = dossier

        hash_a_avant = conf_a.read_text(encoding="utf-8")
        hash_b_avant = conf_b.read_text(encoding="utf-8")

        ancien_stdout = sys.stdout
        sys.stdout = capture = StringIO()
        try:
            code = rattraper_labels.main()
        finally:
            sys.stdout = ancien_stdout
            rattraper_labels.DOSSIER_CONFIGS = original_dossier
            rattraper_labels.creer_labels = original_creer_labels

        assert conf_a.read_text(encoding="utf-8") == hash_a_avant, ".conf modifié"
        assert conf_b.read_text(encoding="utf-8") == hash_b_avant, ".conf modifié"

    sortie = capture.getvalue()
    assert sorted(appels_depots) == ["AlainDelree/ProjA", "AlainDelree/ProjB"]
    assert "projA" in sortie and "AlainDelree/ProjA" in sortie
    assert "projB" in sortie and "AlainDelree/ProjB" in sortie
    assert "mode_scratch" in sortie
    assert "2 projet(s) traité(s)" in sortie
    assert code == 1, "au moins un échec (ProjB) doit se refléter dans le code de sortie"


def main() -> int:
    tests = [
        ("creer_labels : tous présents, rien n'est créé", scenario_tous_labels_presents_rien_cree),
        ("creer_labels : certains manquants, seuls ceux-là créés", scenario_certains_manquants_seuls_ceux_la_crees),
        ("creer_labels : comparaison insensible à la casse", scenario_comparaison_insensible_a_la_casse),
        ("creer_labels : liste illisible + créations en échec, pas d'exception", scenario_liste_illisible_et_creations_en_echec),
        ("verifier_labels_demarrage : résumé + détail journalisés", scenario_watcher_verifier_labels_resume_et_detail),
        ("verifier_labels_demarrage : jamais bloquant sur exception", scenario_watcher_verifier_labels_jamais_bloquant),
        ("rattraper_labels : filtre ccw.conf et fichiers sans DEPOT", scenario_rattrapage_filtre_ccw_et_sans_depot),
        ("rattraper_labels : plusieurs projets, aucun .conf modifié", scenario_rattrapage_plusieurs_projets),
    ]

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
    sys.exit(main())
