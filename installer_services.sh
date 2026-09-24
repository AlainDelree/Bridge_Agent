#!/usr/bin/env bash
#
# installer_services.sh — Installe les watchers du bridge en services
# systemd --user (issue #119, réactivé et corrigé par l'issue #596).
#
# But : chaque watcher de projet actif tourne comme service utilisateur, avec
#   - démarrage automatique à l'ouverture de session (WantedBy=default.target)
#   - démarrage dès le boot, sans session ouverte, grâce au linger utilisateur
#   - redémarrage automatique en cas de crash (Restart=on-failure, RestartSec=10)
#     SANS relancer un watcher qui s'est éteint proprement pour inactivité
#     (SuccessExitStatus=42 — voir systemd/watcher@.service et watcher.py,
#     constante EXIT_INACTIVITE)
#
# Plus besoin de cliquer « Lancer watcher » dans l'interface après un
# redémarrage du PC ou un crash : systemd s'en charge.
#
# ─────────────────────────────────────────────────────────────────────────────
# UNIFIÉ AVEC LE BOUTON « Lancer / Arrêter watcher » DE L'INTERFACE (issue #596)
# ─────────────────────────────────────────────────────────────────────────────
# Avant #596, ce service systemd et app/watchers.py (demarrer_watcher /
# arreter_watcher, derrière le bouton « Lancer / Arrêter watcher » de
# l'interface web) étaient deux mécanismes indépendants qui NE SE VOYAIENT PAS
# — risque de double process. Depuis #596, demarrer_watcher()/arreter_watcher()
# appellent eux-mêmes `systemctl --user start|restart|stop watcher@<projet>` :
# les boutons de l'interface ET ce service systemd sont désormais la même
# source de vérité, plus de doublon possible. `watcher_actif()` continue de
# lire logs/watcher-<nom>.pid, désormais publié par watcher.py lui-même à son
# démarrage (quel que soit son mode de lancement).
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

# ── Paramètres ───────────────────────────────────────────────────────────────
RACINE="/home/alain/Bridge_Agent"
GABARIT="$RACINE/systemd/watcher@.service"
DEST_DIR="$HOME/.config/systemd/user"
LINGER_USER="${USER:-alain}"

echo "== Installation des services systemd --user des watchers =="

# ── 1. Vérifications préalables ──────────────────────────────────────────────
if [[ ! -f "$GABARIT" ]]; then
    echo "ERREUR : gabarit introuvable : $GABARIT" >&2
    exit 1
fi

if [[ ! -x "$RACINE/venv/bin/python3" ]]; then
    echo "ERREUR : interpréteur introuvable : $RACINE/venv/bin/python3" >&2
    echo "        (adapter ExecStart dans le gabarit si le venv a changé)" >&2
    exit 1
fi

# Projets actifs à superviser (issue #596) : un service par configs/*.conf
# VALIDE, déterminé via app.projets.lister_projets() — la même définition
# d'« projet actif » que le reste de l'interface (mêmes champs requis, mêmes
# configs silencieusement ignorées si incomplètes). Remplace la liste codée
# en dur de l'issue #119.
mapfile -t PROJETS < <(cd "$RACINE" && venv/bin/python3 -c '
from app.projets import lister_projets
for cfg in lister_projets():
    print(cfg.nom)
')

if [[ ${#PROJETS[@]} -eq 0 ]]; then
    echo "ERREUR : aucun projet valide trouvé dans $RACINE/configs/*.conf" >&2
    exit 1
fi

echo "-- Projets détectés : ${PROJETS[*]} --"

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

echo "-- start : ${UNITES[*]} --"
systemctl --user start "${UNITES[@]}"

# ── 6. Bilan ─────────────────────────────────────────────────────────────────
echo
echo "== État des services =="
systemctl --user --no-pager --no-legend list-units 'watcher@*' || true
echo
echo "Terminé. Diagnostic :"
echo "  systemctl --user status watcher@${PROJETS[0]}"
echo "  journalctl --user -u watcher@${PROJETS[0]} -f"
echo
echo "Le bouton « Lancer / Arrêter watcher » de l'interface pilote désormais"
echo "ces mêmes services systemd (issue #596) — plus de risque de doublon."
