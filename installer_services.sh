#!/usr/bin/env bash
#
# installer_services.sh — Installe les watchers du bridge en services
# systemd --user (issue #119).
#
# But : chaque watcher de projet actif tourne comme service utilisateur, avec
#   - démarrage automatique à l'ouverture de session (WantedBy=default.target)
#   - démarrage dès le boot, sans session ouverte, grâce au linger utilisateur
#   - redémarrage automatique en cas de crash (Restart=always, RestartSec=10)
#
# Plus besoin de cliquer « Lancer watcher » dans l'interface après un
# redémarrage du PC ou un crash : systemd s'en charge.
#
# ─────────────────────────────────────────────────────────────────────────────
# ⚠️  CONFLIT POSSIBLE AVEC LE BOUTON « Lancer / Arrêter watcher » DE L'INTERFACE
# ─────────────────────────────────────────────────────────────────────────────
# Deux mécanismes indépendants savent lancer le même watcher.py :
#
#   1. Ce service systemd (source de vérité recommandée une fois installé).
#   2. app/watchers.py (demarrer_watcher / arreter_watcher / watcher_actif),
#      derrière le bouton « Lancer / Arrêter watcher » de l'interface web.
#
# Ils NE se voient PAS l'un l'autre :
#   - systemd suit son process via son propre cgroup ;
#   - l'interface suit *son* process via un fichier PID (logs/watcher-<nom>.pid),
#     que le service systemd n'écrit jamais.
#
# Conséquences concrètes si les deux coexistent :
#   - Après cette installation, le watcher tourne (via systemd) mais l'onglet
#     « Watchers » de l'interface l'affichera « inactif » (pas de fichier PID).
#   - Un clic sur « Lancer watcher » démarrerait alors un SECOND process
#     watcher.py pour le même projet -> deux watchers en double, doubles
#     commentaires possibles sur les issues.
#   - Un clic sur « Arrêter watcher » ne tuerait PAS l'instance systemd
#     (il ne connaît pas son PID), et de toute façon Restart=always la
#     relancerait aussitôt.
#
# RECOMMANDATION (à trancher par Alain) :
#   → Privilégier systemd comme source de vérité. Une fois ces services en
#     place, NE PLUS utiliser le bouton « Lancer watcher » pour un démarrage
#     normal : il ne doit servir qu'exceptionnellement (filet de secours), et
#     idéalement le bouton devrait être neutralisé côté interface pour éviter
#     les doublons. Voir §13 de BRIDGE_AGENT_DOC.md.
#   → Cette question (désactiver / réétiqueter le bouton) dépasse le périmètre
#     de ce script : elle touche app/watchers.py et les templates, et fera
#     l'objet d'une décision/issue séparée.
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

# ── Paramètres ───────────────────────────────────────────────────────────────
RACINE="/home/alain/Bridge_Agent"
GABARIT="$RACINE/systemd/watcher@.service"
DEST_DIR="$HOME/.config/systemd/user"
LINGER_USER="${USER:-alain}"

# Projets actifs à superviser (§2 de BRIDGE_AGENT_DOC.md — hors scrabble, pas
# demandé par l'issue #119 ; ajouter « scrabble » ici si souhaité plus tard).
PROJETS=(bridge_agent alchess ff_galerie ecole)

echo "== Installation des services systemd --user des watchers =="

# ── 1. Vérifications préalables ──────────────────────────────────────────────
if [[ ! -f "$GABARIT" ]]; then
    echo "ERREUR : gabarit introuvable : $GABARIT" >&2
    exit 1
fi

for p in "${PROJETS[@]}"; do
    if [[ ! -f "$RACINE/configs/$p.conf" ]]; then
        echo "ERREUR : config manquante : configs/$p.conf (projet $p)" >&2
        exit 1
    fi
done

if [[ ! -x "$RACINE/venv/bin/python3" ]]; then
    echo "ERREUR : interpréteur introuvable : $RACINE/venv/bin/python3" >&2
    echo "        (adapter ExecStart dans le gabarit si le venv a changé)" >&2
    exit 1
fi

# ── 2. Copie du gabarit ──────────────────────────────────────────────────────
mkdir -p "$DEST_DIR"
cp -v "$GABARIT" "$DEST_DIR/watcher@.service"

# ── 3. Rechargement de systemd --user ────────────────────────────────────────
systemctl --user daemon-reload

# ── 4. Linger : services actifs même sans session ouverte ────────────────────
# Nécessite un mot de passe sudo. Sans linger, les services --user s'arrêtent
# à la fermeture de session et ne démarrent pas au boot tant qu'Alain ne s'est
# pas reconnecté.
echo "-- Activation du linger pour $LINGER_USER (peut demander sudo) --"
if loginctl show-user "$LINGER_USER" 2>/dev/null | grep -q "Linger=yes"; then
    echo "   linger déjà actif."
else
    sudo loginctl enable-linger "$LINGER_USER"
    echo "   linger activé."
fi

# ── 5. Activation + démarrage des instances ──────────────────────────────────
UNITES=()
for p in "${PROJETS[@]}"; do
    UNITES+=("watcher@$p")
done

echo "-- enable --now : ${UNITES[*]} --"
systemctl --user enable --now "${UNITES[@]}"

# ── 6. Bilan ─────────────────────────────────────────────────────────────────
echo
echo "== État des services =="
systemctl --user --no-pager --no-legend list-units 'watcher@*' || true
echo
echo "Terminé. Diagnostic :"
echo "  systemctl --user status watcher@alchess"
echo "  journalctl --user -u watcher@alchess -f"
echo
echo "RAPPEL : ne plus utiliser le bouton « Lancer watcher » de l'interface"
echo "pour un démarrage normal (risque de doublon). Voir l'en-tête de ce"
echo "script et §13 de BRIDGE_AGENT_DOC.md."
