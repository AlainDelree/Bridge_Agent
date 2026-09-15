#!/usr/bin/env python3
"""Test de non-régression — issue #556 (2/3) : traitement du champ d'en-tête
`CREATION` dans watcher.py — bootstrap automatique d'un service CCW dédié.

Couvre, SANS vraie issue GitHub ni vraie machine CCW (sur le modèle du test
unitaire SOUS_DOSSIER de #550) :
- extraction/détection des champs CREATION/CREATION_* (`creation_demandee`,
  `extraire_champs_creation`), y compris la non-collision entre `CREATION` et
  `CREATION_NOM_PROJET`/... (préfixe partagé) ;
- retrait des 2 tokens chiffrés du corps (`_corps_avec_tokens_retires`) ;
- résolution robuste du chemin openssl (`_resoudre_openssl`) : PATH, repli
  installation manuelle Windows (#557), repli usr\\bin de Git, échec propre ;
- chiffrement/déchiffrement réel via openssl local (RSA 3072 + OAEP/SHA-256,
  convention documentée en BRIDGE_AGENT_DOC.md §16) — `dechiffrer_token_bootstrap` ;
- le chemin complet `_traiter_creation_projet_ccw` : succès (2 scripts
  PowerShell appelés dans l'ordre, avec les bons arguments, fichier de
  valeurs au format attendu par finaliser_projet_ccw_auto.ps1, tokens
  redirigés du corps GitHub, commentaire + fermeture), échec (champ manquant
  → needs-human, sans toucher à openssl/PowerShell), dry-run (simulé, aucun
  script exécuté) ;
- le dispatch dans `traiter_issue` : une issue CREATION ne lance JAMAIS
  `claude` (décision #554 §2.5) — vérifié en observant qu'un faux `claude`
  marqueur n'est jamais touché.

`gh` et `powershell` sont remplacés par de faux exécutables (même technique
que tests/test_lecture_active_327.py) : aucun accès réseau ni machine
Windows réelle. `platform.system` est monkeypatché pour simuler CCW.

Exécution :  python3 tests/test_creation_bootstrap_ccw_556.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import base64
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import watcher  # noqa: E402


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


def _chiffrer(pub: Path, texte_clair: str) -> str:
    res = subprocess.run(
        ["openssl", "pkeyutl", "-encrypt", "-pubin", "-inkey", str(pub),
         "-pkeyopt", "rsa_padding_mode:oaep", "-pkeyopt", "rsa_oaep_md:sha256"],
        input=texte_clair.encode("utf-8"), capture_output=True, check=True,
    )
    return base64.b64encode(res.stdout).decode("ascii")


# ─── Scénarios : extraction / détection ─────────────────────────────────────

def scenario_creation_demandee_detection():
    """`creation_demandee` reconnaît oui/true/vrai, rejette le reste, et ne
    se laisse PAS piéger par le préfixe partagé avec CREATION_NOM_PROJET."""
    assert watcher.creation_demandee("| CREATION | oui |\n")
    assert watcher.creation_demandee("| CREATION | TRUE |\n")
    assert watcher.creation_demandee("| CREATION | Vrai |\n")
    assert not watcher.creation_demandee("| CREATION | non |\n")
    assert not watcher.creation_demandee("Rien à voir ici.\n")
    # Collision : une ligne CREATION_NOM_PROJET seule (sans ligne CREATION)
    # ne doit JAMAIS activer le bootstrap — bug visé par la comparaison
    # exacte de _extraire_champ_entete plutôt qu'une recherche de sous-chaîne.
    assert not watcher.creation_demandee("| CREATION_NOM_PROJET | oui |\n")
    return {}


def scenario_extraction_champs_creation():
    """extraire_champs_creation lit les 5 champs, sans confondre CREATION_NOM_PROJET
    et CREATION_NOM_PROJET_QUELQUECHOSE (comparaison exacte)."""
    corps = (
        "| CREATION | oui |\n"
        "| CREATION_NOM_PROJET | MonProjet |\n"
        "| CREATION_DEPOT | AlainDelree/MonProjet |\n"
        "| CREATION_TOPIC_NTFY | bridge-monprojet |\n"
        "| CREATION_GH_TOKEN | QUFBQg== |\n"
        "| CREATION_OAUTH_TOKEN | Q0NDRA== |\n"
    )
    champs = watcher.extraire_champs_creation(corps)
    assert champs["CREATION_NOM_PROJET"] == "MonProjet", champs
    assert champs["CREATION_DEPOT"] == "AlainDelree/MonProjet", champs
    assert champs["CREATION_TOPIC_NTFY"] == "bridge-monprojet", champs
    assert champs["CREATION_GH_TOKEN"] == "QUFBQg==", champs
    assert champs["CREATION_OAUTH_TOKEN"] == "Q0NDRA==", champs
    return {"champs": list(champs)}


def scenario_extraction_champs_absents():
    """Champs absents du corps → chaînes vides, pas d'exception."""
    champs = watcher.extraire_champs_creation("| PROJET | bridge_agent |\n")
    assert all(v == "" for v in champs.values()), champs
    return {}


