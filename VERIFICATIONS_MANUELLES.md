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

> Depuis l'issue #652, tout ce formulaire vit dans `static/js/creation.js`
> (module ES sorti d'`app.js`), initialisé par import direct depuis `onglets.js`
> à la première ouverture de l'onglet ; les gestionnaires ne sont plus inline
> (`data-action="creation-*"` + délégation du socle). **Comportement attendu
> STRICTEMENT identique** — vérifier de bout en bout, notamment la première
> ouverture de l'onglet (l'initialisation est paresseuse).

- [ ] Sélection d'un projet dans le bandeau : le libellé « Projet actif » et la
      couleur d'accent se mettent à jour ; dépôt/répertoire/périmètre affichés ;
      la liste des **templates** du projet se recharge (appel `chargerTemplates`
      depuis `app.js` vers `creation.js`).
- [ ] Saisir un titre + un corps ; le résumé d'en-tête apparaît si `#Titre:`/
      champs détectés dans le corps.
- [ ] **Détection automatique à la frappe** (coller un corps avec un en-tête
      tabulaire) : `#Titre:` en 1re ligne → champ Titre ; `| PROJET | … |` →
      combobox projet (si connu, ligne retirée du corps) ; `| TIMEOUT | … |` →
      champ Timeout ; `| MODE | … |` → radio Mode. Une correction manuelle
      ultérieure du champ n'est pas réécrasée à la frappe suivante.
