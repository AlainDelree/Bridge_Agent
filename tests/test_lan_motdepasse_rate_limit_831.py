#!/usr/bin/env python3
"""Test de non-régression — issue #831 : mot de passe obligatoire et
connexion exigée en mode --lan (comme en --externe), et limitation des
tentatives de connexion par ADRESSE source (en plus de la session) dans
app/auth.py. Couvre aussi la décision CLI (new_issue.py) sans démarrer de
serveur réel.

Aucun accès réseau réel : la requête HTTP passe par le test_client() de
Flask (pile WSGI in-process) ; l'horloge du blocage par adresse est simulée
en monkeypatchant `app.auth.time.time`.

Exécution :  python3 tests/test_lan_motdepasse_rate_limit_831.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import hashlib
import sys
from pathlib import Path
from unittest import mock

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from app import create_app  # noqa: E402
from app import auth  # noqa: E402
import new_issue  # noqa: E402

MOT_DE_PASSE_CLAIR = "test-mdp-831"
HASH_MOT_DE_PASSE = hashlib.sha256(MOT_DE_PASSE_CLAIR.encode("utf-8")).hexdigest()


def _app(acces_reseau: bool, mot_de_passe: str = HASH_MOT_DE_PASSE):
    """Application Flask configurée comme le serait new_issue.py, sans
    passer par main() (pas de tunnel, pas de thread, pas de .conf lu)."""
    app = create_app()
    app.config["MOT_DE_PASSE"] = mot_de_passe
    app.config["ACCES_RESEAU"] = acces_reseau
    app.config["TESTING"] = True
    return app


def _reset_blocage_adresses():
    auth._ECHECS_PAR_ADRESSE.clear()


def _echouer_login(client, adresse, mot_de_passe="mauvais"):
    return client.post("/login", data={"mot_de_passe": mot_de_passe},
                        environ_overrides={"REMOTE_ADDR": adresse})


def scenario_lan_page_protegee_redirige_sans_session():
    """En --lan, une page protégée redirige vers /login sans session."""
    app = _app(acces_reseau=True)
    with app.test_client() as client:
        rep = client.get("/", follow_redirects=False)
        assert rep.status_code == 302, f"Attendu une redirection, reçu {rep.status_code}"
        assert "/login" in rep.headers.get("Location", ""), rep.headers.get("Location")


def scenario_lan_page_accessible_apres_connexion():
    """En --lan, la page s'ouvre après une connexion réussie (même adresse)."""
    _reset_blocage_adresses()
    app = _app(acces_reseau=True)
    with app.test_client() as client:
        rep = client.post("/login", data={"mot_de_passe": MOT_DE_PASSE_CLAIR},
                           environ_overrides={"REMOTE_ADDR": "10.0.0.1"},
                           follow_redirects=False)
        assert rep.status_code == 302, (
            f"Connexion réussie attendue (redirection vers l'accueil) : {rep.status_code}")
        rep = client.get("/", follow_redirects=False)
        assert rep.status_code == 200, (
            f"La page aurait dû s'ouvrir après connexion : {rep.status_code}")


def scenario_local_sans_login():
    """Le mode local (ACCES_RESEAU=False) reste accessible sans connexion,
    même si un mot de passe est configuré (aucune régression)."""
    app = _app(acces_reseau=False)
    with app.test_client() as client:
        rep = client.get("/", follow_redirects=False)
        assert rep.status_code == 200, (
            f"Le mode local ne doit jamais exiger de connexion : {rep.status_code}")


def scenario_demarrage_refuse_sans_mdp():
    """new_issue.py refuse --lan (comme --externe) sans mot de passe
    configuré, avec le même message ; le mode local n'exige rien."""
    import argparse
    args_lan = argparse.Namespace(lan=True, externe=False)
    args_externe = argparse.Namespace(lan=False, externe=True)
    args_local = argparse.Namespace(lan=False, externe=False)

    host, schema, acces_lan = new_issue._mode_reseau(args_lan)
    assert (host, schema, acces_lan) == ("0.0.0.0", "http", True)
    host, schema, acces_ext = new_issue._mode_reseau(args_externe)
    assert (host, schema, acces_ext) == ("0.0.0.0", "https", True)
    host, schema, acces_local = new_issue._mode_reseau(args_local)
    assert (host, schema, acces_local) == ("127.0.0.1", "http", False)

    erreur_lan = new_issue._erreur_mot_de_passe_manquant(acces_lan, "")
    erreur_ext = new_issue._erreur_mot_de_passe_manquant(acces_ext, "")
    assert erreur_lan is not None and erreur_ext is not None, (
        "--lan et --externe doivent tous deux refuser de démarrer sans mot de passe")
    assert erreur_lan == erreur_ext, "Même message d'erreur pour --lan et --externe"

    assert new_issue._erreur_mot_de_passe_manquant(acces_local, "") is None, (
        "Le mode local ne doit jamais exiger de mot de passe au démarrage")
    assert new_issue._erreur_mot_de_passe_manquant(acces_lan, HASH_MOT_DE_PASSE) is None, (
        "--lan démarre normalement dès qu'un mot de passe est configuré")


