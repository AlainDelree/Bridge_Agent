#!/usr/bin/env bash
#
# lancer_new_issue.sh — Lanceur supervisé de new_issue.py (issue #150).
#
# But : conserver une trace persistante de chaque session de l'interface web
# de création d'issues. new_issue.py a plusieurs fois « planté silencieusement »
# sans laisser aucune trace (ni terminal fermé, ni log). Ce wrapper :
#   - horodate le DÉMARRAGE, l'ARRÊT et le CODE DE SORTIE de new_issue.py ;
#   - capture stdout + stderr dans logs/new_issue.log (tout en les affichant
#     toujours dans le terminal, via `tee`) ;
#   - fait une rotation par TAILLE, cohérente avec les watchers
#     (logs/new_issue.log, .1, .2 … — voir watcher.py::JournalRotatifDate).
#
# ⚠️  Ne remplace PAS la manière habituelle de lancer l'interface :
#     `python3 new_issue.py` reste valable et inchangé. Ce script est un
#     lanceur EN PLUS, à utiliser quand on veut une trace (recommandé).
#
# Usage — identique à new_issue.py, tous les arguments sont transmis :
#     ./lancer_new_issue.sh                 # mode local
#     ./lancer_new_issue.sh --externe       # mode externe (tunnel)
#     ./lancer_new_issue.sh --port 5100 --no-browser
#
# Après un éventuel prochain plantage, la cause probable sera dans :
#     logs/new_issue.log   (dernières lignes = stderr/traceback + code de sortie)

set -u

DOSSIER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG="$DOSSIER/logs/new_issue.log"
TAILLE_MAX=$((5 * 1024 * 1024))   # 5 Mo, comme le défaut des watchers
ARCHIVES=5                        # nombre d'archives conservées (.1 … .5)

mkdir -p "$DOSSIER/logs"

# ── Rotation par taille (avant démarrage) ────────────────────────────────────
# Si le log actif dépasse TAILLE_MAX, on décale .N-1 -> .N puis log -> .1.
rotation() {
    [ -f "$LOG" ] || return 0
    local taille
    taille=$(stat -c%s "$LOG" 2>/dev/null || echo 0)
    [ "$taille" -lt "$TAILLE_MAX" ] && return 0
    local i
    for (( i=ARCHIVES-1; i>=1; i-- )); do
        [ -f "$LOG.$i" ] && mv -f "$LOG.$i" "$LOG.$((i+1))"
    done
    mv -f "$LOG" "$LOG.1"
}
rotation

horodate() { date '+%Y-%m-%d %H:%M:%S'; }

DEBUT="$(horodate)"
{
    echo "============================================================"
    echo "$DEBUT [START] new_issue.py — args: $* — pid wrapper: $$"
} >> "$LOG"

# ── Lancement : stdout+stderr -> terminal ET log (append) ─────────────────────
# tee casse le code de sortie de python : on le récupère via PIPESTATUS.
python3 "$DOSSIER/new_issue.py" "$@" 2>&1 | tee -a "$LOG"
CODE=${PIPESTATUS[0]}

FIN="$(horodate)"
{
    echo "$FIN [STOP]  new_issue.py — code de sortie: $CODE"
    echo "============================================================"
} >> "$LOG"

exit "$CODE"
