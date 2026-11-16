"""Bouton « Avancement » d'une issue en cours (issue #887) : commits et
fichiers (committés/non committés) du worktree dédié à CETTE issue — pour
qu'Alain puisse estimer l'avancement d'une tâche sans ouvrir de terminal.

Strictement en lecture (contrainte centrale de l'issue) : aucune commande
git qui modifie quoi que ce soit (pas de `add`/`commit`/`reset`/`clean`),
aucun verrou pris, aucun effet sur le traitement en cours — seules des
commandes `git log`/`git diff`/`git status`/`git rev-parse` en lecture, et
une lecture de fichier (comptage de lignes des fichiers non suivis).

Le worktree est retrouvé par le MÊME mécanisme d'identification que la
RELANCE d'une issue mode_write (`watcher._trouver_worktree_reutilisable`,
issue #725) — nom `<projet>-issue<numero>[-bis|-ter]` + branche attendue,
via `git worktree list` — mais via `watcher._trouver_worktree_pour_issue`,
qui en reprend l'identification SANS le filtre « pas en cours de
traitement » : ici on veut justement le worktree d'une issue EN COURS
(donc verrouillée), pas un worktree disponible pour une relance.

Labels transmis par le front en paramètre de requête (`labels`, déjà en
cache côté JS — même esprit que POST /interrompre) plutôt que relus via
`gh` ici : évite un appel réseau GitHub supplémentaire pour une simple
lecture locale, et permet de distinguer les cas dégradés SANS worktree
(lecture seule, lecture active, issue for-windows — machine CCW non prise
en charge dans cette étape, sans SSH) d'un worktree mode_write réellement
introuvable/déjà nettoyé."""

import subprocess
import sys
from pathlib import Path

from flask import jsonify, request

from app.projets import projet_par_nom
from app.issues import _parser_numstat_z, _parser_name_status_z, _statut_libelle

# app.projets a déjà inséré la racine du projet dans sys.path (pour
# « from watcher import »), mais on s'assure ici aussi de l'ordre d'import.
DOSSIER_SCRIPT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(DOSSIER_SCRIPT))
from watcher import _trouver_worktree_pour_issue, _horodatage_dernier_commit  # noqa: E402

TIMEOUT_GIT = 15


def _executer_git(chemin: Path, *args) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(chemin), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=TIMEOUT_GIT,
    )


def _commits_depuis(chemin: Path, base_sha: str) -> list:
    """Commits du worktree `chemin` non présents dans `base_sha` (séparateur
    `\\x1f`, jamais une tabulation/espace qui pourrait apparaître dans un
    message de commit) — identifiant court, message, horodatage epoch.
    Liste vide si la commande échoue ou si aucun commit (jamais d'exception
    propagée, best-effort en lecture)."""
    res = _executer_git(chemin, "log", f"{base_sha}..HEAD", "--format=%h\x1f%s\x1f%ct")
    if res.returncode != 0 or not res.stdout.strip():
        return []
    commits = []
    for ligne in res.stdout.rstrip("\n").split("\n"):
        parties = ligne.split("\x1f")
        if len(parties) != 3:
            continue
        hash_court, message, horodatage_brut = parties
        try:
            horodatage = int(horodatage_brut)
        except ValueError:
            horodatage = None
        commits.append({"hash": hash_court, "message": message, "horodatage": horodatage})
    return commits


def _fichiers_numstat(chemin: Path, *args_diff) -> list:
    """Fichiers touchés par `git diff <args_diff>` (statut + lignes +/-),
    même format que `app.issues.inventaire_commit` (`-z`, `--find-renames`)
    pour réutiliser ses deux parseurs déjà testés. Liste vide si la commande
    échoue (jamais d'exception propagée)."""
    res_statut = _executer_git(chemin, "diff", "--no-color", "--name-status",
                                "--find-renames", "-z", *args_diff)
    res_num = _executer_git(chemin, "diff", "--no-color", "--numstat",
                             "--find-renames", "-z", *args_diff)
    if res_statut.returncode != 0 or res_num.returncode != 0:
        return []
    compteurs = _parser_numstat_z(res_num.stdout)
    return [
        {
            "chemin": enr["chemin"],
            "ancien_chemin": enr["ancien_chemin"],
            "statut": _statut_libelle(enr["statut"]),
            "ajoutees": compteurs.get(enr["chemin"], (None, None))[0],
            "supprimees": compteurs.get(enr["chemin"], (None, None))[1],
        }
        for enr in _parser_name_status_z(res_statut.stdout)
    ]


