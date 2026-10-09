#!/usr/bin/env python3
"""Test de non-régression — issue #744 : suite #743, lecture fiable de la
sortie de « nssm get <service> AppEnvironmentExtra » (caractères NUL
UTF-16) pour reconduire un jeton sans l'altérer.

Un essai réel sur le service CCW-Watcher-Scrabble a montré que cette sortie
n'est PAS du texte propre dans PowerShell : nssm écrit en UTF-16, mais la
console (notamment lancée à distance par SSH, où le décodage peut différer
de la session interactive) la redécode parfois comme du texte 8 bits — il
en résulte un caractère NUL (code 0) après CHAQUE caractère, plus des
lignes parasites d'un seul NUL entre les variables (le CR et le LF UTF-16
découpés séparément).

Couvre, SANS AUCUN vrai nssm/PowerShell (même discipline que
test_ccw_renouveler_un_seul_jeton_743.py) :

- `app.ccw._extraire_valeur_env_service` (port Python PUR de
  `Extraire-ValeurEnvironnementPropre`/`ConvertTo-LignesEnvironnementPropres`,
  provisioning/windows/mettre_a_jour_tokens_ccw.ps1) sur un échantillon
  FACTICE reproduisant fidèlement la sortie réelle mal décodée (encodage
  UTF-16 petit-boutiste puis redécodage comme texte 8 bits) : les valeurs
  d'origine sont retrouvées EXACTEMENT ;
- le même algorithme sur une sortie déjà propre (sans aucun NUL) ;
- lignes vides ignorées, variable absente, variable en double, valeur
  contenant un signe égal, valeur vide refusée ;
- `app.ccw._longueur_plausible` (port Python PUR du contrôle de cohérence
  avant écriture, section 2 du script PowerShell) ;
- aucune valeur de jeton dans les messages d'erreur de
  `_resoudre_jetons_renouvellement` sur ces nouveaux scénarios.

Exécution :  python3 tests/test_lecture_robuste_env_nssm_744.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import app.ccw as ccw  # noqa: E402

JETON_FACTICE_GH = "JETON_FACTICE_GH_1234567890abcdef"
JETON_FACTICE_OAUTH = "JETON_FACTICE_OAUTH_abcdefghijklmnopqrstuvwxyz0123456789"


def _texte_propre_trois_variables() -> str:
    return (
        f"GH_TOKEN={JETON_FACTICE_GH}\r\n"
        f"CLAUDE_CODE_OAUTH_TOKEN={JETON_FACTICE_OAUTH}\r\n"
        "PATH=C:\\Windows;C:\\Users\\AlainW\\.local\\bin\r\n"
    )


def _mal_decoder_comme_nssm_reel(texte: str) -> str:
    """Reproduit fidèlement la sortie réelle observée sur CCW-Watcher-Scrabble :
    encode `texte` en UTF-16 petit-boutiste (ce qu'écrit nssm), puis le
    redécode comme texte 8 bits (ce que fait la console dans ce contexte) —
    insère un NUL après chaque caractère ASCII d'origine."""
    return texte.encode("utf-16-le").decode("latin-1")


# ─── Reproduction fidèle de la sortie réelle (caractères NUL UTF-16) ───────

def test_lecture_sortie_mal_decodee_utf16_retrouve_valeurs_exactes():
    texte_mal_decode = _mal_decoder_comme_nssm_reel(_texte_propre_trois_variables())
    # La sortie mal décodée contient effectivement des NUL (sinon le test
    # ne reproduirait rien de réel).
    assert "\x00" in texte_mal_decode
    assert ccw._extraire_valeur_env_service(texte_mal_decode, "GH_TOKEN") == JETON_FACTICE_GH
    assert ccw._extraire_valeur_env_service(texte_mal_decode, "CLAUDE_CODE_OAUTH_TOKEN") == JETON_FACTICE_OAUTH
    return {}


def test_lecture_sortie_deja_propre_retrouve_valeurs_exactes():
    """Même algorithme, sortie DÉJÀ propre (sans aucun NUL) — doit continuer
    à fonctionner (session interactive, pas de redécodage erroné)."""
    texte_propre = _texte_propre_trois_variables()
    assert "\x00" not in texte_propre
    assert ccw._extraire_valeur_env_service(texte_propre, "GH_TOKEN") == JETON_FACTICE_GH
    assert ccw._extraire_valeur_env_service(texte_propre, "CLAUDE_CODE_OAUTH_TOKEN") == JETON_FACTICE_OAUTH
    return {}


def test_lignes_vides_ignorees():
    texte = _mal_decoder_comme_nssm_reel("\r\n\r\nGH_TOKEN=valeur_ok\r\n\r\n")
    assert ccw._extraire_valeur_env_service(texte, "GH_TOKEN") == "valeur_ok"
    return {}


def test_variable_absente_refuse():
    texte = _mal_decoder_comme_nssm_reel("GH_TOKEN=valeur_ok\r\n")
    assert ccw._extraire_valeur_env_service(texte, "CLAUDE_CODE_OAUTH_TOKEN") is None
    return {}


def test_variable_en_double_refuse():
    """Deux lignes pour la même clé — refus (ne reconduit jamais une valeur
    douteuse), quelle que soit la valeur de la première occurrence trouvée."""
    texte = _mal_decoder_comme_nssm_reel("GH_TOKEN=premiere\r\nGH_TOKEN=seconde\r\n")
    assert ccw._extraire_valeur_env_service(texte, "GH_TOKEN") is None
    return {}


def test_valeur_contenant_un_signe_egal():
    """Découpage sur le PREMIER signe égal seulement — une valeur contenant
    elle-même un « = » reste intacte."""
    texte = _mal_decoder_comme_nssm_reel("GH_TOKEN=abc=def=ghi\r\n")
    assert ccw._extraire_valeur_env_service(texte, "GH_TOKEN") == "abc=def=ghi"
    return {}


def test_valeur_vide_refusee():
    texte = _mal_decoder_comme_nssm_reel("GH_TOKEN=\r\nCLAUDE_CODE_OAUTH_TOKEN=valeur_ok\r\n")
    assert ccw._extraire_valeur_env_service(texte, "GH_TOKEN") is None
    assert ccw._extraire_valeur_env_service(texte, "CLAUDE_CODE_OAUTH_TOKEN") == "valeur_ok"
    return {}


def test_caractere_de_controle_residuel_refuse():
    """Un caractère de contrôle qui aurait survécu au nettoyage (autre qu'un
    NUL — ex. un fragment de NUL mal aligné) reste détecté et refusé."""
    texte = "GH_TOKEN=valeur\x01suspecte\r\n"
    assert ccw._extraire_valeur_env_service(texte, "GH_TOKEN") is None
    return {}


# ─── Contrôle de longueur avant écriture (issue #744, point 3) ────────────

def test_longueur_plausible_accepte_jetons_realistes():
    assert ccw._longueur_plausible(JETON_FACTICE_GH) is True
    assert ccw._longueur_plausible(JETON_FACTICE_OAUTH) is True
    return {}


def test_longueur_plausible_refuse_trop_court():
    assert ccw._longueur_plausible("x" * (ccw.LONGUEUR_JETON_MIN - 1)) is False
    return {}


def test_longueur_plausible_refuse_trop_long():
    assert ccw._longueur_plausible("x" * (ccw.LONGUEUR_JETON_MAX + 1)) is False
    return {}


def test_longueur_plausible_accepte_les_bornes():
    assert ccw._longueur_plausible("x" * ccw.LONGUEUR_JETON_MIN) is True
    assert ccw._longueur_plausible("x" * ccw.LONGUEUR_JETON_MAX) is True
    return {}


# ─── Aucune valeur de jeton dans les messages ──────────────────────────────

def test_resoudre_jetons_messages_derreur_sans_valeur_sur_sortie_mal_decodee():
    """Même avec une sortie d'environnement mal décodée (NUL UTF-16), les
    messages d'erreur de _resoudre_jetons_renouvellement ne contiennent
    jamais de valeur de jeton — ici le cas où la lecture échoue totalement
    (variable absente de l'environnement reconduit)."""
    texte_mal_decode = _mal_decoder_comme_nssm_reel("GH_TOKEN=valeur_secrete_gh\r\n")
    gh, oauth, erreur = ccw._resoudre_jetons_renouvellement("", "nouveau-oauth", texte_mal_decode)
    assert gh == "valeur_secrete_gh", gh
    assert oauth == "nouveau-oauth", oauth
    assert erreur is None, erreur

    gh2, oauth2, erreur2 = ccw._resoudre_jetons_renouvellement("nouveau-gh", "", texte_mal_decode)
    assert gh2 is None and oauth2 is None, (gh2, oauth2)
    assert erreur2 is not None
    assert "valeur_secrete_gh" not in erreur2, erreur2
    return {}


def main() -> int:
    tests = [
        ("sortie mal décodée UTF-16 (NUL) → valeurs exactes retrouvées", test_lecture_sortie_mal_decodee_utf16_retrouve_valeurs_exactes),
        ("sortie déjà propre (sans NUL) → valeurs exactes retrouvées", test_lecture_sortie_deja_propre_retrouve_valeurs_exactes),
        ("lignes vides ignorées", test_lignes_vides_ignorees),
        ("variable absente → refus", test_variable_absente_refuse),
        ("variable en double → refus", test_variable_en_double_refuse),
        ("valeur contenant un signe égal → intacte", test_valeur_contenant_un_signe_egal),
        ("valeur vide → refus", test_valeur_vide_refusee),
        ("caractère de contrôle résiduel → refus", test_caractere_de_controle_residuel_refuse),
        ("_longueur_plausible : jetons réalistes acceptés", test_longueur_plausible_accepte_jetons_realistes),
        ("_longueur_plausible : trop court refusé", test_longueur_plausible_refuse_trop_court),
        ("_longueur_plausible : trop long refusé", test_longueur_plausible_refuse_trop_long),
        ("_longueur_plausible : bornes acceptées", test_longueur_plausible_accepte_les_bornes),
        ("_resoudre_jetons_renouvellement : aucune valeur de jeton dans les messages (sortie mal décodée)", test_resoudre_jetons_messages_derreur_sans_valeur_sur_sortie_mal_decodee),
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
