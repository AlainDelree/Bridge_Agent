# Bridge inter-agents AlChess — Référence des tâches (issues)

## Vocabulaire

Pour SOURCE, DEST, RETOUR : **CC** = Claude Chat, **CCL** = Claude Code Linux, **CCW** = Claude Code Windows.
Remplacer `for-linux` par `for-windows` selon la cible.

## Labels disponibles

| Label | Rôle |
|-------|------|
| `bridge` | Marque l'issue comme tâche du bridge |
| `for-linux` | Cible : agent Linux (CCL), traité par `watcher.py` sur le ThinkPad |
| `for-windows` | Cible : agent Windows (CCW) sur la VM |
| `mode_write` | **ARME le mode écriture** (voir ci-dessous). À poser sciemment. |
| `done` | Ajouté automatiquement par le watcher quand l'issue est traitée |

## ⚠️ Mode lecture seule vs mode écriture (IMPORTANT)

Le watcher lance Claude Code de deux façons selon les labels :

- **Sans `mode_write` (défaut)** → **LECTURE SEULE**. CCL peut lire, `grep`,
  analyser et rapporter, mais **ne peut pas écrire de fichier, ni exécuter, ni
  committer**. C'est le mode sûr, idéal pour les diagnostics.

- **Avec `mode_write`** → **MODE ÉCRITURE**. Le watcher ajoute
  `--dangerously-skip-permissions` : CCL peut écrire des fichiers, exécuter des
  commandes et committer. Garde-fous inscrits dans le prompt :
  - backup pinné obligatoire avant toute modification ;
  - **JAMAIS de `git push`** (Alain pousse lui-même, après vérification) ;
  - aucune commande destructrice non explicitement demandée.

Le mode est visible : le terminal du watcher affiche `MODE ÉCRITURE ARMÉ`, et le
commentaire ACK sur l'issue indique « Mode : **ÉCRITURE ⚠️** » ou « lecture seule ».

**Règle d'usage** : pour un diagnostic → ne PAS mettre `mode_write`. Pour une
modification de code/fichier → ajouter `mode_write`, et toujours relire le diff /
committer / pusher soi-même ensuite.

---

## MODÈLE — Tâche COMPLÈTE (lecture seule / diagnostic)

```bash
gh issue create \
  --repo AlainDelree/AlChess \
  --title "TITRE COURT" \
  --label "bridge,for-linux" \
  --body "## Entête

| Champ | Valeur |
|-------|--------|
| SOURCE | CC |
| DEST | CCL |
| RETOUR | CC |
| PARCOURS | CC → CCL |
| CONV_ID | url_conversation |
| PRIORITE | normale |
| ACK_REQUIS | oui |
| TIMEOUT | 300s |
| RETRY | 3 |
| DEPENDS_ON | aucun |
| CHECKSUM | aucun |

## Contexte

Pourquoi cette tâche existe.

## Tâche demandée

Description précise et actionnable. (LECTURE SEULE : ne rien modifier.)

## Résultat attendu

Ce que l'agent doit produire.

## Retour attendu

Ce que l'agent doit renvoyer une fois terminé."
```

## MODÈLE — Tâche LÉGÈRE (lecture seule / diagnostic)

```bash
gh issue create \
  --repo AlainDelree/AlChess \
  --title "TITRE COURT" \
  --label "bridge,for-linux" \
  --body "## Entête

| Champ | Valeur |
|-------|--------|
| SOURCE | CC |
| DEST | CCL |
| RETOUR | CC |

## Tâche

Description courte et actionnable. (LECTURE SEULE : ne rien modifier.)

## Résultat attendu

Ce que l'agent doit produire ou confirmer."
```

## MODÈLE — Tâche ÉCRITURE (modification de code/fichier)

> Ajouter le label `mode_write`. Toujours exiger un backup pinné et interdire le push.

```bash
gh issue create \
  --repo AlainDelree/AlChess \
  --title "TITRE COURT" \
  --label "bridge,for-linux,mode_write" \
  --body "## Entête

| Champ | Valeur |
|-------|--------|
| SOURCE | CC |
| DEST | CCL |
| RETOUR | CC |
| MODE | ÉCRITURE |

## Contexte

Pourquoi cette modification est nécessaire.

## Tâche demandée

Modification précise à appliquer (fichier(s), logique attendue).

## Contraintes de sécurité

- Faire un backup pinné AVANT toute modification :
  python -m nicsoft.utils.backup_manager --pin --label \"avant-<description>\"
- NE PAS committer.
- NE PAS faire git push.
- Aucune commande destructrice.

## Retour attendu

- Le diff complet des modifications appliquées (pour validation par Alain).
- Confirmation qu'aucun commit ni push n'a été fait."
```

---

## Prérequis d'exécution

- `watcher.py` doit tourner : `python3 ~/bridge-agent/watcher.py`
- Le label `mode_write` doit exister sur le dépôt (créé une fois via `gh label create`).
- Le watcher lance CCL depuis `~/NicLink` comme répertoire de travail.

## Historique — capacités validées

- **2026-07-03** : mode écriture (`mode_write`) ajouté au watcher et **validé** par
  un test (issue #10 : création d'un fichier bidon, sans commit ni push — garde-fous
  confirmés). Le bridge diagnostique en lecture seule par défaut, et n'écrit que sur
  issue explicitement armée.
