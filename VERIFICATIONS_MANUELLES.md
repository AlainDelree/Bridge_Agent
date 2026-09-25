# Vérifications manuelles de non-régression — interface web

> Refonte de l'interface (issue #625 et suivantes). **À rejouer par Alain après
> CHAQUE étape de la refonte.** Objectif : garantir qu'aucune étape ne change le
> comportement visible de l'interface. Tout écart = régression à corriger avant
> de poursuivre.
>
> Rappel : les tests automatiques de logique pure sont séparés —
> `node --test static/js/socle/tests/` (voir `static/js/socle/tests/README.md`).
> Cette liste couvre ce que les tests ne peuvent pas voir (DOM, réseau, rendu).

## Préparation

- [ ] `python3 new_issue.py` démarre sans erreur, le navigateur s'ouvre.
- [ ] **Console du navigateur** (F12) : aucune erreur rouge au chargement. On doit
      voir la trace discrète `[socle] briques chargées et inertes`.
- [ ] Recharger avec le cache vidé (Ctrl+Maj+R) une fois, puis normalement :
      la page se comporte identiquement.
- [ ] Onglet Réseau (F12) : les CSS et JS sont chargés avec un suffixe `?v=…`,
      `index.js` est servi en `text/javascript`, statut 200.
- [ ] **Une seule** connexion `/stream` et **une seule** `/events` dans l'onglet
      Réseau (pas de double connexion introduite par le socle).

## Onglet « Nouvelle issue » (création)

- [ ] Sélection d'un projet dans le bandeau : le libellé « Projet actif » et la
      couleur d'accent se mettent à jour ; dépôt/répertoire/périmètre affichés.
- [ ] Saisir un titre + un corps ; le résumé d'en-tête apparaît si `#Titre:`/
      champs détectés dans le corps.
- [ ] Changement de Mode (lecture / lecture active / écriture) : le bouton
      d'envoi reflète le mode (libellé/avertissement).
- [ ] **Créer une issue via le formulaire** → message de succès ; l'issue est
      bien créée sur GitHub.
- [ ] Bouton « Aperçu de la commande » affiche l'aperçu.
- [ ] Templates : charger un template pré-remplit le formulaire ; créer /
      modifier / supprimer un template fonctionne.
- [ ] Pièce jointe image : formats/limite affichés ; joindre une image insère
      l'URL dans le corps.
- [ ] Bouton « Vider » réinitialise le formulaire.

## Onglet « Résultats » (piloté par le store + SSE depuis l'issue #627)

- [ ] La liste des issues **apparaît** au PREMIER affichage de l'onglet
      (indicateur « Mise à jour… » pendant le chargement initial).
- [ ] **Chargement à la demande** (onglet Réseau F12) : quitter puis revenir sur
      Résultats ne déclenche **AUCUN** appel `/issues-liste` ni
      `/issues-en-attente` (plus de rechargement complet à l'activation). Seuls
      le PREMIER affichage, le bouton ↻ et les événements SSE font des appels.
- [ ] L'issue créée ci-dessus **apparaît dans Résultats** après traitement,
      **sans ↻** (événement SSE).
- [ ] **Décompte TIMEOUT** : dès qu'une issue CCL est prise en charge par le
      watcher (ACK), son badge passe de « ⏳ en file » au décompte, **sans ↻**
      (événement `debut_issue` — vérifier qu'il ne reste PAS bloqué « en file »
      et qu'il n'affiche PAS à tort « dépassement déjà vérifié »).
- [ ] **Clôture** : à la fin d'une issue, sa ligne se met à jour (état final,
      arrêt du décompte) **sans ↻** (événement `fin_issue`).
- [ ] **Une seule** connexion `/stream` dans l'onglet Réseau (jamais deux),
      présente même hors de l'onglet Résultats.
- [ ] **Échec d'un projet** : si un `/issues-liste/<projet>` échoue, ses issues
      **restent affichées** (données précédentes conservées) et un **toast**
      d'erreur apparaît — jamais de disparition silencieuse.
- [ ] Bouton ↻ : recharge liste + décompte ; la limite « par projet : N » saisie
      juste avant s'applique bien au clic sur ↻ (et pas à la frappe).
- [ ] Filtres par projet : activer/désactiver ; bouton « Tous » ; pastilles de
      notification correctes ; état conservé après rechargement (F5).
- [ ] Clic sur une ligne → **détail** de l'issue s'affiche (badges, corps,
      commentaires, réponse CCL).