def scenario_retrait_tokens_corps():
    """_corps_avec_tokens_retires masque UNIQUEMENT les 2 champs de tokens,
    laisse le reste du corps identique (y compris CREATION_NOM_PROJET, qui
    partage le préfixe CREATION_ mais n'est pas un secret)."""
    corps = (
        "| CREATION | oui |\n"
        "| CREATION_NOM_PROJET | MonProjet |\n"
        "| CREATION_GH_TOKEN | SECRETGH== |\n"
        "| CREATION_OAUTH_TOKEN | SECRETOAUTH== |\n"
        "\nTexte libre après l'en-tête.\n"
    )
    nouveau = watcher._corps_avec_tokens_retires(corps)
    assert "SECRETGH==" not in nouveau, nouveau
    assert "SECRETOAUTH==" not in nouveau, nouveau
    assert nouveau.count("<retiré après application>") == 2, nouveau
    assert "| CREATION_NOM_PROJET | MonProjet |" in nouveau, nouveau
    assert "Texte libre après l'en-tête." in nouveau, nouveau
    return {}


# ─── Scénarios : résolution openssl ─────────────────────────────────────────

def scenario_resoudre_openssl_path():
    """openssl déjà sur le PATH (cas CCL, et CCW si l'installeur l'y ajoute) :
    résolu en premier, sans consulter les autres candidats."""
    chemin = watcher._resoudre_openssl()
    assert chemin, chemin
    assert Path(chemin).is_file(), chemin
    return {"chemin": chemin}


def scenario_resoudre_openssl_repli_installation_manuelle(tmp_path_factory):
    """PATH sans openssl → repli sur l'installation manuelle Windows (#557)."""
    tmp = tmp_path_factory()
    faux_openssl = tmp / "openssl.exe"
    faux_openssl.write_text("faux binaire\n")
    ancien_which = watcher.shutil.which
    ancien_chemin = watcher.CHEMIN_OPENSSL_WIN64
    try:
        watcher.shutil.which = lambda nom: None
        watcher.CHEMIN_OPENSSL_WIN64 = faux_openssl
        chemin = watcher._resoudre_openssl()
        assert chemin == str(faux_openssl), chemin
    finally:
        watcher.shutil.which = ancien_which
        watcher.CHEMIN_OPENSSL_WIN64 = ancien_chemin
    return {}


def scenario_resoudre_openssl_repli_git_usr_bin(tmp_path_factory):
    """PATH sans openssl, installation manuelle absente → repli usr\\bin de
    Git (même binaire que celui utilisé par provisionner.ps1 à la
    génération des clés)."""
    tmp = tmp_path_factory()
    racine_git = tmp / "Git"
    git_exe = racine_git / "cmd" / "git.exe"
    git_exe.parent.mkdir(parents=True)
    git_exe.write_text("faux git\n")
    openssl_usr_bin = racine_git / "usr" / "bin" / "openssl.exe"
    openssl_usr_bin.parent.mkdir(parents=True)
    openssl_usr_bin.write_text("faux openssl\n")

    ancien_which = watcher.shutil.which
    ancien_chemin = watcher.CHEMIN_OPENSSL_WIN64
    try:
        def _which(nom):
            return str(git_exe) if nom == "git" else None
        watcher.shutil.which = _which
        watcher.CHEMIN_OPENSSL_WIN64 = tmp / "chemin_inexistant" / "openssl.exe"
        chemin = watcher._resoudre_openssl()
        assert chemin == str(openssl_usr_bin), chemin
    finally:
        watcher.shutil.which = ancien_which
        watcher.CHEMIN_OPENSSL_WIN64 = ancien_chemin
    return {}


