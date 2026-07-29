# Bridge_Agent — notes de reprise

*Rédigé le 29 juillet 2026. À relire au début d'une nouvelle conversation.*

---

## 1. Calibration automatique du TIMEOUT — diagnostic

### Ce qui existe (§19 de `BRIDGE_AGENT_DOC.md`)

```
TIMEOUT_suggéré = max( (duree_typique + k × variabilite) × F × backoff , plancher )
```

| Terme | Rôle | Valeur actuelle |
|---|---|---|
| `duree_typique` | EWMA des durées observées, par `projet\|TYPE\|mode` | demi-vie 15 issues |
| `variabilite` | EWMA de l'écart à `duree_typique` (« nervosité ») | — |
| `k` | Marge de sécurité | 4 |
| `F` | Facteur d'ambiance (`F_reseau` ou `F_local`) | **toujours 1.0** |
| `backoff` | ×1,5 par timeout, reset après 3 succès rapides | — |
| plancher | `TIMEOUT_SUGGERE_PLANCHER` | 30 s |

État persisté dans `logs/etat_timeout.json` et `logs/etat_ambiance.json`
(demi-vie 4 h pour l'ambiance).

**Important** : `TIMEOUT_suggéré` n'est aujourd'hui qu'**indicatif**. Le TIMEOUT
réellement appliqué reste celui de l'en-tête de l'issue (`extraire_timeout`).

### Les deux défauts identifiés

**Défaut 1 — `F` n'est jamais alimenté.** `_detecter_tag_reseau()` retourne
toujours `None` (aucun champ d'en-tête ni détection automatique ne le
renseigne). `F_reseau` et `F_local` restent donc à leur valeur neutre, et le
facteur d'ambiance n'influence rien. Déjà signalé dans les limitations connues
du §19.

**Défaut 2 — le tag n'est pas lu même s'il existait.**
`maj_calibration_timeout` retombe toujours sur `F_local` par défaut, sans
consulter `_detecter_tag_reseau(body)`. Ce sont donc **deux bugs distincts** :
même en peuplant le tag, le facteur choisi serait faux.

**Défaut 3 — les catégories mélangent des populations incompatibles.** La clé
`projet|TYPE|mode` range dans la même case une édition de doc de 250 s et une
refonte de `watcher.py` avec tests de 1800 s. La médiane qui en sort n'a pas de
sens, d'où les `TIMEOUT_suggéré` incohérents observés (2794 s suggérés pour une
issue qui en a pris 351).

### Direction proposée (à décider à froid)

L'idée d'Alain : séparer **le coût de la tâche** et **l'état de la machine**
(réseau, RAM, congestion). C'est exactement la structure de la formule
existante — `(duree_typique + k × variabilite)` pour la tâche, `F` pour
l'environnement.

**Composition : produit, pas somme.** Un agent passe son temps en allers-retours
réseau ; une tâche qui en fait cent souffre cent fois d'une latence dégradée,
une tâche qui en fait dix n'en souffre que dix fois. L'environnement *étire* la
durée proportionnellement au travail, il n'ajoute pas un forfait fixe.

> Exemple : wifi dégradé à +40 %. Édition de doc 250 s → 350 s. Refonte
> 1800 s → 2520 s. Une somme unique (+300 s) surestimerait la première et
> sous-estimerait gravement la seconde.

**Deux signaux à capter, faciles et probablement les plus discriminants :**

1. **Le TIMEOUT déclaré dans l'en-tête** comme proxy de complexité. Claude Chat
   estime déjà la difficulté au moment de rédiger (300 s pour une retouche,
   1800 s pour du code avec tests). Segmenter la calibration là-dessus
   séparerait mécaniquement les deux populations, sans nouvelle donnée à
   collecter.
2. **Une mesure de latence réseau** au démarrage du traitement, pour alimenter
   enfin `tag_reseau` — et corriger au passage le défaut 2.

---

## 2. Archivage de `logs/historique_durees.json`

### État au 29/07/2026

- **682 entrées, 112 Ko**, accumulées depuis mai — jamais purgé.
- Relu et réécrit à chaque clôture d'issue.

| Projet | Entrées |
|---|---|
| scrabble | 284 |
| bridge_agent | 237 |
| alchess | 58 |
| rummikub | 24 |
| actualise | 22 |
| bloc_score | 21 |
| ecole | 18 |
| ff_galerie | 13 |
| diagnostique_programme | 5 |

Les entrées `ff_galerie` datent de mai et ne correspondent pas à un usage réel
du bridge (projet piloté par EmailJS). Elles ne polluent aucun calcul — la
calibration filtre par combinaison — mais brouillent la lecture manuelle.

### Contrainte à respecter

**Ne pas archiver naïvement par mois.** L'EWMA a une demi-vie de 15 issues :
une bascule mensuelle ferait repartir la calibration de zéro à chaque nouveau
mois, précisément pour les projets les plus actifs. Il faut soit archiver les
vieilles entrées **sans les rendre invisibles au calcul**, soit assumer
explicitement la remise à zéro.

