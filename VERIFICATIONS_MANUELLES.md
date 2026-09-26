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
      des onglets : Résultats, Journal watcher, Configuration, CCW, Nouvelle
      issue (l'onglet « Résultats inbox » a été supprimé — issue #639).
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
- [ ] **Badge « en file » stable dès la création** (issue #634) : déposer une
      issue via `issues_inbox/` (ou le formulaire) — la ligne apparaît avec
      « ⏳ en file » **immédiatement**, avec ses **vrais labels** (pas de case
      décochée le temps d'une clôture — voir aussi le panneau latéral,
      ci-dessous) et son **estimation** (si l'historique en fournit une) dès
      l'apparition. Le badge **ne doit JAMAIS disparaître** entre la création
      et la prise en charge par le watcher (`debut_issue`), même en observant
      plusieurs secondes — onglet Réseau (F12) : **aucun** appel
      `/issues-en-attente` déclenché par cette apparition (seuls le premier
      affichage, ↻, `debut_issue` et `fin_issue` en déclenchent).
- [ ] **Décompte TIMEOUT** : dès qu'une issue CCL est prise en charge par le
      watcher (ACK), son badge passe de « ⏳ en file » au décompte, **sans ↻**
      (événement `debut_issue` — vérifier qu'il ne reste PAS bloqué « en file »
      et qu'il n'affiche PAS à tort « dépassement déjà vérifié »).
- [ ] **Clôture** : à la fin d'une issue, sa ligne se met à jour (état final,
      arrêt du décompte) **sans ↻** (événement `fin_issue`).
- [ ] **Badge « modèle forcé »** (issue #638) : créer une issue avec
      `| MODELE | claude-opus-4-8 |` sur un projet dont le défaut est Sonnet →
      sa ligne dans Résultats porte un **badge discret « opus »** (entre le titre
      et les badges de temps, sans les recouvrir), visible aussi après clôture.
      Une issue **sans** champ `MODELE`, ou avec le **modèle par défaut** du
      projet, n'affiche **rien de plus** qu'avant. Une valeur `MODELE` invalide
      (ex. `gpt-5`) n'affiche **aucun** badge et ne casse pas la ligne. Le badge
      apparaît aussi dans la **fenêtre de recherche par titre** (même rendu de
      ligne).
- [ ] **Badge « modèle forcé » dès « en file », via `issues_inbox/`** (issue
      #640) : déposer une issue avec `| MODELE | claude-opus-4-8 |` dans
      `issues_inbox/` sur un projet dont le défaut est Sonnet — le badge
      « opus » doit être visible **dès l'apparition de la ligne** (« ⏳ en
      file »), **sans ↻ ni changement d'onglet**. Puis observer la **prise en
      charge** par le watcher (`debut_issue`) : le badge doit **rester
      affiché** (ou apparaître s'il ne l'était pas encore) **sans ↻**, la ligne
      n'étant PAS reconstruite à ce moment (seuls les badges de temps le sont
      normalement — vérifier par ex. que la sélection/case cochée de la ligne
      n'est pas perdue).
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
- [ ] **Cochage** d'un résultat (case à gauche, issue #636 — état SERVEUR) : la
      ligne passe en « traité » (barré + fond) ; **cocher copie fiablement le
      rapport complet (réponse + diff)** de cette issue dans le presse-papier
      (toast de succès), **décocher ne copie rien**. L'état est conservé après
      **F5** ET après **fermeture/réouverture du navigateur** ET **identique en
      localhost et en `--lan`** (les deux adresses lisent le même état serveur) ;
      il survit à un redémarrage du PC. En cas d'échec de copie : **jamais de faux
      succès** — un toast d'erreur (qui disparaît seul, aucune boîte « OK »).
- [ ] **Copie en localhost / HTTPS** (contexte sécurisé) : cocher une case ou
      cliquer ✅/Diff/All copie bien le contenu attendu, **sans échec
      intermittent** (la copie est engagée au clic, pas après le fetch réseau).
- [ ] **Copie en `--lan`** (HTTP non-localhost, API presse-papier moderne
      absente) : lancer `python3 new_issue.py --lan`, ouvrir depuis une autre
      machine via `http://<ip>:5100`. Cocher une case copie quand même le rapport
      (repli `execCommand`, texte préchargé) ; au tout premier clic sur une issue
      dont le texte n'est pas encore préchargé, un toast « préparation en cours »
      peut apparaître — un second clic aboutit. **Jamais de faux succès.**
- [ ] **Migration du localStorage** (issue #636, à faire UNE fois sur un
      navigateur ayant déjà des coches d'avant #636) : avant mise à jour, cocher
      quelques résultats (anciennes clés `resultat-coche:*`). Après mise à jour +
      rechargement : les mêmes lignes restent cochées (reprise serveur), et les
      clés `resultat-coche:*` ont disparu du `localStorage` (DevTools →
      Application). Rejouer un rechargement ne recrée rien (idempotent).
- [ ] **Pastilles ↔ « Cocher tout »** (issue #636) : avec plusieurs projets
      chargés, cliquer **« ✓ Cocher tout »** → **aucune pastille des projets
      actifs (filtrés) ne reste** (même après une longue coupure). Le périmètre
      coché est celui des pastilles (N premières issues par projet), y compris
      ouvriers et issues hors quota d'affichage. Ne déclenche aucune copie.
- [ ] **Bouton « ⊘ Tout à zéro »** (issue #636), à côté de « Cocher tout » :
      demande une **confirmation légère** (toast de confirmation) ; une fois
      confirmé, **toutes** les pastilles de **tous** les projets (même non
      filtrés) tombent à zéro. **Ne déclenche AUCUNE copie** presse-papier. État
      persisté côté serveur (survit à F5 et changement de navigateur).
- [ ] **Largeur de la liste** (issue #633) : à zoom 100 % sur un écran large,
      panneau latéral **ouvert**, la liste retrouve au moins la largeur qu'elle
      avait avant #628 (plus de colonne étriquée par le panneau). Aucune ligne
      ne déborde de la liste **quelle que soit sa largeur de fenêtre**, panneau
      ouvert ou fermé : le titre s'ellipse (…), les badges de fin de ligne
      (temps restant, estimation, ✅/Diff/All) restent **toujours entièrement
      visibles sans défilement horizontal**. Le redimensionnement manuel de la
      colonne titre (issue #95, poignée avant le titre) a été **entièrement
      retiré** (issue #633, se déclenchait par accident et provoquait
      justement ce défilement) — plus de poignée, et une largeur mémorisée par
      un ancien navigateur ne doit plus avoir aucun effet après rechargement.
- [ ] Recherche par titre : la fenêtre de résultats s'ouvre, double-clic affiche
      le détail dans sa propre zone.
- [ ] Actions sur une issue ouverte : annuler / interrompre / relancer / fermer
      (modale d'interruption : étapes détaillées + rappel de relance watcher) —
      la liste se rafraîchit après l'action. Depuis l'issue #628, Interrompre /
      Retirer needs-human / Fermer définitivement ne sont **plus** dans le détail
      (déplacés dans le panneau latéral, puis sur la ligne — voir ci-dessous et
      §« Actions directes sur la ligne ») — ne doivent apparaître **qu'une seule
      fois**.
- [ ] **Actions directes sur la ligne (issue #641, refonte web étape 6 ;
      correctif #642)** : sur une ligne **OUVERTE** portant `needs-human`, le
      badge **⚠️** est cliquable (curseur, léger fond au survol, infobulle
      **« Retirer needs-human et relancer »**) — cliquer retire directement le
      label et relance **sans sélectionner l'issue ni ouvrir le panneau** (même
      route `/relancer-issue`, même confirmation que l'ancien bouton « Retirer
      needs-human » du panneau). Sur une ligne ouverte en `mode_write`, le
      préfixe **✏️** est désormais **purement informatif** (issue #642 —
      correctif de la régression #641) : infobulle **« Mode écriture en
      cours »**, **plus aucun clic**, curseur normal. Une ligne ouverte sans
      ces labels garde son préfixe **○**/**✅** statique, non cliquable. Une
      ligne **FERMÉE** — y compris fermée+`done`+`needs-human` (cas rare) —
      garde le préfixe statique inchangé et les badges ✅/Diff/All habituels,
      jamais d'action cliquable.
- [ ] **Icône dédiée d'interruption, en LECTURE comme en ÉCRITURE (issue
      #642)** : sur toute ligne **OUVERTE** dont l'issue est actuellement **EN
      COURS** (même état que le décompte ⏳ affiché à droite — pas « en
      file »), un petit carré **VERT « ✓ »** apparaît après le préfixe/⚠️/✏️,
      **que l'issue soit en LECTURE (aucun label mode_write) ou en ÉCRITURE**.
      Survoler le carré le fait passer au **ROUGE « ✕ »** (infobulle
      **« Interrompre l'issue »**) ; cliquer déclenche la **même confirmation
      détaillée + même modale de résultat** que l'ancien bouton « Interrompre
      l'issue » du panneau (même route `/interrompre`) — le clic **ne
      sélectionne pas** la ligne (`stopPropagation`). Vérifier concrètement
      qu'une issue en **LECTURE** en cours peut être interrompue **seule**
      depuis sa ligne, **sans** passer par « Interrompre et relancer (watcher
      CCL) » et **sans** arrêter le reste du watcher (les autres issues du
      projet restent en file, pas relancées). Le carré est **absent** pour une
      issue « en file » (pas encore prise en charge, badge ⏳ « en file ») et
      pour une issue **needs-human** (déjà arrêtée — seule l'action ⚠️
      s'applique). Une ligne **FERMÉE** n'affiche jamais ce carré.
- [ ] **Son de cette issue, sur la ligne (déplacé du panneau, issue #641)** :
      toute ligne **ouverte** porte, après le badge d'action, un mini contrôle
      à 3 lettres **G / P / C** (Global / Plat / Cloche), une seule active à la
      fois, avec infobulle au survol de chacune. L'option active reflète l'état
      serveur (`GET /son-issue/<projet>`, **une seule requête par projet** au
      premier rendu d'une ligne de ce projet — onglet Réseau, F12 : jamais une
      requête par ligne). Cliquer P ou C bascule **immédiatement** (optimiste)
      et envoie un `POST /son-issue/<projet>/<numéro>` sans sélectionner la
      ligne ; cliquer de nouveau la même option ou G revient au réglage global.
      Une ligne **fermée** n'affiche pas ce contrôle. Clôturer une issue mise
      en Plat/Cloche alors que le réglage global est sur l'autre timbre → le
      bip entendu correspond au choix de l'issue.
- [ ] Badges de temps restant / estimation présents et cohérents (compte à
      rebours qui décroît chaque seconde ; « dépassement » figé à zéro puis
      vérification unique 15 s après — jamais de polling), et **entièrement
      visibles à zoom 100 % dès l'affichage de la ligne, sans avoir à faire
      défiler la liste horizontalement** (y compris le badge de la dernière
      colonne d'une ligne, à côté du panneau latéral ouvert — issue #628,
      non-régression du panneau flottant qui les recouvrait ; issue #633,
      non-régression du défilement horizontal introduit par le
      redimensionnement de la colonne titre).
- [ ] **Aucun toast parasite pendant la suite de tests** (issue #635) : lancer
      `python3 -m pytest tests/` (ou un script `tests/test_xxx.py` isolé,
      ex. `test_worktree_parallelisation_337.py`) pendant que l'onglet
      Résultats est ouvert — **aucun** toast « mise à jour impossible » ni
      apparition/rafraîchissement de ligne pour un projet fictif
      (`test611par`, `test576max1`, etc.).
- [ ] **Anti-empilement des toasts** (issue #635) : provoquer plusieurs
      erreurs identiques en rafale (ex. couper le réseau puis déclencher
      plusieurs fois la même action en échec) — un seul toast reste affiché,
      avec un compteur « (×N) », au lieu de s'empiler à l'écran.

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
- [ ] **Jamais flottant** (issue #633) : le panneau ne doit **jamais** apparaître
      détaché de sa colonne (ex. plaqué en haut à gauche de la page) — à
      surveiller particulièrement au chargement de la page, au changement
      d'onglet et à l'ouverture/fermeture du panneau. À vérifier avec un
      rechargement complet (Ctrl+Maj+R, pas juste F5) pour écarter tout ancien
      CSS/JS caché en cache de navigateur.
- [ ] Zone monitoring : une ligne par watcher CCL / service CCW. **Plus aucune
      ligne « VM » et plus aucune requête `/ccw/vm-statut`** (onglet Réseau,
      F12) — route disparue côté serveur depuis #447 (issue #628).
- [ ] Interrupteur son (Plat / Cloche) : bascule ; « Tester le son » actif
      seulement quand une ligne est sélectionnée ; joue la tonalité du projet.
- [ ] Zone extras : contrôle du watcher spool (issues_inbox) — démarrer/arrêter
      avec la modale de durée.
- [ ] **Historique du watcher spool (issue #639)** : sous le contrôle du watcher
      spool, un repli discret **« Historique récent »** (`<details>` fermé par
      défaut) ; l'ouvrir affiche les dernières lignes de `logs/issues_inbox.log`
      (mêmes lignes qu'exposait l'ancien onglet « Résultats inbox », supprimé).
- [ ] Zone actions contextuelles sur l'issue sélectionnée : toggles
      notif_pc/gsm/tous, **Interrompre et relancer / Fermer l'issue**. Depuis
      l'issue #641 (refonte web étape 6), **Interrompre** (seul), **Retirer
      needs-human** et le contrôle **« 🔊 Son de cette issue »** (#637, étape
      7b) ne sont **plus** ici — déplacés sur la ligne de la liste (voir
      « Actions directes sur la ligne » de l'onglet Résultats ci-dessus) : un
      seul emplacement par action. « Interrompre et relancer » et « Fermer
      l'issue » restent les DEUX seules actions réseau propres à une issue
      encore présentes dans ce panneau (avec les toggles de notification).
- [ ] **Cases de notification conformes aux labels réels** (issues #633,
      #634) : pour une issue portant `notif_pc` (et/ou `notif_gsm`/
      `notif_tous`), la case correspondante est **cochée dès l'apparition de
      la ligne** — y compris pour une issue apparue par `creation_issue`
      (issues_inbox), **avant même** sa prise en charge par `debut_issue`
      (issue #634 : les labels réels arrivent dans l'événement de création
      lui-même, plus de fenêtre où la case serait décochée à tort), pas
      seulement au chargement initial/↻. Décocher/cocher depuis le panneau
      modifie bien le label GitHub réel.
- [ ] **Lien « Vérifier le service CCW de ce projet »** : n'apparaît **que**
      pour une issue portant le label `for-windows` — absent pour une issue
      for-linux (issue #633).
- [ ] Onglet Réseau (F12) : une seule requête `/watchers` toutes les ~30s au
      total (mutualisée entre le panneau et le bandeau orange « écriture
      directe dans REP_TRAVAIL », affiché sur tous les onglets en cas de
      repli — issue #628), pas deux pollings indépendants.

## Fusion « Résultats inbox » dans Résultats (issue #639)

L'onglet « Résultats inbox » **n'existe plus** : ses lignes vivent désormais
dans la liste Résultats, son badge est passé sur l'onglet Résultats, et son
historique dans le panneau latéral (voir plus haut).

- [ ] **L'onglet « Résultats inbox » a disparu** de la barre d'onglets.
- [ ] Badge 🚨 désormais sur l'onglet **Résultats** (pas d'ancien onglet inbox),
      **uniquement** tant qu'au moins un fichier est dans `issues_inbox/rejected/`
      (visible même quand un autre onglet est actif ; le polling
      `/issues-inbox/etat` tourne en continu, 7 s).
- [ ] **Dépôt d'un fichier valide** dans `issues_inbox/` → une ligne
      **« 📥 fichier reçu : <nom> »** apparaît **en tête** de la liste Résultats
      en quelques secondes (sans case à cocher ni badges de temps), puis se
      **transforme en ligne d'issue normale** une fois l'issue créée (pas de
      doublon).
- [ ] **Dépôt d'un fichier invalide** → la ligne « fichier reçu » (ou, si elle
      n'a pas eu le temps d'apparaître, directement une ligne) devient une
      **ligne rouge « ✕ fichier refusé : <nom> — <motif> »** ; le motif complet
      s'affiche au survol (`title`). Motif absent → repli
      « refusé, motif indisponible ».
- [ ] **Persistance après rechargement** : recharger la page (F5) alors qu'un
      fichier est encore dans `issues_inbox/rejected/` → la ligne rouge est
      **reconstituée** depuis `/issues-inbox/etat`. Corriger/retirer le fichier
      (il quitte `rejected/`) puis attendre un cycle de polling → la ligne rouge
      **disparaît** (purge). Les lignes « fichier reçu » **ne sont PAS**
      reconstituées au rechargement (éphémères).
- [ ] **Lot multi-blocs mixte** (un fichier contenant plusieurs blocs, certains
      valides, certains invalides) → chaque bloc créé devient sa **ligne d'issue**,
      chaque bloc refusé produit sa **propre ligne rouge distincte** ; aucune
      confusion entre elles.
- [ ] **Exclusion propre** : les lignes fichier reçu/refusé ne sont jamais
      comptées par les **pastilles** de filtre projet, jamais cochables (pas de
      case à cocher), ignorées par **« Cocher tout »**, **« Tout à zéro »** et le
      **filtre projet / quota d'affichage**, et ne portent pas de **badge modèle**.

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
