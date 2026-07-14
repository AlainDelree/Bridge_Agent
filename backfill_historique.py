#!/usr/bin/env python3
"""Amorçage de l'historique des durées (issue #108).

Le watcher n'enregistre les durées réelles que pour les issues fermées APRÈS la
mise en place de ce système. Ce script reconstitue rétroactivement l'historique
à partir des issues déjà fermées : pour chaque issue `for-linux` fermée d'un
projet, la durée réelle est estimée par (fermeture − commentaire ACK du
watcher), puis catégorisée par projet/type/mode — exactement comme le fait
watcher.enregistrer_duree() en fonctionnement normal.

Usage :
    python3 backfill_historique.py            # écrit logs/historique_durees.json
    python3 backfill_historique.py --dry-run  # affiche seulement, n'écrit rien

Réutilise watcher.deduire_type_issue pour garantir une catégorisation IDENTIQUE
à celle du temps réel. Idempotent au sens « catégorie » : relancé, il régénère
le fichier depuis GitHub (il n'ajoute pas de doublons aux entrées existantes).
Le fichier vit dans logs/ (gitignoré) : télémétrie locale, non versionnée.
"""
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

DOSSIER = Path(__file__).resolve().parent
sys.path.insert(0, str(DOSSIER))
from watcher import deduire_type_issue, FICHIER_HISTORIQUE, LABEL_ECRITURE  # noqa: E402

# Marqueur du commentaire ACK posté par le watcher (début de traitement réel).
ACK_MARQUEUR = "ACK — Issue"


def _confs():
    """(nom, depot) de chaque projet, lus dans configs/*.conf."""
    projets = []
    for conf in sorted((DOSSIER / "configs").glob("*.conf")):
        txt = conf.read_text(encoding="utf-8", errors="replace")
        nom = depot = None
        for ligne in txt.splitlines():
            m = re.match(r"\s*NOM\s*=\s*(\S+)", ligne)
            if m:
                nom = m.group(1)
            m = re.match(r"\s*DEPOT\s*=\s*(\S+)", ligne)
            if m:
                depot = m.group(1)
        if nom and depot:
            projets.append((nom, depot))
    return projets


def _gh_json(args):
    """Appel gh renvoyant du JSON (liste/objet), ou None en cas d'échec."""
    try:
        out = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=60)
        if out.returncode != 0:
            return None
        return json.loads(out.stdout or "null")
    except (subprocess.SubprocessError, json.JSONDecodeError):
        return None


def _iso(dt_str):
    """Parse un horodatage GitHub (…Z) en datetime aware."""
    return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))


def backfill():
    entrees = []
    for nom, depot in _confs():
        issues = _gh_json([
            "issue", "list", "--repo", depot, "--state", "closed",
            "--label", "for-linux", "--limit", "200",
            "--json", "number,title,body,labels,closedAt",
        ]) or []
        vues = ignorees = 0
        for it in issues:
            if not it.get("closedAt"):
                continue
            detail = _gh_json([
                "issue", "view", str(it["number"]), "--repo", depot,
                "--json", "comments",
            ])
            if not detail:
                ignorees += 1
                continue
            ack = next((c for c in detail.get("comments", [])
                        if ACK_MARQUEUR in (c.get("body") or "")), None)
            if not ack:
                ignorees += 1   # issue fermée avant l'ère « ACK » : pas de début fiable
                continue
            duree = (_iso(it["closedAt"]) - _iso(ack["createdAt"])).total_seconds()
            if duree <= 0:
                ignorees += 1
                continue
            labels = [(l.get("name") or "").lower() for l in it.get("labels", [])]
            entrees.append({
                "projet": nom,
                "type":   deduire_type_issue(it.get("title") or "", it.get("body") or ""),
                "mode":   "write" if LABEL_ECRITURE in labels else "read",
                "duree":  round(duree),
                "date":   _iso(it["closedAt"]).isoformat(timespec="seconds"),
            })
            vues += 1
        print(f"  {nom:12} : {vues} durée(s) reconstituée(s), {ignorees} ignorée(s)")
    return entrees


def main():
    dry = "--dry-run" in sys.argv
    entrees = backfill()
    entrees.sort(key=lambda e: e["date"])
    print(f"\nTotal : {len(entrees)} entrée(s).")
    if dry:
        print("(--dry-run : rien écrit)")
        return
    FICHIER_HISTORIQUE.parent.mkdir(parents=True, exist_ok=True)
    FICHIER_HISTORIQUE.write_text(
        json.dumps(entrees, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Écrit : {FICHIER_HISTORIQUE}")


if __name__ == "__main__":
    main()
