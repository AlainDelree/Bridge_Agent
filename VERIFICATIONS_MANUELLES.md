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
- [ ] **Console du navigateur** (F12) : aucune erreur rouge au chargement, et
      **aucun** avertissement `[pont] fonction ancienne introuvable`. On doit
      voir les traces discrètes `[socle] briques chargées (issue #625, étape 1).`
      puis onglets/Résultats/panneau/#632 (le socle n'est plus inerte depuis
      l'issue #626 : `[socle] briques chargées et inertes` est obsolète).
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
- [ ] Actions sur une issue ouverte : annuler / interrompre / relancer / fermer
      (modale d'interruption : étapes détaillées + rappel de relance watcher) —
      la liste se rafraîchit après l'action. Depuis l'issue #628, Interrompre /
      Retirer needs-human / Fermer définitivement ne sont **plus** dans le détail
      (déplacés dans le panneau latéral, voir ci-dessous) — ne doivent apparaître
      **qu'une seule fois**.
- [ ] Badges de temps restant / estimation présents et cohérents (compte à
      rebours qui décroît chaque seconde ; « dépassement » figé à zéro puis
      vérification unique 15 s après — jamais de polling), et **entièrement
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
      d'onglet (ex. Configuration), revenir sur Résultats → le panneau reste
      fermé (persistance localStorage). Idem ouvert → ouvert. Vérifier aussi
      après un rechargement complet de la page (Ctrl+Maj+R).
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
      directe dans REP_TRAVAIL », affiché sur tous les onglets en cas de
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
