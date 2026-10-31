#!/usr/bin/env python3
"""Test de non-régression — issue #834 : `app/tunnel.py` lit l'adresse du
tunnel dans la configuration de cloudflared (`~/.cloudflared/config.yml`) au
lieu de l'avoir en dur dans une constante `URL_TUNNEL`.

Couvre `lire_url_tunnel()` : fichier avec un `hostname` (adresse `https://`
renvoyée), fichier sans clé `hostname`, fichier vide, fichier mal formé
(binaire) et fichier illisible (droits retirés) — ces deux derniers cas sans
qu'aucune exception ne sorte de la fonction (repli sur None). Ne lance jamais
`cloudflared`.

Exécution :  python3 tests/test_lire_url_tunnel_834.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import os
import sys
import tempfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from app.tunnel import lire_url_tunnel  # noqa: E402


def scenario_1_hostname_trouve():
    """Une règle d'ingress avec `hostname` → adresse https renvoyée."""
    with tempfile.TemporaryDirectory() as tmp:
        chemin = Path(tmp) / "config.yml"
        chemin.write_text(
            "tunnel: abcd-1234\n"
            "credentials-file: /home/alain/.cloudflared/abcd-1234.json\n"
            "ingress:\n"
            "  - hostname: bridge.exemple.test\n"
            "    service: http://localhost:5100\n"
            "  - service: http_status:404\n",
            encoding="utf-8",
        )
        resultat = lire_url_tunnel(chemin)
        assert resultat == "https://bridge.exemple.test", resultat
        return {"resultat": resultat}


def scenario_2_sans_hostname():
    """Fichier de config valide mais sans clé `hostname` → None."""
    with tempfile.TemporaryDirectory() as tmp:
        chemin = Path(tmp) / "config.yml"
        chemin.write_text(
            "tunnel: abcd-1234\n"
            "credentials-file: /home/alain/.cloudflared/abcd-1234.json\n"
            "ingress:\n"
            "  - service: http_status:404\n",
            encoding="utf-8",
        )
        resultat = lire_url_tunnel(chemin)
        assert resultat is None, resultat
        return {}


def scenario_3_fichier_vide():
    """Fichier vide → None, aucune exception."""
    with tempfile.TemporaryDirectory() as tmp:
        chemin = Path(tmp) / "config.yml"
        chemin.write_text("", encoding="utf-8")
        resultat = lire_url_tunnel(chemin)
        assert resultat is None, resultat
        return {}


def scenario_4_fichier_absent():
    """Fichier absent → None, aucune exception."""
    with tempfile.TemporaryDirectory() as tmp:
        chemin = Path(tmp) / "config.yml"
        resultat = lire_url_tunnel(chemin)
        assert resultat is None, resultat
        return {}


def scenario_5_fichier_mal_forme():
    """Contenu binaire non décodable en UTF-8 → None, aucune exception."""
    with tempfile.TemporaryDirectory() as tmp:
        chemin = Path(tmp) / "config.yml"
        chemin.write_bytes(b"\xff\xfe\x00hostname\x00: \x00\xd8\x00\x00")
        resultat = lire_url_tunnel(chemin)
        assert resultat is None, resultat
        return {}


def scenario_6_fichier_illisible():
    """Fichier sans droit de lecture → None, aucune exception (ignoré si le
    processus tourne en root, qui ignore les permissions)."""
    if os.name != "posix" or os.geteuid() == 0:
        return {"ignore": "non applicable (non POSIX ou exécuté en root)"}
    with tempfile.TemporaryDirectory() as tmp:
        chemin = Path(tmp) / "config.yml"
        chemin.write_text("ingress:\n  - hostname: bridge.exemple.test\n", encoding="utf-8")
        chemin.chmod(0o000)
        try:
            resultat = lire_url_tunnel(chemin)
        finally:
            chemin.chmod(0o644)
        assert resultat is None, resultat
        return {}


def scenario_7_hostname_sans_tiret():
    """Clé `hostname` écrite sans tiret de liste en tête de ligne → reconnue
    quand même (format minimal décrit par la documentation cloudflared)."""
    with tempfile.TemporaryDirectory() as tmp:
        chemin = Path(tmp) / "config.yml"
        chemin.write_text("hostname: bridge.exemple.test\n", encoding="utf-8")
        resultat = lire_url_tunnel(chemin)
        assert resultat == "https://bridge.exemple.test", resultat
        return {"resultat": resultat}


def main():
    tests = [
        ("hostname trouvé → https://<hostname>", scenario_1_hostname_trouve),
        ("config sans hostname → None", scenario_2_sans_hostname),
        ("fichier vide → None", scenario_3_fichier_vide),
        ("fichier absent → None", scenario_4_fichier_absent),
        ("fichier mal formé (binaire) → None, aucune exception", scenario_5_fichier_mal_forme),
        ("fichier illisible → None, aucune exception", scenario_6_fichier_illisible),
        ("hostname sans tiret de liste → reconnu", scenario_7_hostname_sans_tiret),
    ]
    echecs = 0
    for nom, fn in tests:
        try:
            rap = fn()
            print(f"  ✓ {nom}  ({rap})")
        except AssertionError as e:
            echecs += 1
            print(f"  ✗ {nom}\n      {e}")
        except Exception as e:  # noqa: BLE001
            echecs += 1
            print(f"  ✗ {nom} — erreur inattendue : {type(e).__name__}: {e}")

    if echecs:
        print(f"\n❌ {echecs} scénario(s) en échec.")
        return 1
    print("\n✅ Tous les scénarios passent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
