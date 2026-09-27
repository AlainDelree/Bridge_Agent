#!/usr/bin/env python3
"""Test — issue #667 : `TOPIC_NTFY` devient réellement facultatif (plus de
placeholder imposé, plus d'exigence de validation).

Couvre :
- `watcher.CHAMPS_REQUIS` ne contient plus `TOPIC_NTFY` ;
- `watcher.charger_config` accepte un `.conf` sans ligne `TOPIC_NTFY` ;
- `watcher.Config.url_ntfy` renvoie `""` (pas une URL invalide
  `https://ntfy.sh/`) quand `topic_ntfy` est vide/absent ;
- `notifications.notifier_ntfy` avec une `url_ntfy` vide ne tente AUCUNE
  requête réseau (`subprocess.run` jamais appelé) et ne journalise rien en
  `error`/`warning` ;
- `nouveau_projet.creer_projet`/`ecrire_conf` : un topic laissé vide reste
  vide dans le `.conf` généré (n'est plus remplacé par l'ancien placeholder
  `TOPIC_NTFY_DEFAUT`, retiré) ;
- `app.projets.sauvegarder_conf` (route `POST /config/<projet>`) accepte une
  valeur `TOPIC_NTFY` vide sans erreur.

Exécution :  python3 -m pytest tests/test_topic_ntfy_facultatif_667.py
"""

import sys
import tempfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import notifications  # noqa: E402
import nouveau_projet as np_cli  # noqa: E402
import watcher as w  # noqa: E402
import app.projets as projets  # noqa: E402


def _ecrire_conf_sans_topic(dossier: Path, nom: str, rep: Path) -> Path:
    dossier.mkdir(parents=True, exist_ok=True)
    chemin = dossier / f"{nom}.conf"
    chemin.write_text(
        f"NOM = {nom}\nDEPOT = AlainDelree/{nom}\nREP_TRAVAIL = {rep}\n",
        encoding="utf-8",
    )
    return chemin


def test_champs_requis_sans_topic_ntfy():
    assert "TOPIC_NTFY" not in w.CHAMPS_REQUIS
    assert w.CHAMPS_REQUIS == ("NOM", "DEPOT", "REP_TRAVAIL")


def test_charger_config_sans_topic_ntfy_ne_leve_pas(tmp_path):
    chemin = _ecrire_conf_sans_topic(tmp_path, "sanstopic", tmp_path / "rep")
    cfg = w.charger_config(chemin)
    assert cfg.topic_ntfy == ""
    assert cfg.url_ntfy == ""


def test_url_ntfy_vide_si_topic_vide():
    cfg = w.Config(nom="x", depot="a/b", rep_travail=Path("/tmp/x"), topic_ntfy="")
    assert cfg.url_ntfy == ""


def test_url_ntfy_construite_si_topic_present():
    cfg = w.Config(nom="x", depot="a/b", rep_travail=Path("/tmp/x"), topic_ntfy="mon-topic")
    assert cfg.url_ntfy == "https://ntfy.sh/mon-topic"


def test_notifier_ntfy_url_vide_naccede_jamais_au_reseau(monkeypatch):
    appels = []
    monkeypatch.setattr(notifications.subprocess, "run",
                        lambda *a, **k: appels.append((a, k)))
    erreurs = []
    monkeypatch.setattr(notifications._log_defaut, "error",
                        lambda *a, **k: erreurs.append((a, k)))
    monkeypatch.setattr(notifications._log_defaut, "warning",
                        lambda *a, **k: erreurs.append((a, k)))
    notifications.notifier_ntfy("", "titre", "message")
    assert appels == []
    assert erreurs == []


def test_notifier_dispatch_url_vide_transmise_telle_quelle(monkeypatch):
    """notifications.notifier() — dispatch complet (bip/bureau/ntfy) — avec
    le label notif_gsm actif transmet l'url_ntfy vide telle quelle à
    notifier_ntfy (dispatch inchangé) ; c'est à notifier_ntfy lui-même de
    sauter l'envoi (testé isolément ci-dessus par
    test_notifier_ntfy_url_vide_naccede_jamais_au_reseau)."""
    appels_ntfy = []
    monkeypatch.setattr(notifications, "notifier_ntfy",
                        lambda url_ntfy, *a, **k: appels_ntfy.append(url_ntfy))
    monkeypatch.setattr(notifications, "bip", lambda *a, **k: None)
    notifications.notifier(
        ["notif_gsm"], "projet-test", "", RACINE / "scripts" / "traitement_fin.py",
        titre="t", message="m",
    )
    assert appels_ntfy == [""]


