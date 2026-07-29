# Issues prêtes à envoyer — amélioration de la qualité des issues

*Rédigées le 29 juillet 2026. À envoyer depuis `new_issue.py`, projet
`bridge_agent`. Ordre recommandé : A puis B (la seconde renvoie à la première).*

---

## Note de conception — pourquoi pas de label d'échappement

Alain a soulevé le risque du blocage circulaire : si un contrôle de
pré-traitement déraille et refuse toutes les issues, celle qui le corrigerait
serait refusée à son tour.

**C'est ce risque qui a déterminé la conception.** Un contrôle *codé en dur*
dans `watcher.py` aurait exigé un label d'échappement (`sans-prevalidation`) et
une règle de repli stricte — « un validateur qui lève une exception laisse
passer, jamais ne bloque ».

Le choix retenu est plus léger : la prévalidation est une **consigne** injectée
dans le prompt, pas un verrou. Conséquences :

- elle ne peut pas bloquer structurellement — c'est un jugement de l'agent, pas
  une porte fermée ;
- l'échappement est une simple phrase dans le corps de l'issue, sans label ni
  mécanisme à maintenir ;
- coût nul : l'agent lit déjà l'issue au démarrage, aucune invocation
  supplémentaire.

Contrepartie assumée : une consigne peut être ignorée (cf. #243/#244, où la
contrainte d'exécution synchrone n'a pas été suivie). Le pire cas est alors le
comportement actuel — jamais une régression. Durcir seulement si l'expérience
montre que c'est insuffisant.

---

## Issue A — checklist de rédaction dans le §3

```
#Titre: §3 : ajouter une checklist de rédaction d'issue, tirée des échecs réels

| PROJET  | bridge_agent |
| TIMEOUT | 900s |

## Contexte

Les échecs coûteux de cette semaine viennent tous de la RÉDACTION des issues,
jamais de leur exécution. Le cas le plus net est #269 : trois tentatives à
900 s, 5415 secondes consommées, aucun livrable, deux résidus de debug
versionnés — pour une issue qui exigeait une mesure de 2 × 5 minutes dans un
budget de 900 s, une précondition invérifiable (« interface ouverte dans un
navigateur »), et laissait deux décisions de conception ouvertes.

Le diagnostic automatique produit à l'échec (`diagnostiquer_echec`) avait
identifié ces quatre défauts avec justesse — mais après coup.

Le §3 « Créer une issue » décrit aujourd'hui le FORMAT (en-tête, champs,
labels, envoi en lot) mais rien sur ce qui rend une issue exécutable. Or ce
paragraphe est lu par Claude Chat au début de chaque conversation impliquant
Bridge_Agent (règle des préférences utilisateur), contrairement à
`consignes/`, qui n'alimente que le prompt de CCL et n'atteint jamais Claude
Chat.

## Tâche demandée

Ajouter au §3 une sous-section « Rédiger une issue exécutable », placée après
la description du format et avant l'envoi en lot. Elle doit énoncer les
règles suivantes, chacune illustrée par le cas réel qui l'a motivée — les
exemples concrets sont ce qui rend une règle mémorable, ne pas les omettre :

1. **Le budget doit tenir.** La somme des attentes incompressibles demandées
   doit rester nettement sous le TIMEOUT, avant même de compter la lecture de
   code, les modifications et la rédaction du rapport. Contre-exemple : #269,
   qui exigeait 2 × 300 s de mesure dans 900 s.

2. **N'exiger que des préconditions vérifiables par l'agent.** L'agent ne
   contrôle ni le navigateur d'Alain, ni la VM CCW, ni l'état du réseau. Une
   condition qu'il ne peut ni créer ni constater le fait tourner en rond.
   Contre-exemple : « interface ouverte dans un navigateur pendant 5 minutes »
   (#269).

3. **Trancher, jamais déléguer une décision de conception.** « Décider ce qui
   est le moins trompeur entre A et B » n'est pas une tâche exécutable : c'est
   une bifurcation sans réponse unique, sur laquelle un agent hésite et revient
   en arrière. Décider dans l'issue et justifier. Contre-exemple : le point 3
   de #269, tranché explicitement dans #270 — qui a réussi en 243 s.

4. **Vérifier les prémisses dans le code avant d'affirmer une cause.** Une
   issue qui part d'un diagnostic faux fait chercher un bug inexistant.
   Contre-exemple : #259, dont l'hypothèse (`nomsProjetsDisponibles()`
   retournant vide) était fausse — l'agent l'a démontré, correctement, mais
   après 558 s.

5. **Distinguer un bug d'une évolution.** Demander à Alain ce qu'il ATTEND
   avant de qualifier un comportement de défaillance. Contre-exemple : #259
   traitait comme un bug ce qui était une demande de fonctionnalité (le toggle
   du bouton « Tous »), livrée ensuite par #262.

6. **Une issue, un périmètre.** Six livrables hétérogènes dans une même issue
   (code + test + doc + mesure + rapport) multiplient les points de blocage et
   rendent l'échec total plutôt que partiel. Préférer découper.

Ajouter également un rappel court : le TIMEOUT déclaré doit refléter la
complexité réelle estimée — c'est aussi le seul signal de difficulté dont
dispose la calibration automatique (§19).

Ne rien changer au format d'en-tête ni aux autres parties du §3.

## Résultat attendu

Diff committé localement (jamais poussé). Rapport citant le texte complet de
la sous-section ajoutée. Entrée `CHANGELOG.md` et pied de page selon la
convention (#253).
```

