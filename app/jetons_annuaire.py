"""Bandeau d'avertissement d'échéance des jetons de l'annuaire (issue #741).

Lit en lecture seule le fichier `jetons.json` tenu par le projet séparé
annuairetoken (métadonnées de jetons d'accès — jamais de valeur de jeton —
et, depuis l'issue #746, échéance de la licence d'évaluation Windows CCW),
hors de ce dépôt et hors git.
"""

import json
import logging
import os
from datetime import date
from pathlib import Path

log = logging.getLogger(__name__)

STATUTS_CONNUS = ("actif", "abandonné", "expiré")

SEUIL_ORANGE = 14  # jours restants à partir desquels le bandeau orange apparaît
SEUIL_ROUGE = 5    # jours restants (ou dépassement) à partir desquels il passe au rouge


def _niveau(jours_restants: int) -> str | None:
    """Niveau d'alerte ("rouge"/"orange") pour un nombre de jours restants
    donné, ou None si l'échéance est encore lointaine."""
    if jours_restants <= SEUIL_ROUGE:
        return "rouge"
    if jours_restants <= SEUIL_ORANGE:
        return "orange"
    return None

# Chemin par défaut du fichier, surchargeable globalement (pas par projet, pas
# dans configs/*.conf) par la variable d'environnement BRIDGE_JETONS_CHEMIN —
# aucun autre mécanisme de réglage global n'existe à ce jour dans Bridge_Agent.
VARIABLE_ENV_CHEMIN = "BRIDGE_JETONS_CHEMIN"
CHEMIN_DEFAUT = Path.home() / ".config" / "annuairetoken" / "jetons.json"

# Nombre maximal de lignes de jetons affichées avant de les remplacer par une
# ligne de synthèse (issue #742). La ligne « N entrée(s) ignorée(s) » n'est
# pas comptée dans ce plafond.
MAX_LIGNES_JETONS = 3


def _chemin_jetons() -> Path:
    brut = os.environ.get(VARIABLE_ENV_CHEMIN)
    if brut:
        return Path(brut).expanduser()
    return CHEMIN_DEFAUT


def _valider_jeton(brut: dict):
    """Valide une entrée de `jetons`. Renvoie (jours_restants, service, id)
    si le jeton est actif et expirable, None si valide mais rien à afficher
    (statut non-actif, ou sans expiration). Lève ValueError/TypeError si
    l'entrée elle-même est invalide (à compter parmi les ignorées)."""
    statut = brut.get("statut")
    if statut not in STATUTS_CONNUS:
        raise ValueError(f"statut inconnu : {statut!r}")

    service = str(brut.get("service", "")).strip()
    jeton_id = str(brut.get("id", "")).strip()
    if not service or not jeton_id:
        raise ValueError("id ou service manquant")

    expiration_brute = brut.get("expiration", "")
    if expiration_brute == "":
        return None  # n'expire jamais : jamais d'alerte
    date_expiration = date.fromisoformat(str(expiration_brute))  # ValueError si mal formée

    if statut != "actif":
        return None  # abandonné/expiré : jamais d'alerte

    jours_restants = (date_expiration - date.today()).days
    return jours_restants, service, jeton_id


def etat_jetons_annuaire() -> dict | None:
    """État du bandeau d'expiration des jetons de l'annuaire, ou None si rien
    à afficher (fichier absent, ou aucun jeton actif proche de l'échéance)."""
    chemin = _chemin_jetons()
    if not chemin.exists():
        return None

    try:
        with chemin.open(encoding="utf-8") as f:
            data = json.load(f)
        jetons = data["jetons"]
        int(data["version"])
        if not isinstance(jetons, list):
            raise ValueError("clé jetons n'est pas une liste")
    except (json.JSONDecodeError, OSError, KeyError, ValueError, TypeError) as e:
        log.warning("jetons.json illisible (%s) : %s", chemin, e)
        return {"niveau": "gris", "messages": ["jetons.json illisible, bandeau désactivé"]}

    alertes = []
    n_ignores = 0
    for brut in jetons:
        try:
            resultat = _valider_jeton(brut)
        except (KeyError, ValueError, TypeError) as e:
            log.warning("entrée de jetons.json ignorée (%s) : %s", chemin, e)
            n_ignores += 1
            continue
        if resultat is None:
            continue
        jours_restants, service, jeton_id = resultat
        niveau = _niveau(jours_restants)
        if not niveau:
            continue
        if jours_restants < 0:
            texte_jours = f"expiré depuis {-jours_restants} j"
        elif jours_restants == 0:
            texte_jours = "expire aujourd'hui"
        else:
            texte_jours = f"{jours_restants} j restant(s)"
        alertes.append({
            "niveau": niveau,
            "jours_restants": jours_restants,
            "jeton_id": jeton_id,
            "message": f"⚠️ Échéance {service} ({jeton_id}) : {texte_jours}",
        })

    if not alertes and not n_ignores:
        return None

    niveau_global = "rouge" if any(a["niveau"] == "rouge" for a in alertes) else "orange"

    alertes.sort(key=lambda a: (a["jours_restants"], a["jeton_id"]))

    visibles = alertes[:MAX_LIGNES_JETONS]
    masques = alertes[MAX_LIGNES_JETONS:]

    messages = [a["message"] for a in visibles]
    if masques:
        n_masques = len(masques)
        autre = "autre" if n_masques == 1 else "autres"
        jeton = "jeton" if n_masques == 1 else "jetons"
        messages.append(f"⚠️ + {n_masques} {autre} {jeton} à renouveler — voir l'annuaire")
    if n_ignores:
        messages.append(f"⚠️ {n_ignores} entrée(s) ignorée(s) dans jetons.json")

    return {
        "niveau": niveau_global,
        "messages": messages,
    }
