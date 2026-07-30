# Backlog Bridge_Agent

Idées et pistes non prioritaires, à réaliser éventuellement plus tard.
Alain peut modifier ce fichier directement, sans passer par une issue.

---
## Empecher Claude Chat de créer des issues trop détailler
Parfois, Claude Chat ecrit de tres longue issue en détaillant beaucoup trop le code et ce faisant fait le travail de CCL.  Il faut trouver un moyen(consigne ou autre) pour le maintenir dans des issues de plus haut niveau.  Exemple d'issue détaillé ci-après:

`#Titre: Fix JavascriptException callback perdu lors navigation pywebview (reprendre_partie / jeu_retour_accueil)

| PROJET | rummikub |

## Contexte

Au lancement du jeu, des `JavascriptException` apparaissent en boucle dans le
terminal :

    webview.errors.JavascriptException: window.pywebview._returnValuesCallbacks
    ["reprendre_partie"]["<id>"] is not a function

Même chose pour `jeu_retour_accueil`. Aucun crash visible côté UI, mais les
erreurs sont répétées et gênent la lisibilité du terminal.

**Cause** : quand JS appelle `api.reprendre_partie()` (ou `jeu_retour_accueil()`
ou `lancer_nouvelle_partie()`), pywebview traite l'appel dans un thread interne
`Thread-N (_call)`. Ce thread exécute la méthode Python, qui appelle
`self._window.load_url(...)` — ce qui navigue immédiatement vers la nouvelle
page et **détruit le contexte JS de la page source**, y compris les entrées de
`window.pywebview._returnValuesCallbacks`. Ensuite, pywebview tente d'invoquer
le callback de retour sur la nouvelle page, où il n'existe pas → `TypeError`.

**Fix standard pour pywebview** : différer l'appel `load_url` dans un thread
daemon avec `time.sleep(0.05)`, pour laisser pywebview envoyer la valeur de
retour à la page encore chargée avant de naviguer.

## Tâche demandée

Modifier `src/rummikub/ui/api.py` uniquement.

Ajouter en tête de fichier (après les imports existants) :

```python
import threading
import time
```

Remplacer les trois méthodes de navigation comme suit :

**1. `lancer_nouvelle_partie`**

Avant :
```python
def lancer_nouvelle_partie(self, config):
    self._app.naviguer_vers_jeu(config)
    return {"ok": True}
```

Après :
```python
def lancer_nouvelle_partie(self, config):
    def _go():
        time.sleep(0.05)
        self._app.naviguer_vers_jeu(config)
    threading.Thread(target=_go, daemon=True).start()
    return {"ok": True}
```

**2. `reprendre_partie`**

Avant :
```python
def reprendre_partie(self, pid):
    etat = Stockage.charger_partie(pid)
    if not etat:
        return {"ok": False, "erreur": "Partie introuvable"}
    self._app.reprendre_jeu(etat)
    return {"ok": True}
```

Après :
```python
def reprendre_partie(self, pid):
    etat = Stockage.charger_partie(pid)
    if not etat:
        return {"ok": False, "erreur": "Partie introuvable"}
    def _go():
        time.sleep(0.05)
        self._app.reprendre_jeu(etat)
    threading.Thread(target=_go, daemon=True).start()
    return {"ok": True}
```

**3. `jeu_retour_accueil`**

Avant :
```python
def jeu_retour_accueil(self):
    self._app.naviguer_vers_accueil(); return {"ok": True}
```

Après :
```python
def jeu_retour_accueil(self):
    def _go():
        time.sleep(0.05)
        self._app.naviguer_vers_accueil()
    threading.Thread(target=_go, daemon=True).start()
    return {"ok": True}
```

Aucune autre modification. Aucun autre fichier touché.

## Résultat attendu

- `api.py` modifié avec les trois méthodes corrigées et les imports `threading`
  et `time` ajoutés.
- Vérifier que le fichier compile sans erreur (`python3 -c "import
  src.rummikub.ui.api"` ou `python3 -m py_compile
  src/rummikub/ui/api.py` depuis la racine du projet).
- Commit de sauvegarde puis commit du fix.
- Rapport confirmant l'absence d'erreur de compilation.`

## Calibration automatique du TIMEOUT — trois défauts à corriger

**Contexte** : la formule du §19 est
`TIMEOUT_suggéré = max((duree_typique + k × variabilite) × F × backoff, plancher)`
— EWMA par `projet|TYPE|mode`, demi-vie 15 issues, k=4, plancher 30 s,
facteur d'ambiance `F` de demi-vie 4 h. Cette valeur reste purement
INDICATIVE : le TIMEOUT réellement appliqué est celui de l'en-tête de
l'issue (`extraire_timeout`).