Rien d'urgent à 112 Ko. À traiter avant que ça n'atteigne plusieurs Mo.

---

## 3. Contexte utile pour interpréter les durées

- **Depuis le 27/07, Alain travaille en wifi d'hôtel.** Facteur plausible
  d'allongement des durées — l'agent fait des allers-retours réseau en
  permanence pendant son travail. C'est précisément ce que `F` devrait capter.
- Les trois durées aberrantes du 29/07 (900 s, 1805 s, 2710 s) sont les trois
  tentatives ratées de l'issue #269, mal calibrée (mesure infaisable dans le
  TIMEOUT, décisions laissées ouvertes). 5415 s consommées pour aucun livrable.
- **Leçon retenue** : une issue nette coûte 250–550 s ; une issue avec une
  exigence infaisable coûte 45 min et ne livre rien. Le facteur limitant est la
  qualité de la commande, pas l'agent.

---

## 4. Autres sujets en attente

### Consommation d'API — état après correctifs

Mesuré avec `scripts/mesurer_api.py` (issue #263) :

| Moment | Points/heure | Commentaire |
|---|---|---|
| Avant #270 | ≈ 5070 | quota épuisé en 59 min |
| Après #270 | ≈ 1078 | soutenable indéfiniment |

Le poste dominant était **l'interface web ouverte** (badges de temps restant,
≈ 3840 pts/h), supprimé par #270. Le premier poste restant est le **poller de
notifications** (≈ 960 pts/h) — aucune urgence.

**À noter** : `core.used` reste à 0. Les **5000 points REST sont intacts et
inutilisés** pendant que GraphQL sature. Piste possible : basculer certaines
requêtes sur l'API REST, qui a son propre quota.

### Levier non traité — ne charger que les projets actifs

`chargerListeIssues()` appelle `nomsProjetsDisponibles()`, qui lit le `<select>`
global : **tous** les projets configurés, pas ceux qui sont actifs dans le
filtre. Avec 8 projets configurés et 2 affichés, on fait donc 8 appels pour en
montrer 2.

Or #271 a mesuré que le coût GraphQL **ne dépend pas de `--limit`** (1 point par
appel, quelle que soit la taille). Ce sont donc les **appels** qui comptent, pas
leur volume. Ne charger que les projets actifs diviserait le temps de
rafraîchissement et le coût par quatre.

*Point délicat à traiter* : que se passe-t-il quand on réactive un projet
masqué ? Sa liste serait vide — il faudrait la charger à ce moment-là.

### Filet de sécurité sur les rapports d'agent (décidé, non écrit)

Valider **positivement** le format du rapport : présence de la ligne
`✅`/`❌` et de la ligne `Commits`. Un écart est traité comme un **échec**
(issue relancée) plutôt que comme un succès.

Les quatre cas connus d'abandon déguisé auraient tous été attrapés : #241,
#242, #254 (« j'attends la notification… ») et #260.

Une option plus lourde avait été envisagée puis mise en réserve : faire exécuter
les commandes longues par le watcher lui-même, en deux invocations de l'agent
séparées par l'attente. À considérer comme **filet de sécurité** (garantir
l'aboutissement même si l'agent lâche), pas comme optimisation.

### Petits points

- **`git ls-remote` au lieu de `git fetch`** dans la route pièces jointes
  (#248) : le `fetch` écrit `FETCH_HEAD` dans le clone de travail, ce qu'on
  voulait justement éviter. `ls-remote` suffit et ne touche aucune référence.
- **`DELAI_INACTIVITE_MIN = 0` côté VM** : gain quota **≈ 0** (la mesure #263 l'a
  établi — NSSM relance à la même cadence). Reste un problème de bruit dans les
  logs, pas de quota. Priorité basse.
- **§10, point 3** : le garde-fou ajouté par #268 est rédigé comme une note
  d'avertissement dans une liste numérotée d'actions. À reformuler en encart un
  jour — sans conséquence pratique.

---

## 5. Déploiement — rappel des gestes qui s'oublient

| Fichier modifié | Geste nécessaire |
|---|---|
| `watcher.py` | push, `git pull` dans la VM, **`nssm restart CCW-Watcher`** |
| `nouveau_projet.py`, `app/*.py` | push, **redémarrer `new_issue.py`** |
| `static/js/*.js`, `*.css` | push, **`Ctrl+F5`** dans le navigateur |
| `consignes/*.md` | push seul — relues sur disque à chaque traitement |
| `BRIDGE_AGENT_DOC.md` | push seul |

Le clone `C:\CCW\Bridge_Agent` de la VM **n'est jamais mis à jour
automatiquement** (le `git pull --ff-only` du watcher porte sur `REP_TRAVAIL`,
qui est le partage, pas le clone du code). Documenté au §16 depuis #240 —
c'était la cause des 80 commits de retard.
