## 1 novembre 2026 — issue #839

Précharge du rapport : continue désormais quand la page est cachée, et le
texte préparé tient plus longtemps au retour sur la page. Corrige le
scénario constaté : une issue se termine pendant qu'Alain lit un autre
onglet, il revient quelques minutes plus tard et coche la case — la copie
échouait (fenêtre rouge « Préparation trop longue… », `NotAllowedError`)
parce que (1) `precharderVisibles()` (`static/js/resultats_coches.js`)
refusait de rien faire tant que `document.hidden` était vrai, et (2) même
préparé à la clôture, un texte était périmé après trois minutes
(`AGE_MAX_TEXTE_PREPARE_MS`, issue #832 point 3) — bien avant un retour
plausible sur la page.

1. Retrait du garde `if (document.hidden) return;` en tête de
   `precharderVisibles()` : la précharge tourne désormais aussi en
   arrière-plan, déclenchée comme avant par l'abonnement à la clé `issues`
   du store (donc à la clôture d'une issue même onglet caché). Les
   protections existantes sont inchangées : une préparation à la fois,
   borne totale de six (`BORNE_TOTALE_PRECHARGEMENT`), issues terminées
   seulement (règle « en cours » de #838), projets sélectionnés, plus
   ancienne d'abord.
2. Nouvel écouteur `visibilitychange`, posé une seule fois dans
   `initialiser()` avec les autres abonnements du module : au passage
   caché → visible, relance immédiatement `precharderVisibles()` et
   `majReperesVisibles()`, sans attendre le prochain tour du minuteur de
   30s qui rafraîchit sinon le repère « prêt à copier ».
3. `AGE_MAX_TEXTE_PREPARE_MS` porté de 3 minutes à 1 heure. Cette durée
   n'est pas la mesure de péremption normale (c'est la clé de validité —
   état + labels, `cleValiditeIssue` — qui en tient lieu, inchangée) : elle
   ne couvre que le cas rare d'un commentaire ajouté à une issue terminée
   sans changement d'état ni de label, que la liste `/issues-liste`
   n'expose pas. `texteEstValide` et ses cinq points d'appel ne changent
   pas de forme.

Vérification de la chaîne de clôture (`resultats.js::surFinIssue`,
déclenchée par l'événement SSE `fin_issue`) : aucun garde de page cachée ni
minuteur ralenti en arrière-plan n'y a été trouvé, ni dans `sse.js` — rien
à corriger de ce côté, seule la précharge elle-même bloquait.

Tests Node ajoutés (`static/js/tests/`) : `precharderVisibles` prépare une
issue terminée avec `document.hidden` vrai (remplace l'ancien test qui
vérifiait l'inverse) ; une issue « en cours » reste exclue même page cachée ;
l'écouteur `visibilitychange` rafraîchit le repère immédiatement au retour
(sans attendre le minuteur de 30s) ; `texteEstValide`/`AGE_MAX_TEXTE_PREPARE_MS`
valides à 59 minutes, périmés à 61. Les tests déjà existants sur
`texteEstValide`/`reperePretACopier` étaient paramétrés sur la constante
elle-même (jamais sur `180000` en dur) : aucun n'a eu besoin d'être adapté
à la nouvelle durée.

`VERIFICATIONS_MANUELLES.md` : nouveau point Firefox (onglet caché pendant
la clôture d'une issue, retour après plusieurs minutes, repère déjà affiché
+ `logs/charge_interface.log` horodaté à la clôture).

Suites de tests (comptages exacts) : JavaScript (`static/js/tests/` +
`static/js/socle/`) 510 → 515 (476 → 481 dans `tests/`, 34 inchangés dans
`socle/`) ; Python (`tests/lancer_tous_les_tests.py`) 93 → 93, inchangé.
