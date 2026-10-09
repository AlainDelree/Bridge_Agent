#!/usr/bin/env python3
"""Test de non-régression — issue #743 : onglet CCW, renouveler un seul jeton
(GH_TOKEN ou CLAUDE_CODE_OAUTH_TOKEN) en conservant l'autre, et poser le jeton
Claude sur tous les services CCW en une fois.

Couvre, SANS AUCUN vrai SSH/nssm/PowerShell (même discipline que les autres
tests de cette famille, ex. #709/#717) :

- `app.ccw._extraire_valeur_env_service` / `_resoudre_jetons_renouvellement` :
  port Python PUR (testable sans Windows) de l'algorithme RÉELLEMENT exécuté
  en PowerShell (provisioning/windows/mettre_a_jour_tokens_ccw.ps1,
  fonction Lire-EnvironnementActuelService + section 2) — un seul jeton fourni
  accepté (l'autre reconduit depuis l'environnement actuel du service), aucun
  jeton fourni refusé, deux jetons fournis inchangés, environnement actuel
  illisible → refus SANS modification (aucune valeur par défaut renvoyée) ;
- `app.ccw.ccw_finaliser_projet` (route Flask, sans SSH réel — `_preparer`
  substitué) : un seul jeton fourni accepté (fichier de valeurs ne contient
  QUE le jeton fourni — l'absence de la clé est le signal de reconduction
  côté PowerShell), aucun jeton + nom fourni refusé sans appel SSH, deux
  jetons fournis toujours écrits tous les deux (comportement inchangé) ;
- aucune valeur de jeton dans les messages d'erreur retournés par la route.

Exécution :  python3 tests/test_ccw_renouveler_un_seul_jeton_743.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import flask  # noqa: E402

import app.ccw as ccw  # noqa: E402

APP_FLASK = flask.Flask(__name__)


class FauxResultatSsh:
    """Même rôle que CompletedProcess pour les points d'appel SSH substitués
    ci-dessous (returncode/stdout/stderr) — jamais de vrai sous-processus."""

    def __init__(self, returncode, stdout="", stderr=""):
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr


class Patch:
    """Remplace `getattr(module, nom)` par `valeur` ; restaure à la sortie du
    `with`. Même utilitaire minimal que tests/test_demarrage_ccw_windows_717.py."""

    def __init__(self, module, nom, valeur):
        self.module, self.nom, self.valeur = module, nom, valeur

    def __enter__(self):
        self.original = getattr(self.module, self.nom)
        setattr(self.module, self.nom, self.valeur)
        return self.valeur

    def __exit__(self, *exc):
        setattr(self.module, self.nom, self.original)


def _appel_interdit(*_a, **_k):
    raise AssertionError("appel SSH inattendu — la route doit refuser avant tout aller-retour")


# ─── _extraire_valeur_env_service ──────────────────────────────────────────

ENV_SERVICE = (
    "PATH=C:\\Windows;C:\\Users\\AlainW\\.local\\bin\n"
    "GH_TOKEN=ghp_ancien_valeur\n"
    "CLAUDE_CODE_OAUTH_TOKEN=sk-ant-ancien-valeur\n"
)


def test_extraire_valeur_env_service_trouvee():
    assert ccw._extraire_valeur_env_service(ENV_SERVICE, "GH_TOKEN") == "ghp_ancien_valeur"
    assert ccw._extraire_valeur_env_service(ENV_SERVICE, "CLAUDE_CODE_OAUTH_TOKEN") == "sk-ant-ancien-valeur"
    return {}


def test_extraire_valeur_env_service_absente():
    assert ccw._extraire_valeur_env_service(ENV_SERVICE, "AUTRE_CLE") is None
    assert ccw._extraire_valeur_env_service("", "GH_TOKEN") is None
    return {}


# ─── _resoudre_jetons_renouvellement ───────────────────────────────────────

def test_resoudre_jetons_deux_fournis_inchange():
    """Deux jetons fournis : comportement inchangé, aucune lecture de
    l'environnement actuel nécessaire (même avec env_service_texte=None)."""
    gh, oauth, erreur = ccw._resoudre_jetons_renouvellement("nouveau-gh", "nouveau-oauth", None)
    assert (gh, oauth, erreur) == ("nouveau-gh", "nouveau-oauth", None)
    return {}