def scenario_resoudre_openssl_echec_propre(tmp_path_factory):
    """Aucun candidat trouvable → RuntimeError explicite (pas d'exception
    non gérée)."""
    tmp = tmp_path_factory()
    ancien_which = watcher.shutil.which
    ancien_chemin = watcher.CHEMIN_OPENSSL_WIN64
    try:
        watcher.shutil.which = lambda nom: None
        watcher.CHEMIN_OPENSSL_WIN64 = tmp / "chemin_inexistant" / "openssl.exe"
        try:
            watcher._resoudre_openssl()
            assert False, "RuntimeError attendue"
        except RuntimeError as e:
            assert "introuvable" in str(e), e
    finally:
        watcher.shutil.which = ancien_which
        watcher.CHEMIN_OPENSSL_WIN64 = ancien_chemin
    return {}


# ─── Scénarios : déchiffrement réel ──────────────────────────────────────────

def scenario_dechiffrement_aller_retour(tmp_path_factory):
    """Chiffré côté « formulaire » (clé publique, OAEP/SHA-256) → déchiffré
    par dechiffrer_token_bootstrap (clé privée) : round-trip exact."""
    tmp = tmp_path_factory()
    priv, pub = _generer_paire_cles(tmp)
    token_clair = "ghp_CeciEstUnFauxTokenDeTest1234567890"
    b64 = _chiffrer(pub, token_clair)
    dechiffre = watcher.dechiffrer_token_bootstrap(b64, priv)
    assert dechiffre == token_clair, dechiffre
    return {}


def scenario_dechiffrement_base64_invalide(tmp_path_factory):
    """Base64 corrompu → ValueError explicite, pas d'appel openssl inutile."""
    tmp = tmp_path_factory()
    priv, _pub = _generer_paire_cles(tmp)
    try:
        watcher.dechiffrer_token_bootstrap("ceci n'est pas du base64 valide!!", priv)
        assert False, "ValueError attendue"
    except ValueError:
        pass
    return {}


def scenario_dechiffrement_mauvaise_cle(tmp_path_factory):
    """Chiffré avec une clé, déchiffré avec une AUTRE (clé privée non
    correspondante) → RuntimeError (openssl échoue), jamais un résultat
    corrompu silencieux (propriété du padding OAEP)."""
    tmp = tmp_path_factory()
    _priv_a, pub_a = _generer_paire_cles(tmp / "a")
    priv_b, _pub_b = _generer_paire_cles(tmp / "b")
    b64 = _chiffrer(pub_a, "peu importe")
    try:
        watcher.dechiffrer_token_bootstrap(b64, priv_b)
        assert False, "RuntimeError attendue"
    except RuntimeError:
        pass
    return {}


# ─── Scénario complet : _traiter_creation_projet_ccw ────────────────────────