**Trois défauts identifiés le 29/07/2026** :
1. `F` n'est jamais alimenté — `_detecter_tag_reseau()` retourne toujours
   `None`, donc `F_reseau`/`F_local` restent à 1.0 et le facteur
   d'ambiance n'influence rien (déjà listé dans les limitations du §19).
2. Même si le tag existait, `maj_calibration_timeout` retombe toujours sur
   `F_local` par défaut sans le lire — c'est un second bug, distinct du
   premier.
3. La clé `projet|TYPE|mode` mélange des populations incompatibles : une
   édition de doc de 250 s et une refonte de `watcher.py` avec tests de
   1800 s finissent dans la même case. La médiane qui en sort n'a pas de
   sens (observé : 2794 s suggérés pour une issue qui en a pris 351).

**Idée** : séparer explicitement le coût de la TÂCHE et l'état de la
MACHINE (réseau, RAM, congestion) — c'est déjà la structure de la formule,
mais les deux moitiés sont mal alimentées. La composition doit rester un
PRODUIT, pas une somme : un agent enchaîne les allers-retours réseau, donc
une latence dégradée étire la durée proportionnellement au travail au lieu
d'ajouter un forfait fixe. Exemple : wifi à +40 % → une doc passe de 250 à
350 s, une refonte de 1800 à 2520 s ; une somme unique surestimerait la
première et sous-estimerait gravement la seconde.

**Deux signaux à capter, faciles et probablement les plus discriminants** :
- le TIMEOUT déclaré dans l'en-tête, comme proxy de complexité — Claude
  Chat estime déjà la difficulté au moment de rédiger ; segmenter la
  calibration là-dessus séparerait mécaniquement les deux populations,
  sans nouvelle donnée à collecter ;
- une mesure de latence réseau au démarrage du traitement, pour alimenter
  enfin `tag_reseau` et corriger du même coup le défaut 2.

**Statut** : diagnostic établi le 29/07/2026, aucune implémentation
lancée. À reprendre à froid — le sujet touche des EWMA et des choix de
modélisation qu'on prendrait mal à la légère.

---

## Archivage de logs/historique_durees.json

**Contexte** : le fichier accumule depuis mai sans jamais être purgé —
682 entrées, 112 Ko au 29/07/2026 — et il est relu puis réécrit à chaque
clôture d'issue. Répartition : scrabble 284, bridge_agent 237, alchess 58,
rummikub 24, actualise 22, bloc_score 21, ecole 18, ff_galerie 13,
diagnostique_programme 5. Les entrées `ff_galerie` datent de mai et ne
correspondent pas à un usage réel du bridge (projet piloté par EmailJS) ;
elles ne polluent aucun calcul — la calibration filtre par combinaison —
mais brouillent la lecture manuelle.

**Idée** : archiver les vieilles entrées pour contenir la taille du
fichier et rendre son contenu lisible.

**Point à concevoir avant implémentation, impératif** : ne PAS archiver
naïvement par mois. L'EWMA de la calibration a une demi-vie de 15 issues ;
une bascule mensuelle ferait repartir le calcul de zéro à chaque nouveau
mois, précisément pour les projets les plus actifs. Il faut soit archiver
sans rendre les entrées invisibles au calcul, soit assumer explicitement
la remise à zéro.

**Statut** : aucune urgence à 112 Ko. À traiter avant que le fichier
n'atteigne plusieurs Mo. Lié à l'entrée sur la calibration ci-dessus.

---

## Concurrence limitée aux issues mode_lecture

**Contexte** : `watcher.py` est aujourd'hui strictement séquentiel (une issue à
la fois, tous modes confondus, cf. §3 de BRIDGE_AGENT_DOC.md). Pour des tâches
en `mode_lecture` (ex. plusieurs audits Python/JS/CSS sur un même projet), ce
séquentiel n'est pas motivé par un risque réel : sans écriture disque, plusieurs
CCL peuvent lire le même dépôt simultanément sans conflit.

**Idée** : permettre à `watcher.py` de traiter plusieurs issues en **parallèle**
uniquement si elles sont **toutes** en `mode_lecture` — garde-fou strict
interdisant toute concurrence dès qu'une issue `mode_write` est impliquée (là,
le risque de conflit d'accès fichier reste réel).

**Points à concevoir avant implémentation** :
- Limites de débit API (Claude, GitHub) si plusieurs CCL appellent en même temps.
- Charge CPU/RAM du ThinkPad avec plusieurs CCL simultanés.
- Entremêlement des logs (un fichier de log par issue en cours ?).
- Détection fiable que TOUTES les issues d'un lot sont bien en mode_lecture avant
  d'autoriser le parallélisme (une seule mode_write dans le lot → tout repasse en
  séquentiel).