def test_resoudre_jetons_un_seul_fourni_reconduit_lautre():
    """GH_TOKEN fourni, CLAUDE_CODE_OAUTH_TOKEN absent : reconduit depuis
    l'environnement actuel du service, jamais la valeur en dur."""
    gh, oauth, erreur = ccw._resoudre_jetons_renouvellement("nouveau-gh", "", ENV_SERVICE)
    assert erreur is None, erreur
    assert gh == "nouveau-gh", gh
    assert oauth == "sk-ant-ancien-valeur", oauth
    return {}


def test_resoudre_jetons_oauth_fourni_reconduit_gh():
    """Symétrique : CLAUDE_CODE_OAUTH_TOKEN fourni, GH_TOKEN reconduit."""
    gh, oauth, erreur = ccw._resoudre_jetons_renouvellement("", "nouveau-oauth", ENV_SERVICE)
    assert erreur is None, erreur
    assert gh == "ghp_ancien_valeur", gh
    assert oauth == "nouveau-oauth", oauth
    return {}


def test_resoudre_jetons_aucun_fourni_refuse():
    gh, oauth, erreur = ccw._resoudre_jetons_renouvellement("", "", ENV_SERVICE)
    assert gh is None and oauth is None, (gh, oauth)
    assert erreur and "Au moins un jeton" in erreur, erreur
    return {}


def test_resoudre_jetons_environnement_illisible_refuse_sans_modification():
    """Un jeton fourni, l'autre absent, ET la lecture de l'environnement
    actuel du service échoue (None) : refus, AUCUNE valeur n'est renvoyée —
    pas de valeur par défaut substituée en silence."""
    gh, oauth, erreur = ccw._resoudre_jetons_renouvellement("nouveau-gh", "", None)
    assert gh is None and oauth is None, (gh, oauth)
    assert erreur and "CLAUDE_CODE_OAUTH_TOKEN" in erreur, erreur
    assert "fournissez les deux jetons" in erreur.lower(), erreur
    return {}


def test_resoudre_jetons_cle_absente_de_lenvironnement_refuse():
    """L'environnement actuel est lisible mais ne contient PAS la clé
    manquante (ex. service neuf) : même refus que si la lecture avait échoué."""
    env_sans_oauth = "PATH=C:\\Windows\nGH_TOKEN=ghp_ancien\n"
    gh, oauth, erreur = ccw._resoudre_jetons_renouvellement("nouveau-gh", "", env_sans_oauth)
    assert gh is None and oauth is None, (gh, oauth)
    assert erreur and "CLAUDE_CODE_OAUTH_TOKEN" in erreur, erreur
    return {}


# ─── ccw_finaliser_projet (route Flask, sans SSH réel) ─────────────────────

class _RequeteFactice:
    def __init__(self, donnees):
        self.json = donnees


def _appeler_finaliser(donnees, fichiers_copies):
    """Appelle ccw_finaliser_projet() avec request/_preparer/_copier/_executer_ps
    substitués — jamais de vrai SSH. `fichiers_copies` est une liste dans
    laquelle chaque fichier LOCAL copié est consigné (chemin, contenu texte)
    pour inspection — PAS de secret écrit sur disque en dehors du fichier
    temporaire 0600 déjà prévu par le code existant."""
    def _copier_facture(hote, utilisateur, cle_privee, source_local, timeout):
        contenu = None
        if Path(source_local).suffix == ".txt":
            contenu = Path(source_local).read_text(encoding="utf-8")
        fichiers_copies.append((Path(source_local).name, contenu))
        return FauxResultatSsh(0)

    def _executer_ps_facture(hote, utilisateur, cle_privee, nom_script, args_ps, timeout):
        return FauxResultatSsh(0, stdout="[finaliser-auto] OK\n")

    with APP_FLASK.test_request_context(), \
         Patch(ccw, "request", _RequeteFactice(donnees)), \
         Patch(ccw, "_preparer", lambda: (("192.168.1.50", "AlainW", "/chemin/cle"), None)), \
         Patch(ccw, "_copier", _copier_facture), \
         Patch(ccw, "_executer_ps", _executer_ps_facture):
        return ccw.ccw_finaliser_projet()


