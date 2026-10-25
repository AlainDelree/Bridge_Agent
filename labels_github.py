#!/usr/bin/env python3
"""labels_github.py — Labels GitHub requis par le bridge sur chaque dépôt
cible, et logique de création idempotente des manquants (issue #816).

Extrait de `nouveau_projet.py` (LABELS, creer_labels), où cette logique
n'était appliquée qu'à la création d'un projet : chaque label ajouté au
code depuis restait absent de tous les dépôts déjà existants jusqu'à un
`gh label create` manuel — quatre incidents, du rejet d'une création
d'issue (`sans-redacteur`, #647/#648) à une issue de lecture active
exécutée en lecture seule sans la moindre erreur (`mode_scratch`, #785).

Module dédié plutôt qu'un import direct de `nouveau_projet` depuis
`watcher.py` : `nouveau_projet` importe `regenerer_tableaux_projets`, qui
importe lui-même `from watcher import lire_conf` — un import de
`nouveau_projet` par `watcher.py` fermerait ce cycle. Zéro dépendance
externe (stdlib uniquement), aucun effet de bord au chargement : importable
tel quel par `watcher.py` (démarrage de chaque watcher, Linux ET Windows
CCW — un seul et même `watcher.py` tourne sur les deux plateformes),
`nouveau_projet.py` (création de projet, comportement inchangé) et l'outil
de rattrapage `rattraper_labels.py`.

Pour ajouter un nouveau label : l'ajouter à LABELS ci-dessous. Chaque
watcher le crée de lui-même sur son dépôt au prochain démarrage, et
`rattraper_labels.py` le crée tout de suite sur tous les dépôts déclarés —
plus besoin de `gh label create` manuel ni d'attendre un incident pour s'en
apercevoir.
"""

import subprocess

# Treize labels requis par le watcher (§4 de BRIDGE_AGENT_DOC.md). couleur =
# hex sans '#'. Recréés à l'identique sur chaque dépôt cible — watcher.py au
# démarrage (manquants seulement, voir verifier_labels_demarrage ci-dessous)
# et nouveau_projet.py à la création d'un projet ; sans eux, le watcher ne
# voit pas les issues (for-linux) et le mode écriture reste inerte.
LABELS = [
    ("for-linux",      "0e8a16", "Requis — le watcher ne voit que ces issues"),
    ("for-windows",    "0e8a16", "Watcher Windows (CCW) — même principe que for-linux"),
    ("bridge",         "1d76db", "Marque l'issue comme tâche bridge (traçabilité)"),
    ("mode_write",     "d93f0b", "ARME le mode écriture — CCL peut modifier des fichiers"),
    ("mode_scratch",   "1a4d8f", "ARME la lecture active — écriture confinée au dossier scratch"),
    ("needs-human",    "b60205", "Posé après 3 échecs — stoppe le retraitement auto"),
    ("done",           "0e8a16", "Posé automatiquement au succès"),
    ("notif_pc",       "fbca04", "Ajoute une notification bureau (notify-send)"),
    ("notif_gsm",      "fbca04", "Ajoute une notification push (ntfy)"),
    ("notif_tous",     "fbca04", "notify-send + ntfy"),
    ("sans-redacteur", "c2b280", "Posé automatiquement — l'issue ne précisait pas REDACTEUR"),
    ("agent-claude",   "c5def5", "Posé automatiquement — agent d'exécution Claude Code"),
    ("agent-vibe",     "c5def5", "Posé automatiquement — agent d'exécution Mistral Vibe"),
]

# Délai de garde par appel `gh` : borne tout appelant AUTOMATIQUE (vérification
# au démarrage du watcher, outil de rattrapage) contre un blocage indéfini en
# cas de réseau indisponible. Identique au délai déjà utilisé par watcher.gh()
# ailleurs dans le dépôt ; sans incidence sur l'usage interactif (jamais
# atteint en pratique).
TIMEOUT_GH_S = 30


def _gh(*args: str) -> subprocess.CompletedProcess:
    """Lance `gh` avec les arguments donnés et renvoie toujours un
    CompletedProcess exploitable (returncode != 0 et stderr renseigné en cas
    d'erreur d'exécution elle-même — binaire `gh` absent, délai dépassé —
    plutôt que de laisser l'exception remonter : les deux appelants
    automatiques de ce module ne doivent jamais planter pour cette raison)."""
    try:
        return subprocess.run(
            ["gh", *args],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=TIMEOUT_GH_S,
        )
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(args, 1, stdout="",
                                            stderr=f"délai dépassé (> {TIMEOUT_GH_S}s)")
    except OSError as e:
        return subprocess.CompletedProcess(args, 1, stdout="", stderr=str(e))


def creer_labels(depot: str) -> list[tuple[str, str, str]]:
    """Crée les labels manquants sur le dépôt cible (idempotent : les présents
    sont laissés intacts, jamais modifiés ni recolorés). Renvoie une liste
    ordonnée de (label, statut, detail) où statut ∈ {"deja", "cree", "echec"}.
    Ne lève jamais : une liste illisible (réseau, droits, dépôt inaccessible)
    laisse `existants` vide, ce qui fait simplement tenter la création de
    chaque label (chacune échoue proprement avec un statut "echec" si le
    label existe déjà mais n'a pas pu être listé)."""
    res = _gh("label", "list", "--repo", depot, "--limit", "200")
    existants = set()
    if res.returncode == 0:
        for ligne in res.stdout.splitlines():
            if ligne.strip():
                existants.add(ligne.split("\t")[0].strip().lower())

    resultats = []
    for nom_label, couleur, description in LABELS:
        if nom_label.lower() in existants:
            resultats.append((nom_label, "deja", ""))
            continue
        r = _gh("label", "create", nom_label, "--repo", depot,
                "--color", couleur, "--description", description)
        if r.returncode == 0:
            resultats.append((nom_label, "cree", ""))
        else:
            resultats.append((nom_label, "echec", r.stderr.strip()))
    return resultats