FAUX_GH = """#!/bin/bash
# Faux `gh` — issue #556. Stateful sur `issue view --json comments` (marqueur
# touché par `issue comment` quand le body contient MARQUEUR_RESULTAT) et
# journalise les `issue edit --body-file` (retrait des tokens) et
# `issue close`/`issue edit --add-label` dans des fichiers dédiés.
if [ "$1" = "issue" ] && [ "$2" = "comment" ]; then
    bodyfile=""
    prev=""
    for arg in "$@"; do
        if [ "$prev" = "--body-file" ]; then bodyfile="$arg"; fi
        prev="$arg"
    done
    if [ -n "$bodyfile" ] && grep -q -- '<!-- bridge:resultat -->' "$bodyfile" 2>/dev/null; then
        touch "$TEST_556_MARQUEUR"
    fi
    exit 0
fi
if [ "$1" = "issue" ] && [ "$2" = "view" ]; then
    if [ -n "$TEST_556_MARQUEUR" ] && [ -f "$TEST_556_MARQUEUR" ]; then
        echo '{"comments":[{"body":"<!-- bridge:resultat -->\\nfake"}]}'
    else
        echo '{"comments":[]}'
    fi
    exit 0
fi
if [ "$1" = "issue" ] && [ "$2" = "edit" ]; then
    bodyfile=""
    label=""
    prev=""
    for arg in "$@"; do
        if [ "$prev" = "--body-file" ]; then bodyfile="$arg"; fi
        if [ "$prev" = "--add-label" ]; then label="$arg"; fi
        prev="$arg"
    done
    if [ -n "$bodyfile" ]; then
        cp "$bodyfile" "$TEST_556_CORPS_EDITE"
    fi
    if [ -n "$label" ]; then
        echo "$label" >> "$TEST_556_LABELS"
    fi
    exit 0
fi
if [ "$1" = "issue" ] && [ "$2" = "close" ]; then
    touch "$TEST_556_FERME"
    exit 0
fi
exit 0
"""

FAUX_POWERSHELL = """#!/bin/bash
# Faux `powershell` — issue #556. Journalise chaque invocation (script + args)
# dans $TEST_556_LOG_PS, une ligne par appel. Code de sortie piloté par
# $TEST_556_CODE_AJOUTER / $TEST_556_CODE_FINALISER selon le script ciblé.
script=""
prev=""
for arg in "$@"; do
    if [ "$prev" = "-File" ]; then script="$arg"; fi
    prev="$arg"
done
nom_script=$(basename "$script")
echo "$nom_script|$*" >> "$TEST_556_LOG_PS"
if [ "$nom_script" = "ajouter_projet_ccw.ps1" ]; then
    echo "[ajouter-projet] simulation OK"
    exit "${TEST_556_CODE_AJOUTER:-0}"
fi
if [ "$nom_script" = "finaliser_projet_ccw_auto.ps1" ]; then
    echo "[finaliser-auto] simulation OK"
    # Vérifie que le fichier de valeurs contient bien les 3 clés attendues,
    # au format EXACT lu par mettre_a_jour_tokens_ccw.ps1 (Lire-ValeurFichier).
    fichier_valeurs=""
    prev2=""
    for arg in "$@"; do
        if [ "$prev2" = "-FichierValeurs" ]; then fichier_valeurs="$arg"; fi
        prev2="$arg"
    done
    if [ -n "$fichier_valeurs" ] && [ -f "$fichier_valeurs" ]; then
        cp "$fichier_valeurs" "$TEST_556_FICHIER_VALEURS_VU"
    fi
    exit "${TEST_556_CODE_FINALISER:-0}"
fi
exit 0
"""


