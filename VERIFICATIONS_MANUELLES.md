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
- [ ] Actions sur une issue ouverte, dans le **détail** : annuler / interrompre
      et fermer (modale d'interruption : étapes détaillées + rappel de relance
      watcher). Depuis l'issue #628, Interrompre / Retirer needs-human / Fermer
      définitivement ne sont **plus** dans le détail (déplacés dans le panneau
      latéral, voir ci-dessous — ne doivent apparaître **qu'une seule fois**).
- [ ] Badges de temps restant / estimation présents et cohérents, **entièrement
      visibles à zoom 100 %** (y compris le badge de la dernière colonne d'une
      ligne, à côté du panneau latéral ouvert — issue #628, non-régression du
      panneau flottant qui les recouvrait).

## Panneau latéral (Infrastructure)

> Sorti d'`app.js` vers `static/js/panneau_lateral.js` par l'issue #628
> (refonte web étape 4) : colonne à côté de la liste (plus un overlay flottant),
> ne recouvre plus jamais la liste — y compris sur écran étroit, où elle passe
> sous la liste plutôt que de la recouvrir.

- [ ] Bouton « 📊 Infrastructure » ouvre/ferme le panneau ; **ouvert par défaut**
      la première fois (pas de fermeture automatique sur écran étroit : c'est la
      mise en page, pas l'état, qui s'adapte).
- [ ] **État conservé d'un onglet à l'autre** : fermer le panneau, changer
      d'onglet (ex. Watchers), revenir sur Résultats → le panneau reste fermé
      (persistance localStorage). Idem ouvert → ouvert. Vérifier aussi après un
      rechargement complet de la page (Ctrl+Maj+R).
- [ ] Panneau ouvert, écran large : la colonne panneau est **entièrement
      distincte** de la liste (jamais superposée), quel que soit le contenu de
      la liste.
- [ ] Écran étroit (< 900px, ou réduire la fenêtre) : la colonne panneau
      apparaît **sous** la liste (empilement vertical), jamais par-dessus.
- [ ] Zone monitoring : une ligne par watcher CCL / service CCW. **Plus aucune
      ligne « VM » et plus aucune requête `/ccw/vm-statut`** (onglet Réseau,
      F12) — route disparue côté serveur depuis #447 (issue #628).
- [ ] Interrupteur son (Plat / Cloche) : bascule ; « Tester le son » actif
      seulement quand une ligne est sélectionnée ; joue la tonalité du projet.
- [ ] Zone extras : contrôle du watcher spool (issues_inbox) — démarrer/arrêter
      avec la modale de durée.
- [ ] Zone actions contextuelles sur l'issue sélectionnée : toggles
      notif_pc/gsm/tous, **Interrompre / Interrompre et relancer / Retirer
      needs-human / Fermer l'issue** — ces 4 actions n'existent plus que dans
      cette zone (issue #628, retirées du détail qui faisait double emploi).
- [ ] Onglet Réseau (F12) : une seule requête `/watchers` toutes les ~30s au
      total (mutualisée entre le panneau et le bandeau orange « écriture
      directe dans REP_TRAVAIL », visible via l'onglet Watchers en cas de
      repli — issue #628), pas deux pollings indépendants.

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