**Statut** : idée en attente, pas de développement lancé. Discuté le 24/07/2026,
suite à un timeout sur un audit Scrabble.

---

## Parallélisation en mode_write via git worktrees

**Contexte** : contrairement au cas précédent, paralléliser des tâches
`mode_write` sur un même dépôt pose un vrai risque de conflit d'accès fichier
si plusieurs CCL écrivent en même temps dans le même répertoire de travail.

**Idée** : utiliser les *git worktrees* — un dépôt git peut avoir plusieurs
répertoires de travail simultanés, chacun sur sa propre branche, tous rattachés
au même `.git` (pas de duplication lourde comme un clone complet) :

```bash
git worktree add ../Projet-tache1 -b tache-1-issue-XXX
git worktree add ../Projet-tache2 -b tache-2-issue-YYY
```

Chaque tâche parallèle travaille dans son propre dossier physique, sur sa
propre branche → zéro conflit d'accès fichier pendant l'exécution. Le risque
est déplacé au moment du **merge**, où git gère nativement les conflits
(visibles, résolubles), plutôt que de risquer une corruption silencieuse
pendant l'exécution.

**Ce qu'il faudrait construire** :
- Un champ dans l'en-tête d'issue (ex. `WORKTREE`, ou dérivé automatiquement du
  numéro d'issue) pour que le watcher sache dans quel worktree travailler,
  plutôt que dans le `REP_TRAVAIL` fixe du projet.
- Une étape de création/nettoyage des worktrees (`git worktree add` au
  démarrage, `git worktree remove` + `git branch -d` après merge — sinon ils
  s'accumulent).
- Rien à inventer côté verrouillage/détection de conflit : c'est le travail
  natif de git.

**Ce qu'il ne faut PAS automatiser** : le merge lui-même doit rester une étape
manuelle (ou explicitement validée par Alain), cohérente avec la règle actuelle
de vérification avant push — un merge automatique sans supervision humaine est
le genre d'endroit où l'autonomie de CCL doit rester limitée.

**Piste de test avant d'investir dans l'intégration native** : créer les
worktrees manuellement pour deux issues connues indépendantes, pointer les
`REP_TRAVAIL`/`PERIMETRE` de deux `.conf` temporaires vers ces deux worktrees,
et lancer deux watchers en parallèle sur ces configs — sans aucun changement
de code, pour valider le concept avant d'écrire le champ `WORKTREE` natif.

**Statut** : idée en attente, pas de développement lancé. Discuté le 24/07/2026.

---

## Mode mode_tmp_write — écriture scratch limitée pour outillage d'audit

**Contexte** : certains outils d'analyse (eslint flat config pour les
versions ≥ 9, linters divers) exigent un vrai fichier de config sur disque,
pas seulement une commande inline. Le mode_lecture actuel interdit toute
écriture, y compris hors dépôt — ce qui bloque ces outils. Note : ce n'est
PAS ce qui causait les timeouts observés sur Scrabble (#235 vs #238,
réglé par une consigne d'abandon immédiat au refus de permission) — c'est
un besoin distinct et réel, pour les cas où l'outil a effectivement besoin
d'un fichier de config.

**Proposition** (reçue via rapport d'audit Scrabble) : un troisième mode,
`mode_tmp_write`, avec :
- Écriture autorisée uniquement dans un chemin scratch bien défini et
  validé strictement côté watcher (ex. `/tmp/bridge_scratch_<projet>/`),
  jamais dans `REP_TRAVAIL` du projet. Validation stricte du chemin pour
  empêcher tout `../` ou équivalent remontant vers le dépôt.
- Toujours interdit, comme en lecture seule : `git commit`, `git push`,
  toute commande destructrice, toute écriture hors du chemin scratch.
- Nettoyage attendu en fin de tâche par CCL, idéalement complété par un
  nettoyage automatique du dossier scratch par le watcher en fin de
  traitement — pour ne pas reposer uniquement sur la consigne donnée à CCL.
- Conceptuellement plus proche du mode lecture seule que du mode écriture :
  pas de garde-fou "backup avant modification" nécessaire (aucun fichier du
  projet n'est jamais en jeu).

**Point de vigilance** : la garantie ne tient que si la validation du
chemin scratch est réellement stricte côté `watcher.py` — à concevoir avec
soin, pas seulement en confiance sur la consigne donnée à CCL.

**Statut** : idée en attente, pas de développement lancé. Reçue via rapport
d'audit Scrabble le 24/07/2026.