- [ ] Onglets Réponse / Diff du détail ; le Diff se charge.
- [ ] **Copie** : « Copier résumé », « Copier tout », badges ✅ / Diff / All.
- [ ] **Cochage** d'un résultat (case à gauche) : la ligne passe en « traité »
      (barré + fond) ; état conservé après rechargement.
- [ ] Redimensionnement de la colonne titre : largeur mémorisée.
- [ ] Recherche par titre : la fenêtre de résultats s'ouvre, double-clic affiche
      le détail dans sa propre zone.
- [ ] Actions sur une issue ouverte : annuler / fermer / interrompre / relancer
      (modale d'interruption : étapes détaillées + rappel de relance watcher) —
      la liste se rafraîchit après l'action.
- [ ] Badges de temps restant / estimation présents et cohérents (compte à
      rebours qui décroît chaque seconde ; « dépassement » figé à zéro puis
      vérification unique 15 s après — jamais de polling).

## Panneau latéral (Infrastructure)

- [ ] Bouton « 📊 Infrastructure » ouvre/ferme le panneau ; ouvert par défaut à
      l'entrée dans l'onglet (sauf écran étroit).
- [ ] Zone monitoring : une ligne par watcher CCL / service CCW.
- [ ] Interrupteur son (Plat / Cloche) : bascule ; « Tester le son » actif
      seulement quand une ligne est sélectionnée ; joue la tonalité du projet.
- [ ] Zone extras : contrôle du watcher spool (issues_inbox) — démarrer/arrêter
      avec la modale de durée.
- [ ] Zone actions contextuelles : toggles notif_pc/gsm/tous sur l'issue
      sélectionnée.

## Onglet « Résultats inbox »

- [ ] Badge 🚨 sur l'onglet **uniquement** si des fichiers sont dans
      `issues_inbox/rejected/` (visible même hors de cet onglet).
- [ ] Tableau des fichiers rejetés + historique du log ; bouton « Rafraîchir ».

## Onglet « Journal watcher »

- [ ] Sélectionner un projet avec watcher actif : le terminal streame le log en
      direct (SSE), lignes colorées.
- [ ] Bouton « Vider l'affichage ».

## Onglet « Configuration »

- [ ] Identité (lecture seule) affichée ; paramètres éditables chargés.
- [ ] Curseurs Tonalité du bip / Tâches en parallèle : valeur suivie ; « Tester
      le son » joue la tonalité.
- [ ] « Enregistrer » et « Enregistrer et relancer » fonctionnent.
- [ ] Zone dangereuse : « Supprimer ce projet… » ouvre la modale (checklist +
      confirmation par saisie du nom).

## Onglet « Watchers »

- [ ] Tableau des watchers ; cases à cocher + « tout cocher ».
- [ ] Actions Lancer / Relancer / Éteindre ; compteur de sélection.

## Onglet « CCW »

- [ ] Liste des projets CCW (Rafraîchir) ; état des services.
- [ ] Ajouter un projet ; finaliser un projet (tokens masqués + œil).
- [ ] Actions redémarrer/démarrer/arrêter ; nettoyer les verrous ; sortie
      terminal des scripts distants.

## Nouveau projet

- [ ] Bouton « + Nouveau projet » ouvre la modale ; validations nom/dépôt/
      couleur ; création ; rappels git ; bootstrap CCW le cas échéant.

## Bandeaux globaux et cycle de vie

- [ ] Widget rate-limit GitHub (⚡) présent dans l'entête, couleur selon le quota,
      rafraîchi (~30 s).
- [ ] Bandeau éval Windows (si échéance proche) et bandeau repli REP_TRAVAIL
      (si tâche mode_write hors worktree) s'affichent sur tous les onglets.
- [ ] **Bouton « Quitter »** : demande confirmation, arrête le serveur, l'overlay
      « Serveur arrêté » s'affiche.
- [ ] Couper le serveur (Ctrl+C) : l'overlay d'arrêt apparaît côté navigateur.
- [ ] Déconnexion (mode `--externe`) redirige vers le login.

## Modes de lancement

- [ ] **Local** (`python3 new_issue.py`) : tout ce qui précède OK.
- [ ] **`--lan`** (`python3 new_issue.py --lan`) : accès depuis un autre appareil
      du réseau local ; interface identique ; modules servis (statut 200,
      `text/javascript`).
- [ ] **`--externe`** (HTTPS + login) : après connexion, interface identique ;
      modules et CSS chargés en HTTPS ; **session expirée** → la page redirige
      vers le login mais les fichiers statiques restent servis (pas d'erreur MIME
      de module).
