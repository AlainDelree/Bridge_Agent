#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""creer_vm_ccw.py — Provisioning phase 1 de la VM Windows CCW.

Crée (via VBoxManage) une VM VirtualBox nommée « CCW-Build » destinée à
héberger le futur agent Claude Code Windows (CCW) chargé des builds .exe
(PyInstaller) délégués par CCL. Voir issue #146.

La VM cible Windows 11 IoT Enterprise LTSC 2024 en évaluation 90 jours : elle
doit pouvoir être recréée facilement à l'expiration — d'où le flag --recreate.

Ce script se contente de CRÉER et CONFIGURER la VM (matériel + disque fixe +
dossier partagé). Il n'attache PAS d'ISO et NE LANCE PAS l'installation : ces
étapes restent manuelles (voir le résumé en fin d'issue) et l'automatisation
complète de l'OOBE est portée par autounattend.xml (même dossier).

Usage :
    python3 creer_vm_ccw.py               # crée la VM (refuse si elle existe)
    python3 creer_vm_ccw.py --recreate    # détruit la VM existante puis recrée
    python3 creer_vm_ccw.py --dry-run     # affiche les commandes sans exécuter

Prérequis : VirtualBox installé (VBoxManage dans le PATH).
"""

import argparse
import os
import shutil
import subprocess
import sys

# ---------------------------------------------------------------------------
# Constantes de configuration — à adapter ici en tête de script.
# ---------------------------------------------------------------------------

NOM_VM = "CCW-Build"                 # nom VirtualBox de la VM
RAM_MO = 6144                        # mémoire vive en Mo (6 Go)
NB_CPU = 4                           # nombre de cœurs virtuels
PARAVIRT = "kvm"                     # paravirtprovider (kvm recommandé sous Linux)
TAILLE_DISQUE_MO = 40 * 1024         # disque virtuel FIXE : 40 Go (40960 Mo)
TYPE_OS = "Windows11_64"             # identifiant OS type VirtualBox

# Dossier partagé hôte <-> invité. Créé s'il n'existe pas. Configurable via
# la variable d'environnement CCW_SHARE_DIR, sinon ~/Bridge_Agent_CCW_Share.
DOSSIER_PARTAGE_HOTE = os.environ.get(
    "CCW_SHARE_DIR",
    os.path.expanduser("~/Bridge_Agent_CCW_Share"),
)
NOM_PARTAGE = "CCW_Share"            # nom logique du partage vu côté invité

# Emplacement du disque .vdi. Par défaut à côté du fichier .vbox de la VM, dans
# le dossier machines par défaut de VirtualBox (résolu à l'exécution).
NOM_DISQUE = f"{NOM_VM}.vdi"


# ---------------------------------------------------------------------------
# Utilitaires d'exécution
# ---------------------------------------------------------------------------

def _vboxmanage_dispo():
    """Retourne le chemin de VBoxManage ou None s'il est introuvable."""
    return shutil.which("VBoxManage")


def executer(cmd, dry_run=False, verifier=True):
    """Exécute une commande (liste d'arguments) et affiche ce qu'elle fait.

    dry_run=True : affiche seulement, n'exécute pas.
    verifier=True : lève CalledProcessError en cas de code retour non nul.
    """
    print("  $ " + " ".join(cmd))
    if dry_run:
        return None
    return subprocess.run(cmd, check=verifier, text=True)


def vm_existe(nom):
    """Vrai si une VM de ce nom est déjà enregistrée dans VirtualBox."""
    res = subprocess.run(
        ["VBoxManage", "list", "vms"],
        capture_output=True, text=True, check=True,
    )
    # Chaque ligne ressemble à :  "CCW-Build" {uuid}
    return any(f'"{nom}"' in ligne for ligne in res.stdout.splitlines())


def chemin_disque(nom_vm, dry_run=False):
    """Chemin absolu attendu du .vdi (dossier machines par défaut/NOM_VM/)."""
    if dry_run:
        # En dry-run on ne résout pas le dossier réel : valeur indicative.
        return os.path.join("<VBox_default_machine_folder>", nom_vm, NOM_DISQUE)
    res = subprocess.run(
        ["VBoxManage", "list", "systemproperties"],
        capture_output=True, text=True, check=True,
    )
    dossier_machines = None
    for ligne in res.stdout.splitlines():
        if ligne.startswith("Default machine folder:"):
            dossier_machines = ligne.split(":", 1)[1].strip()
            break
    if not dossier_machines:
        dossier_machines = os.path.expanduser("~/VirtualBox VMs")
    return os.path.join(dossier_machines, nom_vm, NOM_DISQUE)


# ---------------------------------------------------------------------------
# Étapes de provisioning
# ---------------------------------------------------------------------------

def detruire_vm(nom, dry_run=False):
    """Détruit proprement la VM et ses disques (unregistervm --delete)."""
    print(f"[--recreate] Destruction de la VM existante « {nom} »…")
    executer(["VBoxManage", "unregistervm", nom, "--delete"], dry_run=dry_run)


def creer_dossier_partage(chemin, dry_run=False):
    """Crée le dossier partagé hôte s'il n'existe pas."""
    if os.path.isdir(chemin):
        print(f"Dossier partagé déjà présent : {chemin}")
        return
    print(f"Création du dossier partagé hôte : {chemin}")
    if not dry_run:
        os.makedirs(chemin, exist_ok=True)


def creer_vm(dry_run=False):
    """Crée et configure la VM CCW-Build de zéro."""
    # 1. Création + enregistrement de la VM.
    executer([
        "VBoxManage", "createvm",
        "--name", NOM_VM,
        "--ostype", TYPE_OS,
        "--register",
    ], dry_run=dry_run)

    # 2. Matériel : RAM, CPU, paravirt, I/O APIC (requis pour Windows 64 bits).
    executer([
        "VBoxManage", "modifyvm", NOM_VM,
        "--memory", str(RAM_MO),
        "--cpus", str(NB_CPU),
        "--paravirtprovider", PARAVIRT,
        "--ioapic", "on",
        "--rtcuseutc", "on",
        "--firmware", "efi",          # Windows 11 exige UEFI
        "--graphicscontroller", "vboxsvga",
        "--vram", "128",
        "--nic1", "nat",              # réseau NAT (accès sortant pour phase 2)
    ], dry_run=dry_run)

    # 3. Disque virtuel FIXE (--variant Fixed, pas dynamique).
    disque = chemin_disque(NOM_VM, dry_run=dry_run)
    executer([
        "VBoxManage", "createmedium", "disk",
        "--filename", disque,
        "--size", str(TAILLE_DISQUE_MO),
        "--variant", "Fixed",
        "--format", "VDI",
    ], dry_run=dry_run)

    # 4. Contrôleur SATA + attachement du disque.
    executer([
        "VBoxManage", "storagectl", NOM_VM,
        "--name", "SATA",
        "--add", "sata",
        "--controller", "IntelAhci",
        "--portcount", "2",
    ], dry_run=dry_run)
    executer([
        "VBoxManage", "storageattach", NOM_VM,
        "--storagectl", "SATA",
        "--port", "0",
        "--device", "0",
        "--type", "hdd",
        "--medium", disque,
    ], dry_run=dry_run)

    # 5. Dossier partagé hôte <-> invité (montage automatique côté invité).
    executer([
        "VBoxManage", "sharedfolder", "add", NOM_VM,
        "--name", NOM_PARTAGE,
        "--hostpath", DOSSIER_PARTAGE_HOTE,
        "--automount",
    ], dry_run=dry_run)


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Crée la VM VirtualBox CCW-Build (provisioning phase 1).",
    )
    parser.add_argument(
        "--recreate", action="store_true",
        help="détruit une VM existante du même nom avant de la recréer",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="affiche les commandes VBoxManage sans les exécuter",
    )
    args = parser.parse_args(argv)

    if not args.dry_run and _vboxmanage_dispo() is None:
        print("ERREUR : VBoxManage introuvable dans le PATH. "
              "Installez VirtualBox ou utilisez --dry-run.", file=sys.stderr)
        return 2

    print(f"=== Provisioning VM « {NOM_VM} » "
          f"({RAM_MO} Mo, {NB_CPU} CPU, disque fixe "
          f"{TAILLE_DISQUE_MO // 1024} Go) ===")
    if args.dry_run:
        print("[dry-run] aucune commande ne sera réellement exécutée.\n")

    # Gestion d'une VM déjà existante.
    if not args.dry_run and vm_existe(NOM_VM):
        if args.recreate:
            detruire_vm(NOM_VM, dry_run=args.dry_run)
        else:
            print(f"ERREUR : la VM « {NOM_VM} » existe déjà. "
                  f"Relancez avec --recreate pour la détruire et la recréer.",
                  file=sys.stderr)
            return 1
    elif args.dry_run and args.recreate:
        # En dry-run on montre quand même la commande de destruction.
        detruire_vm(NOM_VM, dry_run=True)

    creer_dossier_partage(DOSSIER_PARTAGE_HOTE, dry_run=args.dry_run)
    creer_vm(dry_run=args.dry_run)

    print("\n=== Terminé ===")
    print(f"VM « {NOM_VM} » créée. Prochaines étapes MANUELLES :")
    print("  1. Attacher l'ISO Windows 11 IoT Enterprise LTSC 2024 :")
    print(f'     VBoxManage storageattach {NOM_VM} --storagectl SATA \\')
    print("       --port 1 --device 0 --type dvddrive --medium /chemin/vers/windows.iso")
    print("  2. Placer autounattend.xml (ce dossier) à la racine d'une clé/ISO")
    print("     secondaire lue par le programme d'installation Windows.")
    print(f"  3. Démarrer : VBoxManage startvm {NOM_VM}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