---

## Issue B — prévalidation par l'agent, avant de travailler

```
#Titre: Consignes : faire refuser une issue inexécutable en début de traitement plutôt qu'après trois timeouts

| PROJET  | bridge_agent |
| TIMEOUT | 900s |

## Contexte

Quand une issue est mal formée, le système ne s'en aperçoit qu'après avoir
épuisé ses trois tentatives. Cas réel #269 : 900 s × 3, soit 5415 secondes
consommées, aucun livrable, et deux résidus de debug laissés versionnés dans
l'arbre de travail par les tentatives successives.

Or `diagnostiquer_echec` (déclenché APRÈS l'échec définitif) avait identifié
les quatre défauts de cette issue avec une justesse remarquable : mesure plus
longue que le budget, précondition invérifiable par l'agent, décisions de
conception laissées ouvertes, tâche à embranchements multiples.

Ce même jugement, exercé AVANT la première tentative, ramènerait le coût de
45 minutes à quelques dizaines de secondes.

**Conception retenue — et pourquoi.** Le contrôle est une CONSIGNE injectée
dans le prompt, pas un verrou codé dans `watcher.py`. Raison : un validateur
en dur créerait un blocage circulaire — s'il déraillait et refusait tout,
l'issue qui le corrigerait serait refusée à son tour, et il faudrait un label
d'échappement plus une règle de repli. Une consigne ne peut pas bloquer
structurellement, se lève par une simple phrase, et ne coûte aucune
invocation supplémentaire (l'agent lit déjà l'issue au démarrage).

Contrepartie assumée : une consigne peut être ignorée (cf. #243/#244). Le
pire cas est alors le comportement actuel, jamais une régression.

## Tâche demandée

1. Ajouter à `consignes/globales.md` un rappel de **prévalidation**, placé en
   tête des rappels systématiques (avant même la règle du `git push`) — c'est
   le premier geste attendu, avant toute lecture de code.

   Il doit demander à l'agent, AVANT de commencer le travail, de vérifier
   trois points objectifs :

   - **Budget** : la tâche demande-t-elle des attentes incompressibles
     (mesures, sommeils, exécutions longues) dont la somme dépasse ou approche
     le TIMEOUT de l'issue ?
   - **Préconditions** : la tâche exige-t-elle un état que l'agent ne peut ni
     créer ni constater (navigateur ouvert, VM démarrée, action humaine
     concurrente) ?
   - **Décisions ouvertes** : la tâche demande-t-elle de choisir entre
     plusieurs options de conception sans que l'issue tranche ?

2. **Formuler le refus de façon conservatrice.** Ces critères doivent être
   objectifs et vérifiables par simple lecture de l'issue — jamais un jugement
   de valeur sur la pertinence de la demande. La consigne doit dire
   explicitement : **en cas de doute, exécuter la tâche**. Un refus abusif
   coûte plus cher qu'une tentative qui échoue, puisqu'il exige une
   intervention humaine.

3. En cas de refus, l'agent doit : ne modifier AUCUN fichier, ne faire AUCUN
   commit (pas même le commit de sauvegarde), et produire un rapport
   commençant par `❌` qui nomme précisément lequel des trois critères est en
   cause et pourquoi. Un refus doit être aussi informatif que le diagnostic
   automatique actuel.

4. **Échappement** : documenter dans la même consigne qu'une phrase explicite
   dans le corps de l'issue lève la prévalidation, avec un libellé exact et
   reconnaissable à retenir — proposition : `PRÉVALIDATION : ignorée`. La
   consigne doit préciser que l'agent, voyant cette mention, procède sans
   vérifier. C'est ce qui garantit qu'aucune issue ne peut être bloquée
   définitivement, y compris celle qui corrigerait ce mécanisme.

5. Mettre à jour le **§12.1** (parenthèse résumant les rappels globaux dans le
   tableau des trois couches) pour mentionner la prévalidation.

6. Documenter le mécanisme et son échappement dans le **§3**, à la suite de la
   checklist de rédaction ajoutée par l'issue A — c'est là que Claude Chat le
   lira. Si l'issue A n'a pas encore été traitée, placer la mention à
   l'endroit le plus cohérent du §3 et le signaler dans le rapport.

7. Entrée `CHANGELOG.md` et pied de page selon la convention (#253).

## Hors périmètre — ne pas faire

Aucune modification de `watcher.py` : pas de validateur codé en dur, pas de
label, pas de nouveau champ d'en-tête. Le mécanisme est entièrement porté par
la consigne injectée, délibérément.

## Résultat attendu

Diff committé localement (jamais poussé). Rapport citant le texte complet du
rappel ajouté à `consignes/globales.md`, et confirmant que `watcher.py` n'a
pas été touché.
```

---

## Après application — quoi observer

- Le déploiement d'une consigne ne demande **qu'un push** : `_lire_consigne`
  relit le fichier sur disque à chaque traitement, aucun redémarrage.
- Surveiller les **premiers refus** : s'ils portent sur des issues qui étaient
  en réalité exécutables, c'est que la formulation est trop stricte — corriger
  vers plus de tolérance, la consigne devant privilégier l'exécution en cas de
  doute.
- Si à l'inverse des issues manifestement mal formées passent quand même, la
  consigne est ignorée : envisager alors le durcissement en code, avec cette
  fois le label d'échappement et la règle « échec du validateur = laisser
  passer ».