- [ ] **COMPLEXITE / REDACTEUR / ATTENTE collés dans l'en-tête (issue #884)** —
      coller EXACTEMENT ceci dans le champ Corps (projet `gestionstock`
      existant, sinon remplacer par un projet réel) :
      ```
      | PROJET     | gestionstock |
      | REDACTEUR  | gestionstock |
      | MODE       | écriture     |
      | COMPLEXITE | rapide       |
      | TIMEOUT    | 900s         |

      #Titre: Test manuel issue #884
      Corps de test, à ne pas envoyer pour de vrai (ou envoyer sur un projet
      de test et fermer l'issue créée ensuite).
      ```
      Vérifier dans l'ordre :
      1. le sélecteur **Complexité** passe sur `rapide` ;
      2. dans le champ Corps, les lignes `COMPLEXITE` ET `REDACTEUR` ont
         disparu (seules `PROJET`/`MODE`/`TIMEOUT` disparaissent déjà, comme
         avant) — il ne doit plus rester trace de `REDACTEUR` ni de
         `COMPLEXITE` dans le texte ;
      3. cliquer « Aperçu de la commande » (ou envoyer réellement sur un
         projet de test) : le corps final ne doit porter **qu'un seul**
         tableau `## En-tête`, avec **une seule** ligne `COMPLEXITE` (valeur
         `rapide`) et aucune ligne `REDACTEUR`.
      - Remplacer ensuite `| COMPLEXITE | rapide |` par
        `| COMPLEXITE | archi-vite |` (valeur invalide) et recoller : un
        toast discret doit apparaître (« Complexité « archi-vite » non
        reconnue… ») ; le sélecteur Complexité ne doit PAS changer ; la ligne
        doit quand même disparaître du corps.
      - Remplacer enfin par `| ATTENTE | après la release 2.0 |` (en plus du
        reste) : un toast clair doit apparaître (« Champ ATTENTE détecté …
        mais NON géré par ce formulaire… ») et la ligne `ATTENTE` doit
        **rester visible** dans le corps (contrairement à REDACTEUR/
        COMPLEXITE) — l'issue serait créée immédiatement si on l'envoyait.
      - Rejouer le même essai en **mode lot** (coller 2 blocs `#Titre:`, l'un
        avec `COMPLEXITE` valide, l'autre avec une valeur invalide) : le
        récapitulatif de fin de lot doit mentionner « COMPLEXITE non reconnue
        dans l'en-tête du bloc » pour le second bloc.
      - Cliquer « Vider » puis recoller un corps SANS aucun de ces champs :
        le sélecteur Complexité doit être revenu à `normal` (pas resté sur la
        valeur de l'essai précédent).
- [ ] Changement de Mode (lecture / lecture active / écriture) : le bouton
      d'envoi reflète le mode (couleur noir/bleu/rouge).
- [ ] **Créer une issue via le formulaire** → message de succès ; l'issue est
      bien créée sur GitHub. Anti-double-clic : le bouton se désactive pendant
      l'envoi. Modales de garde-fou : issues en attente sur le projet, et
      incohérence projet en-tête ⇄ sélection.
- [ ] Bouton « Aperçu de la commande » affiche l'aperçu.
- [ ] Templates : charger un template pré-remplit le formulaire ; créer (bouton
      « Créer le template ») / modifier (✏️) / supprimer (🗑️) un template
      fonctionne ; le toast de confirmation s'affiche.
- [ ] **Envoi en lot** : coller 2+ blocs `#Titre:` → le bouton devient « Envoyer
      le lot (N issues) sur … » (mentionne « plusieurs projets » / « modes
      mixtes » le cas échéant) ; l'envoi enchaîne les issues et affiche le
      récapitulatif (✓/✗ par bloc).
- [ ] Pièce jointe image : formats/limite affichés ; le bouton « Joindre une
      image » ne s'active qu'après choix d'un fichier ; joindre une image insère
      le lien `![…](url)` dans le corps.
- [ ] Case **Bureau (`notif_pc`)** : cochée par défaut ; si on la décoche, l'état
      est mémorisé et respecté à la réouverture (issue #93). « Vider » la remet à
      l'état mémorisé, pas décochée.
- [ ] Bouton « Vider » réinitialise le formulaire (titre, corps, priorité,
      timeout du projet, mode lecture, notifs, modèle, image, template
      désélectionné).
- [ ] **Dépôt cible** (`REPO_CIBLE`, issue #829) : sélectionner un projet à
      `PERIMETRE_DYNAMIQUE=true` affiche le champ obligatoire ; le sélectionner
      vers un projet à périmètre fixe le masque ET vide sa valeur. Envoyer sans
      le remplir (projet dynamique) → message clair, rien n'est créé. Envoyer
      avec un chemin invalide (relatif, inexistant) → même chose, avec la
      raison. Envoyer avec un chemin valide → l'issue créée porte bien la ligne
      `| REPO_CIBLE | <chemin> |` dans son en-tête sur GitHub.
- [ ] **Complexité** (`#complexite`, issue #848) : défaut « normal » ; un
      template enregistré avec une autre valeur la recharge correctement ; un
      ANCIEN template (créé avant #848) recharge « normal » sans erreur
      console. L'issue créée porte la ligne `| COMPLEXITE | <valeur> |` et
      **jamais** le label `sans-complexite`.
- [ ] **Bandeau d'audit** (`#audit-bandeau`, issue #848) : apparaît uniquement
      après un clic sur « Préparer l'audit » (onglet Configuration d'un autre
      projet) ; disparaît si on change le projet manuellement ensuite.

## Onglet Configuration — section Audit (issue #848)

- [ ] Projet sans template d'audit : section vide, message explicatif, bouton
      « Préparer l'audit » **désactivé** (avec titre explicatif au survol).
- [ ] Importer un fichier `.txt` valide (format `issues_inbox/`) : aperçu en
      lecture seule rempli (titre/mode/timeout/complexité/corps), bouton
      activé, aucun avertissement affiché.
- [ ] Importer un fichier **sans** ligne COMPLEXITE, ou avec une valeur non
      reconnue (ex. `moyen`) : avertissement visible, complexité retenue =
      `normal`.
- [ ] Importer un fichier avec `PROJET` ≠ `diagnostique_programme` et/ou
      `REPO_CIBLE` ≠ le dossier de travail de ce projet : avertissement
      visible nommant la valeur ignorée, import quand même accepté.
- [ ] Réimporter un fichier alors qu'un template existe déjà : confirmation
      demandée avant remplacement ; annuler la confirmation laisse l'ancien
      template intact.
- [ ] Bouton « 🗑 Supprimer le template d'audit » : confirmation, puis retour à
      l'état vide (bouton « Préparer l'audit » redésactivé).
- [ ] **Préparer l'audit** : bascule sur l'onglet « Nouvelle issue », projet
      actif = `diagnostique_programme` (bandeau de couleur + libellé à jour),
      formulaire pré-rempli avec le texte d'audit, Dépôt cible = `REP_TRAVAIL`
      **Linux** (pas le chemin Windows) du projet audité, complexité du
      template. Bandeau visible nommant le projet audité et
      `diagnostique_programme`. Aucun envoi automatique — vérifier le contenu
      puis cliquer soi-même sur « Envoyer ».
- [ ] **Cas particulier** : « Préparer l'audit » depuis la Configuration de
      `diagnostique_programme` lui-même — Dépôt cible = son propre
      `REP_TRAVAIL`, envoi accepté normalement (périmètre fixe, §7 du DOC).

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
- [ ] **Badge « sans REDACTEUR »** (issue #647) : déposer dans `issues_inbox/`
      une issue **sans** champ `REDACTEUR` dans l'en-tête → sa ligne dans
      Résultats porte un **badge discret ambré** (infobulle « Créée sans
      REDACTEUR »), sans **rien bloquer** — l'issue se crée normalement. Une
      issue indiquant `| REDACTEUR | <projet> |` **cohérent** avec `PROJET`
      n'affiche **rien de plus** qu'avant. Une issue avec `REDACTEUR`
      **incohérent** (autre projet) reste **rejetée** vers `rejected/` comme
      avant #647 (aucune issue créée, donc aucun badge à vérifier pour ce cas).
      Le badge doit apparaître **dès l'apparition de la ligne** (« ⏳ en
      file »), sans ↻.
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
      absente, mot de passe obligatoire depuis #831) : lancer `python3
      new_issue.py --lan`, ouvrir depuis une autre
      machine via `http://<ip>:5100`. Cocher une case copie quand même le rapport
      (repli `execCommand`, texte préchargé) ; au tout premier clic sur une issue
      dont le texte n'est pas encore préchargé, un toast « préparation en cours »
      peut apparaître — un second clic aboutit. **Jamais de faux succès.**
- [ ] **Copie dans Firefox, préparation à l'avance en mode moderne (issue
      #832, chemin rapide conservé par #858)** : ouvrir l'onglet Résultats
      dans **Firefox** sur `http://localhost` (mode moderne, pas `--lan`),
      attendre la fin du chargement de la liste (laisser passer quelques
      secondes pour le préchargement en tâche de fond), puis cocher la case
      d'une issue **dont le rapport compte plusieurs commits** : la copie
      doit être **immédiate**, **sans la fenêtre rouge** d'échec (le texte
      était déjà préparé avant le clic).
- [ ] **Préparation lente SANS préchargement, dans le geste du clic (issue
      #858)** : juste après avoir **rechargé la page** (cache de l'onglet
      vidé, rien n'a encore eu le temps d'être préchargé), cocher
      IMMÉDIATEMENT la case d'une issue dont le rapport n'est manifestement
      pas encore préchargé (idéalement un rapport volumineux, plusieurs
      commits, pour que la préparation prenne sciemment **plus de 10
      secondes**) : contrairement au comportement d'avant cette issue
      (jusque-là, le geste expirait et une fenêtre rouge « Préparation trop
      longue pour le presse-papier » apparaissait, issue #832 point 4),
      **aucune fenêtre rouge ne doit apparaître**, même en attendant
      longtemps. Une fois la préparation terminée (patienter, puis **coller
      avec Ctrl+V** dans un éditeur) : le rapport complet doit être présent.
      C'est le point établi par cette issue : l'écriture presse-papier est
      désormais engagée DANS le geste du clic, le contenu pouvant arriver
      après coup quelle que soit sa durée — comme c'était déjà le cas avant
      l'issue #782. Si une fenêtre rouge apparaît malgré tout, l'hypothèse de
      cette issue (que Firefox accepte réellement un contenu différé après
      plusieurs secondes) ne tient pas en pratique : à signaler.
- [ ] **Plusieurs cases cochées très vite, sans vouloir leur rapport (issue
      #858 point 3)** : cocher 2 ou 3 cases d'affilée très rapidement (comme
      pour simplement barrer des issues sans intention de copier leur
      rapport) : **aucune fenêtre rouge ni aucun message d'échec** ne doit
      apparaître pour les cases cochées en premier (abandon silencieux) —
      seul le rapport de la DERNIÈRE case cochée doit se retrouver dans le
      presse-papier (coller pour vérifier).
- [ ] **Vidage immédiat du presse-papier au clic, dans Firefox (issue #857,
      PUIS correctif de l'issue #865)** : CAUSE établie par #865 — jusque-là,
      le vidage (chaîne vide) et l'écriture du rapport (contenu différé)
      étaient engagés l'un après l'autre SANS ATTENDRE la fin du premier ;
      Firefox annule une écriture encore pendante dès qu'une nouvelle est
      lancée avant qu'elle n'aboutisse (constat de #782), si bien que le
      vidage était TOUJOURS annulé par l'écriture du rapport qui le suivait,
      AVANT d'avoir pu remplacer l'ancien contenu — l'ancien rapport restait
      donc en place pendant toute la préparation. Depuis #865, `lancerCopie`
      ATTEND la fin réelle du vidage avant d'engager l'écriture du rapport.
      Prouvé par les tests JS (modèle du presse-papier réel, avec annulation
      simulée) : le vidage se termine bien AVANT que le rapport ne soit
      engagé, et le contenu réel ne contient jamais l'ancien rapport pendant
      la préparation, ni en cas d'échec. NON prouvable sous Node, à vérifier
      à la main (voir essai ci-dessous) : que Firefox se comporte réellement
      comme modélisé (annulation d'une écriture pendante par une plus
      récente, mise à jour différée jusqu'à résolution du contenu), et que
      le délai introduit par l'attente du vidage (quelques millisecondes)
      ne fait pas sortir l'écriture du rapport de la fenêtre d'activation du
      clic.
      **Essai précis** : copier un texte quelconque ailleurs (Ctrl+C) pour
      avoir un « ancien contenu » reconnaissable dans le presse-papier.
      Recharger la page (cache de l'onglet vidé, rien n'a encore eu le temps
      d'être préchargé), puis dans l'onglet Résultats cocher la case d'une
      issue dont le rapport n'est manifestement pas encore préchargé.
      **Coller (Ctrl+V) immédiatement dans un éditeur de texte, le plus vite
      possible après le clic** : le résultat attendu est **vide** (ou un
      simple espace) — JAMAIS l'ancien texte copié avant. Attendre quelques
      secondes (fin de la préparation), puis **coller de nouveau** dans le
      même éditeur : le rapport complet de l'issue cochée doit apparaître
      cette fois. Si l'ancien contenu ressurgit au premier collage, le
      correctif de #865 ne suffit pas en pratique (hypothèse de ce correctif
      invalidée) : à signaler avec le délai observé entre le clic et le
      collage.
- [ ] **Repère « prêt à copier » et périmètre/ordre de la précharge (issue
      #835)** : sur une issue non cochée dont le texte est déjà préparé et
      valide, un petit repère (pastille à contour vert `✓`) apparaît juste
      après la case (info-bulle « Rapport prêt : la copie sera immédiate ») ;
      cocher la case fait **disparaître le repère immédiatement**. Désélectionner
      la pastille d'un projet (filtre) : les issues de ce projet **ne sont plus
      préparées** (aucun nouveau repère n'y apparaît) ; les re-sélectionner
      relance leur préparation. Avec plusieurs projets sélectionnés et
      plusieurs issues en attente de préparation, **les plus anciennes doivent
      obtenir leur repère avant les plus récentes** (observable en rechargeant
      la page avec le réseau ralenti dans les DevTools, pour voir les repères
      apparaître un par un dans cet ordre).
- [ ] **Issue « en cours » exclue de la précharge et du repère (issue #838)** :
      une issue **ouverte** et **sans label `needs-human`** (ex. un ouvrier en
      cours d'exécution côté watcher) ne reçoit **jamais** le repère « prêt à
      copier », même après avoir laissé passer largement le temps de
      préchargement — et aucune requête `/issue` ne doit être faite pour elle
      en tâche de fond (vérifiable dans l'onglet Réseau des DevTools). À sa
      **clôture** (ou dès qu'elle reçoit le label `needs-human`), le repère
      apparaît **après** la préparation qui suit (quelques secondes, le temps
      du prochain cycle de précharge) — sans action manuelle. Une issue
      **ouverte** qui porte déjà le label `needs-human` (échec avec rapport
      posté) est, elle, **normalement préparée** : son repère apparaît comme
      pour une issue fermée.
- [ ] **Précharge qui continue page cachée, texte qui tient le temps du retour
      (issue #839)** : dans **Firefox**, ouvrir l'onglet Bridge Agent (onglet
      Résultats), puis ouvrir et activer un **autre onglet** du navigateur.
      Laisser une issue se terminer (clôture ou label `needs-human`) pendant
      que l'onglet Bridge Agent est **caché**. Attendre **plusieurs minutes**
      (plus que les trois minutes de l'ancienne durée de validité, pour
      vérifier que la nouvelle durée d'une heure tient), puis revenir sur
      l'onglet Bridge Agent : le repère « prêt à copier » est **déjà affiché**
      sur la ligne de l'issue dès le retour (pas d'attente supplémentaire), et
      cocher sa case copie **immédiatement**, sans la fenêtre rouge
      « Préparation trop longue ». Dans `logs/charge_interface.log` (mesure de
      précharge, issue #835 point 4), une série de préparation apparaît à
      l'**heure de la clôture** de l'issue — pas seulement à l'heure du retour
      sur l'onglet.
- [ ] **Clic sans effet juste après la fin d'une issue, en plein redessin de
      sa ligne (issue #878, situation 1)** : CAUSE établie par relecture du
      code — `remplacerLigneIssue` (déclenchée par l'événement `/stream`
      `fin_issue`) détruisait et reconstruisait intégralement le nœud DOM de
      la ligne (donc de sa case), **sans aucune garde**, contrairement à
      `restaurerCasesCocheesResultats` qui protège déjà (issues #462/#463) la
      case sur laquelle l'utilisateur est **en train d'agir** (focus posé par
      le navigateur au `mousedown`, avant `click`/`change`). Corrigé en
      étendant cette même garde : la reconstruction est désormais **différée**
      au `focusout` de la case plutôt qu'exécutée en plein geste. **Prouvé
      sous Node** (`static/js/tests/app_redessin_878.test.js`) que la ligne
      n'est plus détruite tant que sa case a le focus, et qu'elle est bien
      reconstruite une fois le focus parti — **NON prouvable sous Node** (pas
      de vrai moteur d'événements souris) : que Firefox livre réellement
      `click`/`change` à la case d'une ligne qui vient d'être redessinée
      JUSTE AVANT le `mousedown` (ce correctif ne protège QUE la fenêtre
      après le `mousedown` — avant, remplacer la ligne est sans risque, la
      nouvelle case reçoit alors normalement le geste).
      **Essai précis** : lancer une issue dont on sait qu'elle va se
      terminer dans les secondes qui suivent (ex. une issue `rapide` déjà en
      cours côté watcher), rester sur l'onglet Résultats, et cliquer **le
      plus vite possible** sur la case de cette issue dès qu'elle passe à
      l'état fermé/terminé (répéter l'essai une dizaine de fois, en visant
      des instants de clic légèrement différents par rapport au moment du
      redessin). Résultat attendu à chaque fois : soit le clic copie bien le
      rapport (toast de succès, presse-papier à jour), soit — si le clic est
      arrivé sur l'ANCIENNE case juste avant son remplacement — la case
      reste décochée et un second clic, immédiatement après, aboutit
      normalement. **Jamais** un clic qui ne coche ni ne copie SANS qu'un
      second clic immédiat ne corrige la situation.
- [ ] **Clic sans effet au premier retour sur l'onglet après une longue
      inactivité (issue #878, situation 2)** : CAUSE établie par relecture du
      code — un retour au premier plan après ≥30 s de masquage
      (`SEUIL_RESYNC_MASQUAGE_MS`, static/js/resultats.js) OU une
      reconnexion du flux `/stream` après coupure déclenchent tous deux
      `resynchroniserResultatsAuRetour` → `rendreListeIssues`, qui
      reconstruisait **toute** la liste (donc **toutes** les cases) sans
      aucune garde. Même correctif que la situation 1, appliqué cette fois à
      la liste entière : la reconstruction complète est différée tant qu'une
      case a le focus. **Essai précis** : ouvrir l'onglet Résultats dans
      **Firefox**, puis basculer sur un **autre onglet/une autre fenêtre**
      et y rester **plus de 30 secondes** (le plus simple : plusieurs
      minutes, pour laisser aussi le temps à une éventuelle coupure/
      reconnexion du flux `/stream` en arrière-plan). Revenir sur l'onglet
      Bridge Agent et cliquer **IMMÉDIATEMENT**, sans attendre, sur la case
      de la première issue visible. Résultat attendu : le clic coche et
      copie normalement (toast de succès) — si un premier clic reste sans
      effet (case non cochée, pas de toast), un second clic immédiatement
      après doit, lui, aboutir.
      **Si `DIAGNOSTIC_COPIE` est activé** (voir ci-dessous) : relever, pour
      chacun des deux essais, la ou les lignes `logs/diagnostic_copie.log`
      correspondant aux clics faits — en particulier `etatSse`,
      `depuisDernierEvenementSse` et `ligneRedessineeRecemment` — et les
      joindre à un commentaire sur l'issue si un clic reste malgré tout sans
      effet après ce correctif.
      **Activer le journal de diagnostic (issue #878)** : ajouter
      `DIAGNOSTIC_COPIE = oui` dans `identite_locale.conf` (racine du
      dépôt, créer le fichier s'il n'existe pas — voir `identite.py` pour le
      format), puis relancer `python3 new_issue.py`. DÉSACTIVÉ PAR DÉFAUT :
      sans ce réglage, aucun fichier n'est créé et rien n'est envoyé au
      serveur. Une fois activé, chaque clic sur une case de copie écrit une
      ligne dans **`logs/diagnostic_copie.log`** (gitignoré, taille bornée
      avec rotation) ET dans la **console du navigateur** (F12, préfixe
      `[diagnostic-copie]`) — champs à relever en priorité : `etatSse`
      (connexion du flux /stream au moment du clic), `depuisDernierEvenementSse`
      (silence du flux avant le clic), `elementDansDocument` (la case
      cliquée existait-elle encore), `ligneRedessineeRecemment` (la ligne
      vient-elle d'être reconstruite) et `resultat` (succès/vide/échec/non
      prêt, ou `aucun_changement_detecte` si le `change` attendu n'a jamais
      été livré — exactement le symptôme de cette issue). Si le serveur est
      injoignable au moment du clic, la ligne n'est PAS perdue : elle reste
      en file (`localStorage`) et est réenvoyée au chargement suivant de la
      page.
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
- [ ] Actions sur une issue : plus AUCUN bouton d'action par issue dans le
      panneau de détail (issue #950 — « Annuler cette issue » et « Interrompre
      et fermer cette issue » retirés, décision d'Alain : toutes les actions
      par issue vivent sur la ligne de la liste, jamais dans un panneau). Le
      rappel « ⚠️ Échec — intervention humaine requise » reste affiché pour
      une issue needs-human, mais SANS bouton. Voir ci-dessous pour les
      boutons eux-mêmes (ne doivent apparaître **qu'à un seul endroit**, la
      ligne).
- [ ] **Boutons d'action par état, sur la ligne (issue #950, remplace les
      boutons A/B de l'étude #938)** : sur une ligne **OUVERTE**, APRÈS le
      préfixe informatif (⚠️/✏️/○/✅, plus aucun clic dessus désormais) et
      AVANT le contrôle de son G/P/C/S, un groupe de 0 à 2 petits boutons
      textuels apparaît selon l'état — jamais plus d'un groupe actif à la
      fois, le clic ne sélectionne JAMAIS la ligne (`stopPropagation`) :
      - **en file** (pas encore prise en charge, badge ⏳ « en file ») →
        **« Annuler »** seul ;
      - **en cours** (même état que le décompte ⏳ actif — lecture ou
        écriture) → **« Interrompre »** seul ;
      - **needs-human** → **« Relancer »** + **« Fermer »** ;
      - **terminée** (`done`) → aucun bouton.
      Une ligne **FERMÉE** n'affiche jamais aucun de ces boutons.
- [ ] **« Annuler »** : clic sur la ligne d'une issue en file → confirmation
      courte, puis `POST /annuler-issue/<projet>/<numero>` (gh issue close,
      commentaire d'annulation) — la ligne disparaît (ou passe fermée) au
      rechargement. Essai de la petite course (issue #950, point 4) :
      déposer deux issues `testvibe` d'affilée pendant que la première tourne
      encore, cliquer « Annuler » sur la SECONDE (en file) juste au moment où
      le watcher pourrait la prendre en charge — si elle a démarré entre
      temps, le message « déjà prise en charge par le watcher — utilisez
      Interrompre » apparaît (aucune fermeture), sinon elle est annulée
      normalement et ne démarre jamais.
- [ ] **« Interrompre » — issue NON interactive** : clic → confirmation
      COURTE rappelant le numéro ET le titre de l'issue, annonçant que SEULE
      cette issue sera arrêtée (needs-human, relançable, les autres issues du
      projet continuent) — `POST /demander-interruption-issue` (PAS
      `/interrompre`, vérifiable dans l'onglet Réseau, F12). En ~10s, SANS
      rechargement manuel : la ligne passe à `needs-human`, affiche
      « Relancer »/« Fermer ». Si la réponse indique que l'issue ne tourne
      plus (`deposee:false`) : message clair (toast, pas une alerte
      d'erreur), aucune ligne affectée.
- [ ] **« Interrompre » — issue INTERACTIVE (label `mode_interactif`,
      session tmux)** : comportement HISTORIQUE inchangé (watcher ENTIER du
      projet, même route `/interrompre`, même modale de résultat détaillée
      qu'avant #950) — la confirmation liste désormais, si le projet a
      d'autres issues en cours, leur(s) numéro(s) et annonce clairement
      qu'elles seront interrompues EN MÊME TEMPS (route `/issues-en-cours`,
      #947).
- [ ] **« Relancer »** (needs-human/interrompue) : clic → même confirmation/
      route `/relancer-issue` qu'avant #950 (retrait de `needs-human`,
      purge d'une demande d'interruption périmée) — AUCUNE interruption,
      AUCUN redémarrage de watcher déclenché par ce bouton.
- [ ] **« Fermer »** (needs-human/interrompue) : clic → confirmation dont le
      texte NE PRÉTEND PAS à une intervention humaine, puis `POST
      /fermer-issue/<projet>/<numero>` — commentaire GitHub posté : « Issue
      fermée manuellement depuis l'interface (new_issue.py). » (remplace
      l'ancien texte trompeur « … intervention humaine effectuée »). Le
      watcher du projet n'est PAS arrêté ; les autres issues du projet ne
      sont pas affectées (vérifier qu'une autre issue en cours du même
      projet continue sans interruption pendant ce clic).
- [ ] **Robustesse du clic (issue #950, point 8)** : double-clic rapide sur
      une ligne ouverte EN COURS → ouvre/referme le détail normalement, mais
      **aucune action réseau** n'est déclenchée par ce double-clic lui-même.
      Clics rapprochés sur les boutons de PLUSIEURS lignes différentes
      (ouvrir plusieurs issues de `testvibe`, cliquer rapidement sur
      « Interrompre »/« Annuler » de lignes distinctes) → chaque clic agit
      sur SA PROPRE issue (numéro affiché dans la confirmation/le toast),
      jamais sur une autre. Provoquer un rechargement de la liste (↻,
      événement début/fin d'une AUTRE issue) juste après un clic sur un
      bouton (avant la réponse réseau) → l'action en cours se termine
      normalement sur la BONNE issue (pas d'erreur, pas d'action sur une
      autre ligne).
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
- [ ] **Messages de panne de connexion auto-effaçables** (issue #807) :
      couper le réseau (ou arrêter le point d'accès Wi-Fi) avec l'onglet
      Résultats ouvert, laisser les rechargements automatiques échouer
      plusieurs fois de suite, puis reconnecter. Vérifier :
      - les trois bandeaux (« Résultats — échec de chargement… », « Résultats
        — décompte non rechargé… », état de GitHub) disparaissent SEULS après
        ~10s, sans clic sur la croix (pas de bouton « × » visible dessus) ;
      - ils ne s'empilent jamais, même si le texte change entre deux échecs
        (liste de projets différente) — un seul bandeau par source, dont le
        contenu se met à jour ;
      - survoler un bandeau pendant les 10s gèle son compte à rebours (la
        pause au survol reste active, comme pour info/succès) ;
      - toutes les occurrences restent consultables dans le panneau
        « Messages » (icône de l'en-tête), y compris celles déjà disparues de
        l'écran ;
      - une autre erreur/avertissement SANS cette option (ex. échec de copie
        presse-papier) reste, elle, affichée jusqu'au clic sur sa croix —
        aucune régression de la persistance par défaut (issue #730).

## Veille, réveil, rechargement sur événements et copie du rapport (issues #917, #933, #940, #943)

> Nouveau mécanisme — aucune infrastructure de test de navigateur dans le
> dépôt, donc RIEN de ce qui suit n'a pu être vérifié automatiquement. En
> particulier, la détection d'activité quand la fenêtre n'a PAS le focus
> (autre application au premier plan) dépend du système de fenêtrage/
> navigateur, pas seulement du code — à vérifier ici en priorité. Après
> redémarrage de l'interface (issue #933) : les essais (a)/(b)/(c) ci-dessous
> sont ceux demandés par cette issue — déposer une issue non interactive du
> projet sélectionné sans rien toucher, laisser l'issue se terminer, répéter
> plusieurs fois et consulter `logs/charge_interface.log`.

- [ ] **(a, #933)** Déposer une issue non interactive du projet SÉLECTIONNÉ
      dans le filtre Résultats, SANS cliquer ↻ ni rien toucher : sa ligne
      apparaît au plus tard au DÉBUT de son traitement (ACK du watcher) —
      pas seulement à sa création ni à sa fin.
- [ ] **(b, #933)** Laisser cette même issue se terminer : sa ligne (état
      final) ET les compteurs du panneau Infrastructure se mettent à jour
      SANS clic ↻.
- [ ] **(c, #933)** Répéter (a)/(b) plusieurs fois (idéalement avec des
      issues interactives et non interactives, comme les essais du
      23/11/2026), puis consulter `logs/charge_interface.log` : chaque appel
      de `/issues-liste/<projet>` y laisse une ligne `rechargement_liste`
      (projet, nb_issues, numero_plus_recent, duree_gh_s, raison) ; AUCUNE
      ligne `avertissement_issue_absente` n'est attendue — si certaines
      apparaissent, elles montrent le retard de GitHub (projet, numéro, âge
      en secondes) plutôt qu'un bug de l'interface.
- [ ] **(d, #933)** Régler le délai de veille à 1 minute (panneau
      Infrastructure, partie globale, sous l'interrupteur de son), ne rien
      toucher : le voile gris « Interface en veille — cliquez pour la
      réveiller » apparaît après 1 minute, couvrant toute l'interface. Un
      clic (n'importe où sur le voile) le fait passer à « Mise à jour… »,
      puis il disparaît une fois les données arrivées — jamais avant, jamais
      de disparition silencieuse. Les réglages « Rafraîchir toutes les (s) »
      et « Rattrapage création (s) » de l'issue #917 ont disparu du panneau
      (retirés par #933) : seul « Veille après (min) » reste affiché.
- [ ] Pendant la veille : appuyer une touche au clavier (sans cliquer) lève
      aussi le voile — ET cette touche ne doit avoir AUCUN autre effet visible
      (pas de caractère tapé dans un champ, pas de raccourci déclenché).
- [ ] Onglet Réseau (F12) pendant la veille : **aucune** requête `/issues-liste`
      ni `/issues-en-attente` pendant toute la durée de la veille — y compris
      si une issue est créée, débute ou se termine PENDANT la veille (rien ne
      doit partir avant le réveil).
- [ ] Déposer une issue PENDANT la veille : elle n'apparaît qu'APRÈS le
      réveil (pas pendant la veille elle-même).
- [ ] **(issue #933 point 4, corrigé par #937)** Interface éveillée depuis
      plus de 90s sans aucun événement `/stream` : via l'onglet Réseau,
      cliquer sur la connexion `/stream` (type EventSource, onglet
      « EventStream » de Chrome/Edge) et observer qu'un événement NOMMÉ
      `battement` (pas une ligne `: ping` invisible) arrive bien au moins
      une fois toutes les ~30s. Si le flux est artificiellement coupé côté
      serveur sans que le navigateur le détecte (ex. coupure de tunnel),
      l'onglet Réseau doit montrer une fermeture + réouverture de `/stream`
      au plus 15-30s après le dépassement du seuil, suivie d'un SEUL
      rechargement de `/issues-liste` du SEUL projet sélectionné (raison
      `flux_silencieux` dans le journal, précédé d'une ligne
      `reouverture_stream` portant l'ancienneté constatée) — pas d'un
      rechargement répété si la coupure se prolonge. Difficile à provoquer
      sans outillage réseau dédié, best-effort à vérifier si l'occasion se
      présente.
- [ ] **(a, #937)** Redémarrer l'interface (watcher ou `new_issue.py`),
      recharger la page de force (Ctrl+Maj+R) juste après : consulter
      `logs/charge_interface.log` dans la minute qui suit — AUCUNE ligne
      `flux_silencieux` ni `reouverture_stream` ne doit apparaître (le délai
      de grâce doit couvrir le temps que le flux s'ouvre réellement après un
      redémarrage).
- [ ] **(b, #937)** Laisser la page ouverte au repos, sans y toucher, au
      moins 10 minutes, avec plusieurs projets sélectionnés dans le filtre
      Résultats : AUCUNE ligne `flux_silencieux` dans le journal pendant
      toute cette durée (donc aucun rechargement de liste déclenché sans
      véritable événement) — l'onglet Réseau doit montrer le battement
      `battement` arriver régulièrement sur `/stream` pendant ce temps.
- [ ] **(c, #937)** Arrêter puis relancer l'interface avec la page laissée
      ouverte (sans la recharger) : au plus UNE ligne `flux_silencieux` dans
      le journal (la coupure réelle du serveur), suivie d'une ligne
      `reouverture_stream`, puis plus rien ensuite — pas de répétition
      toutes les 15s.
- [ ] **(c, issue #835)** Revenir sur un onglet resté ouvert plus d'une heure
      (ou simuler une session expirée) et cocher la case d'une issue
      terminée : message « Préparation du rapport… » dès le clic, puis la
      copie réussit, ou la fenêtre de repli (texte à copier manuellement, ou
      message d'erreur avec bouton « Réessayer ») s'ouvre en moins de 30s —
      jamais de silence, jamais confondu avec « réponse pas encore
      disponible ».
- [ ] Désactiver la veille (délai = 0) : le voile ne doit plus jamais
      apparaître, quelle que soit la durée d'inactivité.
- [ ] (Dé)sélectionner un projet dans le filtre pastille Résultats : le
      projet qui vient d'être (ré)sélectionné se recharge à ce moment-là
      (onglet Réseau) ; un projet désélectionné ne déclenche plus aucun appel
      réseau tant qu'il reste masqué.
- [ ] L'affichage « sync HH:MM:SS » (près du ↻) devient rouge/gras quand la
      dernière synchro dépasse 90s (3 × intervalle des battements du flux
      `/stream`, depuis #933 — plus aucun réglage d'intervalle dont dépendre).
- [ ] **(a, #940)** Après redémarrage de l'interface et rechargement forcé de
      la page (Ctrl+Maj+R) : cocher une case de l'onglet Résultats, puis,
      SANS rien toucher d'autre (aucun autre clic, aucune touche, aucun
      changement de fenêtre), déposer une issue du projet SÉLECTIONNÉ dans le
      filtre — sa ligne apparaît D'ELLE-MÊME, au plus tard au DÉBUT de son
      traitement (ACK du watcher), sans attendre un clic sur ↻. AVANT ce
      correctif, la ligne restait absente indéfiniment tant que la case
      cochée gardait le focus.
- [ ] **(b, #940)** Cocher une case PENDANT la fin d'une issue (clic au
      moment précis où `fin_issue` redessine sa ligne, ou juste après) : le
      clic garde son effet (case cochée, copie lancée) — pas de régression
      sur #878 — et la liste se met à jour ensuite (ligne isolée reconstruite
      peu après, sans attendre un clic sur ↻).
- [ ] **(c, #940)** Après les essais (a)/(b), consulter
      `logs/charge_interface.log` : chaque rendu différé par la case cochée
      y laisse une ligne `rendu_differe` (`type_rendu` `liste` ou `ligne`,
      `duree_report_ms`) — la durée doit rester COURTE (proche de 0 ms dans
      le cas normal, puisque la case retrouve son focus décoché après son
      `change` ; jamais au-delà de 1000 ms, le plafond de sécurité
      `DELAI_MAX_REPORT_RENDU_MS`, même si la case est restée focalisée sans
      être rebasculée).
- [ ] **(a, #943)** Après redémarrage de l'interface et rechargement forcé de
      la page : double-cliquer une issue (zone de détail affichée, titre du
      panneau Infrastructure « Actions — <projet> #<numéro> » sur cette
      même issue), puis déposer une issue du projet sélectionné (ou en
      laisser terminer une en cours) SANS rien re-cliquer : la liste se
      recharge (ligne visible qui apparaît/se met à jour), mais la zone de
      détail ET le titre du panneau d'actions restent sur l'issue ouverte au
      double-clic — AVANT ce correctif, la sélection « sautait » à la
      première ligne de la liste à chaque rechargement (création, début ou
      fin de traitement depuis #933), avec le risque qu'un bouton du panneau
      (ex. « Interrompre et relancer ») s'applique à une autre issue que
      celle crue sélectionnée.
- [ ] **(b, #943)** Même point de départ (issue ouverte au double-clic) :
      cliquer sur ↻ — même résultat qu'en (a), zone de détail et panneau
      d'actions inchangés.
- [ ] **(c, #943)** Toujours avec une issue ouverte au double-clic : changer
      de projet actif, ou (dé)sélectionner un projet dans le filtre pastille
      Résultats : la sélection se réinitialise comme AVANT ce correctif
      (première ligne visible du nouveau contexte) — ce cas-ci n'est pas
      concerné par la conservation de sélection, volontairement.
- [ ] **(d, #943)** Fermer/désélectionner l'issue actuellement sélectionnée
      (ex. elle devient filtrée/masquée, ou disparaît de la liste), puis
      déclencher un rechargement (↻) : la première ligne encore visible est
      sélectionnée, comme avant ce correctif (non-régression du cas « rien
      de sélectionné » ou « sélection disparue »).

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
- [ ] Zone monitoring : une ligne par watcher CCL / service CCW.
- [ ] **Bouton « ⏹ Arrêter » par watcher CCL (issue #655 ; confirmation
      enrichie par #950)** : visible **seulement** à côté de « ↺ Relancer »
      sur un watcher **actif** (🟢) — absent quand il est éteint (⚫, bouton
      « ▶ Lancer » seul). Cliquer dessus déclenche une confirmation
      (« Arrêter le watcher CCL du projet « <nom> » ? ») — avec, SI ce
      watcher a une ou plusieurs tâches en cours (`testvibe` en train de
      traiter une issue longue, par exemple), une ligne supplémentaire
      listant leur(s) numéro(s) et précisant qu'elles ne seront PAS
      interrompues (process orphelin, non supervisé) ; **Annuler** ne fait
      rien ; **Arrêter** désactive le bouton pendant l'appel (`POST
      /arreter-watcher`), puis la ligne repasse à ⚫ / « ▶ Lancer » après
      rafraîchissement — vérifier que la tâche en cours continue réellement
      (son process `claude` n'est pas tué).
- [ ] Interrupteur son (Plat / Cloche) : bascule ; « Tester le son » actif
      seulement quand une ligne est sélectionnée ; joue le timbre choisi à
      tonalité neutre (plus de tonalité par projet, issue #643).
- [ ] **Zone extras : démarrage direct du watcher spool, sans boîte de durée
      (issue #754)** : cliquer « ▶ Démarrer » (ou « ↺ Relancer » s'il est déjà
      actif) démarre/relance **immédiatement** le watcher spool (issues_inbox),
      **sans aucune boîte de dialogue** — plus de choix Indéfiniment/30
      min/minutes personnalisées. Pendant l'appel, le bouton se désactive et
      affiche « Démarrage… », puis se rétablit (libellé + état d'origine) et
      le panneau se rafraîchit ; le point vert 🟢 confirme le démarrage (aucun
      nouveau toast de succès). Couper le réseau et retenter : le toast
      d'erreur existant (de l'appel API) s'affiche, et le bouton se rétablit
      quand même (pas bloqué désactivé).
- [ ] **Historique du watcher spool (issue #639)** : sous le contrôle du watcher
      spool, un repli discret **« Historique récent »** (`<details>` fermé par
      défaut) ; l'ouvrir affiche les dernières lignes de `logs/issues_inbox.log`
      (mêmes lignes qu'exposait l'ancien onglet « Résultats inbox », supprimé).
- [ ] Zone actions contextuelles sur l'issue sélectionnée : toggles
      notif_pc/gsm/tous, **Interrompre et relancer (watcher CCL)**. Depuis
      l'issue #950, **« ✖ Fermer l'issue » a été retiré d'ici** (plus aucune
      action de fermeture par issue dans ce panneau — seule « Interrompre et
      relancer », niveau PROJET assumé, y reste, avec les toggles de
      notification) ; depuis l'issue #641, **Interrompre** (seul), **Retirer
      needs-human** et le contrôle **« 🔊 Son de cette issue »** (#637, étape
      7b) n'étaient déjà plus ici — tout est désormais sur la ligne de la
      liste (voir les boutons par état de l'onglet Résultats ci-dessus) : un
      seul emplacement par action. **« Interrompre et relancer » reste la
      SEULE action réseau propre à une issue encore présente dans ce
      panneau** — sa confirmation (celle d'« Interrompre », déclenchée en
      premier) liste désormais les autres issues en cours du projet, comme
      décrit ci-dessus pour le bouton « Interrompre » d'une issue
      interactive.
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

## Trace d'arrêt, arrêt non propre, alerte « en file, watcher éteint » (issue #945)

> Nécessite un accès terminal au ThinkPad (pour envoyer les signaux) en plus
> du navigateur. Redémarrer l'interface (`new_issue.py`) et recharger la page
> en forcé (Ctrl+Maj+R) avant de commencer, pour écarter tout ancien JS en
> cache.

- [ ] **Arrêt par SIGTERM** : relever le PID d'un watcher de projet actif
      (`cat logs/watcher-<nom>.pid` ou la colonne `pid` de `/watchers`), puis
      `kill -TERM <pid>` depuis un terminal. Dans `logs/watcher-<nom>.log` :
      une ligne `Watcher arrêté par signal SIGTERM — arrêt demandé, sortie
      propre.` apparaît, et le fichier `watcher-<nom>.pid` est retiré. Le
      panneau Infrastructure passe ce watcher à ⚫ au rafraîchissement suivant
      (≤ 30s), **sans** avertissement « arrêt non propre ».
- [ ] **Arrêt non propre détecté au redémarrage suivant** : avec le watcher
      du test précédent toujours éteint, `kill -KILL` un AUTRE watcher de
      projet actif (ou relancer le même après l'avoir d'abord relancé puis
      re-tué par `-KILL` — l'essentiel est qu'un fichier `watcher-<nom>.pid`
      reste en place pour un process mort). Déposer une issue `for-linux` de
      ce projet (formulaire ou fichier dans `issues_inbox/`) et attendre le
      délai de grâce (~60s) : l'alerte « ⚠️ N en file, watcher éteint »
      apparaît sur le badge du filtre projet (liste des résultats) ET sur sa
      ligne du panneau Infrastructure, accompagnée d'**un seul** toast.
      Relancer ce watcher avec le bouton « ▶ Lancer » : l'alerte disparaît
      des deux endroits au rafraîchissement suivant, et
      `logs/watcher-<nom>.log` affiche, tout en haut, une ligne
      `⚠️ Arrêt précédent non propre détecté : ... pid <celui tué par
      -KILL> ... Dernière ligne du journal avant ce démarrage : ...`.
- [ ] **Pas de fausse alerte à l'auto-extinction** : laisser un watcher
      s'éteindre seul par inactivité (`DELAI_INACTIVITE_MIN` du projet, ou
      réduire temporairement ce réglage pour le test) — aucune alerte dans
      l'interface, et aucun avertissement « arrêt non propre » au prochain
      démarrage de ce watcher (son fichier PID a bien été retiré par
      l'auto-extinction elle-même).
- [ ] **Pas de fausse alerte pendant le lancement automatique** : déposer une
      issue `for-linux` d'un projet dont le watcher est éteint (cas normal,
      `redemarrer_si_eteint` le relance) : aucune alerte ne doit apparaître
      durant la courte fenêtre entre le dépôt et la publication du fichier
      PID (délai de grâce de 60s largement suffisant).
- [ ] **Non vérifié par cette tâche** (à faire par Alain sur le déploiement
      réel, hors de ce worktree isolé) : relire `logs/issues_inbox.log` et
      `logs/new_issue.log` autour de 17:44 et 17:48 le 23/11/2026, pour
      confirmer ou écarter l'hypothèse du PID recyclé retenue au point 4 du
      rapport de l'issue #945 (voir `ARCHITECTURE.md` §16.5).

## Interruption propre d'UNE issue (issue #949, étude #939)

> Après fusion, redémarrer l'interface (`new_issue.py`) et relancer le
> watcher du projet `testvibe`. Nécessite un accès terminal au ThinkPad en
> plus du navigateur.

- [ ] **Déposer une issue longue et l'interrompre en cours** : déposer
      `issue_test_relance_testvibe_longue.txt` sur `testvibe`. Pendant
      qu'elle tourne, créer à la main le fichier de demande :
      `touch logs/demandes_interruption/testvibe-issue<numero>.demande`
      (remplacer `<numero>` par le numéro réel de l'issue en cours,
      affiché dans l'onglet Résultats). En ~3 secondes : `claude` s'arrête
      (vérifier qu'aucun process `claude` de ce PID ne subsiste), l'issue
      reçoit `needs-human` et un commentaire « ⛔ Interrompue sur demande »,
      **aucun** « ❌ Échec après 3 tentatives » n'apparaît, et le verrou
      (`logs/verrous/testvibe-*.lock`) disparaît.
- [ ] **Processus détachés** : avec `ps aux | grep sleep` juste après le
      point précédent, vérifier qu'aucun `sleep 120` ne subsiste — sinon,
      c'est la limite documentée (`docs/contexte/interruption_issue.md`,
      processus détaché hors du groupe de `claude`) qui s'observe en
      conditions réelles ; le noter sans le considérer comme un échec de
      cette issue.
- [ ] **Relance normale après interruption** : relancer l'issue interrompue
      avec le bouton existant (retrait de `needs-human`) — elle repart
      normalement, sans être interrompue de nouveau aussitôt (la demande
      périmée a bien été purgée à la relance).
- [ ] **Demande pour une issue qui ne tourne pas** : créer un fichier de
      demande pour un numéro d'issue qui n'est pas actuellement en cours de
      traitement (`touch logs/demandes_interruption/testvibe-issue1.demande`
      avec un numéro arbitraire) : rien ne se passe, aucune issue n'est
      affectée.

## Boutons par état sur la ligne — essais UI (issue #950)

> Après fusion, redémarrer l'interface (`new_issue.py`) et relancer le
> watcher du projet `testvibe` (reprend les essais ci-dessus, cette fois via
> les boutons de l'interface plutôt qu'en touchant le fichier-sentinelle à
> la main).

- [ ] **(a)** Déposer `issue_test_relance_testvibe_longue.txt` sur
      `testvibe` : sa ligne affiche **« Interrompre »** ET **« Fermer »**
      (issue #951 — voir la section dédiée ci-dessous pour ce second
      bouton). Cliquer sur « Interrompre » : confirmation rappelant le
      numéro et le titre de l'issue, annonçant que SEULE cette issue sera
      arrêtée. En une dizaine de secondes, SANS rechargement manuel (↻) : la
      ligne passe à `needs-human`, affiche **« Relancer »** + **« Fermer »**.
- [ ] **(b)** Cliquer **« Relancer »** sur cette même ligne : l'issue repart
      normalement (comportement inchangé de la relance existante).
- [ ] **(c)** Déposer DEUX issues `testvibe` d'affilée (pendant que la
      première tourne encore) : la seconde, encore en file, affiche
      **« Annuler l'issue »**. Cliquer : elle est fermée sur GitHub avec le
      commentaire d'annulation et ne démarre JAMAIS (vérifier qu'elle
      n'apparaît plus comme « en cours » même après que le watcher ait eu le
      temps de la prendre).
- [ ] **(d)** Cliquer **« Fermer »** sur une issue interrompue (needs-human,
      issue du point (a) si pas encore relancée, ou une autre) : elle est
      fermée sur GitHub avec le commentaire « Issue fermée manuellement
      depuis l'interface (new_issue.py). » — le watcher du projet CONTINUE
      (vérifier qu'une autre issue éventuellement en cours du même projet
      n'est pas affectée).
- [ ] **(e)** Double-clic sur une ligne (ouvre/referme le détail,
      normalement) ET clics rapprochés sur les boutons de PLUSIEURS lignes
      différentes : vérifier qu'aucune action n'a jamais lieu sur une
      MAUVAISE issue (numéro confirmé dans chaque confirmation/toast).

## Fermeture propre d'une issue EN COURS depuis sa ligne (issue #951)

> Après fusion, redémarrer l'interface (`new_issue.py`), relancer le watcher
> du projet `testvibe` et recharger la page en forçant (Ctrl+Maj+R). Les
> essais (a)/(b) sont ceux demandés par Alain dans l'issue de clôture.

- [ ] **(a) Fermeture normale — issue non interactive** : déposer
      `issue_test_relance_testvibe_longue.txt` sur `testvibe`. Sur sa ligne
      « en cours », cliquer **« Fermer »** : confirmation rappelant le
      numéro, le titre, et précisant que SEULE cette issue sera arrêtée puis
      fermée (les autres issues du projet continuent, le travail déjà fait
      est conservé). Confirmer : en quelques secondes (le temps que la
      boucle d'attente de `claude` détecte la demande, ~3s, puis que
      l'interface confirme l'arrêt via `/issues-en-cours`), la ligne indique
      « ⏳ Fermeture… » puis l'issue se ferme avec le commentaire « Issue
      fermée manuellement depuis l'interface (new_issue.py). » — SANS passer
      par un état `needs-human` visible durablement (ou, si observé
      brièvement, il disparaît avec la fermeture). Vérifier qu'aucun process
      `claude` de ce PID ne subsiste.
- [ ] **(b) Les autres issues ne sont pas affectées** : déposer EN MÊME
      TEMPS les deux issues en écriture `issue_test_ecriture_a.txt` et
      `issue_test_ecriture_b.txt` sur un projet dont `MAX_WRITE_PARALLELE`
      permet aux deux de tourner ensemble (ex. `testvibe`) ; attendre
      qu'elles tournent TOUTES LES DEUX (deux lignes « en cours »). Cliquer
      « Fermer » sur A : seule A s'arrête et se ferme (comme en (a)) ; B
      continue normalement jusqu'à sa fin naturelle, sans interruption ni
      ralentissement visible.
- [ ] **(c) Affichage d'une issue fermée manuellement** : après (a) ou (b),
      ouvrir le détail de l'issue fermée (ou la retrouver par la recherche)
      — vérifier qu'elle n'affiche PLUS le badge « ⚠️ échec » (le label
      `needs-human` a été retiré après la fermeture, issue #951 point 4) ;
      comparer avec une issue restée `needs-human` et OUVERTE (jamais
      fermée), qui doit CONTINUER à afficher ce badge.
- [ ] **(d) Délai dépassé (claude ne s'arrête pas à temps)** : sur une issue
      dont le process ne répond pas à la demande d'interruption dans les 30s
      (difficile à provoquer en conditions normales — à défaut, lire le code
      de `_attendreIssuesAbsentesDeEnCours`/`DELAI_MAX_ATTENTE_ARRET_FERMETURE_MS`
      dans `static/js/app.js` pour confirmer la logique) : un message clair
      apparaît, l'issue n'est PAS fermée, et reste dans son état (en cours ou
      `needs-human`) — à rejouer « Fermer » une fois l'arrêt confirmé.
- [ ] **(e) Issue interactive, aucune autre issue en cours** : déposer une
      issue avec `INTERACTIF | oui` sur un projet CCL sans autre issue en
      cours. Cliquer « Fermer » sur sa ligne : confirmation mentionnant
      l'arrêt du watcher ENTIER du projet (mécanisme historique, #949 ne la
      couvre pas) et l'absence d'autre issue affectée. Confirmer : le
      watcher s'arrête, l'issue se ferme. Relancer le watcher manuellement
      ensuite (comportement inchangé de `/interrompre`).
- [ ] **(f) Issue interactive, avec d'autres issues non interactives en
      cours** : même projet, une issue interactive ET une ou plusieurs
      issues normales en cours. Cliquer « Fermer » sur la ligne interactive :
      une fenêtre (pas un simple `confirm()`) liste les autres issues en
      cours avec deux boutons, **« Interrompre les autres puis fermer »** et
      **« Annuler »**. Cliquer « Annuler » : rien ne bouge. Recliquer
      « Fermer » puis **« Interrompre les autres puis fermer »** : les autres
      issues s'arrêtent (needs-human, comme #949), PUIS le watcher s'arrête
      et l'issue interactive se ferme.
- [ ] **(g) Issue interactive, avec une AUTRE issue interactive en cours** :
      deux issues interactives sur le même projet, la seconde encore en
      cours. Cliquer « Fermer » sur la première : la fenêtre indique qu'une
      autre issue interactive est en cours et ne peut pas être interrompue
      proprement, et ne propose QUE « Annuler » (pas de bouton
      « Interrompre les autres… »).
- [ ] **(h) Pas de double fermeture** : pendant l'attente (a)/(b)/(f),
      cliquer plusieurs fois rapidement sur « Fermer » de la même ligne —
      un seul message « Fermeture déjà en cours pour cette issue. » pour les
      clics suivants, une seule fermeture effective au final.

## Résistance à une coupure réseau (issue #952)

> Après fusion, relancer le watcher du projet `testvibe`. Ces trois essais
> nécessitent de couper/rétablir le réseau réel de la machine (Wi-Fi) —
> impossible à automatiser, donc non couverts par les tests. Couper
> uniquement le Wi-Fi, PAS tout le réseau de la box, pour ne pas perdre
> l'accès à l'interface web elle-même si elle est consultée à distance.

- [ ] **(a) Coupure pendant l'exécution de `claude`, texte perdu sans la
      correction** : déposer `issue_test_relance_testvibe_longue.txt` sur
      `testvibe`. Une fois que la ligne « en cours » confirme que `claude`
      tourne, couper le Wi-Fi quelques minutes, PUIS le rétablir alors que
      `claude` est toujours en train de tourner (ou juste après sa fin).
      Vérifier dans `logs/watcher-testvibe.log` : le watcher ne s'éteint PAS
      pendant la coupure, aucune ligne « disparue des issues ouvertes » n'est
      journalisée, une seule ligne « Panne réseau/GitHub détectée » apparaît
      au début de la coupure (pas une par cycle) et une seule « Réseau/GitHub
      de retour » à son rétablissement. Si la coupure a touché la publication
      du commentaire de résultat : un fichier apparaît sous
      `logs/publications_en_attente/testvibe/` pendant la coupure, et
      disparaît dès le cycle suivant le retour du réseau — le commentaire de
      résultat est alors visible sur GitHub, posté UNE SEULE FOIS (pas de
      doublon), et l'issue se ferme à ce moment-là (pas avant).
- [ ] **(b) Coupure pendant que `claude` termine (tentative non comptée)** :
      déposer une issue dont le traitement prend quelques dizaines de
      secondes ; couper le Wi-Fi juste avant la fin de `claude` (viser le
      moment où il écrit son rapport). Si la tentative échoue à cause de la
      coupure : le journal doit afficher « tentative échouée pendant une
      coupure réseau apparente » puis, au retour du réseau, « réseau de
      retour […] reprise de la tentative » — SANS que le compteur de
      tentatives n'ait avancé (relire le numéro de tentative affiché avant/
      après dans le journal). Si la tentative a simplement réussi malgré la
      coupure (réseau revenu avant l'échec), ce scénario ne s'est pas
      déclenché — réessayer en coupant plus tôt/plus longtemps.
- [ ] **(c) Pas de régression sans coupure** : laisser le watcher `testvibe`
      inactif (aucune issue déposée) pendant plus de `DELAI_INACTIVITE_MIN`
      (20 min par défaut) SANS toucher au réseau : l'auto-extinction se
      déclenche exactement comme avant l'issue #952 (ligne « Auto-extinction
      […] arrêt propre du watcher », code de sortie 42).
- [ ] **(d) Panneau latéral** : pendant une coupure (a), ouvrir le panneau
      latéral Infrastructure (onglet Résultats) — la ligne du projet affiche
      « ⚠️ en attente du réseau — N publication(s) en attente » tant que la
      panne ou la file d'attente persiste, et cette ligne disparaît une fois
      les deux revenus à zéro, sans recharger la page (rafraîchi par le
      polling existant, ~30s).

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
- [ ] **Disparition automatique d'une ligne reçue en direct** (issue #663) :
      un fichier refusé **pendant que l'onglet est déjà ouvert** (ligne rouge
      apparue via l'événement SSE `fichier_refuse`, sans rechargement) se
      referme lui aussi tout seul, **sans recharger la page**, dès que le
      fichier quitte `issues_inbox/rejected/` (traité/retiré) — au prochain
      cycle de polling `/issues-inbox/etat` (7 s), même comportement qu'une
      ligne reconstituée au rechargement. Pas besoin d'un F5 d'entretien.
      Vérifier aussi qu'une ligne **tout juste refusée** ne clignote pas :
      elle reste affichée sans interruption jusqu'à ce que le fichier soit
      effectivement retiré du disque.
- [ ] **Lot multi-blocs mixte** (un fichier contenant plusieurs blocs, certains
      valides, certains invalides) → chaque bloc créé devient sa **ligne d'issue**,
      chaque bloc refusé produit sa **propre ligne rouge distincte** ; aucune
      confusion entre elles.
- [ ] **Exclusion propre** : les lignes fichier reçu/refusé ne sont jamais
      comptées par les **pastilles** de filtre projet, jamais cochables (pas de
      case à cocher), ignorées par **« Cocher tout »**, **« Tout à zéro »** et le
      **filtre projet / quota d'affichage**, et ne portent pas de **badge modèle**.

## Onglet « En attente » — pastille durée typique/maximale (issue #842)

- [ ] **Dépôt d'une issue avec `ATTENTE`** (issues_inbox/, `| TIMEOUT | 1200s |`
      déclaré) → la pastille apparaît sur la ligne, à côté de la date de dépôt :
      « max 20min » si aucune calibration connue pour ce projet+type+mode+
      complexité, ou « ≈ … · max 20min » si une durée typique est connue
      (même source que la pastille « ≈ … » des issues en cours de l'onglet
      Résultats). Survoler la pastille (`title`) : le texte précise bien
      « N tentatives de X min au maximum » avec les vraies valeurs du projet.
- [ ] **Remplacement du fichier** par une version à un autre `TIMEOUT` (même
      nom, dans `issues_inbox/en_attente/`) alors que l'onglet est déjà ouvert
      → la pastille se met à jour **sans rechargement manuel** (signature de
      rechargement de l'issue #825, inchangée par #842).
- [ ] **Projet jamais calibré** (aucun succès enregistré pour sa combinaison
      projet+type+mode+complexité) → la pastille affiche **seulement** le
      `TIMEOUT` (« max … »), jamais de « ≈ … » ni d'exception/ligne manquante.
- [ ] **Issue critique** (`| PRIORITE | haute |` ou `critique`) → le mot
      **« infini »** remplace la durée maximale, affiché en **rouge et en
      gras** ; vérifier qu'il reste identifiable même en désaturant l'écran
      (le gras seul suffit, la couleur n'est pas le seul porteur de
      l'information). Au survol, le texte précise que l'issue est critique et
      reprise à chaque cycle sans limite.
- [ ] La pastille ne gêne ni les boutons ↑/↓ (#819) ni le bouton 📋 copier le
      titre (#823), ni la lisibilité du titre lui-même.

## Onglet « Journal watcher »

*(sorti d'app.js vers `static/js/journal.js`, issue #650, étape 11 — import
direct depuis `onglets.js`, plus par le pont. Bouton « Vider l'affichage »
branché par délégation, `data-action="journal-vider"`, plus d'`onclick=`
inline.)*

- [ ] Sélectionner un projet avec watcher actif : le terminal streame le log en
      direct (SSE), lignes colorées.
- [ ] **Changement de projet/ré-entrée dans l'onglet** : l'ancienne connexion
      SSE se ferme proprement (pas de doublon de lignes, pas d'avertissement
      `[pont] fonction ancienne introuvable` en console) et le terminal se
      réinitialise (label + contenu) sur le nouveau projet.
- [ ] Bouton « Vider l'affichage ».

## Onglet « Configuration »

*(sorti d'app.js vers `static/js/config.js`, issue #651, étape 12 — import
direct de `chargerConfig` depuis `onglets.js`, plus par le pont ; boutons
Enregistrer/Enregistrer et relancer/Supprimer ce projet, curseur Tâches en
parallèle et modale de suppression branchés par délégation, `data-action`,
plus d'`onclick=`/`onchange=`/`oninput=` inline.)*

- [ ] Identité (lecture seule) affichée ; paramètres éditables chargés.
- [ ] **Modèle Claude Code** (`MODELE_CCL`, issue #656) : liste déroulante
      (plus de champ texte libre) avec une option vide en tête (« -- Défaut
      global (claude-sonnet-5) -- »), suivie des 4 modèles reconnus. Un
      projet sans `MODELE_CCL` affiche l'option vide sélectionnée ; un projet
      qui en fixe un affiche ce modèle sélectionné. Enregistrer avec un
      modèle choisi puis recharger l'onglet → le même modèle reste
      sélectionné. Si un `.conf` de test porte une ancienne valeur non
      reconnue (éditer temporairement `configs/<projet>.conf` à la main),
      elle apparaît comme option supplémentaire en fin de liste, sélectionnée,
      avec un avertissement discret sous le champ — la page ne plante pas.
- [ ] **Plus aucun réglage de son** (ni « Script bip », ni « Tonalité du
      bip », ni bouton « Tester le son » — retirés à l'issue #643 ; le son se
      règle désormais uniquement depuis le panneau latéral, interrupteur
      global + choix par issue).
- [ ] Curseur Tâches en parallèle : valeur suivie.
- [ ] « Enregistrer » et « Enregistrer et relancer » fonctionnent.
- [ ] **Changement de projet (sélecteur global) pendant que l'onglet
      Configuration est déjà actif** : la config affichée se recharge pour le
      nouveau projet (pas d'avertissement `[pont] fonction ancienne
      introuvable` en console — `chargerConfig` doit rester accessible en
      `window.chargerConfig` malgré le passage en module ES).
- [ ] Zone dangereuse : « Supprimer ce projet… » ouvre la modale (checklist +
      confirmation par saisie du nom) ; les 3 cases + le nom retapé
      correctement sont bien nécessaires pour activer « Supprimer
      définitivement » (garde-fous #587 inchangés).
- [ ] **Suppression d'un projet — purge `localStorage`** (issue #644) : avant
      suppression, consulter (double-clic) une issue du projet à supprimer
      (crée une clé `bridge_cache_detail_<projet>_<numero>`, DevTools →
      Application → Local Storage), puis le démasquer/masquer une fois dans le
      filtre de l'onglet Résultats (crée une entrée `<projet>` dans
      `bridge_filtres_resultats`). Supprimer le projet → les clés
      `bridge_cache_detail_<projet>_*` ont disparu, et l'entrée `<projet>` a
      disparu de `bridge_filtres_resultats` (DevTools, avant/après).

## Onglet « CCW » (sorti d'app.js vers `static/js/ccw.js`, issue #649)

- [ ] Liste des projets CCW (bouton « Rafraîchir ») ; état des services,
      TOPIC_NTFY (⚠ à définir / ✓ renseigné / ? inconnu).
- [ ] Cliquer une ligne du tableau pré-sélectionne le projet dans « Finaliser »
      — cliquer un bouton d'action de la même ligne (Redémarrer/Démarrer/
      Arrêter) ne déclenche PAS la pré-sélection.
- [ ] Changer de projet dans « Finaliser » (clic sur une ligne du tableau OU
      sélection directe dans le menu déroulant) vide les trois champs (topic,
      GH_TOKEN, CLAUDE_CODE_OAUTH_TOKEN) — un token d'un projet précédent ne
      doit jamais rester affiché pour un autre projet (issue #666).
- [ ] Finaliser un projet vide aussi le champ TOPIC_NTFY (en plus des deux
      tokens, déjà vidés) après soumission, succès ou échec (issue #666).
- [ ] Ajouter un projet ; finaliser un projet (tokens masqués + œil 👁/🙈).
- [ ] Actions redémarrer/démarrer/arrêter (confirmation avant redémarrer/
      arrêter) ; nettoyer les verrous depuis le panneau latéral (confirmation) ;
      sortie terminal des scripts distants.
- [ ] Panneau latéral, zone « Services CCW » : liste à jour après une action
      dans l'onglet CCW (redémarrer/démarrer/arrêter/nettoyer/ajouter/
      finaliser) sans re-fetch SSH depuis le panneau lui-même ; boutons
      « ↺ Relancer watcher CCW » / « 🔒 Nettoyer verrous CCW + redémarrer »
      (issue #632) fonctionnent identiquement.

## Nouveau projet

- [ ] Bouton « + Nouveau projet » ouvre la modale ; validations nom/dépôt/
      couleur ; création ; rappels git ; bootstrap CCW le cas échéant.
- [ ] (issue #870, comportement par défaut d'Alain — SANS `identite_locale.conf`
      ni réglage posé) **inchangé** : créer puis supprimer un projet affiche
      toujours l'encadré « Action requise — dépôt Bridge_Agent » en cas
      d'échec RÉEL de commit/push (simulable en coupant le réseau avant un
      push), et l'encadré « Action requise — relancer le hook de relecture »
      s'affiche après une création réussie (présent sur cette machine :
      `~/Relecture_Bridge/installer.sh`).
- [ ] (issue #870, `COPIE_NON_PROPRIETAIRE = oui` dans `identite_locale.conf`,
      cf. #869 — **à essayer à la main sur la copie de test Windows seul**)
      créer puis supprimer un projet : le compte-rendu annonce
      « liste des projets écrite dans PROJETS_LOCAUX.md, doc de l'outil
      inchangée » et **aucun** encadré orange « Action requise — dépôt
      Bridge_Agent » ne doit apparaître (ni après création, ni après
      suppression) — c'était le faux message d'échec corrigé par #870.
- [ ] (issue #870, machine sans `~/Relecture_Bridge/installer.sh` — **à
      essayer à la main sur la copie Windows seul**, qui n'a pas cet outil)
      créer un projet : l'encadré « Action requise — relancer le hook de
      relecture » ne doit PAS apparaître (comportement inchangé si l'outil
      est bien présent, comme sur les machines d'Alain).
- [ ] (issue #870, `MACHINE_SEULE = oui` dans `identite_locale.conf` — **à
      essayer à la main**) l'onglet « CCW » de la barre d'onglets et la case
      « Projet CCW » du formulaire de nouveau projet sont masqués ; sans ce
      réglage (défaut, installations d'Alain), les deux restent visibles et
      inchangés.
- [ ] (issue #879, **comportement par défaut d'Alain — SANS
      `identite_locale.conf` ni réglage posé**) **inchangé** : ouvrir la
      modale « Nouveau projet » → la case « Dépôt public » est **cochée**,
      libellé « Dépôt public (décocher pour un dépôt privé) » ; créer un
      dépôt neuf sans toucher la case → le compte-rendu affiche bien
      « … créé (public) », et le dépôt est effectivement public sur GitHub.
- [ ] (issue #879, `COPIE_NON_PROPRIETAIRE = oui` dans
      `identite_locale.conf` — **à essayer à la main sur la copie de test
      Windows seul, comme pour #870**) ouvrir la modale : la case « Dépôt
      public » est **décochée** par défaut, libellé « Dépôt public (cocher
      pour un dépôt public ; privé par défaut sur cette installation) ». Sur
      cette copie (`gh auth login`, pas de `GH_TOKEN` exporté), l'avertissement
      ⚠ « Dépôt privé : GH_TOKEN doit avoir les permissions nécessaires… » ne
      doit **PLUS** apparaître (corrigé par #882 — voir ce point plus bas) ;
      créer un dépôt neuf sans toucher la case → le compte-rendu affiche
      « … créé (privé) », dépôt effectivement privé sur GitHub. Cocher la
      case avant de créer → « … créé (public) », dépôt effectivement public.
- [ ] (issue #879, `DEPOT_PRIVE_PAR_DEFAUT = oui` dans
      `identite_locale.conf`, SANS `COPIE_NON_PROPRIETAIRE` — **à essayer
      sur la machine d'Alain**) même effet que le point précédent (case
      décochée par défaut, libellé adapté) : ce réglage permet à Alain de
      choisir le privé par défaut sur SA PROPRE installation, sans dépendre
      de `COPIE_NON_PROPRIETAIRE`.
- [ ] (issue #879, `DEPOT_PRIVE_PAR_DEFAUT = non` avec
      `COPIE_NON_PROPRIETAIRE = oui` — **à essayer sur la copie de test
      Windows seul**) la case reste **cochée** par défaut malgré
      `COPIE_NON_PROPRIETAIRE` : ce réglage prime bien dans les deux sens.
- [ ] (issue #879) **ré-ouvrir la modale plusieurs fois dans la même
      session** (Fermer puis « + Nouveau projet » de nouveau) sans recharger
      la page : l'état de la case à l'ouverture suit toujours le réglage
      d'installation (pas figé à la valeur laissée par la fermeture
      précédente) — vérifie que `ouvrirNouveauProjet()` relit bien
      `window.DEPOT_PUBLIC_PAR_DEFAUT` à CHAQUE ouverture.
- [ ] (issue #882, **à essayer sur la machine d'Alain, pour les deux sens**)
      ouvrir la modale « Nouveau projet » AVEC `GH_TOKEN` (ou `GITHUB_TOKEN`)
      exporté dans l'environnement du processus `new_issue.py` (cas normal
      sur cette machine) → décocher « Dépôt public » pour un dépôt qui
      n'existe pas encore : l'avertissement ⚠ « Dépôt privé : GH_TOKEN doit
      avoir les permissions nécessaires… » apparaît, texte inchangé. Arrêter
      `new_issue.py`, relancer son processus SANS `GH_TOKEN` ni `GITHUB_TOKEN`
      dans l'environnement (`env -u GH_TOKEN -u GITHUB_TOKEN python3
      new_issue.py`, ou commenter temporairement leur export), recharger la
      page, répéter la même manipulation de case : l'avertissement ne doit
      plus apparaître. Remettre `GH_TOKEN` et relancer normalement ensuite.
- [ ] (issue #882, **à essayer sur la copie de test Windows seul** — `gh auth
      login`, aucune variable `GH_TOKEN`/`GITHUB_TOKEN`) ouvrir la modale,
      décocher « Dépôt public » pour un dépôt absent : l'avertissement ⚠ ne
      doit PAS apparaître (gh utilise son propre jeton de trousseau, qui a
      déjà les permissions nécessaires) ; créer malgré tout le dépôt privé et
      vérifier qu'il se crée bien sans erreur.
- [ ] (issue #882, vérification en retard sur le champ « Dépôt GitHub ») dans
      le champ « Dépôt GitHub », taper un nom de dépôt qui n'existe PAS sur
      GitHub, PUIS continuer à taper pour le corriger en un AUTRE nom qui
      n'existe pas non plus (ex. taper `votre-compte/Bridge`, laisser le
      message « …/Bridge n'existe pas encore » apparaître, puis AVANT ou
      juste APRÈS qu'il apparaisse, compléter en `votre-compte/Bridgebc`) :
      le message final affiché doit TOUJOURS porter sur le nom qui est
      effectivement dans le champ en ce moment (`…/Bridgebc`), jamais sur un
      nom intermédiaire déjà remplacé — répéter l'essai plusieurs fois avec
      des frappes à des vitesses différentes (y compris très rapide) pour
      augmenter les chances de déclencher l'ordre d'arrivée réseau inversé
      observé dans l'issue d'origine. Vérifier aussi sur GitHub qu'aucun
      dépôt correspondant au nom intermédiaire n'a été créé par erreur.

## Bandeaux globaux et cycle de vie

- [ ] Widget rate-limit GitHub (⚡) présent dans l'entête, couleur selon le quota,
      rafraîchi (~30 s).
- [ ] Bandeau éval Windows (si échéance proche) et bandeau repli REP_TRAVAIL
      (si tâche mode_write hors worktree) s'affichent sur tous les onglets.
- [ ] **Bouton « Quitter »** : demande confirmation, arrête le serveur, l'overlay
      « Serveur arrêté » s'affiche.
- [ ] Couper le serveur par Ctrl+C (arrêt propre, signal géré) : l'overlay
      d'arrêt bloquant apparaît côté navigateur (inchangé).
- [ ] **(d, issue #917)** Couper le serveur plus brutalement (ex. `kill -9` du
      process, ou simplement débrancher le réseau quelques secondes) : un
      **bandeau rouge** « connexion perdue » (NON bloquant, distinct du voile
      gris de veille et de l'overlay d'arrêt) apparaît après quelques
      secondes — l'interface reste par ailleurs utilisable. Relancer le
      serveur (ou reconnecter le réseau) : le bandeau **disparaît tout seul**,
      sans recharger la page.
- [ ] Déconnexion (mode `--externe`) redirige vers le login.

## Modes de lancement

- [ ] **Local** (`python3 new_issue.py`) : tout ce qui précède OK.
- [ ] **`--lan`** (`python3 new_issue.py --lan`) : refuse de démarrer sans
      `MOT_DE_PASSE` configuré (issue #831) ; une fois configuré, accès depuis
      un autre appareil du réseau local nécessite une connexion (login en
      HTTP, même page que `--externe`) ; interface identique après connexion ;
      modules servis (statut 200, `text/javascript`), y compris avant connexion.
- [ ] **`--externe`** (HTTPS + login) : après connexion, interface identique ;
      modules et CSS chargés en HTTPS ; **session expirée** → la page redirige
      vers le login mais les fichiers statiques restent servis (pas d'erreur MIME
      de module).

## Archives — vérifications ponctuelles déjà rejouées

Cas one-shot déjà validés au moment de leur issue d'origine, sans intérêt à
rejouer à chaque étape suivante de la refonte (le mécanisme testé reste en
place, mais son déclencheur — un navigateur avec de l'état pré-migration —
n'existe plus en pratique). Conservés ici pour mémoire plutôt que supprimés.

- [ ] **Migration du localStorage** (issue #636, à faire UNE fois sur un
      navigateur ayant déjà des coches d'avant #636) : avant mise à jour, cocher
      quelques résultats (anciennes clés `resultat-coche:*`). Après mise à jour +
      rechargement : les mêmes lignes restent cochées (reprise serveur), et les
      clés `resultat-coche:*` ont disparu du `localStorage` (DevTools →
      Application). Rejouer un rechargement ne recrée rien (idempotent).
