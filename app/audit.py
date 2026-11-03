"""Template d'audit par projet + préparation de l'issue d'audit (issue #848).

Chaque projet a son propre texte d'audit (toujours la même structure de
tâche, un seul texte par projet) — importé depuis un fichier `.txt` AU MÊME
FORMAT que ceux déposés dans `issues_inbox/` (en-tête `| CHAMP | valeur |`,
ligne `#Titre:`, corps), pour qu'un fichier rédigé par Claude Chat soit
importable tel quel. On réutilise donc `extraire_champs()` de
`scripts/watcher_issues_inbox.py` (et `watcher.extraire_complexite_pour_historique`
pour la COMPLEXITE, qui n'est PAS un champ d'en-tête de ce parseur — elle
reste embarquée dans le corps, voir son commentaire) plutôt que d'écrire un
second parseur du même format.

Stockage : fichier JSON gitignoré `configs/audit_<projet>.json` — un objet
UNIQUE (pas une liste comme `configs/templates_<projet>.json`), DISTINCT du
fichier de templates ordinaires : l'audit n'est jamais lu par
`GET /templates/<projet>` et n'apparaît donc jamais dans la liste déroulante
« Charger un template » du formulaire du projet audité lui-même.

Les champs PROJET et REPO_CIBLE du fichier importé sont IGNORÉS (jamais
enregistrés) — l'audit est toujours créé sur `diagnostique_programme`
(jamais sur le projet audité, voir `app/issues.py::envoyer`) et le Dépôt
cible est calculé depuis le `REP_TRAVAIL` du projet audité au moment de
« Préparer l'audit » (côté navigateur, `static/js/config.js`), pas depuis le
fichier importé. Un avertissement est renvoyé si ces champs sont présents
avec une valeur inattendue, pour qu'une incohérence ne passe jamais en
silence.
"""

import json
import sys
from pathlib import Path

from flask import jsonify, request

from app.projets import projet_par_nom

# Racine du projet (dossier parent du package app/) : configs/ et scripts/ y
# vivent — même principe que app/templates.py et app/issues_inbox.py.
DOSSIER_SCRIPT = Path(__file__).resolve().parent.parent
DOSSIER_TEMPLATES = DOSSIER_SCRIPT / "configs"
sys.path.insert(0, str(DOSSIER_SCRIPT))
sys.path.insert(0, str(DOSSIER_SCRIPT / "scripts"))

from watcher_issues_inbox import extraire_champs, retirer_ligne_entete, reconnaitre_mode  # noqa: E402
from watcher import extraire_complexite_pour_historique  # noqa: E402


def _chemin_audit(nom_projet: str) -> Path:
    return DOSSIER_TEMPLATES / f"audit_{nom_projet}.json"


def _charger_audit(nom_projet: str) -> dict | None:
    """Template d'audit du projet, ou None si aucun n'a encore été importé
    (ou si le fichier est illisible/corrompu — jamais une erreur serveur)."""
    chemin = _chemin_audit(nom_projet)
    try:
        if chemin.exists():
            return json.loads(chemin.read_text(encoding="utf-8")) or None
    except (json.JSONDecodeError, OSError):
        pass
    return None


def _sauvegarder_audit(nom_projet: str, audit: dict) -> None:
    chemin = _chemin_audit(nom_projet)
    chemin.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")


# ─── Routes Flask ──────────────────────────────────────────────────────────────

def audit_lire(nom_projet):
    """Retourne le template d'audit du projet (GET), ou `existe=false` si
    aucun n'a encore été importé."""
    if not projet_par_nom(nom_projet):
        return jsonify(erreur="Projet introuvable."), 404
    audit = _charger_audit(nom_projet)
    if not audit:
        return jsonify(existe=False)
    return jsonify(existe=True, **audit)


