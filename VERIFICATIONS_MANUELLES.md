# Vérifications manuelles de non-régression — interface web

> Refonte de l'interface (issue #625 et suivantes). **À rejouer par Alain après
> CHAQUE étape de la refonte.** Objectif : garantir qu'aucune étape ne change le
> comportement visible de l'interface. Tout écart = régression à corriger avant
> de poursuivre.
>
> Rappel : les tests automatiques de logique pure sont séparés —
> `node --test static/js/socle/tests/` (voir `static/js/socle/tests/README.md`)
> et `node --test static/js/tests/` (modules de fonctionnalité sortis d'app.js,
> ex. `onglets.js`, issue #626). Cette liste couvre ce que les tests ne peuvent
> pas voir (DOM, réseau, rendu).

## Préparation

- [ ] `python3 new_issue.py` démarre sans erreur, le navigateur s'ouvre.
- [ ] La page s'ouvre sur l'onglet **Résultats** (issue #626, étape 2) ; ordre
      des onglets : Résultats, Résultats inbox, Journal watcher, Configuration,
      CCW, Nouvelle issue.
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

## Onglet « Résultats »

- [ ] La liste des issues **apparaît** (rendu immédiat depuis le cache puis
      rafraîchissement de fond, indicateur « Mise à jour… »).
- [ ] L'issue créée ci-dessus **apparaît dans Résultats** après traitement.
- [ ] Filtres par projet : activer/désactiver ; bouton « Tous » ; pastilles de
      notification correctes ; état conservé après rechargement.
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
      (modale d'interruption : étapes détaillées + rappel de relance watcher).
- [ ] Badges de temps restant / estimation présents et cohérents.

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
