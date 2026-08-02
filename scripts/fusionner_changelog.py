#!/usr/bin/env python3
"""scripts/fusionner_changelog.py — fusionne les CHANGELOG-<N>.md dans CHANGELOG.md.

Contexte : issue #336 — futur système de worktrees. Quand CCL travaille dans
un répertoire isolé, il écrit son entrée dans un fichier `CHANGELOG-<N>.md`
(N = numéro de l'issue) plutôt que dans `CHANGELOG.md` directement, pour
éviter les conflits systématiques sur ce fichier unique quand plusieurs
issues mode_write tournent en parallèle dans des worktrees distincts. Ce
script fusionne ces fichiers dans `CHANGELOG.md` avant le push d'Alain.

Fonctionnement : chaque `CHANGELOG-<N>.md` trouvé à la racine du dépôt est
inséré tel quel (contenu repris sans modification) en tête de `CHANGELOG.md`,
juste après l'en-tête fixe du fichier (jusqu'à la ligne vide qui suit
« Convention d'ajout : ... »), triés par N décroissant — cohérent avec la
convention « plus récente en tête » de `CHANGELOG.md` (issue #252). Les
fichiers `CHANGELOG-<N>.md` traités sont ensuite supprimés. Aucun fichier
trouvé : message et sortie propre (code 0), `CHANGELOG.md` inchangé —
propriété qui rend une seconde exécution sans nouveaux fichiers idempotente,
puisque les fichiers sources du premier passage ont déjà été supprimés.

Ce script n'est pas encore appelé automatiquement par watcher.py (le système
de worktrees qui produit des CHANGELOG-<N>.md n'existe pas encore) —
lancement manuel uniquement pour l'instant.

Usage :
    python3 scripts/fusionner_changelog.py                # dépôt courant (.)
    python3 scripts/fusionner_changelog.py --repo /chemin/vers/le/depot
"""
import argparse
import re
import sys
from pathlib import Path

MOTIF_FICHIER = re.compile(r"^CHANGELOG-(\d+)\.md$")


def _trouver_fichiers(repo: Path) -> list:
    """Retourne les (N, chemin) des CHANGELOG-<N>.md trouvés à la racine du
    dépôt, triés par N décroissant (plus récent en tête)."""
    fichiers = []
    for chemin in repo.iterdir():
        if not chemin.is_file():
            continue
        m = MOTIF_FICHIER.match(chemin.name)
        if m:
            fichiers.append((int(m.group(1)), chemin))
    fichiers.sort(key=lambda t: t[0], reverse=True)
    return fichiers


def _point_insertion(lignes: list) -> int:
    """Index (dans `lignes`) de la ligne juste après la ligne vide qui suit
    « Convention d'ajout : ... » — point d'insertion en tête du contenu,
    juste après l'en-tête fixe de CHANGELOG.md. None si l'en-tête attendu
    est introuvable (fichier non conforme à la convention #252)."""
    for i, ligne in enumerate(lignes):
        if ligne.startswith("Convention d'ajout"):
            for j in range(i + 1, len(lignes)):
                if lignes[j].strip() == "":
                    return j + 1
            return len(lignes)
    return None


def fusionner(repo: Path) -> dict:
    """Exécute la fusion. Retourne un rapport structuré (utilisé aussi bien
    pour l'affichage console que pour des tests)."""
    fichiers = _trouver_fichiers(repo)
    if not fichiers:
        return {"erreur": None, "traites": [], "message": "Aucun CHANGELOG-<N>.md trouvé — rien à fusionner."}

    fichier_changelog = repo / "CHANGELOG.md"
    if not fichier_changelog.exists():
        return {"erreur": f"CHANGELOG.md introuvable : {fichier_changelog}"}

    contenu = fichier_changelog.read_text(encoding="utf-8")
    lignes = contenu.splitlines(keepends=True)
    idx = _point_insertion(lignes)
    if idx is None:
        return {"erreur": "en-tête fixe introuvable dans CHANGELOG.md "
                           "(ligne « Convention d'ajout : ... » absente)"}

    blocs = []
    for n, chemin in fichiers:
        texte = chemin.read_text(encoding="utf-8").strip("\n")
        blocs.append(texte + "\n\n")

    nouveau_contenu = "".join(lignes[:idx]) + "".join(blocs) + "".join(lignes[idx:])
    fichier_changelog.write_text(nouveau_contenu, encoding="utf-8")

    for n, chemin in fichiers:
        chemin.unlink()

    return {"erreur": None, "traites": [(n, chemin.name) for n, chemin in fichiers]}


def _afficher_rapport(rapport: dict) -> int:
    if rapport.get("erreur"):
        print(f"ERREUR : {rapport['erreur']}", file=sys.stderr)
        return 1

    if not rapport["traites"]:
        print(rapport["message"])
        return 0

    numeros = ", ".join(f"#{n}" for n, _ in rapport["traites"])
    print(f"{len(rapport['traites'])} fichier(s) fusionné(s) dans CHANGELOG.md (issues {numeros}) :")
    for n, nom in rapport["traites"]:
        print(f"  - {nom} -> supprimé après fusion")
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Fusionne les CHANGELOG-<N>.md (worktrees) dans CHANGELOG.md, "
                     "les plus récents (N décroissant) en tête, puis les supprime."
    )
    parser.add_argument("--repo", type=Path, default=Path("."),
                         help="racine du dépôt à scanner (défaut : .)")
    args = parser.parse_args()

    rapport = fusionner(args.repo.resolve())
    sys.exit(_afficher_rapport(rapport))


if __name__ == "__main__":
    main()