def scenario_blocage_par_adresse_independant_session():
    """Après MAX_ECHECS_LOGIN échecs depuis une adresse, une NOUVELLE session
    (nouveau test_client, donc nouveau cookie) de la MÊME adresse est
    refusée, alors qu'une autre adresse ne l'est pas."""
    _reset_blocage_adresses()
    app = _app(acces_reseau=True)
    adresse_attaquante = "203.0.113.9"
    with app.test_client() as client:
        for _ in range(auth.MAX_ECHECS_LOGIN):
            _echouer_login(client, adresse_attaquante)

    # Nouvelle session (nouveau cookie), même adresse : refusée d'office.
    with app.test_client() as nouvelle_session:
        rep = nouvelle_session.post(
            "/login", data={"mot_de_passe": MOT_DE_PASSE_CLAIR},
            environ_overrides={"REMOTE_ADDR": adresse_attaquante})
        assert auth.MESSAGE_BLOCAGE in rep.get_data(as_text=True), (
            "L'adresse bloquée doit être refusée même avec un mot de passe correct "
            "et une session neuve")

    # Une autre adresse n'est pas affectée par le blocage de la première.
    with app.test_client() as autre_client:
        rep = autre_client.post(
            "/login", data={"mot_de_passe": MOT_DE_PASSE_CLAIR},
            environ_overrides={"REMOTE_ADDR": "198.51.100.4"})
        assert rep.status_code == 302, (
            f"Une autre adresse ne doit pas être bloquée : {rep.status_code} "
            f"{rep.get_data(as_text=True)[:200]}")


def scenario_succes_remet_compteur_a_zero():
    """Un succès de connexion remet le compteur de l'adresse à zéro."""
    _reset_blocage_adresses()
    app = _app(acces_reseau=True)
    adresse = "203.0.113.50"
    with app.test_client() as client:
        for _ in range(auth.MAX_ECHECS_LOGIN - 1):
            _echouer_login(client, adresse)
        rep = client.post("/login", data={"mot_de_passe": MOT_DE_PASSE_CLAIR},
                           environ_overrides={"REMOTE_ADDR": adresse})
        assert rep.status_code == 302, "La connexion correcte doit réussir"

    assert adresse not in auth._ECHECS_PAR_ADRESSE, (
        "Un succès doit retirer l'adresse du suivi des échecs")

    # Une nouvelle session de la même adresse n'est plus bloquée.
    with app.test_client() as nouvelle_session:
        rep = nouvelle_session.get("/login")
        assert rep.status_code == 200 and auth.MESSAGE_BLOCAGE not in rep.get_data(as_text=True)


def scenario_blocage_expire_horloge_simulee():
    """Le blocage par adresse expire après DUREE_BLOCAGE_ADRESSE secondes
    (horloge simulée — aucun vrai delai)."""
    _reset_blocage_adresses()
    app = _app(acces_reseau=True)
    adresse = "203.0.113.77"
    horodatage = [1_000_000.0]
    with mock.patch.object(auth.time, "time", lambda: horodatage[0]):
        with app.test_client() as client:
            for _ in range(auth.MAX_ECHECS_LOGIN):
                _echouer_login(client, adresse)
            assert auth._adresse_bloquee(adresse), "L'adresse doit être bloquée après 5 échecs"

            horodatage[0] += auth.DUREE_BLOCAGE_ADRESSE - 1
            assert auth._adresse_bloquee(adresse), "Pas encore expiré à T-1s"

            horodatage[0] += 2
            assert not auth._adresse_bloquee(adresse), "Doit être expiré après DUREE_BLOCAGE_ADRESSE"

            # Nouvelle session : le blocage PAR SESSION du client précédent
            # (5 échecs, lui, permanent jusqu'à suppression du cookie) ne
            # doit pas fausser la mesure du blocage PAR ADRESSE, seul testé
            # ici — cf. scenario_blocage_par_adresse_independant_session
            # pour la session neuve + adresse bloquée (cas inverse).
            with app.test_client() as nouvelle_session:
                rep = nouvelle_session.post(
                    "/login", data={"mot_de_passe": MOT_DE_PASSE_CLAIR},
                    environ_overrides={"REMOTE_ADDR": adresse})
                assert rep.status_code == 302, (
                    "Une fois le blocage par adresse expiré, une connexion correcte "
                    f"depuis une session neuve doit réussir : {rep.status_code}")


def main():
    tests = [
        ("--lan : page protégée redirige vers /login sans session",
         scenario_lan_page_protegee_redirige_sans_session),
        ("--lan : page accessible après connexion réussie",
         scenario_lan_page_accessible_apres_connexion),
        ("mode local : jamais de login exigé",
         scenario_local_sans_login),
        ("démarrage refusé sans mot de passe (--lan comme --externe)",
         scenario_demarrage_refuse_sans_mdp),
        ("blocage par adresse indépendant de la session",
         scenario_blocage_par_adresse_independant_session),
        ("un succès remet le compteur d'adresse à zéro",
         scenario_succes_remet_compteur_a_zero),
        ("le blocage par adresse expire (horloge simulée)",
         scenario_blocage_expire_horloge_simulee),
    ]
    echecs = 0
    for nom, fn in tests:
        try:
            fn()
            print(f"  ✓ {nom}")
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
