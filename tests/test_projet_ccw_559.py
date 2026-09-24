#!/usr/bin/env python3
"""Test de non-régression — issue #559 (3/3, ordre du flux corrigé par
#560) : case « Projet CCW » sur le formulaire de création de projet —
chiffrement et génération automatique des 2 issues (app/projet_ccw.py).

Couvre, SANS vraie machine CCW ni vraie issue GitHub (même technique que
tests/test_creation_bootstrap_ccw_556.py — `gh` remplacé par un faux
exécutable sur le PATH) :
- `_chiffrer_token` : aller-retour réel via openssl avec
  `watcher.dechiffrer_token_bootstrap` (#556) — vérifie que le chiffrement
  côté formulaire est le MIROIR EXACT du déchiffrement déjà validé côté
  watcher.py, padding OAEP/SHA-256 compris ;
- `_corps_issue_ccw` : le corps produit est parsable par
  `watcher.creation_demandee`/`extraire_champs_creation` — format EXACT
  attendu par #556 (BRIDGE_AGENT_DOC.md §16.6), verrou anti-régression le
  plus important de ce fichier ;
- `_corps_issue_ccl` : ne contient plus les 2 étapes manuelles caduques
  depuis #597 (#602), mais référence toujours le projet/dépôt et la
  cross-référence vers l'issue CCW une fois son numéro connu ;
- `_titre_issue_ccl`/`_titre_issue_ccw` : déterministes (même nom → même
  titre), condition nécessaire à la réutilisation de
  `_issue_ouverte_meme_titre` (anti-double-soumission, #189) ;
- `_creer_issue_gh` : création réussie (numéro extrait de l'URL `gh`) ET
  anti-doublon (aucun `gh issue create` déclenché si une issue ouverte
  porte déjà ce titre) ;
- `bootstrap_projet_ccw` (route Flask complète, via test_request_context) :
  validations (tokens manquants, clé publique absente du cache, **dépôt pas
  encore créé — garde-fou #560**), puis chemin de succès bout en bout — les
  2 issues sont créées avec les BONS labels/corps, la référence croisée est
  postée, et le démarrage du watcher (best-effort) est neutralisé pour ne
  jamais lancer un vrai sous-processus watcher.py pendant le test.

Exécution :  python3 tests/test_projet_ccw_559.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import base64
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import flask  # noqa: E402

import watcher  # noqa: E402
from app import projet_ccw  # noqa: E402

APP_FLASK = flask.Flask(__name__)


# ─── Aides crypto (openssl réel, disponible sur CCL) ────────────────────────

def _generer_paire_cles(tmp: Path) -> tuple[Path, Path]:
    tmp.mkdir(parents=True, exist_ok=True)
    priv = tmp / "bootstrap_privee.pem"
    pub = tmp / "bootstrap_publique.pem"
    subprocess.run(["openssl", "genpkey", "-algorithm", "RSA",
                     "-pkeyopt", "rsa_keygen_bits:3072", "-out", str(priv)],
                    check=True, capture_output=True)
    subprocess.run(["openssl", "pkey", "-in", str(priv), "-pubout", "-out", str(pub)],
                    check=True, capture_output=True)
    return priv, pub


# ─── Scénarios : chiffrement (miroir de dechiffrer_token_bootstrap) ────────

def scenario_chiffrement_aller_retour_watcher(tmp_path_factory):
    """_chiffrer_token (app/projet_ccw.py) chiffre avec la clé publique ;
    watcher.dechiffrer_token_bootstrap (#556, déjà validé en conditions
    réelles) doit pouvoir déchiffrer avec la clé privée correspondante et
    retrouver exactement le texte en clair — c'est LE point de compatibilité
    critique entre le formulaire (3/3) et le traitement watcher.py (2/3)."""
    tmp = tmp_path_factory()
    priv, pub = _generer_paire_cles(tmp)
    clair = "ghp_TokenSecretDeTest1234567890"
    b64 = projet_ccw._chiffrer_token(clair, pub)
    # Une seule ligne (issue #16.6 : base64 -w0 ou équivalent).
    assert "\n" not in b64, "le base64 ne doit tenir que sur une seule ligne"
    retrouve = watcher.dechiffrer_token_bootstrap(b64, priv)
    assert retrouve == clair, (retrouve, clair)
    return {}


def scenario_chiffrement_mauvaise_cle_echoue(tmp_path_factory):
    """Chiffré avec la clé publique A, déchiffré avec la clé privée B (sans
    rapport) → RuntimeError côté watcher.py, jamais un résultat corrompu
    silencieux (propriété OAEP, déjà couverte côté déchiffrement par #556 —
    revérifiée ici du point de vue du chiffrement)."""
    tmp = tmp_path_factory()
    _priv_a, pub_a = _generer_paire_cles(tmp / "a")
    priv_b, _pub_b = _generer_paire_cles(tmp / "b")
    b64 = projet_ccw._chiffrer_token("peu importe", pub_a)
    try:
        watcher.dechiffrer_token_bootstrap(b64, priv_b)
        assert False, "RuntimeError attendue"
    except RuntimeError:
        pass
    return {}


# ─── Scénarios : construction des corps d'issue ─────────────────────────────

def scenario_corps_issue_ccw_parsable_par_watcher():
    """Le corps produit par _corps_issue_ccw doit être EXACTEMENT ce
    qu'attendent creation_demandee/extraire_champs_creation (watcher.py,
    #556) — sinon la case « Projet CCW » produirait une issue CCW jamais
    traitée automatiquement, silencieusement."""
    corps = projet_ccw._corps_issue_ccw(
        "monprojet", "AlainDelree/MonProjet", "bridge-monprojet",
        "QUFBQg==", "Q0NDRA==", numero_ccl=123,
    )
    assert watcher.creation_demandee(corps), "champ CREATION non détecté"
    champs = watcher.extraire_champs_creation(corps)
    assert champs["CREATION_NOM_PROJET"] == "monprojet", champs
    assert champs["CREATION_DEPOT"] == "AlainDelree/MonProjet", champs
    assert champs["CREATION_TOPIC_NTFY"] == "bridge-monprojet", champs
    assert champs["CREATION_GH_TOKEN"] == "QUFBQg==", champs
    assert champs["CREATION_OAUTH_TOKEN"] == "Q0NDRA==", champs
    assert "#123" in corps, "référence croisée vers l'issue CCL absente"
    return {"champs": list(champs)}


def scenario_corps_issue_ccl_contenu():
    """Le corps de l'issue CCL ne contient plus les 2 étapes manuelles
    caduques depuis #597 (tableau $Projets de reinstaller_projets_ccw.ps1 +
    tableau de rappel REINSTALLATION_CCW.md §7, issue #602), référence bien
    le projet/dépôt et, une fois le numéro CCW connu, la cross-référence."""
    sans_ref = projet_ccw._corps_issue_ccl("monprojet", "AlainDelree/MonProjet", None)
    assert "reinstaller_projets_ccw.ps1" not in sans_ref
    assert "REINSTALLATION_CCW.md" not in sans_ref
    assert "monprojet" in sans_ref and "AlainDelree/MonProjet" in sans_ref
    assert "Issue CCW liée" not in sans_ref

    avec_ref = projet_ccw._corps_issue_ccl("monprojet", "AlainDelree/MonProjet", 456)
    assert "#456" in avec_ref
    return {}


def scenario_titres_deterministes():
    """Même nom de projet → même titre (nécessaire à la réutilisation
    correcte de _issue_ouverte_meme_titre, anti-double-soumission #189)."""
    assert projet_ccw._titre_issue_ccl("scrabble") == projet_ccw._titre_issue_ccl("scrabble")
    assert projet_ccw._titre_issue_ccw("scrabble") == projet_ccw._titre_issue_ccw("scrabble")
    assert projet_ccw._titre_issue_ccl("scrabble") != projet_ccw._titre_issue_ccl("rummikub")
    assert projet_ccw._titre_issue_ccl("scrabble") != projet_ccw._titre_issue_ccw("scrabble")
    return {}


# ─── Scénarios : _creer_issue_gh (faux `gh`) ────────────────────────────────

FAUX_GH = """#!/bin/bash
# Faux `gh` — issue #559 (+ garde-fou #560). issue list : renvoie
# $TEST_559_LISTE_OUVERTES (JSON, defaut []) pour piloter l'anti-doublon.
# issue create : journalise repo/titre/label/corps dans
# $TEST_559_LOG_CREATE, renvoie une URL avec un numero incremental
# ($TEST_559_COMPTEUR). issue comment : journalise dans
# $TEST_559_LOG_COMMENT. repo view : pilote _depot_existe_deja (#560) via
# $TEST_559_DEPOT_EXISTE (defaut "1", vide/absent = existe, "0" = n'existe
# pas encore).
if [ "$1" = "repo" ] && [ "$2" = "view" ]; then
    if [ "$TEST_559_DEPOT_EXISTE" = "0" ]; then
        exit 1
    fi
    exit 0
fi
if [ "$1" = "issue" ] && [ "$2" = "list" ]; then
    if [ -n "$TEST_559_LISTE_OUVERTES" ] && [ -f "$TEST_559_LISTE_OUVERTES" ]; then
        cat "$TEST_559_LISTE_OUVERTES"
    else
        echo "[]"
    fi
    exit 0
fi
if [ "$1" = "issue" ] && [ "$2" = "create" ]; then
    depot=""; titre=""; label=""; bodyfile=""
    prev=""
    for arg in "$@"; do
        if [ "$prev" = "--repo" ]; then depot="$arg"; fi
        if [ "$prev" = "--title" ]; then titre="$arg"; fi
        if [ "$prev" = "--label" ]; then label="$arg"; fi
        if [ "$prev" = "--body-file" ]; then bodyfile="$arg"; fi
        prev="$arg"
    done
    n=$(cat "$TEST_559_COMPTEUR" 2>/dev/null || echo 1000)
    n=$((n + 1))
    echo "$n" > "$TEST_559_COMPTEUR"
    {
        echo "=== create #$n ==="
        echo "DEPOT=$depot"
        echo "TITRE=$titre"
        echo "LABEL=$label"
        echo "BODY-BEGIN"
        cat "$bodyfile"
        echo "BODY-END"
    } >> "$TEST_559_LOG_CREATE"
    echo "https://github.com/$depot/issues/$n"
    exit 0
fi
if [ "$1" = "issue" ] && [ "$2" = "comment" ]; then
    depot=""; bodyfile=""; numero="$3"
    prev=""
    for arg in "$@"; do
        if [ "$prev" = "--repo" ]; then depot="$arg"; fi
        if [ "$prev" = "--body-file" ]; then bodyfile="$arg"; fi
        prev="$arg"
    done
    {
        echo "=== comment on #$numero ($depot) ==="
        cat "$bodyfile"
    } >> "$TEST_559_LOG_COMMENT"
    exit 0
fi
exit 0
"""


def _preparer_bin(tmp: Path) -> Path:
    bin_dir = tmp / "bin"
    bin_dir.mkdir(exist_ok=True)
    chemin = bin_dir / "gh"
    chemin.write_text(FAUX_GH, encoding="utf-8")
    chemin.chmod(chemin.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return bin_dir


def scenario_creer_issue_gh_succes(tmp_path_factory):
    """Chemin de succès : le numéro est correctement extrait de l'URL
    renvoyée par gh, le corps/labels transmis sont ceux du fichier
    temporaire (pas tronqués/déformés)."""
    tmp = tmp_path_factory()
    bin_dir = _preparer_bin(tmp)
    ancien_path = os.environ.get("PATH", "")
    log_create = tmp / "log_create.txt"
    compteur = tmp / "compteur.txt"
    os.environ["TEST_559_LOG_CREATE"] = str(log_create)
    os.environ["TEST_559_COMPTEUR"] = str(compteur)
    os.environ.pop("TEST_559_LISTE_OUVERTES", None)
    try:
        os.environ["PATH"] = f"{bin_dir}:{ancien_path}"
        cfg = SimpleNamespace(depot="AlainDelree/Bridge_Agent", nom="bridge_agent")
        res = projet_ccw._creer_issue_gh(cfg, "Un titre de test #559",
                                          "bridge,for-linux,mode_write", "corps de test")
        assert res["succes"], res
        assert res["numero"] == 1001, res
        assert res["url"] == "https://github.com/AlainDelree/Bridge_Agent/issues/1001", res
        contenu = log_create.read_text()
        assert "TITRE=Un titre de test #559" in contenu, contenu
        assert "corps de test" in contenu, contenu
    finally:
        os.environ["PATH"] = ancien_path
        for var in ("TEST_559_LOG_CREATE", "TEST_559_COMPTEUR", "TEST_559_LISTE_OUVERTES"):
            os.environ.pop(var, None)
    return {}


def scenario_creer_issue_gh_anti_doublon(tmp_path_factory):
    """Une issue OUVERTE portant déjà ce titre → refus, AUCUN `gh issue
    create` déclenché (vérifié par l'absence du fichier de log — le faux gh
    n'écrit dedans QUE sur la branche create)."""
    tmp = tmp_path_factory()
    bin_dir = _preparer_bin(tmp)
    ancien_path = os.environ.get("PATH", "")
    log_create = tmp / "log_create.txt"
    liste = tmp / "liste_ouvertes.json"
    liste.write_text('[{"number": 42, "title": "Titre déjà pris #559"}]', encoding="utf-8")
    os.environ["TEST_559_LOG_CREATE"] = str(log_create)
    os.environ["TEST_559_LISTE_OUVERTES"] = str(liste)
    try:
        os.environ["PATH"] = f"{bin_dir}:{ancien_path}"
        cfg = SimpleNamespace(depot="AlainDelree/Bridge_Agent", nom="bridge_agent")
        res = projet_ccw._creer_issue_gh(cfg, "Titre déjà pris #559", "bridge,for-linux", "corps")
        assert not res["succes"], res
        assert "42" in res["erreur"], res
        assert not log_create.exists(), "gh issue create n'aurait pas dû être invoqué"
    finally:
        os.environ["PATH"] = ancien_path
        for var in ("TEST_559_LOG_CREATE", "TEST_559_LISTE_OUVERTES"):
            os.environ.pop(var, None)
    return {}


# ─── Scénarios : route bootstrap_projet_ccw (Flask) ─────────────────────────

def _appeler_bootstrap(payload: dict):
    with APP_FLASK.test_request_context("/projet-ccw/bootstrap", json=payload):
        return projet_ccw.bootstrap_projet_ccw().get_json()


def scenario_bootstrap_tokens_manquants():
    r = _appeler_bootstrap({"nom": "monprojet", "depot": "AlainDelree/MonProjet",
                             "topic": "bridge-monprojet", "gh_token": "", "oauth_token": ""})
    assert not r["succes"], r
    assert "tokens" in r["erreur"].lower(), r
    return {}


def scenario_bootstrap_champs_absents():
    r = _appeler_bootstrap({"gh_token": "a", "oauth_token": "b"})
    assert not r["succes"], r
    return {}


def scenario_bootstrap_cle_publique_absente(tmp_path_factory):
    tmp = tmp_path_factory()
    ancien_cle = projet_ccw.CHEMIN_CLE_PUBLIQUE_CACHE
    projet_ccw.CHEMIN_CLE_PUBLIQUE_CACHE = tmp / "n-existe-pas.pem"
    try:
        r = _appeler_bootstrap({"nom": "monprojet", "depot": "AlainDelree/MonProjet",
                                 "topic": "bridge-monprojet",
                                 "gh_token": "ghp_x", "oauth_token": "oauth_y"})
        assert not r["succes"], r
        assert "Rafraîchir la clé" in r["erreur"], r
    finally:
        projet_ccw.CHEMIN_CLE_PUBLIQUE_CACHE = ancien_cle
    return {}


def scenario_bootstrap_succes_complet(tmp_path_factory):
    """Chemin complet, succès : les 2 issues sont créées (labels/corps
    attendus, format CREATION parsable par watcher.py), la référence
    croisée est postée sur l'issue CCL, et demarrer_watcher (best-effort)
    est neutralisé — jamais un vrai sous-processus lancé pendant le test."""
    tmp = tmp_path_factory()
    bin_dir = _preparer_bin(tmp)
    priv, pub = _generer_paire_cles(tmp / "cles")

    ancien_path = os.environ.get("PATH", "")
    ancien_cle = projet_ccw.CHEMIN_CLE_PUBLIQUE_CACHE
    ancien_config_ba = projet_ccw._config_bridge_agent

    log_create = tmp / "log_create.txt"
    log_comment = tmp / "log_comment.txt"
    compteur = tmp / "compteur.txt"
    os.environ["TEST_559_LOG_CREATE"] = str(log_create)
    os.environ["TEST_559_LOG_COMMENT"] = str(log_comment)
    os.environ["TEST_559_COMPTEUR"] = str(compteur)
    os.environ.pop("TEST_559_LISTE_OUVERTES", None)

    import app.watchers as watchers_mod
    ancien_demarrer = watchers_mod.demarrer_watcher
    appels_demarrer = []
    watchers_mod.demarrer_watcher = lambda cfg, forcer=False: (appels_demarrer.append(cfg.nom), (False, 0))[1]

    try:
        os.environ["PATH"] = f"{bin_dir}:{ancien_path}"
        projet_ccw.CHEMIN_CLE_PUBLIQUE_CACHE = pub
        cfg_ba = SimpleNamespace(depot="AlainDelree/Bridge_Agent", nom="bridge_agent")
        projet_ccw._config_bridge_agent = lambda: cfg_ba

        r = _appeler_bootstrap({
            "nom": "monprojet", "depot": "AlainDelree/MonProjet",
            "topic": "bridge-monprojet",
            "gh_token": "ghp_secretGH", "oauth_token": "oauth_secretCC",
        })
        assert r["succes"], r
        numero_ccl = r["issue_ccl_numero"]
        numero_ccw = r["issue_ccw_numero"]
        assert numero_ccw == numero_ccl + 1, r
        assert r["issue_ccl_url"].endswith(f"/issues/{numero_ccl}"), r
        assert r["issue_ccw_url"].endswith(f"/issues/{numero_ccw}"), r

        contenu_create = log_create.read_text()
        # Issue CCL : label for-linux, sans champ CREATION.
        assert "LABEL=bridge,for-linux,mode_write" in contenu_create, contenu_create
        # Issue CCW : label for-windows, avec le bloc CREATION complet.
        assert "LABEL=bridge,for-windows,mode_write" in contenu_create, contenu_create
        assert "CREATION_NOM_PROJET   | monprojet" in contenu_create, contenu_create
        assert "CREATION_DEPOT        | AlainDelree/MonProjet" in contenu_create, contenu_create
        assert "CREATION_TOPIC_NTFY   | bridge-monprojet" in contenu_create, contenu_create
        # Les tokens en clair ne doivent JAMAIS apparaître dans le corps posté.
        assert "ghp_secretGH" not in contenu_create, "token GH en clair dans le corps de l'issue"
        assert "oauth_secretCC" not in contenu_create, "token OAuth en clair dans le corps de l'issue"

        # Déchiffrement réel des valeurs CREATION_* extraites du corps loggé,
        # pour vérifier que ce qui a été réellement chiffré/posté redonne les
        # tokens d'origine via le déchiffrement déjà validé côté watcher.py.
        bloc_ccw = contenu_create.split(f"=== create #{numero_ccw} ===", 1)[1]
        champs = watcher.extraire_champs_creation(bloc_ccw)
        assert watcher.dechiffrer_token_bootstrap(champs["CREATION_GH_TOKEN"], priv) == "ghp_secretGH"
        assert watcher.dechiffrer_token_bootstrap(champs["CREATION_OAUTH_TOKEN"], priv) == "oauth_secretCC"

        contenu_comment = log_comment.read_text()
        assert f"=== comment on #{numero_ccl}" in contenu_comment, contenu_comment
        assert f"#{numero_ccw}" in contenu_comment, contenu_comment

        assert appels_demarrer == ["bridge_agent"], appels_demarrer
    finally:
        os.environ["PATH"] = ancien_path
        for var in ("TEST_559_LOG_CREATE", "TEST_559_LOG_COMMENT", "TEST_559_COMPTEUR",
                    "TEST_559_LISTE_OUVERTES"):
            os.environ.pop(var, None)
        projet_ccw.CHEMIN_CLE_PUBLIQUE_CACHE = ancien_cle
        projet_ccw._config_bridge_agent = ancien_config_ba
        watchers_mod.demarrer_watcher = ancien_demarrer
    return {}


def scenario_bootstrap_depot_inexistant_refuse(tmp_path_factory):
    """Garde-fou #560 — l'ordre corrigé du flux (case « Projet CCW ») : si le
    dépôt cible n'existe pas ENCORE sur GitHub, /projet-ccw/bootstrap refuse
    proprement AVANT de chiffrer quoi que ce soit ou de créer une issue.
    C'est le scénario qui aurait dû se produire dans l'ancien flux #559 (token
    demandé avant la création du dépôt) : plutôt que de laisser l'utilisateur
    coller un token scopé sur un dépôt inexistant, le serveur revérifie et
    bloque — aucune ligne ne doit apparaître dans le log `gh issue create`."""
    tmp = tmp_path_factory()
    bin_dir = _preparer_bin(tmp)
    _priv, pub = _generer_paire_cles(tmp / "cles")

    ancien_path = os.environ.get("PATH", "")
    ancien_cle = projet_ccw.CHEMIN_CLE_PUBLIQUE_CACHE
    log_create = tmp / "log_create.txt"
    os.environ["TEST_559_LOG_CREATE"] = str(log_create)
    os.environ["TEST_559_DEPOT_EXISTE"] = "0"
    try:
        os.environ["PATH"] = f"{bin_dir}:{ancien_path}"
        projet_ccw.CHEMIN_CLE_PUBLIQUE_CACHE = pub
        r = _appeler_bootstrap({
            "nom": "monprojet", "depot": "AlainDelree/MonProjet",
            "topic": "bridge-monprojet",
            "gh_token": "ghp_x", "oauth_token": "oauth_y",
        })
        assert not r["succes"], r
        assert "n'existe pas encore" in r["erreur"], r
        assert not log_create.exists(), "aucune issue n'aurait dû être créée (dépôt inexistant)"
    finally:
        os.environ["PATH"] = ancien_path
        for var in ("TEST_559_LOG_CREATE", "TEST_559_DEPOT_EXISTE"):
            os.environ.pop(var, None)
        projet_ccw.CHEMIN_CLE_PUBLIQUE_CACHE = ancien_cle
    return {}


def main():
    tmp = tempfile.TemporaryDirectory()
    compteur = {"n": 0}

    def _tmp_path_factory():
        compteur["n"] += 1
        p = Path(tmp.name) / f"scenario{compteur['n']}"
        p.mkdir(parents=True, exist_ok=True)
        return p

    tests = [
        ("_chiffrer_token : aller-retour réel avec dechiffrer_token_bootstrap (#556)",
         lambda: scenario_chiffrement_aller_retour_watcher(_tmp_path_factory)),
        ("_chiffrer_token : mauvaise clé privée → RuntimeError (pas de résultat corrompu)",
         lambda: scenario_chiffrement_mauvaise_cle_echoue(_tmp_path_factory)),
        ("_corps_issue_ccw : parsable par watcher.creation_demandee/extraire_champs_creation",
         scenario_corps_issue_ccw_parsable_par_watcher),
        ("_corps_issue_ccl : plus d'étapes obsolètes, projet/dépôt + cross-référence", scenario_corps_issue_ccl_contenu),
        ("_titre_issue_ccl/_titre_issue_ccw : déterministes par projet", scenario_titres_deterministes),
        ("_creer_issue_gh : succès, numéro extrait de l'URL", lambda: scenario_creer_issue_gh_succes(_tmp_path_factory)),
        ("_creer_issue_gh : anti-doublon, aucun gh issue create déclenché",
         lambda: scenario_creer_issue_gh_anti_doublon(_tmp_path_factory)),
        ("bootstrap_projet_ccw : tokens manquants → échec propre", scenario_bootstrap_tokens_manquants),
        ("bootstrap_projet_ccw : nom/depot/topic absents → échec propre", scenario_bootstrap_champs_absents),
        ("bootstrap_projet_ccw : clé publique absente du cache → échec propre",
         lambda: scenario_bootstrap_cle_publique_absente(_tmp_path_factory)),
        ("bootstrap_projet_ccw : chemin complet, succès (2 issues, format CREATION, cross-réf, watcher neutralisé)",
         lambda: scenario_bootstrap_succes_complet(_tmp_path_factory)),
        ("bootstrap_projet_ccw : dépôt pas encore créé → refus propre, aucune issue (garde-fou #560)",
         lambda: scenario_bootstrap_depot_inexistant_refuse(_tmp_path_factory)),
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

    tmp.cleanup()
    if echecs:
        print(f"\n❌ {echecs} scénario(s) en échec.")
        return 1
    print("\n✅ Tous les scénarios passent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
