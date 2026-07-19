#!/usr/bin/env bash
#
# demarrer_ccw.sh — Démarre la VM VirtualBox de l'agent Windows CCW (issue #166).
#
# But : wrapper simple et sûr autour de VBoxManage pour piloter la VM
# `CCW-Build` depuis CCL (Linux). Par défaut, démarrage *headless* (sans
# fenêtre) — c'est le mode voulu pour un agent qui tourne en service et n'a
# pas besoin d'affichage.
#
# Usage :
#   ./demarrer_ccw.sh                # démarre en headless (défaut)
#   ./demarrer_ccw.sh --gui          # démarre avec une fenêtre (alias --fenetre)
#   ./demarrer_ccw.sh --status       # affiche l'état sans rien démarrer
#   ./demarrer_ccw.sh --help         # cette aide
#
# Détails :
#   - Si la VM est déjà démarrée, le script est silencieux (rien à faire) et
#     sort en succès — sauf --gui qui rattache alors une fenêtre.
#   - --gui / --fenetre : démarre avec --type separate (fenêtre détachable),
#     ou, si la VM tourne déjà en headless, ouvre une fenêtre sur la session
#     en cours (VBoxManage startvm --type separate rattache l'affichage).
#   - Ce script n'a été testé qu'en relecture (dry-run visuel) : il n'enveloppe
#     que des commandes VBoxManage déjà validées manuellement.
#
set -euo pipefail

VM="CCW-Build"

usage() {
    sed -n '3,23p' "$0" | sed 's/^# \{0,1\}//'
}

# État de la VM : "running", "poweroff", "paused", "saved", … ou "" si absente.
etat_vm() {
    VBoxManage showvminfo "$VM" --machinereadable 2>/dev/null \
        | grep '^VMState=' | cut -d'"' -f2
}

# Vérifie que la VM existe, sinon message clair et sortie en erreur.
verifier_vm_existe() {
    if ! VBoxManage list vms 2>/dev/null | grep -q "\"$VM\""; then
        echo "Erreur : la VM « $VM » n'existe pas (VBoxManage ne la connaît pas)." >&2
        echo "         Créez-la d'abord : python3 provisioning/windows/creer_vm_ccw.py" >&2
        exit 1
    fi
}

demarrer() {
    local type_demarrage="$1"   # headless | separate
    local etat
    etat="$(etat_vm)"

    if [ "$etat" = "running" ]; then
        if [ "$type_demarrage" = "separate" ]; then
            # Déjà démarrée (probablement en headless) : rattacher une fenêtre.
            echo "VM « $VM » déjà démarrée — ouverture d'une fenêtre…"
            VBoxManage startvm "$VM" --type separate
        else
            # Silencieux en headless si déjà en route.
            echo "VM « $VM » déjà démarrée (headless) — rien à faire."
        fi
        return 0
    fi

    echo "Démarrage de « $VM » (--type $type_demarrage)…"
    if ! VBoxManage startvm "$VM" --type "$type_demarrage"; then
        echo "Erreur : échec du démarrage de la VM « $VM »." >&2
        exit 1
    fi
}

afficher_status() {
    local etat
    etat="$(etat_vm)"
    if [ -z "$etat" ]; then
        echo "VM « $VM » : introuvable (non créée)."
        exit 1
    fi
    echo "VM « $VM » : $etat"
}

# ── Analyse des arguments ────────────────────────────────────────────────────
case "${1:-}" in
    --status)
        verifier_vm_existe
        afficher_status
        ;;
    --gui|--fenetre)
        verifier_vm_existe
        demarrer separate
        ;;
    --help|-h)
        usage
        ;;
    "")
        verifier_vm_existe
        demarrer headless
        ;;
    *)
        echo "Argument inconnu : $1" >&2
        usage >&2
        exit 2
        ;;
esac
