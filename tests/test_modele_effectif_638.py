#!/usr/bin/env python3
"""Test de non-régression — issue #638 : mise en évidence, dans l'onglet
Résultats, des issues qui forcent un modèle différent du défaut du projet.

Couvre le versant SERVEUR (extraction du champ MODELE depuis le CORPS d'une
issue GitHub) :
- `extraire_modele_entete()` : champ présent et reconnu → nom canonique ;
  champ absent → None ; cellule vide → None ; valeur invalide/inconnue → None
  (ne plante pas, n'affiche rien) ; insensibilité à la casse ; robustesse aux
  corps dégénérés (vide, None) ;
- `modele_defaut_projet()` : MODELE_CCL du .conf s'il en fixe un, sinon le
  défaut global « claude-sonnet-5 » ;
- `_enrichir_modele()` : ajoute `modele`/`modele_defaut` à chaque issue et
  retire le corps volumineux.

Le versant NAVIGATEUR (calcul « modèle effectif ≠ défaut » → badge) est couvert
par static/js/tests/resultats.test.js (`node --test`).

Exécution :  python3 tests/test_modele_effectif_638.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import app.issues as ai  # noqa: E402


# En-tête bridge type, avec un champ MODELE forçant Opus.
CORPS_OPUS = """## En-tête

| Champ    | Valeur |
|----------|--------|
| SOURCE   | CC |
| DEST     | CCL |
| MODE     | écriture |
| PRIORITE | normale |
| TIMEOUT  | 1800s |
| PROJET   | bridge_agent |
| MODELE   | claude-opus-4-8 |

Corps de l'issue.
"""

# En-tête sans champ MODELE (cas le plus courant).
CORPS_SANS_MODELE = """## En-tête

| Champ    | Valeur |
|----------|--------|
| SOURCE   | CC |
| DEST     | CCL |
| MODE     | lecture |
| PROJET   | bridge_agent |

Corps de l'issue.
"""


def test_extraction_modele_present():
    """Champ MODELE présent et reconnu → nom canonique (minuscules)."""
    assert ai.extraire_modele_entete(CORPS_OPUS) == "claude-opus-4-8"
    for m in ("claude-sonnet-5", "claude-haiku-4-5", "claude-fable-5"):
        corps = CORPS_SANS_MODELE + f"\n| MODELE | {m} |\n"
        assert ai.extraire_modele_entete(corps) == m, m
    return "présent → nom canonique (4 modèles reconnus)"


def test_extraction_modele_absent():
    """Champ MODELE absent → None (l'appelant n'affiche rien de plus)."""
    assert ai.extraire_modele_entete(CORPS_SANS_MODELE) is None
    return "absent → None"


def test_extraction_modele_invalide_ne_plante_pas():
    """Valeur invalide/inconnue ou cellule vide → None, sans lever."""
    invalides = [
        "| MODELE | gpt-5 |",                 # modèle inconnu
        "| MODELE |  |",                       # cellule vide
        "| MODELE | claude-opus |",            # valeur tronquée non reconnue
        "| MODELE | défaut |",                 # ancien placeholder
    ]
    for ligne in invalides:
        corps = CORPS_SANS_MODELE + "\n" + ligne + "\n"
        assert ai.extraire_modele_entete(corps) is None, ligne
    # Corps dégénérés : ne lèvent jamais.
    assert ai.extraire_modele_entete("") is None
    assert ai.extraire_modele_entete(None) is None
    return "invalide/vide/inconnu/None → None (aucune exception)"


def test_extraction_modele_insensible_casse():
    """Le mot-clé MODELE et la valeur sont reconnus quelle que soit la casse."""
    corps = CORPS_SANS_MODELE + "\n| Modele | CLAUDE-OPUS-4-8 |\n"
    assert ai.extraire_modele_entete(corps) == "claude-opus-4-8"
    return "casse mixte du champ et de la valeur → reconnu"


def test_modele_defaut_projet():
    """Défaut projet = MODELE_CCL du .conf s'il en fixe un, sinon défaut global."""
    # .conf fixant explicitement un modèle.
    cfg_opus = SimpleNamespace(modele_ccl="claude-opus-4-8")
    assert ai.modele_defaut_projet(cfg_opus) == "claude-opus-4-8"
    # .conf sans MODELE_CCL (chaîne vide) → défaut global.
    cfg_vide = SimpleNamespace(modele_ccl="")
    assert ai.modele_defaut_projet(cfg_vide) == "claude-sonnet-5"
    # Champ absent de l'objet Config → défaut global (robustesse).
    cfg_absent = SimpleNamespace()
    assert ai.modele_defaut_projet(cfg_absent) == "claude-sonnet-5"
    # Casse/espaces normalisés.
    cfg_casse = SimpleNamespace(modele_ccl="  Claude-Haiku-4-5  ")
    assert ai.modele_defaut_projet(cfg_casse) == "claude-haiku-4-5"
    return "MODELE_CCL fixé / vide / absent / avec casse → défaut correct"


def test_enrichir_modele_ajoute_et_retire_body():
    """_enrichir_modele ajoute modele/modele_defaut et retire le corps."""
    cfg = SimpleNamespace(modele_ccl="claude-sonnet-5")
    issues = [
        {"number": 1, "title": "A", "body": CORPS_OPUS},
        {"number": 2, "title": "B", "body": CORPS_SANS_MODELE},
    ]
    enrichies = ai._enrichir_modele(issues, cfg)
    assert enrichies is issues                      # mute en place
    assert issues[0]["modele"] == "claude-opus-4-8"
    assert issues[0]["modele_defaut"] == "claude-sonnet-5"
    assert issues[1]["modele"] is None
    assert issues[1]["modele_defaut"] == "claude-sonnet-5"
    assert "body" not in issues[0] and "body" not in issues[1]
    return "modele/modele_defaut ajoutés, body retiré"


def main() -> int:
    print("Issue #638 — extraction MODELE (serveur) :")
    tests = [
        ("extraire_modele_entete : présent → nom canonique", test_extraction_modele_present),
        ("extraire_modele_entete : absent → None", test_extraction_modele_absent),
        ("extraire_modele_entete : invalide/vide → None sans planter",
         test_extraction_modele_invalide_ne_plante_pas),
        ("extraire_modele_entete : insensible à la casse", test_extraction_modele_insensible_casse),
        ("modele_defaut_projet : .conf sinon défaut global", test_modele_defaut_projet),
        ("_enrichir_modele : enrichit + retire body", test_enrichir_modele_ajoute_et_retire_body),
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
