## 3 novembre 2026 — issue #848

Onglet Configuration : ajout d'une section **Audit** (issue #848) — un
template d'audit par projet, importé depuis un fichier `.txt` au même
format que ceux déposés dans `issues_inbox/` (réutilise
`scripts/watcher_issues_inbox.py::extraire_champs()`, pas de second
parseur), stocké à part (`configs/audit_<projet>.json`, un objet unique,
jamais lu par `GET /templates/<projet>` pour qu'il n'apparaisse jamais dans
la liste « Charger un template » du formulaire du projet lui-même). Pas
d'éditeur : aperçu en lecture seule, réimport = remplacement après
confirmation, bouton Supprimer. Les champs `PROJET`/`REPO_CIBLE` du fichier
sont toujours ignorés (avertissement si inattendus) ; `COMPLEXITE` absente
ou non reconnue replie sur `normal` avec avertissement. Nouveau bouton
« Préparer l'audit » : bascule sur le formulaire « Nouvelle issue » de
`diagnostique_programme` (jamais le projet audité), pré-rempli avec le
template d'audit et le `REP_TRAVAIL` Linux du projet audité comme Dépôt
cible, bandeau explicite sur la destination réelle — réutilise le
formulaire et ses vérifications existantes, aucun envoi automatique.
`static/js/app.js::onProjetChange()` est devenu `async` (await de
`mettreAJourInfoProjet`) pour permettre cette séquence sans course.

Formulaire « Nouvelle issue » : ajout du sélecteur **Complexité** (quatre
valeurs `rapide`/`court`/`normal`/`lourd`, défaut `normal`), mémorisé par la
bibliothèque de templates (issue #284) et transmis à la création de l'issue
via le paramètre `complexite` que `app.issues.formater_entete()` acceptait
déjà sans jamais être alimenté — une issue créée par ce sélecteur porte
désormais la ligne `COMPLEXITE` et ne reçoit plus le label
`sans-complexite` (issue #844). Le **Dépôt cible** (`REPO_CIBLE`, issue
#829) est maintenant mémorisé par tous les templates (pas seulement utile à
l'audit) ; un ancien template sans ces deux nouveaux champs se recharge
sans erreur (défauts `""` / `"normal"`).

Aucun fichier `configs/*.conf` modifié. Tests : +28 Python
(`tests/test_audit_projet_848.py`) et +8 JavaScript (`static/js/tests/config.test.js`).

Documenté dans `ARCHITECTURE.md` (nouveau §15).