def _preparer_bin(tmp: Path) -> Path:
    bin_dir = tmp / "bin"
    bin_dir.mkdir(exist_ok=True)
    for nom, contenu in (("gh", FAUX_GH), ("powershell", FAUX_POWERSHELL)):
        chemin = bin_dir / nom
        chemin.write_text(contenu, encoding="utf-8")
        chemin.chmod(chemin.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return bin_dir


def _corps_creation(nom_projet, depot, topic, gh_b64, oauth_b64):
    return (
        "## En-tête\n\n"
        "| CREATION | oui |\n"
        f"| CREATION_NOM_PROJET | {nom_projet} |\n"
        f"| CREATION_DEPOT | {depot} |\n"
        f"| CREATION_TOPIC_NTFY | {topic} |\n"
        f"| CREATION_GH_TOKEN | {gh_b64} |\n"
        f"| CREATION_OAUTH_TOKEN | {oauth_b64} |\n"
    )


def scenario_traiter_creation_succes(tmp_path_factory):
    """Chemin complet, succès : les 2 scripts PowerShell sont appelés dans
    l'ordre avec les bons arguments, le fichier de valeurs respecte le
    format -FichierValeurs, les tokens en clair (déchiffrés) y figurent (pas
    les versions chiffrées), le corps GitHub est édité pour retirer les
    tokens AVANT l'exécution des scripts, et l'issue est fermée avec le
    commentaire de résultat marqué."""
    tmp = tmp_path_factory()
    bin_dir = _preparer_bin(tmp)
    priv, pub = _generer_paire_cles(tmp)
    gh_clair, oauth_clair = "ghp_secretGH1234", "oauth_secretCCC5678"
    corps = _corps_creation("MonProjet", "AlainDelree/MonProjet", "bridge-monprojet",
                             _chiffrer(pub, gh_clair), _chiffrer(pub, oauth_clair))

    ancien_path = os.environ.get("PATH", "")
    ancien_cfg = watcher.CFG
    ancien_cle = watcher.CHEMIN_CLE_PRIVEE_BOOTSTRAP
    ancien_dossier_ps = watcher.DOSSIER_PROVISIONING_WINDOWS
    ancien_system = watcher.platform.system
    marqueur = tmp / "marqueur_resultat"
    corps_edite = tmp / "corps_edite.md"
    labels_fichier = tmp / "labels.txt"
    ferme_fichier = tmp / "ferme"
    log_ps = tmp / "log_ps.txt"
    fichier_valeurs_vu = tmp / "fichier_valeurs_vu.txt"
    os.environ.update({
        "TEST_556_MARQUEUR": str(marqueur),
        "TEST_556_CORPS_EDITE": str(corps_edite),
        "TEST_556_LABELS": str(labels_fichier),
        "TEST_556_FERME": str(ferme_fichier),
        "TEST_556_LOG_PS": str(log_ps),
        "TEST_556_FICHIER_VALEURS_VU": str(fichier_valeurs_vu),
    })
    try:
        os.environ["PATH"] = f"{bin_dir}:{ancien_path}"
        watcher.CFG = watcher.Config(
            nom="ccw", depot="AlainDelree/Bridge_Agent",
            rep_travail=Path("/tmp/nexiste-pas-556"), topic_ntfy="ccw",
            label="for-windows", notifier_local=False,
        )
        watcher.CHEMIN_CLE_PRIVEE_BOOTSTRAP = priv
        # Scripts PowerShell attendus : seule leur PRÉSENCE (fichier) est
        # vérifiée par le code avant exécution — le faux `powershell` sur le
        # PATH ignore leur contenu réel.
        dossier_ps = tmp / "provisioning" / "windows"
        dossier_ps.mkdir(parents=True)
        for nom_ps in ("ajouter_projet_ccw.ps1", "finaliser_projet_ccw_auto.ps1", "mettre_a_jour_tokens_ccw.ps1"):
            (dossier_ps / nom_ps).write_text("# script factice\n")
        watcher.DOSSIER_PROVISIONING_WINDOWS = dossier_ps
        watcher.platform.system = lambda: "Windows"

        watcher._traiter_creation_projet_ccw(9556, corps, ["for-windows"], dry_run=False)

        assert marqueur.exists(), "commentaire de résultat jamais posté"
        assert ferme_fichier.exists(), "issue jamais fermée"
        assert not labels_fichier.exists() or "needs-human" not in labels_fichier.read_text(), \
            "needs-human posé alors que le scénario doit réussir"

        lignes_ps = log_ps.read_text().splitlines()
        assert len(lignes_ps) == 2, lignes_ps
        assert lignes_ps[0].startswith("ajouter_projet_ccw.ps1|"), lignes_ps
        assert lignes_ps[1].startswith("finaliser_projet_ccw_auto.ps1|"), lignes_ps
        assert "-NomProjet MonProjet" in lignes_ps[0], lignes_ps[0]
        assert "-Depot AlainDelree/MonProjet" in lignes_ps[0], lignes_ps[0]
        assert "-NomProjet MonProjet" in lignes_ps[1], lignes_ps[1]

        contenu_valeurs = fichier_valeurs_vu.read_text()
        assert "TOPIC_NTFY=bridge-monprojet" in contenu_valeurs, contenu_valeurs
        assert f"GH_TOKEN={gh_clair}" in contenu_valeurs, contenu_valeurs
        assert f"CLAUDE_CODE_OAUTH_TOKEN={oauth_clair}" in contenu_valeurs, contenu_valeurs

        corps_final = corps_edite.read_text()
        assert gh_clair not in corps_final and oauth_clair not in corps_final, corps_final
        assert "<retiré après application>" in corps_final, corps_final
        assert "MonProjet" in corps_final, "le reste du corps ne doit pas être altéré"
    finally:
        os.environ["PATH"] = ancien_path
        for var in ("TEST_556_MARQUEUR", "TEST_556_CORPS_EDITE", "TEST_556_LABELS",
                    "TEST_556_FERME", "TEST_556_LOG_PS", "TEST_556_FICHIER_VALEURS_VU"):
            os.environ.pop(var, None)
        watcher.CFG = ancien_cfg
        watcher.CHEMIN_CLE_PRIVEE_BOOTSTRAP = ancien_cle
        watcher.DOSSIER_PROVISIONING_WINDOWS = ancien_dossier_ps
        watcher.platform.system = ancien_system
    return {}


def scenario_traiter_creation_champ_manquant_needs_human(tmp_path_factory):
    """Champ CREATION_DEPOT absent → échec DÉFINITIF immédiat (needs-human),
    SANS toucher openssl ni PowerShell (vérifié : aucune entrée dans le log
    des invocations PowerShell)."""
    tmp = tmp_path_factory()
    bin_dir = _preparer_bin(tmp)
    corps = (
        "| CREATION | oui |\n"
        "| CREATION_NOM_PROJET | MonProjet |\n"
        "| CREATION_TOPIC_NTFY | bridge-monprojet |\n"
        "| CREATION_GH_TOKEN | QUFBQg== |\n"
        "| CREATION_OAUTH_TOKEN | Q0NDRA== |\n"
    )
    ancien_path = os.environ.get("PATH", "")
    ancien_cfg = watcher.CFG
    ancien_system = watcher.platform.system
    labels_fichier = tmp / "labels.txt"
    log_ps = tmp / "log_ps.txt"
    os.environ.update({
        "TEST_556_MARQUEUR": str(tmp / "marqueur"),
        "TEST_556_CORPS_EDITE": str(tmp / "corps_edite.md"),
        "TEST_556_LABELS": str(labels_fichier),
        "TEST_556_FERME": str(tmp / "ferme"),
        "TEST_556_LOG_PS": str(log_ps),
        "TEST_556_FICHIER_VALEURS_VU": str(tmp / "fichier_valeurs_vu.txt"),
    })
    try:
        os.environ["PATH"] = f"{bin_dir}:{ancien_path}"
        watcher.CFG = watcher.Config(
            nom="ccw", depot="AlainDelree/Bridge_Agent",
            rep_travail=Path("/tmp/nexiste-pas-556b"), topic_ntfy="ccw",
            label="for-windows", notifier_local=False,
        )
        watcher.platform.system = lambda: "Windows"

        watcher._traiter_creation_projet_ccw(9557, corps, ["for-windows"], dry_run=False)

        assert labels_fichier.exists() and "needs-human" in labels_fichier.read_text(), \
            "label needs-human attendu"
        assert not log_ps.exists(), "aucun script PowerShell ne doit être lancé pour un champ manquant"
    finally:
        os.environ["PATH"] = ancien_path
        for var in ("TEST_556_MARQUEUR", "TEST_556_CORPS_EDITE", "TEST_556_LABELS",
                    "TEST_556_FERME", "TEST_556_LOG_PS", "TEST_556_FICHIER_VALEURS_VU"):
            os.environ.pop(var, None)
        watcher.CFG = ancien_cfg
        watcher.platform.system = ancien_system
    return {}


def scenario_traiter_creation_dry_run(tmp_path_factory):
    """dry_run=True : simulé (commentaire + fermeture), AUCUN script
    PowerShell exécuté, aucun déchiffrement tenté."""
    tmp = tmp_path_factory()
    bin_dir = _preparer_bin(tmp)
    corps = _corps_creation("MonProjet", "AlainDelree/MonProjet", "bridge-monprojet",
                             "chiffre-bidon-gh", "chiffre-bidon-oauth")
    ancien_path = os.environ.get("PATH", "")
    ancien_cfg = watcher.CFG
    ancien_system = watcher.platform.system
    marqueur = tmp / "marqueur"
    ferme_fichier = tmp / "ferme"
    log_ps = tmp / "log_ps.txt"
    os.environ.update({
        "TEST_556_MARQUEUR": str(marqueur),
        "TEST_556_CORPS_EDITE": str(tmp / "corps_edite.md"),
        "TEST_556_LABELS": str(tmp / "labels.txt"),
        "TEST_556_FERME": str(ferme_fichier),
        "TEST_556_LOG_PS": str(log_ps),
        "TEST_556_FICHIER_VALEURS_VU": str(tmp / "fichier_valeurs_vu.txt"),
    })
    try:
        os.environ["PATH"] = f"{bin_dir}:{ancien_path}"
        watcher.CFG = watcher.Config(
            nom="ccw", depot="AlainDelree/Bridge_Agent",
            rep_travail=Path("/tmp/nexiste-pas-556c"), topic_ntfy="ccw",
            label="for-windows", notifier_local=False,
        )
        watcher.platform.system = lambda: "Windows"

        watcher._traiter_creation_projet_ccw(9558, corps, ["for-windows"], dry_run=True)

        assert marqueur.exists(), "commentaire de résultat (simulé) jamais posté"
        assert ferme_fichier.exists(), "issue jamais fermée (dry-run)"
        assert not log_ps.exists(), "aucun script PowerShell ne doit être lancé en dry-run"
    finally:
        os.environ["PATH"] = ancien_path
        for var in ("TEST_556_MARQUEUR", "TEST_556_CORPS_EDITE", "TEST_556_LABELS",
                    "TEST_556_FERME", "TEST_556_LOG_PS", "TEST_556_FICHIER_VALEURS_VU"):
            os.environ.pop(var, None)
        watcher.CFG = ancien_cfg
        watcher.platform.system = ancien_system
    return {}


def scenario_dispatch_jamais_claude(tmp_path_factory):
    """Bout en bout via watcher.traiter_issue() : une issue portant CREATION
    ne lance JAMAIS `claude`, même si un faux `claude` (qui échouerait le
    test s'il était invoqué) est sur le PATH — décision #554 §2.5."""
    tmp = tmp_path_factory()
    bin_dir = _preparer_bin(tmp)
    marqueur_claude = tmp / "claude_a_ete_lance"
    claude_path = bin_dir / "claude"
    claude_path.write_text(f"#!/bin/bash\ntouch {marqueur_claude}\nexit 1\n", encoding="utf-8")
    claude_path.chmod(claude_path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    priv, pub = _generer_paire_cles(tmp)
    corps = _corps_creation("AutreProjet", "AlainDelree/AutreProjet", "bridge-autreprojet",
                             _chiffrer(pub, "ghtok"), _chiffrer(pub, "oauthtok"))
    issue = {
        "number": 9559, "title": "Créer le projet AutreProjet",
        "body": corps, "labels": [{"name": "for-windows"}],
    }

    ancien_path = os.environ.get("PATH", "")
    ancien_cfg = watcher.CFG
    ancien_cle = watcher.CHEMIN_CLE_PRIVEE_BOOTSTRAP
    ancien_dossier_ps = watcher.DOSSIER_PROVISIONING_WINDOWS
    ancien_system = watcher.platform.system
    ancien_dossier_verrous = watcher.DOSSIER_VERROUS
    marqueur_resultat = tmp / "marqueur_resultat"
    os.environ.update({
        "TEST_556_MARQUEUR": str(marqueur_resultat),
        "TEST_556_CORPS_EDITE": str(tmp / "corps_edite.md"),
        "TEST_556_LABELS": str(tmp / "labels.txt"),
        "TEST_556_FERME": str(tmp / "ferme"),
        "TEST_556_LOG_PS": str(tmp / "log_ps.txt"),
        "TEST_556_FICHIER_VALEURS_VU": str(tmp / "fichier_valeurs_vu.txt"),
    })
    try:
        os.environ["PATH"] = f"{bin_dir}:{ancien_path}"
        watcher.DOSSIER_VERROUS = tmp / "verrous"
        watcher.CFG = watcher.Config(
            nom="ccw", depot="AlainDelree/Bridge_Agent",
            rep_travail=Path("/tmp/nexiste-pas-556d"), topic_ntfy="ccw",
            label="for-windows", notifier_local=False,
        )
        watcher.CHEMIN_CLE_PRIVEE_BOOTSTRAP = priv
        dossier_ps = tmp / "provisioning" / "windows"
        dossier_ps.mkdir(parents=True)
        for nom_ps in ("ajouter_projet_ccw.ps1", "finaliser_projet_ccw_auto.ps1", "mettre_a_jour_tokens_ccw.ps1"):
            (dossier_ps / nom_ps).write_text("# script factice\n")
        watcher.DOSSIER_PROVISIONING_WINDOWS = dossier_ps
        watcher.platform.system = lambda: "Windows"
        watcher.issues_en_cours.discard(9559)

        watcher.traiter_issue(issue, dry_run=False)

        assert not marqueur_claude.exists(), "claude a été invoqué alors que CREATION doit s'en passer entièrement (#554 §2.5)"
        assert marqueur_resultat.exists(), "le bootstrap déterministe n'a pourtant pas abouti"
    finally:
        os.environ["PATH"] = ancien_path
        for var in ("TEST_556_MARQUEUR", "TEST_556_CORPS_EDITE", "TEST_556_LABELS",
                    "TEST_556_FERME", "TEST_556_LOG_PS", "TEST_556_FICHIER_VALEURS_VU"):
            os.environ.pop(var, None)
        watcher.CFG = ancien_cfg
        watcher.CHEMIN_CLE_PRIVEE_BOOTSTRAP = ancien_cle
        watcher.DOSSIER_PROVISIONING_WINDOWS = ancien_dossier_ps
        watcher.platform.system = ancien_system
        watcher.DOSSIER_VERROUS = ancien_dossier_verrous
        watcher.issues_en_cours.discard(9559)
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
        ("creation_demandee : détection + non-collision avec CREATION_NOM_PROJET", scenario_creation_demandee_detection),
        ("extraire_champs_creation : les 5 champs, valeurs exactes", scenario_extraction_champs_creation),
        ("extraire_champs_creation : champs absents → chaînes vides", scenario_extraction_champs_absents),
        ("_corps_avec_tokens_retires : masque uniquement les 2 tokens", scenario_retrait_tokens_corps),
        ("_resoudre_openssl : trouvé sur le PATH", scenario_resoudre_openssl_path),
        ("_resoudre_openssl : repli installation manuelle Windows (#557)", lambda: scenario_resoudre_openssl_repli_installation_manuelle(_tmp_path_factory)),
        ("_resoudre_openssl : repli usr\\bin de Git", lambda: scenario_resoudre_openssl_repli_git_usr_bin(_tmp_path_factory)),
        ("_resoudre_openssl : aucun candidat → RuntimeError propre", lambda: scenario_resoudre_openssl_echec_propre(_tmp_path_factory)),
        ("dechiffrer_token_bootstrap : aller-retour chiffrement réel (openssl)", lambda: scenario_dechiffrement_aller_retour(_tmp_path_factory)),
        ("dechiffrer_token_bootstrap : base64 invalide → ValueError", lambda: scenario_dechiffrement_base64_invalide(_tmp_path_factory)),
        ("dechiffrer_token_bootstrap : mauvaise clé → RuntimeError (pas de résultat corrompu)", lambda: scenario_dechiffrement_mauvaise_cle(_tmp_path_factory)),
        ("_traiter_creation_projet_ccw : chemin complet, succès", lambda: scenario_traiter_creation_succes(_tmp_path_factory)),
        ("_traiter_creation_projet_ccw : champ manquant → needs-human, aucun script lancé", lambda: scenario_traiter_creation_champ_manquant_needs_human(_tmp_path_factory)),
        ("_traiter_creation_projet_ccw : dry-run simulé, aucun script lancé", lambda: scenario_traiter_creation_dry_run(_tmp_path_factory)),
        ("traiter_issue : dispatch CREATION → claude JAMAIS invoqué (#554 §2.5)", lambda: scenario_dispatch_jamais_claude(_tmp_path_factory)),
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
