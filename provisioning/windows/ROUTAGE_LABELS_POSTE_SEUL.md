# ROUTAGE_LABELS_POSTE_SEUL — piège for-linux/for-windows sur un PC Windows seul (issue #866)

Issue #866, suite de l'audit de parité #862. Complète
`DEMARRAGE_SESSION_WINDOWS.md` (même dossier, issue #864) : ce document-ci
explique pourquoi les labels GitHub `for-linux`/`for-windows` ne doivent
**jamais** être confondus avec « quel OS fait tourner l'agent », et ce
qui se passe réellement si on s'y trompe sur un poste Windows **seul**
(pas de second poste CCW délégué).

## 1. Ce que les labels signifient réellement

`for-linux` et `for-windows` ne désignent **pas** une plateforme — ils
désignent **quel watcher** doit voir l'issue :

- `for-linux` → le watcher **local** du projet (`watcher.py --config
  configs\<nom>.conf`), qu'il tourne sous Linux (ThinkPad d'Alain) ou
  sous Windows natif (depuis #682, portable) ;
- `for-windows` → le service **CCW** : un second poste Windows,
  piloté à distance en SSH (ou en local sur la machine CCW elle-même,
  issue #717) via un service NSSM `CCW-Watcher-<projet>` dédié, installé
  par `ajouter_projet_ccw.ps1`/`provisionner.ps1` — **jamais** par
  `installer_demarrage_session.ps1` (#864).

Un poste Windows seul, provisionné via #864, n'a **que** des tâches de
session lançant `watcher.py` (filtré sur `LABEL=for-linux` par défaut
dans chaque `.conf`) + `watcher_issues_inbox.py` + `new_issue.py`. Il n'a
**aucun** service `CCW-Watcher-*`.

## 2. Le piège

Toute issue créée avec le label `for-windows` (champ `LABELS` du
formulaire web ou d'un fichier déposé dans `issues_inbox\`, rempli par
erreur, par habitude du canal CCW décrit au §16 de `BRIDGE_AGENT_DOC.md`,
ou directement par `gh issue create`) sur un poste Windows seul :

1. **n'est vue par aucun watcher local** — `watcher.py::lister_issues()`
   interroge `gh issue list --label <LABEL du .conf>`, et `LABEL` vaut
   `for-linux` par défaut (jamais `for-windows`, et cette clé ne doit
   jamais être modifiée à la main pour contourner le problème : règle
   §12 de `BRIDGE_AGENT_DOC.md`, aucune écriture dans `configs/*.conf`) ;
2. **déclenche une tentative de démarrage qui échoue silencieusement** —
   `app/ccw.py::demarrer_service_ccw_arriere_plan()` est appelé en
   arrière-plan (thread démon, non bloquant) et, sous Windows natif sans
   hôte SSH configuré, tente `nssm start CCW-Watcher-<projet>`
   **localement** (issue #717) : ce service n'existe pas sur ce type de
   poste, l'appel échoue (nssm absent du PATH, ou service inconnu). Cet
   échec n'est journalisé que côté serveur (journal de `new_issue.py`) —
   **jamais** en commentaire sur l'issue GitHub, **jamais** sous forme de
   notification bureau/push. Même limite, déjà documentée pour le cas
   SSH, en §14 de `BRIDGE_AGENT_DOC.md`.

Résultat : l'issue reste ouverte indéfiniment, sans qu'aucun signal
visible (bip, bulle, badge de l'onglet Résultats) n'indique que quelque
chose s'est mal passé.

La case **« Projet CCW »** de la modale de création de projet
(provisionnement automatique d'un **second** poste délégué, voir
`app/projet_ccw.py`) n'a elle non plus rien à faire sur un poste seul —
elle exige d'ailleurs deux tokens et une clé publique de bootstrap
récupérée en SSH, ce qui échoue proprement (message d'erreur explicite)
si aucun second poste n'est joignable ; ce n'est donc pas un piège
silencieux, juste une case à ne pas cocher. Depuis l'issue #870, le
réglage `MACHINE_SEULE` (voir §4 ci-dessous) la masque purement et
simplement, avec l'onglet « CCW » de la barre d'onglets — sans rien
changer au piège des labels décrit ci-dessus.

## 3. À faire aujourd'hui, sans aucun changement de code

- **Ne jamais** remplir le champ `LABELS` avec `for-windows` sur un poste
  seul — le laisser vide : `construire_labels()` pose alors `for-linux`
  par défaut, traité normalement par le watcher local.
- **Ne jamais** cocher « Projet CCW » à la création d'un projet sur un
  poste seul.
- Si une issue `for-windows` a été créée par erreur et reste bloquée :
  retirer le label `for-windows`, poser `for-linux` à la main (interface
  GitHub ou `gh issue edit --add-label for-linux --remove-label
  for-windows`), le watcher local la prendra en charge au cycle suivant
  (ou relancer son watcher depuis l'onglet Infrastructure si besoin).

## 4. Solution de fond, proposée mais non implémentée

Un réglage machine dans `identite_locale.conf` (racine du dépôt, hors
`configs/`, jamais committé — issue #859) indiquant que ce poste joue
**tous les rôles**, pour que les deux labels soient traités localement
sans SSH ni appel `nssm` distant. Comparée à deux autres pistes :

**Précision (issue #870)** : le nom `MACHINE_SEULE` évoqué ci-dessous a été
posé dans `identite_locale.conf`, mais seulement pour masquer l'onglet
« CCW » et la case « Projet CCW » décrits au §2 ci-dessus (interface web
uniquement) — PAS pour router les labels `for-linux`/`for-windows`. La
« solution de fond » décrite dans cette section (modifier
`watcher.py::lister_issues()` et les points de démarrage/relance cités en
(b) ci-dessous) reste entièrement non implémentée ; le piège du §2 reste
donc actif, seules les consignes du §3 y répondent pour l'instant.

- **(a) Documenter seulement** (ce document) : coût nul, mais le piège
  reste actif — un oubli (champ `LABELS` mal rempli par Claude Chat ou
  l'agent Vibe) redonne le même symptôme silencieux.
- **(b) Réglage machine `identite_locale.conf`** (retenue en principe) :
  cohérente avec le précédent #859, n'exige aucune modification de
  `configs/*.conf`, comportement par défaut strictement inchangé pour
  les deux machines d'Alain (absence du réglage). Mais une implémentation
  fidèle touche le cœur du polling GitHub de `watcher.py`
  (`lister_issues()`) ainsi que 4 autres points de démarrage/relance/
  interruption à la demande (`app/issues.py`, `scripts/
  watcher_issues_inbox.py` ×2, `app/interruption.py`) — trop de fichiers
  sensibles, utilisés en continu par les installations en production,
  pour l'issue #866 qui a produit ce document (aucune possibilité de
  test réel sous Windows depuis l'environnement de l'agent Linux). Voir
  l'issue #867 pour le détail exact de l'implémentation proposée.
- **(c) Nouveaux labels neutres** (déconseillée) : trop invasive —
  renommer ou dupliquer `for-linux`/`for-windows` casserait tout le code
  existant qui s'appuie sur ces deux noms exacts (`watcher.py`,
  `app/issues.py`, `app/interruption.py`, `app/notifications_poller.py`,
  `scripts/watcher_issues_inbox.py`...) pour un gain net identique à (b).

## 5. À valider à la main sur un vrai poste Windows seul

Ce qui précède est vérifié **par lecture du code** depuis un
environnement Linux (aucune exécution Windows possible ici). Une fois
l'issue #867 traitée, à tester manuellement sur le PC de l'ami d'Alain :

1. Créer une issue de test avec `LABELS` vide (donc `for-linux`) depuis
   le formulaire web local — vérifier qu'elle est bien prise en charge
   par le watcher du projet sans aucune intervention.
2. Créer une issue de test avec `| LABELS | for-windows |` — avant #867,
   constater le symptôme décrit au §2 (issue jamais prise en charge,
   rien dans les notifications, seulement une trace dans le journal de
   `new_issue.py` si on va le consulter) ; après #867, avec
   `MACHINE_SEULE` renseigné dans `identite_locale.conf`, vérifier
   qu'elle est désormais traitée comme une `for-linux`.
