"""Bandeau d'avertissement d'échéance de l'éval Windows CCW (issue #454).

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


def etat_eval_windows() -> dict | None:
    """État du bandeau d'avertissement, ou None si rien à afficher (fichier
    absent/invalide, ou échéance encore lointaine)."""
    if not FICHIER_META.exists():
        return None
    try:
        with FICHIER_META.open(encoding="utf-8") as f:
            meta = json.load(f)
        date_install = date.fromisoformat(str(meta["date_installation"]))
        eval_jours = int(meta["eval_jours"])
    except (json.JSONDecodeError, OSError, KeyError, ValueError, TypeError):
        return None

    date_expiration = date_install + timedelta(days=eval_jours)
    jours_restants = (date_expiration - date.today()).days

    if jours_restants <= SEUIL_ROUGE:
        niveau = "rouge"
    elif jours_restants <= SEUIL_ORANGE:
        niveau = "orange"
    else:
        return None

    if jours_restants < 0:
        texte_jours = f"expirée depuis {-jours_restants} jour(s)"
    else:
        texte_jours = f"{jours_restants} jour(s) restant(s)"

    return {
        "jours_restants": jours_restants,
        "date_expiration": date_expiration.strftime("%d/%m/%Y"),
        "niveau": niveau,
        "message": (f"⚠️ Éval Windows CCW : {texte_jours} — réinstaller avant le "
                    f"{date_expiration.strftime('%d/%m/%Y')}"),
    }
