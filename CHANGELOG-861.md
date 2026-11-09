## 9 novembre 2026 — issue #861

Droit de démarrage des services CCW (`sc.exe sdset`, issue #717) : compte par
défaut devenu l'utilisateur courant, au lieu du compte d'Alain codé en dur —
même principe que #860 pour le compte de service NSSM.

**`ccw-commun.psm1::Autoriser-DemarrageServiceCcw`** : le paramètre
`-NomCompte` vaut désormais par défaut `$env:USERNAME` (compte qui lance le
script appelant) au lieu de `'AlainW'`. Commentaire de la fonction reformulé
pour ne plus citer un compte précis, en gardant le constat technique (le
jeton d'une session normale, même administrateur, est bridé par l'UAC —
`nssm start` échoue avec « Access is denied », `nssm status` fonctionne).

**`autoriser_demarrage_ccw.ps1`** : même changement de défaut pour
`-NomCompte`, aide en tête de fichier et commentaires reformulés sans
référence à `AlainW`.

**`ajouter_projet_ccw.ps1`** : commentaire de l'étape 5 (pose des droits à
chaque création/recréation de service) reformulé — ne citait plus
`AlainW` que par erreur, le comportement (appel sans `-NomCompte`, donc
défaut de la fonction) était déjà correct et inchangé.

**`configurer_ssh_ccw.ps1`** : le message de fin, qui donnait
`ssh AlainW@<hôte>` en exemple, devient un texte neutre
(`ssh <compte-administrateur>@<hôte>`) — ce script écrit la clé publique
dans `administrators_authorized_keys`, valable pour n'importe quel compte
administrateur local, pas un compte précis.

**`REINSTALLATION_CCW.md`** : non modifié — ce document ne traite pas le
sujet des droits `sc.exe sdset` (aucune mention de `autoriser_demarrage_ccw.ps1`
ni de l'issue #717 avant ce changement).

**Comportement pour Alain inchangé** : sur son PC fixe, `AlainW` est déjà
le compte interactif/SSH courant — `$env:USERNAME` y vaut `AlainW`, donc
même résultat qu'avant. Aucun appelant (`ajouter_projet_ccw.ps1`,
`autoriser_demarrage_ccw.ps1`) ne dépendait de l'ancienne valeur codée en
dur pour un comportement différent.

**Non testé** (code PowerShell, ne s'exécute pas sous Linux) : relecture
rigoureuse uniquement — vérification réelle (`nssm start`/`stop` en session
non élevée après exécution d'`autoriser_demarrage_ccw.ps1` ou
`ajouter_projet_ccw.ps1`) à faire par Alain sur le PC Windows.