def test_finaliser_un_seul_token_gh_fourni_fichier_ne_contient_que_lui():
    """GH_TOKEN seul fourni : la route accepte, et le fichier de valeurs
    poussé au PC fixe NE CONTIENT PAS de ligne CLAUDE_CODE_OAUTH_TOKEN
    (absence de la clé = signal de reconduction côté PowerShell)."""
    fichiers = []
    rep = _appeler_finaliser(
        {"nom": "Scrabble", "topic": "", "gh_token": "ghp_nouveau", "oauth_token": ""},
        fichiers)
    j = rep.get_json()
    assert j["succes"] is True, j
    noms_contenus = [c for (_, c) in fichiers if c is not None]
    assert len(noms_contenus) == 1, fichiers
    contenu = noms_contenus[0]
    assert "GH_TOKEN=ghp_nouveau" in contenu, contenu
    assert "CLAUDE_CODE_OAUTH_TOKEN=" not in contenu, contenu
    assert "ghp_nouveau" not in repr(j), "le token ne doit jamais apparaître dans la réponse JSON"
    return {}


def test_finaliser_un_seul_token_oauth_fourni_fichier_ne_contient_que_lui():
    fichiers = []
    rep = _appeler_finaliser(
        {"nom": "Scrabble", "topic": "", "gh_token": "", "oauth_token": "sk-ant-nouveau"},
        fichiers)
    j = rep.get_json()
    assert j["succes"] is True, j
    contenu = next(c for (_, c) in fichiers if c is not None)
    assert "CLAUDE_CODE_OAUTH_TOKEN=sk-ant-nouveau" in contenu, contenu
    assert "GH_TOKEN=" not in contenu, contenu
    return {}


def test_finaliser_deux_tokens_fournis_comportement_inchange():
    fichiers = []
    rep = _appeler_finaliser(
        {"nom": "Scrabble", "topic": "monTopic", "gh_token": "ghp_x", "oauth_token": "sk-ant-y"},
        fichiers)
    j = rep.get_json()
    assert j["succes"] is True, j
    contenu = next(c for (_, c) in fichiers if c is not None)
    assert "GH_TOKEN=ghp_x" in contenu, contenu
    assert "CLAUDE_CODE_OAUTH_TOKEN=sk-ant-y" in contenu, contenu
    assert "TOPIC_NTFY=monTopic" in contenu, contenu
    return {}


def test_finaliser_aucun_token_refuse_sans_appel_ssh():
    """Aucun jeton fourni : refus IMMÉDIAT, avant tout aller-retour SSH
    (_preparer n'est même pas atteint)."""
    with APP_FLASK.test_request_context(), \
         Patch(ccw, "request", _RequeteFactice({"nom": "Scrabble", "topic": "", "gh_token": "", "oauth_token": ""})), \
         Patch(ccw, "_preparer", _appel_interdit):
        rep = ccw.ccw_finaliser_projet()
    j = rep.get_json()
    assert j["succes"] is False, j
    assert "Au moins un" in j["erreur"], j
    return {}


def main() -> int:
    tests = [
        ("_extraire_valeur_env_service : clé trouvée", test_extraire_valeur_env_service_trouvee),
        ("_extraire_valeur_env_service : clé absente", test_extraire_valeur_env_service_absente),
        ("_resoudre_jetons_renouvellement : deux fournis, inchangé", test_resoudre_jetons_deux_fournis_inchange),
        ("_resoudre_jetons_renouvellement : GH fourni, OAUTH reconduit", test_resoudre_jetons_un_seul_fourni_reconduit_lautre),
        ("_resoudre_jetons_renouvellement : OAUTH fourni, GH reconduit", test_resoudre_jetons_oauth_fourni_reconduit_gh),
        ("_resoudre_jetons_renouvellement : aucun fourni → refus", test_resoudre_jetons_aucun_fourni_refuse),
        ("_resoudre_jetons_renouvellement : environnement illisible → refus sans modification", test_resoudre_jetons_environnement_illisible_refuse_sans_modification),
        ("_resoudre_jetons_renouvellement : clé absente de l'environnement → refus", test_resoudre_jetons_cle_absente_de_lenvironnement_refuse),
        ("ccw_finaliser_projet : GH seul fourni → fichier ne contient que GH_TOKEN", test_finaliser_un_seul_token_gh_fourni_fichier_ne_contient_que_lui),
        ("ccw_finaliser_projet : OAUTH seul fourni → fichier ne contient que OAUTH", test_finaliser_un_seul_token_oauth_fourni_fichier_ne_contient_que_lui),
        ("ccw_finaliser_projet : deux tokens fournis, comportement inchangé", test_finaliser_deux_tokens_fournis_comportement_inchange),
        ("ccw_finaliser_projet : aucun token → refus sans appel SSH", test_finaliser_aucun_token_refuse_sans_appel_ssh),
    ]
    echecs = 0
    for nom, fn in tests:
        try:
            rap = fn()
            print(f"  ✓ {nom}" + (f"  ({rap})" if rap else ""))
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
