"""Journal watcher en temps réel (Server-Sent Events) du bridge.

Extraite de new_issue.py à l'étape 8 du refactoring modulaire. Regroupe la
route SSE qui streame le fichier de log d'un watcher vers l'onglet « Journal »
de l'interface : envoi des dernières lignes existantes puis suivi au fil de
l'eau (avec détection de rotation du fichier).
"""

import time
from pathlib import Path

from flask import Response

from app.projets import projet_par_nom
from app.auth import login_requis  # noqa: F401 (exporté pour l'enregistrement des routes)


def journal(nom_projet):
    """Server-Sent Events : streame le journal du watcher en temps réel."""
    cfg = projet_par_nom(nom_projet)
    if not cfg:
        return Response("Projet introuvable.", status=404)
    fichier_log = cfg.fichier_log

    def generer():
        # ── 1. Les 80 dernières lignes existantes ──────────────────────────
        if fichier_log.exists():
            with open(fichier_log, "r", encoding="utf-8", errors="replace") as f:
                lignes = f.readlines()
            for l in lignes[-80:]:
                yield f"data: {l.rstrip()}\n\n"
        else:
            yield "data: (journal vide — le watcher n'a pas encore démarré)\n\n"

        # ── 2. Nouvelles lignes au fil de l'eau ────────────────────────────
        while True:
            try:
                taille = fichier_log.stat().st_size if fichier_log.exists() else 0
                with open(fichier_log, "r", encoding="utf-8", errors="replace") as f:
                    f.seek(taille)
                    while True:
                        ligne = f.readline()
                        if ligne:
                            taille += len(ligne.encode("utf-8"))
                            yield f"data: {ligne.rstrip()}\n\n"
                        else:
                            time.sleep(0.5)
                            yield ": ping\n\n"  # keepalive (ignoré par onmessage)
                            # Vérifier si le fichier a été rotaté (taille diminuée)
                            nouvelle_taille = fichier_log.stat().st_size if fichier_log.exists() else 0
                            if nouvelle_taille < taille:
                                break  # rotation détectée → réouvrir
            except FileNotFoundError:
                time.sleep(2)
                yield ": ping\n\n"

    return Response(
        generer(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
