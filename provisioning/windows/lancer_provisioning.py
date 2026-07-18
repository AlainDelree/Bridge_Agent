#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""lancer_provisioning.py — Pousse et exécute provisionner.ps1 dans la VM CCW.

Provisioning phase 2 (issue #147), côté CCL (Linux). Ce script utilise
« VBoxManage guestcontrol » pour :

  1. copier provisionner.ps1 (même dossier) dans la VM « CCW-Build » ;
  2. l'exécuter via powershell.exe sous le compte ccw-admin (créé en phase 1).

Pourquoi guestcontrol plutôt que WinRM ? Aucune dépendance réseau/pare-feu :
seules les Guest Additions (déjà requises) sont nécessaires. WinRM reste
disponible (activé par autounattend.xml) mais surdimensionné pour cette étape.

SÉCURITÉ — mot de passe :
  Le mot de passe du compte ccw-admin est lu depuis la variable
  d'environnement CCW_ADMIN_PASSWORD. Il n'est JAMAIS passé en argument en
  clair (invisible dans `ps`) : VBoxManage le lit via --passwordfile sur un
  fichier temporaire à permissions restreintes, supprimé en fin d'exécution.
  Aucun mot de passe n'est écrit dans ce script ni committé.

Usage :
    export CCW_ADMIN_PASSWORD='…'          # jamais committé
    python3 lancer_provisioning.py               # copie + exécute
    python3 lancer_provisioning.py --dry-run     # affiche les commandes
    python3 lancer_provisioning.py --vm CCW-Build --user ccw-admin

Prérequis : VirtualBox (VBoxManage), VM démarrée avec Guest Additions,
Windows installé et session ccw-admin ouverte (voir autounattend.xml).
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile

# Emplacement du script PowerShell à pousser (à côté de ce fichier).
ICI = os.path.dirname(os.path.abspath(__file__))
SCRIPT_PS1_LOCAL = os.path.join(ICI, "provisionner.ps1")

# Destination du script DANS la VM (invité). Chemins Windows explicites : ce
# script tourne sous Linux, où os.path ne comprend pas « \ » — on ne dérive
# donc PAS le dossier via os.path.dirname (qui renverrait une valeur erronée).
DEST_DIR_INVITE = "C:\\Windows\\Temp\\"
DEST_INVITE = DEST_DIR_INVITE + "provisionner.ps1"

NOM_VM_DEFAUT = "CCW-Build"
USER_DEFAUT = "ccw-admin"


def _vboxmanage_dispo():
    """Retourne le chemin de VBoxManage ou None s'il est introuvable."""
    return shutil.which("VBoxManage")


def executer(cmd, passwordfile, dry_run=False):
    """Exécute une commande VBoxManage en masquant le --passwordfile à l'écran.

    Le chemin du passwordfile est réel dans la commande exécutée, mais affiché
    de façon neutre pour ne pas suggérer qu'un secret transiterait en clair.
    """
    affichage = [("<passwordfile>" if a == passwordfile else a) for a in cmd]
    print("  $ " + " ".join(affichage))
    if dry_run:
        return 0
    res = subprocess.run(cmd, text=True)
    return res.returncode


def construire_base(vm, user, passwordfile):
    """Préfixe commun des commandes guestcontrol (VM + identifiants)."""
    return [
        "VBoxManage", "guestcontrol", vm,
        "--username", user,
        "--passwordfile", passwordfile,
    ]


def copier_script(vm, user, passwordfile, dry_run=False):
    """Copie provisionner.ps1 de l'hôte vers la VM (copyto)."""
    cmd = construire_base(vm, user, passwordfile) + [
        "copyto",
        "--target-directory", DEST_DIR_INVITE,
        SCRIPT_PS1_LOCAL,
    ]
    print("→ Copie du script dans la VM…")
    return executer(cmd, passwordfile, dry_run=dry_run)


def executer_script(vm, user, passwordfile, dry_run=False):
    """Lance provisionner.ps1 dans la VM via powershell.exe (run)."""
    cmd = construire_base(vm, user, passwordfile) + [
        "run",
        "--exe", r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
        "--wait-stdout", "--wait-stderr",
        "--",
        "powershell.exe",
        "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-File", DEST_INVITE,
    ]
    print("→ Exécution du provisioning dans la VM (peut prendre plusieurs minutes)…")
    return executer(cmd, passwordfile, dry_run=dry_run)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Pousse et exécute provisionner.ps1 dans la VM CCW "
                    "via VBoxManage guestcontrol (provisioning phase 2).",
    )
    parser.add_argument("--vm", default=NOM_VM_DEFAUT,
                        help=f"nom de la VM (défaut : {NOM_VM_DEFAUT})")
    parser.add_argument("--user", default=USER_DEFAUT,
                        help=f"compte invité (défaut : {USER_DEFAUT})")
    parser.add_argument("--dry-run", action="store_true",
                        help="affiche les commandes sans les exécuter")
    args = parser.parse_args(argv)

    if not os.path.isfile(SCRIPT_PS1_LOCAL):
        print(f"ERREUR : script introuvable : {SCRIPT_PS1_LOCAL}", file=sys.stderr)
        return 2

    if not args.dry_run and _vboxmanage_dispo() is None:
        print("ERREUR : VBoxManage introuvable dans le PATH. "
              "Installez VirtualBox ou utilisez --dry-run.", file=sys.stderr)
        return 2

    # Mot de passe : jamais en argument, toujours via l'environnement.
    mot_de_passe = os.environ.get("CCW_ADMIN_PASSWORD")
    if not args.dry_run and not mot_de_passe:
        print("ERREUR : variable d'environnement CCW_ADMIN_PASSWORD non définie.\n"
              "  export CCW_ADMIN_PASSWORD='…' avant de lancer ce script.",
              file=sys.stderr)
        return 2

    print(f"=== Provisioning phase 2 — VM « {args.vm} », compte « {args.user} » ===")
    if args.dry_run:
        print("[dry-run] aucune commande ne sera réellement exécutée.\n")

    # Écrit le mot de passe dans un fichier temporaire à permissions 0600,
    # supprimé quoi qu'il arrive (finally). En dry-run on utilise un chemin
    # fictif : rien n'est écrit ni exécuté.
    passwordfile = None
    fichier_temp = None
    try:
        if args.dry_run:
            passwordfile = "<CCW_ADMIN_PASSWORD>"
        else:
            fd, passwordfile = tempfile.mkstemp(prefix="ccw-pw-")
            fichier_temp = passwordfile
            os.chmod(passwordfile, 0o600)
            with os.fdopen(fd, "w") as f:
                f.write(mot_de_passe)

        code = copier_script(args.vm, args.user, passwordfile, dry_run=args.dry_run)
        if code != 0:
            print(f"ERREUR : la copie a échoué (code {code}).", file=sys.stderr)
            return code

        code = executer_script(args.vm, args.user, passwordfile, dry_run=args.dry_run)
        if code != 0:
            print(f"ERREUR : l'exécution a échoué (code {code}).", file=sys.stderr)
            return code
    finally:
        if fichier_temp and os.path.exists(fichier_temp):
            os.remove(fichier_temp)

    print("\n=== Terminé ===")
    print("Le provisioning logiciel a été lancé dans la VM.")
    print("Vérifier la sortie ci-dessus, puis dans la VM :")
    print("  • renseigner TOPIC_NTFY dans configs\\ccw.conf ;")
    print("  • authentifier Claude (ANTHROPIC_API_KEY ou `claude auth login`) ;")
    print("  • la tâche planifiée « CCW-Watcher » démarrera au prochain logon.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