def audit_importer(nom_projet):
    """Importe/remplace le template d'audit du projet depuis un fichier `.txt`
    au format `issues_inbox/` (POST, multipart, champ `fichier`).

    Extrait titre/corps/timeout/mode via `extraire_champs()` (déjà utilisée
    pour les fichiers déposés dans issues_inbox/) puis la COMPLEXITE via
    `extraire_complexite_pour_historique()` (watcher.py — même reconnaissance
    EXACTE que la calibration TIMEOUT), avec repli 'normal' + avertissement si
    absente ou non reconnue. PROJET et REPO_CIBLE, s'ils sont présents et
    inattendus, déclenchent un avertissement mais ne sont JAMAIS enregistrés
    (voir docstring du module)."""
    cfg = projet_par_nom(nom_projet)
    if not cfg:
        return jsonify(succes=False, erreur="Projet introuvable."), 404

    fichier = request.files.get("fichier")
    if fichier is None or not fichier.filename:
        return jsonify(succes=False, erreur="Aucun fichier reçu."), 400
    contenu = fichier.read().decode("utf-8", errors="replace")

    champs = extraire_champs(contenu)
    if not champs["titre"]:
        return jsonify(succes=False, erreur=(
            "Titre introuvable (ligne « #Titre: » absente ou vide).")), 400

    avertissements = []

    # COMPLEXITE (issue #843/#848) : jamais un champ d'en-tête d'extraire_champs
    # (elle reste embarquée dans le corps, voir docstring du module) — repli
    # 'normal' + avertissement si absente ou non reconnue, puis ligne retirée
    # du corps conservé pour ne pas la dupliquer avec celle que le sélecteur de
    # complexité du formulaire web ajoutera à la création de l'issue d'audit.
    valeur_complexite, statut_complexite, brute_complexite = \
        extraire_complexite_pour_historique(champs["corps"])
    if statut_complexite == "absente":
        avertissements.append(
            "Aucune ligne COMPLEXITE dans le fichier — « normal » retenu par "
            "défaut (modifiable depuis le formulaire « Nouvelle issue »).")
    elif statut_complexite == "non_reconnue":
        avertissements.append(
            f"COMPLEXITE « {brute_complexite} » non reconnue (valeurs valides : "
            "rapide / court / normal / lourd) — « normal » retenu par défaut "
            "(modifiable depuis le formulaire « Nouvelle issue »).")
    corps = retirer_ligne_entete(champs["corps"], "COMPLEXITE").strip("\n")

    # PROJET (issue #848) : toujours ignoré — l'audit est créé sur
    # diagnostique_programme, jamais sur le projet audité.
    if champs["projet"] and champs["projet"] != "diagnostique_programme":
        avertissements.append(
            f"Champ PROJET « {champs['projet']} » ignoré — l'audit est toujours "
            "créé sur diagnostique_programme, jamais sur le projet audité.")

    # REPO_CIBLE (issue #848) : toujours ignoré — calculé automatiquement
    # depuis le REP_TRAVAIL (Linux) du projet audité au clic sur « Préparer
    # l'audit » (static/js/config.js), jamais depuis le fichier importé.
    if champs.get("repo_cible_brut"):
        attendu = str(cfg.rep_travail)
        fourni = champs["repo_cible_brut"]
        try:
            memes = Path(fourni).expanduser().resolve() == Path(attendu).expanduser().resolve()
        except OSError:
            memes = False
        if not memes:
            avertissements.append(
                f"Champ REPO_CIBLE « {fourni} » ignoré (ne correspond pas au "
                f"dossier de travail de « {nom_projet} », {attendu}) — calculé "
                "automatiquement par « Préparer l'audit ».")

    timeout = "300"
    if champs["timeout_brut"]:
        brut_timeout = champs["timeout_brut"].strip().lower().rstrip("s")
        if brut_timeout.isdigit():
            timeout = brut_timeout
        else:
            avertissements.append(
                f"TIMEOUT « {champs['timeout_brut']} » invalide (ignoré) — "
                "300s retenu par défaut.")

    # MODE : reconnaissance tolérante, jamais un motif de rejet (même principe
    # que pour un fichier issues_inbox, §5/§6 du DOC) — pas d'avertissement.
    mode = reconnaitre_mode(champs.get("mode_brut"))

    audit = {
        "titre":      champs["titre"],
        "corps":      corps,
        "timeout":    timeout,
        "mode":       mode,
        "complexite": valeur_complexite,
    }
    _sauvegarder_audit(nom_projet, audit)
    return jsonify(succes=True, audit=audit, avertissements=avertissements)


def audit_supprimer(nom_projet):
    """Supprime le template d'audit du projet (DELETE)."""
    if not projet_par_nom(nom_projet):
        return jsonify(succes=False, erreur="Projet introuvable."), 404
    chemin = _chemin_audit(nom_projet)
    if not chemin.exists():
        return jsonify(succes=False, erreur="Aucun template d'audit pour ce projet."), 404
    chemin.unlink()
    return jsonify(succes=True)