def test_ecrire_conf_topic_vide_reste_vide(tmp_path, monkeypatch):
    """ecrire_conf() (fonction pure, sans réseau) : un topic vide reste vide
    dans le .conf généré — n'est plus remplacé par l'ancien placeholder."""
    configs = tmp_path / "configs"
    configs.mkdir()
    monkeypatch.setattr(np_cli, "DOSSIER_CONFIGS", configs)
    chemin = np_cli.ecrire_conf(
        "topicvide667", "AlainDelree/TopicVide667", str(tmp_path / "rep"),
        str(tmp_path / "rep"), topic="",
    )
    contenu = chemin.read_text(encoding="utf-8")
    assert "TOPIC_NTFY  = \n" in contenu
    assert "hippocampe" not in contenu


def test_creer_projet_topic_vide_reste_vide(monkeypatch, tmp_path):
    """creer_projet() (orchestrateur appelé par la route Flask/le CLI) :
    un topic laissé vide n'est plus remplacé par TOPIC_NTFY_DEFAUT — étapes
    réseau (gh/git) court-circuitées pour rester un test unitaire."""
    configs = tmp_path / "configs"
    configs.mkdir()
    monkeypatch.setattr(np_cli, "DOSSIER_CONFIGS", configs)
    monkeypatch.setattr(np_cli, "depot_existe", lambda depot: True)
    monkeypatch.setattr(np_cli, "creer_labels", lambda depot: [])
    monkeypatch.setattr(np_cli, "creer_fichiers_contexte",
                        lambda rep, avec_specs: {"crees": [], "rep_cree": False})
    monkeypatch.setattr(np_cli, "initialiser_git", lambda rep, depot: {
        "ok": True, "detail": "ignoré (test)", "deja_git": True, "push_ok": None,
        "contenu_preexistant": [], "commande_manuelle": None,
    })
    monkeypatch.setattr(np_cli, "mettre_a_jour_doc",
                        lambda: {"existe": False, "ok2": False, "ok7": False, "ok_date": False})
    # "existe": False court-circuite l'appel à committer_pousser_doc ;
    # garde-fou supplémentaire (defense in depth) : même si ce chemin
    # changeait, committer_pousser_doc ne doit JAMAIS s'exécuter pour de
    # vrai depuis un test (commit + push RÉELS sur le dépôt de travail —
    # jamais toléré, cf. règle « CCL ne pousse jamais »).
    def _committer_pousser_doc_interdit(*a, **k):
        raise AssertionError("committer_pousser_doc ne doit jamais être appelé depuis un test")
    monkeypatch.setattr(np_cli.regenerer_tableaux_projets, "committer_pousser_doc",
                        _committer_pousser_doc_interdit)

    resultat = np_cli.creer_projet(
        nom="topicvide667", depot="AlainDelree/TopicVide667",
        rep=str(tmp_path / "rep"), perimetre=str(tmp_path / "rep"),
        topic="",
    )
    assert resultat["succes"] is True
    contenu = (configs / "topicvide667.conf").read_text(encoding="utf-8")
    assert "TOPIC_NTFY  = \n" in contenu
    assert "hippocampe" not in contenu


def test_topic_ntfy_defaut_retire():
    assert not hasattr(np_cli, "TOPIC_NTFY_DEFAUT")


def test_ecrire_conf_defaut_vide():
    import inspect
    sig = inspect.signature(np_cli.ecrire_conf)
    assert sig.parameters["topic"].default == ""


def test_sauvegarder_conf_topic_vide_sans_erreur(tmp_path, monkeypatch):
    configs = tmp_path / "configs"
    configs.mkdir()
    chemin = configs / "projettest667.conf"
    chemin.write_text(
        "NOM = projettest667\nDEPOT = AlainDelree/x\nREP_TRAVAIL = /tmp/x\n"
        "TOPIC_NTFY = ancien-topic\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(projets, "DOSSIER_SCRIPT", tmp_path)
    ok, msg = projets.sauvegarder_conf("projettest667", {"TOPIC_NTFY": ""})
    assert ok is True
    contenu = chemin.read_text(encoding="utf-8")
    assert "ancien-topic" not in contenu
    assert "TOPIC_NTFY = " in contenu


def main() -> int:
    import types
    tests = [(n, f) for n, f in globals().items()
             if n.startswith("test_") and isinstance(f, types.FunctionType)]
    echecs = 0
    for nom, fn in tests:
        try:
            import inspect
            params = inspect.signature(fn).parameters
            if "tmp_path" in params or "monkeypatch" in params:
                print(f"  · {nom} (ignoré hors pytest — nécessite un fixture)")
                continue
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
    print("\n✅ Tous les scénarios directement exécutables passent (lancer pytest pour la couverture complète).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
