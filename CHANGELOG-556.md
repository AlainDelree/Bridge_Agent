# CHANGELOG-556 — entrées à fusionner dans CHANGELOG.md

## 15 septembre 2026 — issue #556 (2/3)

Traitement du champ d'en-tête `CREATION` dans `watcher.py` — bootstrap
automatique d'un service CCW dédié, suite de la conception validée en #554
et de la génération de la paire de clés RSA 3072 (#554 1/3) : ENTIÈREMENT
déterministe, n'invoque JAMAIS `claude` (décision #554 §2.5) — réutilise
directement les scripts PowerShell déjà testés (`ajouter_projet_ccw.ps1`
puis `finaliser_projet_ccw_auto.ps1 -FichierValeurs`, format vérifié par
lecture du script avant écriture du code, identique à celui déjà produit
par `app/ccw.py`).

`_traiter_issue_synchrone` détecte `| CREATION | oui |` tôt dans le
dispatch, AVANT tout ce qui touche au pipeline `lancer_claude`. Convention
de 6 champs d'en-tête proposée et documentée (`CREATION`,
`CREATION_NOM_PROJET`, `CREATION_DEPOT`, `CREATION_TOPIC_NTFY`,
`CREATION_GH_TOKEN`, `CREATION_OAUTH_TOKEN`) : les deux tokens transitent
chiffrés individuellement (RSA/OAEP-SHA256 via `openssl pkeyutl -encrypt`,
clé publique de bootstrap) puis encodés en base64 sur une seule ligne.
`_extraire_champ_entete` compare le nom de champ EXACTEMENT (pas une
sous-chaîne comme les extracteurs existants SOUS_DOSSIER/REPO_CIBLE) : évite
la collision entre `CREATION` et son propre préfixe partagé avec
`CREATION_NOM_PROJET`/etc.

Résolution robuste du chemin `openssl` (`_resoudre_openssl`, point
d'attention hérité de #557 puisque #558 n'était pas encore mergé au moment
de cette tâche) : PATH → installation manuelle Windows
(`C:\Program Files\OpenSSL-Win64\bin\openssl.exe`, pas sur le PATH par
défaut sur CCW) → repli `usr\bin` de Git pour Windows — dupliqué en Python
plutôt que réutilisé depuis `Resoudre-OpenSSL` côté PowerShell
(`provisionner.ps1`, #554) : pas de dot-sourcing PowerShell depuis Python,
et un simple calcul de chemin ne justifie pas d'exécuter un script externe.

Retrait immédiat des deux tokens chiffrés du corps GitHub (`gh issue edit
--body-file`, remplacés par `<retiré après application>`) DÈS que les
valeurs sont en mémoire — avant même la tentative de déchiffrement — pour
limiter le temps d'exposition résiduel (§2.4 de #554). Fichier de valeurs
temporaire supprimé en deux lignes de défense (le `finally` PowerShell déjà
en place côté `finaliser_projet_ccw_auto.ps1`, PUIS un nettoyage Python en
repli). Compte-rendu + fermeture si succès (codes 0/2), `needs-human` + log
complet en commentaire si échec — un champ manquant est traité comme une
erreur de configuration définitive (aucun script PowerShell ni
déchiffrement tenté).

Testé sans vraie issue GitHub ni machine CCW réelle (sur le modèle du test
`SOUS_DOSSIER` de #550) : `tests/test_creation_bootstrap_ccw_556.py`, 15
scénarios — extraction/détection, non-collision `CREATION`/
`CREATION_NOM_PROJET`, retrait des tokens, résolution `openssl` (3 replis),
chiffrement/déchiffrement RÉEL via un openssl local (RSA 3072 généré à la
volée), chemin complet succès/champ manquant/dry-run (faux `gh` et faux
`powershell` sur le `PATH`), et un scénario bout en bout via `traiter_issue`
vérifiant qu'un faux `claude` marqueur n'est jamais touché.

Documenté en détail dans `BRIDGE_AGENT_DOC.md` §16.6 (nouvelle
sous-section), à l'intention du formulaire web à venir (3/3, #559 ou
suivant — non traité ici, `new_issue.py` non touché).
