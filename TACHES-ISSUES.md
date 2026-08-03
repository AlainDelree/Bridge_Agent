# Bridge inter-agents AlChess — Référence des tâches (issues)

Document de référence pour Claude Chat (CC) lors de la création d'issues
vers Claude Code Linux (CCL) via Bridge_Agent.

---

## Labels disponibles

| Label | Rôle |
|-------|------|
| `bridge` | Marque l'issue comme tâche du bridge |
| `for-linux` | Cible : agent Linux (CCL) sur le ThinkPad |
| `for-windows` | Cible : agent Windows (CCW) sur la VM |
| `mode_write` | **ARME le mode écriture** — CCL peut modifier des fichiers et committer |
| `mode_scratch` | **ARME la lecture active** — CCL peut écrire uniquement dans un dossier scratch temporaire |
| `done` | Posé automatiquement par le watcher en cas de succès |
| `needs-human` | Posé automatiquement après 3 échecs — stoppe le retraitement |
| `notif_pc` | Notification bureau (notify-send) à la clôture |
| `notif_gsm` | Notification push (ntfy) à la clôture |
| `notif_tous` | Les deux |

---

## Modes de traitement

| Mode | Label | Ce que CCL peut faire |
|------|-------|----------------------|
| **Lecture seule** (défaut) | aucun | Lire, grep, analyser, rapporter. Aucune écriture. |
| **Lecture active** | `mode_scratch` | Lire + écrire uniquement dans `/tmp/bridge_scratch_alchess/` (outils nécessitant un fichier de config sur disque, ex. linters). Le livrable reste un rapport. |
| **Écriture** | `mode_write` | Modifier des fichiers, exécuter des commandes, committer. Backup obligatoire avant toute modification. Jamais de `git push`. |

Le mode est visible dans le log du watcher (`MODE ÉCRITURE ARMÉ` ou `MODE LECTURE ACTIVE`) et dans le commentaire ACK de l'issue.

**Règle** : pour un diagnostic → lecture seule (défaut). Pour un outil nécessitant un fichier temporaire → lecture active. Pour une modification de code → écriture, et toujours relire le diff avant de pousser.

---

## Champs d'en-tête reconnus

À placer en tableau markdown en début de corps de l'issue. Tous optionnels sauf `PROJET`.

| Champ | Exemple | Effet |
|-------|---------|-------|
| `PROJET` | `alchess` | **Obligatoire** — nom du projet cible |
| `MODE` | `lecture` / `écriture` / `lecture active` | Auto-détecté par new_issue.py, pré-sélectionne le radio Mode |
| `TIMEOUT` | `600s` | Surcharge le timeout par défaut (300s) |
| `MODELE` | `claude-sonnet-5` | Force un modèle CCL spécifique |
| `SUITE_DE` | `#42` | Indique que cette issue fait suite à l'issue #N |
| `TYPE` | `chef` / `ouvrier` | Rôle dans le pattern multi-agent (§14 de la doc Bridge_Agent) |
| `LABELS` | `for-windows` | Labels supplémentaires ajoutés à ceux posés d'office |

---

## Format des issues — new_issue.py

Toutes les issues passent par l'interface web `new_issue.py` (ou son alias `bridge`).
Coller le bloc suivant dans le champ **Corps** — le champ `#Titre:` est
auto-détecté et remplit le titre.

```
#Titre: Titre court et actionnable
| PROJET | alchess |
| MODE   | lecture |

## Contexte
Pourquoi cette tâche existe.

## Tâche demandée
Description précise. Indiquer explicitement si LECTURE SEULE.

## Résultat attendu
Ce que CCL doit produire ou confirmer.
```

Pour envoyer plusieurs issues en un seul copier-coller (mode lot), enchaîner
plusieurs blocs `#Titre:` dans le même corps — le bouton devient
« Envoyer le lot (N issues) ». Le MODE est commun à tout le lot (radio du
formulaire), les autres champs d'en-tête sont par bloc.

---

## MODÈLE — Tâche lecture seule / diagnostic

```
#Titre: Titre court et actionnable
| PROJET  | alchess |
| MODE    | lecture |
| TIMEOUT | 300s    |

## Contexte
Pourquoi cette tâche existe.

## Tâche demandée
Description précise et actionnable. LECTURE SEULE : ne rien modifier.

## Résultat attendu
Ce que CCL doit produire ou confirmer.
```

---

## MODÈLE — Tâche lecture active (outil nécessitant un fichier temporaire)

```
#Titre: Titre court et actionnable
| PROJET  | alchess         |
| MODE    | lecture active  |
| TIMEOUT | 300s            |

## Contexte
Pourquoi cet outil nécessite de la lecture active plutôt que la lecture seule.

## Tâche demandée
Description précise. CCL peut écrire dans /tmp/bridge_scratch_alchess/ uniquement.
Le livrable attendu est un rapport, pas une modification du projet.

## Résultat attendu
Rapport produit par l'outil (ex. liste d'erreurs de lint, résultats d'analyse).
```

---

## MODÈLE — Tâche écriture (modification de code/fichier)

```
#Titre: Titre court et actionnable
| PROJET  | alchess  |
| MODE    | écriture |
| TIMEOUT | 300s     |

## Contexte
Pourquoi cette modification est nécessaire.

## Tâche demandée
Modification précise à appliquer (fichier(s), logique attendue).
Ne pas fournir le code complet — décrire le problème et l'intention ;
CCL lit les fichiers source et fait l'implémentation lui-même.

## Résultat attendu
- Diff des modifications appliquées.
- Confirmation qu'aucun push n'a été fait.
```

---

## Parallélisation mode_write (depuis #337)

Plusieurs issues `mode_write` d'un même projet peuvent tourner **en parallèle**
via git worktrees. Deux issues touchant les mêmes fichiers ou zones de code
peuvent générer un conflit de merge à résoudre manuellement.

**Recommandation** : scoper chaque issue sur un périmètre de fichiers aussi
distinct que possible des autres issues `mode_write` en cours.

---

## Prérequis d'exécution

- Le watcher AlChess démarre **automatiquement** à la création d'une issue
  `for-linux` via new_issue.py — aucune action manuelle requise.
- Il s'éteint automatiquement après `DELAI_INACTIVITE_MIN` minutes d'inactivité
  (défaut : 20 min).
- Périmètre CCL : `/home/alain/NicLink` — CCL refuse tout travail hors de ce dossier.
