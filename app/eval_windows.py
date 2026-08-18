"""Bandeau d'avertissement d'échéance de l'éval Windows CCW (issue #454) et
du CLAUDE_CODE_OAUTH_TOKEN du service CCW-Watcher (issue #456).

Réutilise le même calcul que provisioning/windows/verifier_expiration_ccw.py
(date_installation + eval_jours → date d'expiration), mais retourne un état
structuré pour l'interface web plutôt que d'imprimer sur la sortie standard.
"""

import json
from datetime import date, timedelta

from app.etat import RACINE

FICHIER_META = RACINE / "provisioning" / "windows" / "eval-expiration.json"

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


def etat_eval_windows() -> dict | None:
    """État du bandeau d'avertissement (éval Windows + token OAuth CCW), ou
    None si rien à afficher (fichier absent/invalide, ou échéances encore
    lointaines)."""
    if not FICHIER_META.exists():
        return None
    try:
        with FICHIER_META.open(encoding="utf-8") as f:
            meta = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None

    alertes = []

    try:
        date_install = date.fromisoformat(str(meta["date_installation"]))
        eval_jours = int(meta["eval_jours"])
        date_expiration = date_install + timedelta(days=eval_jours)
        jours_restants = (date_expiration - date.today()).days
        niveau = _niveau(jours_restants)
        if niveau:
            if jours_restants < 0:
                texte_jours = f"expirée depuis {-jours_restants} jour(s)"
            else:
                texte_jours = f"{jours_restants} jour(s) restant(s)"
            alertes.append({
                "niveau": niveau,
                "message": (f"⚠️ Éval Windows CCW : {texte_jours} — réinstaller avant le "
                            f"{date_expiration.strftime('%d/%m/%Y')}"),
            })
    except (KeyError, ValueError, TypeError):
        pass

    try:
        date_token = date.fromisoformat(str(meta["date_expiration_oauth_token"]))
        jours_restants_token = (date_token - date.today()).days
        niveau_token = _niveau(jours_restants_token)
        if niveau_token:
            if jours_restants_token < 0:
                texte_jours = f"expiré depuis {-jours_restants_token} jour(s)"
            else:
                texte_jours = f"{jours_restants_token} jours restants"
            alertes.append({
                "niveau": niveau_token,
                "message": (f"⚠️ OAuth Token CCW : {texte_jours} — renouveler avant le "
                            f"{date_token.strftime('%d/%m/%Y')}"),
            })
    except (KeyError, ValueError, TypeError):
        pass

    if not alertes:
        return None

    niveau_global = "rouge" if any(a["niveau"] == "rouge" for a in alertes) else "orange"

    return {
        "niveau": niveau_global,
        "messages": [a["message"] for a in alertes],
    }