def _fichiers_non_suivis(chemin: Path) -> list:
    """Fichiers NON SUIVIS du worktree (`??` de `git status --porcelain`,
    absents de `git diff`) — comptés en lignes ajoutées par simple lecture
    du fichier (jamais via une commande git qui modifierait l'index, ex.
    `add --intent-to-add`). `ajoutees` reste None si le fichier est illisible
    (binaire, permissions) plutôt que d'affirmer à tort « 0 ligne »."""
    res = _executer_git(chemin, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    if res.returncode != 0 or not res.stdout:
        return []
    fichiers = []
    for enr in res.stdout.split("\0"):
        if not enr or not enr.startswith("??"):
            continue
        rel = enr[3:]
        ajoutees = None
        try:
            contenu = (chemin / rel).read_text(encoding="utf-8", errors="replace")
            if contenu:
                ajoutees = contenu.count("\n") + (0 if contenu.endswith("\n") else 1)
            else:
                ajoutees = 0
        except OSError:
            pass
        fichiers.append({"chemin": rel, "ancien_chemin": None, "statut": "non suivi",
                          "ajoutees": ajoutees, "supprimees": 0})
    return fichiers


def _horodatage_mtime_max(chemin: Path, chemins_relatifs: list) -> float:
    """Plus récent mtime (epoch) parmi `chemins_relatifs`, relatifs à
    `chemin` — 0.0 si aucun fichier lisible (jamais d'exception)."""
    maximum = 0.0
    for rel in chemins_relatifs:
        try:
            maximum = max(maximum, (chemin / rel).stat().st_mtime)
        except OSError:
            continue
    return maximum


def _mode_depuis_labels(labels: list) -> str:
    """Même classification que `modeEcritureDepuisLabels` (static/js/app.js)
    — 'ccw' en plus, prioritaire : une issue for-windows n'a pas de worktree
    accessible localement, quel que soit son mode (machine CCW, hors
    périmètre de cette étape, sans SSH, issue #887)."""
    noms = [str(l or "").strip().lower() for l in (labels or [])]
    if "for-windows" in noms:
        return "ccw"
    if "mode_write" in noms:
        return "ecriture"
    if "mode_scratch" in noms:
        return "lecture_active"
    return "lecture_seule"


MESSAGES_SANS_WORKTREE = {
    "ccw": ("ccw", "Cette issue tourne sur la machine CCW (Windows) — non pris en charge "
                    "par ce bouton dans cette étape (pas de SSH depuis cette vue)."),
    "lecture_active": ("lecture_active", "Issue en lecture active (mode_scratch) : aucun "
                        "worktree de projet dédié — pas d'avancement de ce type à montrer."),
    "lecture_seule": ("lecture_seule", "Issue en lecture seule : aucun worktree dédié — "
                       "pas d'avancement de ce type à montrer."),
}


def avancement_issue(nom_projet, numero):
    """GET /avancement/<nom_projet>/<numero>?labels=a,b,c — lecture seule,
    voir docstring de module. `labels` (facultatif, comme transmis par le
    front depuis son cache) pilote les cas dégradés de l'issue #887 ; en son
    absence, retombe sur une tentative de recherche du worktree mode_write
    (comportement précédent, utile aux tests/appels directs)."""
    cfg = projet_par_nom(nom_projet)
    if not cfg:
        return jsonify(erreur="Projet introuvable."), 404
    try:
        numero_int = int(numero)
    except (TypeError, ValueError):
        return jsonify(erreur="Numéro d'issue invalide."), 400

    labels_brut = request.args.get("labels", "")
    labels = [l for l in labels_brut.split(",") if l]
    mode = _mode_depuis_labels(labels) if labels_brut else "ecriture"

    if mode in MESSAGES_SANS_WORKTREE:
        raison, message = MESSAGES_SANS_WORKTREE[mode]
        return jsonify(disponible=False, raison=raison, message=message)

    if not cfg.rep_travail.is_dir():
        return jsonify(erreur="Répertoire de travail introuvable."), 404

    trouve = _trouver_worktree_pour_issue(cfg, numero_int)
    if trouve is None:
        return jsonify(
            disponible=False, raison="worktree_introuvable",
            message="Aucun worktree trouvé pour cette issue — déjà nettoyé après fusion, "
                    "ou le traitement s'est fait directement dans le dépôt principal "
                    "(repli faute de worktree disponible, voir WORKTREES.md).",
        )
    chemin, branche = trouve

    try:
        base = _executer_git(cfg.rep_travail, "rev-parse", "HEAD")
        base_branche = _executer_git(cfg.rep_travail, "rev-parse", "--abbrev-ref", "HEAD")
    except subprocess.TimeoutExpired:
        return jsonify(erreur="Timeout (git n'a pas répondu en 15s)."), 504
    except FileNotFoundError:
        return jsonify(erreur="git introuvable dans le PATH."), 500
    if base.returncode != 0:
        return jsonify(erreur="Impossible de lire HEAD du dépôt principal."), 500
    base_sha = base.stdout.strip()
    nom_branche_base = base_branche.stdout.strip() if base_branche.returncode == 0 else base_sha[:7]

    try:
        commits = _commits_depuis(chemin, base_sha)
        fichiers_committes = _fichiers_numstat(chemin, base_sha, "HEAD")
        fichiers_non_committes = _fichiers_numstat(chemin, "HEAD")
        non_suivis = _fichiers_non_suivis(chemin)
    except subprocess.TimeoutExpired:
        return jsonify(erreur="Timeout (git n'a pas répondu en 15s)."), 504
    except FileNotFoundError:
        return jsonify(erreur="git introuvable dans le PATH."), 500

    fichiers_non_committes = fichiers_non_committes + non_suivis

    derniere_activite = _horodatage_dernier_commit(chemin)
    chemins_modifies = [f["chemin"] for f in fichiers_non_committes]
    derniere_activite = max(derniere_activite, _horodatage_mtime_max(chemin, chemins_modifies))

    return jsonify(
        disponible=True,
        chemin=str(chemin),
        branche=branche,
        branche_base=nom_branche_base,
        commits=commits,
        fichiers_committes=fichiers_committes,
        fichiers_non_committes=fichiers_non_committes,
        derniere_activite=(derniere_activite or None),
    )
