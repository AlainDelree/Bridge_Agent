## 1 novembre 2026 — issue #838

Précharge du rapport (issue #835) : une issue « en cours » (ouverte ET sans
label `needs-human`) n'est désormais ni préparée en tâche de fond ni
signalée « prête à copier », puisqu'aucun rapport n'existe encore pour elle
— seul ce qui sera refait à la clôture. Nouvelle fonction pure exportée
`issueEnCours(it, estIssueEnEchecFn)` (`static/js/resultats_coches.js`),
reprenant la règle d'« ouvert » déjà utilisée pour le suffixe [ouvert]/[fermé]
d'une ligne (`construireLigneIssueDOM`, `static/js/app.js`) : tout ce qui
n'est pas explicitement `CLOSED` compte comme ouvert (`gh issue list` ne
renvoie que `OPEN`/`CLOSED` pour une issue, pas de 3e état). `candidatsPrechargement`
exclut désormais ces issues (sans consommer la borne totale ni changer les
autres règles : fenêtre par projet, ordre par ancienneté, cochées/déjà
préparées exclues) ; `reperePretACopier` reçoit un nouveau paramètre optionnel
`enCours` et renvoie faux dans ce cas, même si un texte préparé et valide
existe déjà pour elle. Une issue ouverte portant déjà `needs-human` (rapport
d'échec posté) continue d'être préparée normalement — `estIssueEnEchec`
(app.js, issue #830) reste la seule source pour ce label, via un petit pont
(`estIssueEnEchecPont`, `appelerAncien`) puisque app.js est un script
classique non importable depuis ce module ES. Aucun changement à la copie
elle-même, aux messages du toast, au mode repli ni à la mesure de charge
(#835). `VERIFICATIONS_MANUELLES.md` : nouveau point de vérification manuelle.
10 tests JavaScript ajoutés (`issueEnCours`, exclusion/borne/transition dans
`candidatsPrechargement`, `enCours` dans `reperePretACopier`) ; 4 fixtures
existantes de `resultats_coches_variantes.test.js` (issues `OPEN` sans
rapport, utilisées pour tester la file/l'abandon/le résumé de précharge, pas
l'état ouvert/fermé) passées à `CLOSED` pour rester candidates malgré la
nouvelle exclusion. Suite JS : 466 → 476 tests, tous passants. Suite Python
inchangée (aucun fichier `.py` modifié), 93 fichiers, tous passants.
