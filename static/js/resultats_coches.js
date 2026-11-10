// resultats_coches.js — case « traité/lu » de l'onglet Résultats : état SERVEUR,
// copie fiable au cochage, « Cocher tout » et bouton de remise à zéro
// (refonte web, étape 5b, issue #636 — ARCHITECTURE.md §6.7).
//
// POURQUOI UN MODULE DÉDIÉ (et pas dans resultats.js)
//   resultats.js est déjà le moteur de DONNÉES/ÉVÉNEMENTS/BADGES (liste, /stream,
//   décompte TIMEOUT). La case à cocher est une préoccupation distincte et
//   volumineuse (état serveur synchronisé, migration du localStorage, moteur de
//   copie presse-papier fiable, périmètre « Cocher tout » / pastilles / remise à
//   zéro) : la loger dans resultats.js le rendrait illisible. Un module propre
//   garde chaque fichier centré sur une responsabilité (choix expliqué dans le
//   rapport de l'issue #636).
//
// CE QUE CE MODULE A SORTI DE app.js
//   - cleCocheResultat / estResultatCoche / basculerCocheResultat : la case ne
//     vit plus dans le localStorage, mais dans store.casesCochees, synchronisé
//     avec le serveur via les routes /cases-cochees (issue #629). Une SEULE
//     requête GET par projet au chargement (jamais une par issue).
//   - La copie déclenchée au cochage (ex-copierToutEtDiffDepuisBadge) et les
//     copies apparentées (badges ✅/Diff/All) : refondues autour d'un moteur
//     unique qui ENGAGE la copie PENDANT le geste utilisateur (correctif du
//     défaut d'activation) et ne signale JAMAIS un faux succès.
//   - cocherToutesVisibles : élargi au même périmètre que les pastilles.
//   - Nouveau bouton de remise à zéro (toutes issues chargées, tous projets).
//
// SOURCE DE VÉRITÉ
//   store.casesCochees = { nomProjet: [numero, ...] }. app.js n'en garde AUCUN
//   miroir : estResultatCoche() délègue ici (via le pont), et le rendu d'une
//   ligne lit donc toujours l'état serveur consolidé.

import { store } from './socle/store.js';
import { api } from './socle/api.js';
import { toasts } from './socle/toasts.js';
import { appelerAncien } from './socle/pont.js';
import * as persistance from './socle/persistance.js';
import { sse } from './socle/sse.js';
import {
  diagnostiquer, rejouerFileEnAttente, diagnosticActif, ligneRedessineeRecemment,
} from './socle/diagnostic_copie.js';

// ─────────────────────────────────────────────────────────────────────────────
// 1. LOGIQUE PURE (testée sous Node — voir static/js/tests/resultats_coches.test.js)
//    Aucune dépendance au DOM, au réseau ni au store : tout est passé en argument.
// ─────────────────────────────────────────────────────────────────────────────

// Normalise un numéro d'issue en entier (le DOM porte des chaînes, le serveur
// des entiers) — pour que la comparaison coché/décoché soit fiable des deux côtés.
export function normaliserNumero(numero) {
  return Number(numero);
}

// Fusionne la réponse serveur GET /cases-cochees/<projet> dans la tranche
// casesCochees : REMPLACE la liste du projet concerné (le serveur fait foi),
// dédoublonnée et normalisée en entiers. Les autres projets sont conservés.
export function fusionnerCasesServeur(etat, projet, numeros) {
  const propres = [...new Set((numeros || []).map(normaliserNumero))]
    .filter((n) => Number.isFinite(n));
  return { ...(etat || {}), [projet]: propres };
}

// Vrai si (projet, numero) est coché dans la tranche donnée.
export function estCocheDansEtat(etat, projet, numero) {
  const n = normaliserNumero(numero);
  const liste = etat && etat[projet];
  return Array.isArray(liste) && liste.includes(n);
}

// Ajoute (projet, numero) — retour immuable, idempotent.
export function ajouterDansEtat(etat, projet, numero) {
  const n = normaliserNumero(numero);
  if (estCocheDansEtat(etat, projet, numero)) return etat;
  const liste = (etat && etat[projet]) || [];
  return { ...(etat || {}), [projet]: [...liste, n] };
}

// Retire (projet, numero) — retour immuable, idempotent (supprime la clé projet
// si sa liste devient vide, comme le fait le serveur).
export function retirerDansEtat(etat, projet, numero) {
  const n = normaliserNumero(numero);
  if (!estCocheDansEtat(etat, projet, numero)) return etat;
  const reste = (etat[projet] || []).filter((x) => x !== n);
  const copie = { ...etat };
  if (reste.length) copie[projet] = reste;
  else delete copie[projet];
  return copie;
}

// Décide le mode de copie selon le contexte du navigateur (issue #636) :
//   - 'moderne'  : contexte sécurisé (HTTPS/localhost) ET navigator.clipboard.write
//                  ET ClipboardItem disponibles → écriture différée par
//                  ClipboardItem(promesse), engagée immédiatement au clic (le
//                  texte peut être fetché ensuite, hors fenêtre d'activation).
//   - 'repli'    : contexte non sécurisé (--lan HTTP non-localhost) ou API absente
//                  → il faut le texte AVANT le clic, copie synchrone (execCommand).
// `clipboardItemDispo` (défaut true) : présence du constructeur ClipboardItem —
// paramètre explicite pour rester purement testable sous Node (où il n'existe pas).
export function decisionModeCopie(contexteSecurise, clipboard, clipboardItemDispo = true) {
  const moderne = !!contexteSecurise
    && !!clipboard
    && typeof clipboard.write === 'function'
    && !!clipboardItemDispo;
  return moderne ? 'moderne' : 'repli';
}

// Famille + version du navigateur, à partir de `navigator.userAgent` (issue
// #824 : diagnostic d'un échec de copie, hypothèse non confirmée d'un lien
// avec l'activation utilisateur sous Firefox — ne tranche rien, donne juste
// le contexte). Best-effort, ni exhaustif ni garanti exact (chaînes d'UA
// multiples/trompeuses par nature) : Edge et Safari doivent être testés avant
// Chrome, dont la chaîne contient aussi « Chrome/ » et « Safari/ ».
export function detecterNavigateur(userAgent) {
  if (!userAgent) return 'navigateur inconnu';
  const motifs = [
    { nom: 'Edge', re: /Edg\/([\d.]+)/ },
    { nom: 'Firefox', re: /Firefox\/([\d.]+)/ },
    { nom: 'Chrome', re: /Chrome\/([\d.]+)/ },
    { nom: 'Safari', re: /Version\/([\d.]+).*Safari/ },
  ];
  for (const { nom, re } of motifs) {
    const m = userAgent.match(re);
    if (m) return `${nom} ${m[1]}`;
  }
  return 'navigateur inconnu';
}

// Ligne de détail technique d'un échec de copie (issue #824) — pure, sans
// accès DOM/navigateur (ceux-ci sont lus par l'appelant, voir
// `construireDetailEchecCopie` ci-dessous), pour rester testable sous Node.
// Ne reçoit et n'affiche JAMAIS le texte copié lui-même, seulement sa
// longueur (`longueurTexte`) — le rapport peut contenir des informations
// qu'on ne veut pas voir recopiées ailleurs (console, journal des messages).
// Chaque champ de contexte est omis (pas affiché « =undefined ») quand sa
// valeur n'est pas disponible plutôt que de mentir par une valeur par défaut.
export function formaterDetailEchecCopie(contexte) {
  const { erreur, mode, delaiMs, focus, contexteSecurise, navigateur, longueurTexte } = contexte || {};
  const cause = erreur
    ? `${erreur.name || 'Erreur'}: ${erreur.message || String(erreur)}`
    : '(aucune exception)';
  const champs = [];
  if (mode) champs.push(`mode=${mode}`);
  if (typeof delaiMs === 'number' && Number.isFinite(delaiMs)) champs.push(`délai=${delaiMs} ms`);
  if (typeof focus === 'boolean') champs.push(`focus=${focus ? 'oui' : 'non'}`);
  if (typeof contexteSecurise === 'boolean') champs.push(`contexteSécurisé=${contexteSecurise ? 'oui' : 'non'}`);
  if (navigateur) champs.push(`navigateur=${navigateur}`);
  if (typeof longueurTexte === 'number' && Number.isFinite(longueurTexte)) champs.push(`longueur=${longueurTexte} car.`);
  return champs.length ? `Détail copie — ${cause} · ${champs.join(' · ')}` : `Détail copie — ${cause}`;
}

// Extrait les cases héritées du localStorage (clé `resultat-coche:<projet>:<numero>`
// = '1', issue #154) à migrer vers le serveur (issue #636). `entrees` =
// [{cle, valeur}, ...]. Renvoie { cases: [{projet, numero}], cles: [<clé>, ...] }
// — `cases` pour POST /cases-cochees/importer (idempotent), `cles` à retirer du
// localStorage ensuite. Rejouable sans dégât (idempotent) : ne dépend que du
// contenu courant du localStorage. Le nom de projet peut contenir n'importe quoi
// sauf que le numéro est le DERNIER segment (entier) — on découpe sur le dernier
// ':' pour rester robuste à un nom de projet contenant un ':'.
export function extraireCasesLegacy(entrees) {
  const PREFIXE = 'resultat-coche:';
  const cases = [];
  const cles = [];
  for (const { cle, valeur } of entrees || []) {
    if (typeof cle !== 'string' || cle.indexOf(PREFIXE) !== 0) continue;
    if (valeur !== '1') continue;
    const reste = cle.slice(PREFIXE.length);
    const sep = reste.lastIndexOf(':');
    if (sep <= 0 || sep === reste.length - 1) continue;
    const projet = reste.slice(0, sep);
    const numero = Number(reste.slice(sep + 1));
    if (!projet || !Number.isInteger(numero)) continue;
    cases.push({ projet, numero });
    cles.push(cle);
  }
  return { cases, cles };
}

// Applique un événement SSE `case_decochee` (issue #720, après une RELANCE
// réussie — { projet, numero }) à la tranche casesCochees : réutilise
// retirerDansEtat, donc idempotent (renvoie LE MÊME objet `etat` si la case
// n'était pas cochée — l'appelant peut s'en servir pour éviter une écriture
// inutile du store/DOM). Événement malformé (projet/numero absent) → no-op.
export function appliquerCaseDecochee(etat, notif) {
  if (!notif || !notif.projet || notif.numero == null) return etat;
  return retirerDansEtat(etat, notif.projet, notif.numero);
}

// Regroupe les `limite` premières issues de chaque projet (issues déjà triées
// par date décroissante), renvoyant { projet: [numero, ...] }. C'est EXACTEMENT
// le périmètre compté par les pastilles (majPastillesFiltres, issue #382) : le
// « Cocher tout » et la remise à zéro s'y alignent pour qu'aucune pastille ne
// reste après coup (correctif anomalie #3 de l'issue #636). `limite = Infinity`
// → toutes les issues chargées (remise à zéro).
export function premieresParProjet(issuesTriees, limite) {
  const vus = {};
  const parProjet = {};
  for (const it of issuesTriees || []) {
    const projet = it.projet;
    const v = vus[projet] || 0;
    if (v >= limite) continue;
    vus[projet] = v + 1;
    (parProjet[projet] || (parProjet[projet] = [])).push(normaliserNumero(it.number));
  }
  return parProjet;
}

// ─── Ligne d'identité en tête des copies « réponse »/« all » (issue #723) ─────
// Sans elle, le texte copié par la case/les badges ✅/All ne contenait que le
// dernier commentaire (rapport ou « ❌ Échec après N tentatives ») : collé dans
// Claude.ai, il fallait redonner le numéro d'issue pour rédiger une RELANCE. Ne
// s'applique PAS à la variante « diff » (diff brut, hors périmètre de #723).
// Le titre est aplati sur une seule ligne : un titre multiligne ou très long ne
// doit jamais faire déborder la ligne d'identité sur plusieurs lignes.
export function ligneIdentite(it, projet) {
  const numero = it && it.number;
  const titre = ((it && it.title) || '').replace(/\s+/g, ' ').trim();
  const base = 'Issue #' + numero + ' — ' + (projet || '');
  return titre ? base + ' — ' + titre : base;
}

// Préfixe `texte` par la ligne d'identité suivie d'une ligne vide — sauf si
// `texte` est vide (issue pas encore répondue) : pas de ligne d'identité
// orpheline, pour que lancerCopie continue de détecter correctement le cas
// « pas encore disponible » (texteVide).
export function prefixerIdentite(it, projet, texte) {
  if (!texte || !texte.trim()) return texte;
  return ligneIdentite(it, projet) + '\n\n' + texte;
}

// Point d'assemblage unique des 3 variantes de copie : seules 'reponse' et
// 'all' reçoivent la ligne d'identité — 'diff' (diff brut) passe inchangé.
export function texteCopieAvecIdentite(variante, it, projet, texte) {
  return variante === 'diff' ? texte : prefixerIdentite(it, projet, texte);
}

// ─── Section « Fichiers modifiés » ajoutée au texte copié (issue #788) ───────
// Construite à partir de l'inventaire SERVEUR (statut + lignes +/- par
// fichier, JAMAIS le contenu du patch — route /inventaire-commit) des commits
// de l'issue, pour qu'un rapport d'agent inexact (ex. accents perdus dans un
// fichier réécrit) soit détectable sans dérouler le diff complet. Règles
// (constats de l'issue, complétées par les issues #808 et #830) :
//   - issue for-windows (etat 'windows') → l'inventaire n'est PAS DEMANDÉ au
//     serveur (ses commits sont sur le PC fixe, le dépôt du ThinkPad ne les
//     connaît pas) : texte neutre expliquant pourquoi et où regarder à la
//     place, sans symbole d'alerte — ce n'est pas une anomalie.
//   - ligne « Commits » explicitement « aucun » (lecture seule) → aucune
//     section, aucune alerte : c'est le cas normal.
//   - ligne absente/non reconnue SUR UNE ISSUE EN ÉCHEC (needs-human, etat
//     'echec') → texte neutre, sans symbole d'alerte (issue #830). N'affirme
//     ni le moment de l'échec ni l'absence d'anomalie de CCL : seul le label
//     needs-human et l'absence de ligne « Commits » sont établis (issue
//     #832, correctif de la phrase trop affirmative de #830).
//   - ligne absente/non reconnue SUR UNE ISSUE RÉUSSIE (etat 'absente'), OU un
//     commit en échec (introuvable, git en panne…) → le dire CLAIREMENT dans
//     la section, jamais en silence (contrairement au bouton Diff, qui ignore
//     un diff en échec) — un bug de reconnaissance des commits est déjà resté
//     invisible deux mois (#784).
//   - inventaire CUMULÉ (pas commit par commit) : un fichier touché par
//     plusieurs commits de l'issue n'apparaît qu'une fois, lignes +/- sommées,
//     statut du commit le plus RÉCENT à l'avoir touché (l'appelant fournit
//     les résultats dans l'ordre chronologique de hashesDeCommit : backup
//     puis fix) — reflète l'état final, pas l'historique intermédiaire. Un
//     commit de sauvegarde vide ne contribue simplement aucun fichier.

const TITRE_SECTION_FICHIERS = 'Fichiers modifiés';

// Texte neutre affiché pour une issue for-windows (etat 'windows', issue
// #808) : pas de symbole d'alerte, ce n'est pas une anomalie — seulement un
// cas où l'inventaire est impossible par construction depuis le ThinkPad.
const TEXTE_INVENTAIRE_WINDOWS =
  'L\'inventaire des fichiers modifiés n\'est pas disponible depuis le ThinkPad pour une '
  + 'issue Windows : ses commits sont sur le PC fixe, dans le worktree indiqué par la ligne '
  + '« Commits ». Pour voir les fichiers modifiés, ouvrir dans l\'outil de relecture l\'entrée '
  + 'du projet dont le nom se termine par « _ccw ».';

// Somme deux compteurs, sauf si l'un des deux est inconnu (fichier binaire,
// compté `null` côté serveur) — jamais d'addition qui affirmerait un compte
// faux.
function sommeOuNull(a, b) {
  return (a == null || b == null) ? null : a + b;
}

// Fusionne l'inventaire d'UN fichier (tel que renvoyé par /inventaire-commit)
// dans l'accumulateur { chemin → {statut, ancienChemin, ajoutees, supprimees} }.
// Retour immuable (comme ajouterDansEtat/retirerDansEtat plus haut).
export function fusionnerInventaireFichier(acc, fichier) {
  const existant = acc[fichier.chemin];
  return {
    ...acc,
    [fichier.chemin]: {
      statut: fichier.statut,
      ancienChemin: fichier.ancien_chemin || null,
      ajoutees: existant ? sommeOuNull(existant.ajoutees, fichier.ajoutees) : fichier.ajoutees,
      supprimees: existant ? sommeOuNull(existant.supprimees, fichier.supprimees) : fichier.supprimees,
    },
  };
}

// Combine les résultats /inventaire-commit de plusieurs commits (dans l'ordre
// chronologique) en { fichiers, erreurs } — `resultatsParCommit` = [{ hash,
// fichiers:[...] } | { hash, erreur }, ...] (un élément par commit, succès ou
// échec : voir inventaireCommits ci-dessous).
export function construireInventaireCumule(resultatsParCommit) {
  let fichiers = {};
  const erreurs = [];
  for (const r of (resultatsParCommit || [])) {
    if (r.erreur) { erreurs.push({ hash: r.hash, message: r.erreur }); continue; }
    for (const f of (r.fichiers || [])) fichiers = fusionnerInventaireFichier(fichiers, f);
  }
  return { fichiers, erreurs };
}

function libelleCompteurs(f) {
  return (f.ajoutees == null || f.supprimees == null)
    ? '(binaire)' : '(+' + f.ajoutees + ' -' + f.supprimees + ')';
}

// Construit le texte de la section, ou '' si aucune section ne doit être
// ajoutée (`etatCommits` === 'aucun'). `etatCommits` ∈ {'windows','hashes',
// 'aucun','echec','absente'} (voir etatCommitsDeclares, app.js) ;
// `resultatsParCommit` est ignoré si `etatCommits` !== 'hashes'.
export function texteSectionFichiers(etatCommits, resultatsParCommit) {
  if (etatCommits === 'aucun') return '';
  const lignes = ['===== ' + TITRE_SECTION_FICHIERS + ' ====='];
  if (etatCommits === 'windows') {
    lignes.push('', TEXTE_INVENTAIRE_WINDOWS);
    return lignes.join('\n');
  }
  if (etatCommits === 'echec') {
    lignes.push('', 'Cette issue est en échec (needs-human) : son commentaire de clôture ne '
      + 'contient pas de ligne « Commits », donc aucun inventaire des fichiers n\'est possible.');
    return lignes.join('\n');
  }
  if (etatCommits === 'absente') {
    lignes.push('', '⚠ Ligne « Commits » absente ou non reconnue dans la réponse CCL — '
      + 'inventaire des fichiers impossible (anomalie à vérifier, pas un cas normal).');
    return lignes.join('\n');
  }
  const { fichiers, erreurs } = construireInventaireCumule(resultatsParCommit);
  const chemins = Object.keys(fichiers).sort();
  if (!chemins.length && !erreurs.length) {
    lignes.push('', '(aucun fichier — commit(s) vide(s), ex. sauvegarde)');
  }
  for (const chemin of chemins) {
    const f = fichiers[chemin];
    const nom = f.ancienChemin ? f.ancienChemin + ' → ' + chemin : chemin;
    lignes.push(f.statut + '  ' + nom + '  ' + libelleCompteurs(f));
  }
  for (const e of erreurs) {
    lignes.push('⚠ Commit ' + e.hash + ' : inventaire impossible — ' + e.message);
  }
  return lignes.join('\n');
}

// ─────────────────────────────────────────────────────────────────────────────
// 2. ÉTAT SERVEUR DES CASES (store.casesCochees ⇄ routes /cases-cochees)
// ─────────────────────────────────────────────────────────────────────────────

const enc = encodeURIComponent;

function etatCases() { return store.get('casesCochees') || {}; }

// Lue par app.js (via le pont) au rendu de chaque ligne et par majPastillesFiltres.
function estCoche(projet, numero) {
  return estCocheDansEtat(etatCases(), projet, numero);
}

// Noms de projets disponibles (sélecteur global peuplé côté serveur).
function nomsProjets() {
  const sel = document.getElementById('projet');
  if (!sel) return [];
  return [...sel.options].map((o) => o.value).filter(Boolean);
}

// Issues du store triées par date décroissante (même ordre que le miroir d'app.js
// listeIssuesResultats, pour que premieresParProjet corresponde aux pastilles).
function issuesTriees() {
  return store.listerIssues().slice()
    .sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt));
}

function limiteParProjet() {
  const v = appelerAncien('limiteIssuesProjet');
  return Number.isFinite(v) ? v : 5;
}

// Resynchronise le DOM (cases + classe .resultat-traite) et les pastilles depuis
// l'état courant — délègue à l'ancien code qui possède le markup des lignes.
function resyncDom() {
  appelerAncien('restaurerCasesCocheesResultats');
  appelerAncien('majPastillesFiltres');
}

// Recharge l'état serveur d'un ou plusieurs projets (GET par projet), puis
// resynchronise le DOM. Sert au chargement initial ET à la resynchronisation
// après un échec d'écriture (retour à la vérité serveur).
async function rechargerCases(projets) {
  const noms = projets && projets.length ? projets : nomsProjets();
  await Promise.all(noms.map(async (nom) => {
    try {
      const rep = await api.get('/cases-cochees/' + enc(nom), { silencieux: true });
      const numeros = (rep && rep.numeros) || [];
      store.set('casesCochees', fusionnerCasesServeur(etatCases(), nom, numeros));
    } catch (e) { /* projet injoignable : état précédent conservé */ }
  }));
  resyncDom();
}

// ─── Migration du localStorage hérité (issue #154 → #636), idempotente ───────
// Rejouable sans dégât : POST /cases-cochees/importer est idempotent côté serveur
// (issue #629) ; on ne retire les clés du localStorage qu'APRÈS un import réussi.
// Interrompu avant le retrait → au prochain chargement les clés sont toujours là,
// on réimporte (sans doublon) puis on retire. Interrompu en plein retrait → les
// clés restantes seront retirées au tour suivant.
async function migrerLocalStorage() {
  const entrees = persistance.toutesLesEntrees();
  const { cases, cles } = extraireCasesLegacy(entrees);
  if (!cases.length) return;
  try {
    const rep = await api.post('/cases-cochees/importer', { cases }, { silencieux: true });
    if (rep && rep.succes) {
      for (const cle of cles) persistance.supprimer(cle);
    }
  } catch (e) { /* réseau : on retentera au prochain chargement */ }
}

// ─── Événement SSE `case_decochee` (issue #720) ───────────────────────────────
// Pousse instantanément vers un onglet Résultats déjà ouvert la décoche faite
// côté serveur après une RELANCE réussie (§3.14 du DOC) — sans ce handler, la
// case resterait cochée à l'écran jusqu'au prochain chargement par projet
// (rechargerCases, qui ne relit l'état serveur qu'à ce moment-là).
function surCaseDecochee(notif) {
  const avant = etatCases();
  const suivant = appliquerCaseDecochee(avant, notif);
  if (suivant === avant) return;   // idempotent : déjà décochée (ou événement malformé)
  store.set('casesCochees', suivant);
  resyncDom();
}

// ─── Bascule d'une case (onchange de la case, issue #636) ─────────────────────
// Engage la copie PENDANT le geste (cocher) ; la persistance/grisage/pastilles ne
// dépendent JAMAIS de la copie. Décocher ne copie rien.
function basculer(event, projet, numero) {
  const cb = event && event.target;
  const coche = !!(cb && cb.checked);
  const ligne = cb && cb.closest ? cb.closest('.ligne-issue') : null;

  // 1) Copie IMMÉDIATE au clic si on coche (avant toute écriture réseau de l'état,
  //    pour rester dans la fenêtre d'activation utilisateur). Indépendante du reste.
  //    Variante 'reponse' (résultat SEUL, issue #787) : le bouton Diff copie le
  //    diff seul, le bouton All copie les deux — la case ne doit copier que le
  //    résultat. Avant ce correctif, la case appelait texteAll par erreur ; le
  //    défaut est resté invisible deux mois tant que la reconnaissance des
  //    numéros de commit (#784) était cassée, texteAll ne trouvant alors jamais
  //    de diff à ajouter.
  if (coche) lancerCopie(projet, numero, texteReponse, feedbackToastAvecDiagnostic(projet, numero, ligne, cb));

  // 2) Mise à jour optimiste : store + grisage + pastilles.
  const avant = etatCases();
  store.set('casesCochees', coche
    ? ajouterDansEtat(avant, projet, numero)
    : retirerDansEtat(avant, projet, numero));
  if (ligne) ligne.classList.toggle('resultat-traite', coche);
  if (ligne) majRepereLigne(ligne);   // disparaît dès la coche (issue #835 point 2)
  appelerAncien('majPastillesFiltres');

  // 3) Persistance serveur (asynchrone) ; en cas d'échec, resync depuis la vérité
  //    serveur (l'API a déjà levé son toast d'erreur).
  const url = '/cases-cochees/' + enc(projet) + '/' + enc(normaliserNumero(numero));
  const p = coche ? api.post(url, null) : api.supprimer(url);
  p.catch(() => rechargerCases([projet]));
}

// ─── « Cocher tout » (issue #381, élargi #636) ────────────────────────────────
// Coche toutes les issues chargées, dans la limite par projet, des projets
// ACTUELLEMENT FILTRÉS (actifs) — même périmètre que les pastilles, sans le quota
// d'affichage ni le filtre ouvriers. Après coup, aucune pastille des projets
// actifs ne reste. NE copie rien.
async function cocherTout() {
  const actifs = new Set(appelerAncien('projetsActifsDansFiltreResultats') || nomsProjets());
  const parProjet = premieresParProjet(issuesTriees(), limiteParProjet());
  const cases = [];
  for (const [projet, numeros] of Object.entries(parProjet)) {
    if (!actifs.has(projet)) continue;
    for (const n of numeros) if (!estCoche(projet, n)) cases.push({ projet, numero: n });
  }
  await marquerCases(cases);
}

// ─── Remise à zéro des pastilles (nouveau bouton, issue #636) ─────────────────
// Marque comme cochées, côté serveur, TOUTES les issues chargées de TOUS les
// projets, quel que soit le filtre courant. Confirmation légère (toasts.confirmer).
// NE copie rien.
async function remettreAZero() {
  const ok = await toasts.confirmer(
    'Marquer comme traitées toutes les issues chargées de tous les projets ? '
    + 'Cela remet toutes les pastilles à zéro. Aucune copie n\'est déclenchée.',
    { titre: 'Tout marquer comme traité', texteConfirmer: 'Tout marquer' });
  if (!ok) return;
  const parProjet = premieresParProjet(issuesTriees(), Infinity);
  const cases = [];
  for (const [projet, numeros] of Object.entries(parProjet)) {
    for (const n of numeros) if (!estCoche(projet, n)) cases.push({ projet, numero: n });
  }
  if (!cases.length) { toasts.info('Toutes les issues chargées sont déjà cochées.', false); return; }
  await marquerCases(cases);
}

// Applique un lot de cases (import serveur idempotent + mise à jour optimiste du
// store + resync DOM). Facteur commun à « Cocher tout » et à la remise à zéro.
async function marquerCases(cases) {
  if (!cases.length) return;
  let etat = etatCases();
  for (const { projet, numero } of cases) etat = ajouterDansEtat(etat, projet, numero);
  store.set('casesCochees', etat);
  resyncDom();
  try {
    await api.post('/cases-cochees/importer', { cases });
  } catch (e) {
    // L'API a levé son toast ; on resynchronise depuis la vérité serveur.
    await rechargerCases([...new Set(cases.map((c) => c.projet))]);
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// 3. MOTEUR DE COPIE FIABLE (issue #636, mode moderne revu #782 puis #858, fichier #790)
//    Un seul chemin pour toutes les copies « fetch puis écriture » : cocher une
//    case, badges ✅/Diff/All. Le succès n'est signalé QUE s'il a réellement eu
//    lieu. Mode moderne (voir copierModerne) : depuis l'issue #858,
//    navigator.clipboard.write() est appelé SYNCHRONEMENT au clic (comme avant
//    #782), le contenu étant fourni de façon DIFFÉRÉE — l'ENGAGEMENT, pas la
//    résolution du contenu, doit tomber dans la fenêtre d'activation. #782
//    avait abandonné cet engagement différé pour sérialiser les écritures
//    (texte préparé AVANT la demande d'écriture) afin que cocher plusieurs
//    cases rapprochées ne fasse plus échouer toutes les copies sauf la
//    dernière ; mais l'écriture avait alors lieu hors fenêtre d'activation, ce
//    qui faisait échouer une préparation lente (issue #824 : 10,1s de
//    préparation, NotAllowedError). #858 restaure l'engagement synchrone et
//    traite les clics rapprochés par un compteur de génération (voir
//    generationCopieModerne) : seule la DERNIÈRE copie demandée compte, une
//    copie supplantée par une plus récente est abandonnée EN SILENCE.
//    Diff/All au-delà de SEUIL_LIGNES_VOLUMINEUX lignes (issue #790) : ni
//    moderne ni repli ne copient — un fichier .txt est téléchargé à la place
//    (voir declencherTelechargement, et telechargerOuSignalerVolumineux pour
//    le repli). 'reponse' n'est jamais concernée (seul l'ancien toast
//    d'avertissement s'applique).
// ─────────────────────────────────────────────────────────────────────────────

const TITRE_COPIE_VIDE = 'Réponse pas encore disponible — réessaie dans quelques secondes';

function texteVide(t) { return !t || !t.trim(); }

function modeCopie() {
  return decisionModeCopie(
    (typeof window !== 'undefined') ? window.isSecureContext : false,
    (typeof navigator !== 'undefined') ? navigator.clipboard : null,
    (typeof ClipboardItem !== 'undefined'));
}

// Cache de détail (économie de fetch) et textes préchargés (issue #636, étendu
// aux deux modes par #832 — voir precharderVisibles). Chaque entrée de
// `textesPrepares` est { valeur, ts, cleValidite } : `valeur` est le texte
// produit (ou {aucun:true}, cf. precharger), `ts` l'horodatage de préparation
// et `cleValidite` la signature de l'issue au moment de la préparation (voir
// cleValiditeIssue) — les deux servent à texteEstValide ci-dessous à écarter
// un texte périmé plutôt que de l'écrire tel quel (issue #832 point 3).
const DETAIL_TTL_MS = 60000;
const detailCache = new Map();          // cle → { ts, it }
const textesPrepares = new Map();       // cle → { all?, diff?, reponse?: {valeur, ts, cleValidite} }
const prechargementEnCours = new Set(); // "cle|variante" dont un préchargement est en file

function cleIC(projet, numero) { return projet + '#' + normaliserNumero(numero); }

// Pont vers estIssueEnEchec (app.js, script classique non importable depuis
// ce module ES — voir pont.js) — seul point d'appel réel de ce fichier,
// injecté dans issueEnCours là où ce module en a besoin (issue #838).
function estIssueEnEchecPont(it) { return !!appelerAncien('estIssueEnEchec', it); }

// Signature de l'issue utilisée comme clé de validité d'un texte préparé
// (issue #832 point 3) : state + labels, dans cet ordre, triés — c'est tout
// ce que la liste /issues-liste expose (voir _enrichir_modele côté serveur :
// ni nombre de commentaires, ni date de mise à jour ne sont renvoyés). Un
// nouveau commentaire sans changement d'état ni de label n'est donc PAS
// détecté ici : c'est l'âge maximum (AGE_MAX_TEXTE_PREPARE_MS) qui couvre ce
// cas, en filet de sécurité. `it` vient de store.lireIssue (reflet de la
// liste, pas du détail complet).
export function cleValiditeIssue(it) {
  if (!it) return null;
  const noms = (it.labels || []).map((l) => (l && l.name) || l || '').filter(Boolean).sort();
  return (it.state || '') + '|' + noms.join(',');
}

// Âge maximum d'un texte préparé. Le texte d'une issue terminée ne change
// plus tant que sa clé de validité (état + labels, voir cleValiditeIssue)
// reste la même : cette durée n'est PAS la mesure de péremption normale,
// c'est un filet de sécurité pour le seul cas que cleValiditeIssue ne peut
// pas voir (un commentaire ajouté à l'issue sans changement d'état ni de
// label, que la liste /issues-liste n'expose pas) — un cas rare. Portée à
// une heure (depuis 3 minutes) par l'issue #839 : trois minutes périmait un
// texte préparé à la clôture avant même le retour d'Alain sur la page après
// une absence de quelques minutes.
export const AGE_MAX_TEXTE_PREPARE_MS = 60 * 60 * 1000;

// Vrai si `entree` ({valeur, ts, cleValidite} | undefined) est encore
// utilisable tel quel : clé de validité inchangée ET pas plus vieille que
// `ageMaxMs`. Un texte périmé n'est JAMAIS renvoyé valide (issue #832 point
// 3) — l'appelant retombe alors sur le chemin lent (préparer puis écrire).
export function texteEstValide(entree, cleValiditeActuelle, maintenant, ageMaxMs) {
  return !!entree
    && entree.cleValidite === cleValiditeActuelle
    && (maintenant - entree.ts) <= ageMaxMs;
}

// Vrai si l'issue est « en cours » (issue #838) : ouverte ET pas en échec
// (needs-human) — dans ces deux cas un rapport existe déjà, et c'est lui
// qu'on veut préparer/signaler, pas refaire un futur rapport de clôture.
// Règle d'« ouvert » REPRISE de construireLigneIssueDOM (static/js/app.js,
// suffixe [ouvert]/[fermé] affiché sur chaque ligne) : tout ce qui n'est pas
// explicitement CLOSED compte comme ouvert — `gh issue list` ne renvoie que
// OPEN ou CLOSED pour des issues (pas de 3e état, à la différence des PR).
// `estIssueEnEchecFn` injectée plutôt qu'importée : app.js reste un script
// classique (pas un module ES), donc non importable depuis ce fichier — même
// contrainte que estCocheFn/dejaPresentFn de candidatsPrechargement ci-après.
export function issueEnCours(it, estIssueEnEchecFn) {
  if (!it) return false;
  const fermee = (it.state || '').toUpperCase() === 'CLOSED';
  return !fermee && !estIssueEnEchecFn(it);
}

async function detailIssue(projet, numero) {
  const cle = cleIC(projet, numero);
  const c = detailCache.get(cle);
  if (c && (Date.now() - c.ts) < DETAIL_TTL_MS) return c.it;
  let it = null;
  try {
    it = await api.get('/issue/' + enc(projet) + '/' + enc(normaliserNumero(numero)), { silencieux: true });
  } catch (e) { return null; }
  if (!it || it.erreur) return null;
  detailCache.set(cle, { ts: Date.now(), it });
  return it;
}

async function diffCommits(projet, hashes) {
  const morceaux = [];
  for (const h of hashes) {
    try {
      const j = await api.get('/diff/' + enc(projet) + '/' + enc(h), { silencieux: true });
      if (j && j.diff) morceaux.push('===== Diff ' + h + ' =====\n\n' + j.diff);
    } catch (e) { /* un diff en échec n'empêche pas les autres */ }
  }
  return morceaux;
}

// Inventaire /inventaire-commit de chaque hash, dans l'ordre reçu — CONTRAIREMENT
// à diffCommits ci-dessus, un échec n'est jamais avalé : il est transmis tel
// quel ({ hash, erreur }) pour que texteSectionFichiers le signale (issue #788).
async function inventaireCommits(projet, hashes) {
  const resultats = [];
  for (const h of hashes) {
    try {
      const j = await api.get('/inventaire-commit/' + enc(projet) + '/' + enc(h), { silencieux: true });
      resultats.push({ hash: h, fichiers: (j && j.fichiers) || [] });
    } catch (e) {
      resultats.push({ hash: h, erreur: messageErreurInventaire(e) });
    }
  }
  return resultats;
}

// ErreurApi (api.js) porte le corps JSON brut de la réponse en échec — on y
// retrouve le message `erreur` posé par la route Flask (ex. « Commit … introuvable »)
// plutôt que le générique « Erreur 404 sur … ».
function messageErreurInventaire(e) {
  if (e && e.corps) {
    try {
      const j = JSON.parse(e.corps);
      if (j && j.erreur) return j.erreur;
    } catch (_) { /* corps non-JSON : retombe sur e.message */ }
  }
  return (e && e.message) || 'échec inattendu';
}

// Section « Fichiers modifiés » (issue #788) à ajouter au texte de la case —
// '' si la ligne « Commits » dit explicitement « aucun » (cas normal, lecture
// seule). L'inventaire n'est demandé au serveur QUE pour l'etat 'hashes' —
// une issue for-windows (etat 'windows', issue #808) ne déclenche donc aucune
// requête /inventaire-commit, le dépôt du ThinkPad ne connaissant pas ses
// commits. Voir texteSectionFichiers pour le détail de ces cas.
async function sectionFichiersModifies(projet, it) {
  const etatCommits = appelerAncien('etatCommitsDeclares', it) || { etat: 'absente', hashes: [] };
  const resultats = etatCommits.etat === 'hashes'
    ? await inventaireCommits(projet, etatCommits.hashes)
    : [];
  return texteSectionFichiers(etatCommits.etat, resultats);
}

// Producteurs de texte (réutilisent reponseCompleteCcl/hashesDeCommit d'app.js
// via le pont — aucune duplication de la reconstruction markdown). La ligne
// d'identité (issue #723) est préfixée ici, pas dans reponseCompleteCcl : elle
// ne concerne que ces deux variantes, pas texteDiff.
async function texteReponse(projet, numero) {
  const it = await detailIssue(projet, numero);
  if (!it) return '';
  let corps = appelerAncien('reponseCompleteCcl', it) || '';
  // Pas encore répondue (corps vide) : pas de section, pour rester détecté
  // par texteVide en amont comme avant ce correctif.
  if (corps.trim()) {
    const section = await sectionFichiersModifies(projet, it);
    if (section) corps += '\n\n' + section;
  }
  return texteCopieAvecIdentite('reponse', it, projet, corps);
}
async function texteAll(projet, numero) {
  const it = await detailIssue(projet, numero);
  if (!it) return '';
  let texte = appelerAncien('reponseCompleteCcl', it) || '';
  const hashes = appelerAncien('hashesDeCommit', it) || [];
  const diffs = await diffCommits(projet, hashes);
  if (diffs.length) texte += '\n\n' + diffs.join('\n\n');
  return texteCopieAvecIdentite('all', it, projet, texte);
}
async function texteDiff(projet, numero) {
  const it = await detailIssue(projet, numero);
  if (!it) return '';
  const hashes = appelerAncien('hashesDeCommit', it) || [];
  if (!hashes.length) { const e = new Error('aucun'); e.aucun = true; throw e; }
  return (await diffCommits(projet, hashes)).join('\n\n');
}

// Seuil de lignes au-delà duquel Claude.ai risque de ne pas lire le texte en
// entier — SOURCE UNIQUE (issue #790, remplace l'ancien `1000` dupliqué dans
// `avertirVolumineux`). Pour 'diff'/'all' dépassant ce seuil, on bascule sur un
// fichier téléchargé (voir `doitTelecharger`) ; pour 'reponse', seul l'ancien
// toast d'avertissement s'applique (comportement volontairement inchangé).
export const SEUIL_LIGNES_VOLUMINEUX = 1000;

export function nombreLignes(texte) {
  return (texte || '').split('\n').length;
}

// 'diff'/'all' seulement (pas 'reponse', issue #790 point 5) : au-delà du
// seuil, on télécharge un fichier au lieu de copier dans le presse-papier.
export function doitTelecharger(variante, texte, seuil = SEUIL_LIGNES_VOLUMINEUX) {
  return (variante === 'diff' || variante === 'all') && nombreLignes(texte) > seuil;
}

// Nom de fichier reconnaissable à coup sûr : projet + numéro d'issue + variante
// (issue #790 point 3). Caractères hors [a-zA-Z0-9_-] neutralisés (nom de
// projet potentiellement inattendu) pour rester un nom de fichier valide.
export function nomFichierCopie(projet, numero, variante) {
  const propre = (s) => String(s).replace(/[^a-zA-Z0-9_-]+/g, '_');
  return propre(projet) + '-' + normaliserNumero(numero) + '-' + variante + '.txt';
}

function libelleVariante(variante) {
  return variante === 'diff' ? 'Le diff' : 'Le rapport (résultat + diff)';
}

// Message de remplacement de l'avertissement « Diff volumineux » quand un
// fichier est téléchargé à la place de la copie (issue #790 point 4) : dit
// que le texte était trop long, qu'un fichier a été produit, et où le
// retrouver.
export function messageFichierVolumineux(variante, nbLignes, nomFichier) {
  return libelleVariante(variante) + ' était trop long (' + nbLignes + ' lignes) pour être copié '
    + 'dans le presse-papier — un fichier a été téléchargé à la place : ' + nomFichier
    + ' (dossier de téléchargements du navigateur).';
}

function avertirVolumineux(texte) {
  const nb = nombreLignes(texte);
  if (nb > SEUIL_LIGNES_VOLUMINEUX) {
    toasts.avertissement('Diff volumineux (' + nb + ' lignes) — Claude.ai pourrait ne pas le lire.');
  }
}

// Déclenche le téléchargement de `texte` sous le nom `nomFichier` (lien <a
// download> éphémère + Blob) — pas de contrainte d'activation comme le
// presse-papier (issues #636/#782) : un clic programmatique sur <a download>
// n'exige pas d'être synchrone avec le geste utilisateur, donc aucun risque de
// réintroduire ces défauts ici.
function declencherTelechargement(nomFichier, texte) {
  try {
    const blob = new Blob([texte], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = nomFichier;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    return true;
  } catch (e) {
    console.warn('resultats_coches : échec du téléchargement de secours.', e);
    return false;
  }
}

// Copie synchrone (mode repli) via un <textarea> temporaire + execCommand('copy').
function copierExecCommand(texte) {
  try {
    const ta = document.createElement('textarea');
    ta.value = texte;
    ta.style.position = 'fixed';
    ta.style.left = '-9999px';
    ta.style.top = '0';
    document.body.appendChild(ta);
    ta.focus();
    ta.select();
    const ok = document.execCommand('copy');
    document.body.removeChild(ta);
    return ok;
  } catch (e) {
    console.warn('resultats_coches : échec execCommand(copy).', e);
    return false;
  }
}

// ─── Mode « moderne » : écriture ENGAGÉE au clic, contenu DIFFÉRÉ (issue #858,
//     retour à l'esprit d'avant #782) ──────────────────────────────────────
// CAUSE CONFIRMÉE par relecture du code et de l'historique (pas une simple
// hypothèse) : depuis #782, le texte est entièrement PRÉPARÉ (fetch /issue,
// /diff, /inventaire-commit…) AVANT même de DEMANDER l'écriture — l'appel à
// navigator.clipboard.write() n'a donc lieu qu'une fois la préparation
// terminée, potentiellement bien après la fin de la fenêtre d'activation
// ouverte par le clic. Firefox refuse alors l'écriture (NotAllowedError),
// comme diagnostiqué sur un cas réel à 10,1s de préparation (issue #824).
// Avant #782, l'appel à write() était SYNCHRONE au clic — seul le CONTENU
// (confié au ClipboardItem via une promesse) pouvait arriver après coup — et
// Firefox l'acceptait quelle que soit la durée de préparation : c'est
// l'ENGAGEMENT (l'appel), pas la résolution du contenu, qui doit tomber dans
// la fenêtre du geste. #782 avait abandonné cet engagement différé pour une
// AUTRE cause, elle aussi réelle mais distincte : plusieurs cases cochées
// très vite annulaient les écritures précédentes (Firefox annule une
// écriture encore pendante dès qu'une nouvelle est lancée avant qu'elle
// n'aboutisse). #832/#835/#839 avaient ensuite contourné le SYMPTÔME
// (précharger AVANT le clic pour que la préparation soit déjà faite) sans
// toucher à la cause : un clic trop rapide pour un rapport pas encore
// préchargé restait exposé.
//
// Cette issue restaure l'engagement synchrone ET règle directement la
// seconde cause (clics rapprochés), par un compteur de génération GLOBAL :
// seule la DERNIÈRE copie demandée (case ou badge, n'importe quelle issue —
// une seule écriture presse-papier possible à la fois, comme le système
// lui-même) compte ; une copie en vol supplantée par une plus récente est
// abandonnée EN SILENCE (ni toast, ni fenêtre de secours, ni badge
// d'échec) — Alain coche parfois plusieurs cases très vite sans vouloir le
// rapport de chacune (voir le contexte de l'issue), il ne doit donc jamais
// être interrompu par un « échec » qui n'en est pas un pour lui. Un échec
// RÉEL (toute autre cause) garde l'affichage existant (toast, fenêtre de
// secours, ligne de détail technique).
//
// NON vérifié ici, seulement SIMULÉ par les tests Node (mock de
// clipboard.write) : que Firefox accepte RÉELLEMENT une préparation de
// plusieurs secondes une fois l'écriture engagée au clic. C'est le
// comportement documenté d'avant #782, mais pas re-reproduit en vrai
// navigateur pour cette issue — voir l'essai ajouté à
// VERIFICATIONS_MANUELLES.md.
//
// DEPUIS L'ISSUE #865 : copierModerne n'est plus appelée EXACTEMENT dans le
// même tick synchrone que le clic, mais juste après la fin du vidage
// immédiat du presse-papier (viderPressePapier, quelques millisecondes,
// voir lancerCopie) — toujours dans la fenêtre d'activation du geste
// (hypothèse reprise de l'issue #865, non re-vérifiée ici en vrai
// navigateur, voir VERIFICATIONS_MANUELLES.md), mais plus littéralement
// synchrone avec l'événement DOM.
let generationCopieModerne = 0;

// Vrai si la copie de génération `monGen` a été supplantée par une copie plus
// récente (issue #858 point 3) — comparaison PURE d'un compteur, testée par
// construction via les tests d'intégration de copierModerne (une fonction
// aussi triviale n'a pas besoin de son propre test unitaire séparé).
function copieSupplantee(monGen) {
  return monGen !== generationCopieModerne;
}

// Conservée UNIQUEMENT pour copierTexteConnu (issue #823, hors périmètre de
// cette issue, non modifiée) : ni viderPressePapier ni copierModerne ne s'en
// servent plus depuis #858 — la sérialisation qu'elle offrait (#782) allait
// à l'encontre du nouveau comportement voulu (seule la dernière copie
// compte, pas « toutes finissent par réussir, dans l'ordre d'arrivée »).
let chaineCopieModerne = Promise.resolve();

// Construit la ligne de détail technique d'un échec (issue #824) : lit le
// contexte navigateur/fenêtre au moment de l'échec (pas avant) — notamment
// `focus`, pour vérifier l'hypothèse non confirmée d'un lien avec l'activation
// utilisateur. `debut` = Date.now() au tout début de la copie (voir chaque
// appelant ci-dessous) ; `texte` = celui qui a échoué à être copié, dont SEULE
// la longueur est transmise (jamais le contenu).
function construireDetailEchecCopie(e, mode, debut, texte) {
  return formaterDetailEchecCopie({
    erreur: e,
    mode,
    delaiMs: typeof debut === 'number' ? Date.now() - debut : undefined,
    focus: (typeof document !== 'undefined' && typeof document.hasFocus === 'function')
      ? document.hasFocus() : undefined,
    contexteSecurise: (typeof window !== 'undefined' && typeof window.isSecureContext === 'boolean')
      ? window.isSecureContext : undefined,
    navigateur: (typeof navigator !== 'undefined' && navigator.userAgent)
      ? detecterNavigateur(navigator.userAgent) : undefined,
    longueurTexte: texte != null ? String(texte).length : undefined,
  });
}

// Enveloppe le `feedback` reçu pour que son `echec(e, texte, messagePrincipal?)`
// reçoive la ligne de détail ci-dessus en 3e argument, sans toucher aux autres
// callbacks ni au contrat existant (issue #824 : les appelants de
// signalerEchecCopie ignoraient jusqu'ici l'exception `e`). Posée une fois par
// point d'entrée (copierModerne/lancerCopie/copierTexteConnu) pour que tous
// les appels internes à `feedback.echec` (y compris depuis
// telechargerOuSignalerVolumineux) portent `mode`/`debut` sans avoir à les
// faire transiter partout. `messagePrincipal` (issue #832 point 4b) transite
// tel quel jusqu'à signalerEchecCopie, pour le cas précis où la préparation a
// dépassé la fenêtre d'activation du geste.
function envelopperFeedbackEchec(feedback, mode, debut) {
  if (!feedback || typeof feedback.echec !== 'function') return feedback;
  return {
    ...feedback,
    echec: (e, texte, messagePrincipal) =>
      feedback.echec(e, texte, construireDetailEchecCopie(e, mode, debut, texte), messagePrincipal),
  };
}

// Variante associée à un producteur de texte — un seul endroit (issue #790,
// réutilisé par copierModerne ET lancerCopie en mode repli, qui dupliquaient
// ce test).
function variantDuProducteur(producteur) {
  return producteur === texteAll ? 'all' : producteur === texteDiff ? 'diff' : 'reponse';
}

// Bascule commune (moderne/repli) une fois le texte en main : fichier
// téléchargé au-delà du seuil (diff/all), copie sinon — partagée pour que les
// deux modes appliquent EXACTEMENT la même règle (issue #790). Si le
// téléchargement échoue, pas de « fichier téléchargé » mensonger : on retombe
// sur le mécanisme d'échec de copie existant (issue #782), texte à l'appui
// pour une copie manuelle (issue #791).
function telechargerOuSignalerVolumineux(projet, numero, variante, t, feedback) {
  if (doitTelecharger(variante, t)) {
    const nomFichier = nomFichierCopie(projet, numero, variante);
    if (declencherTelechargement(nomFichier, t)) {
      feedback.fichier(messageFichierVolumineux(variante, nombreLignes(t), nomFichier));
    } else {
      feedback.echec(undefined, t);
    }
    return true;
  }
  avertirVolumineux(t);
  return false;
}

// Seuil de durée de préparation (issue #832 point 4a) au-delà duquel une
// écriture refusée est traitée comme « geste expiré » même sans
// NotAllowedError explicite (certains navigateurs/contextes peuvent refuser
// pour une autre raison une fois la fenêtre d'activation dépassée).
export const SEUIL_PREPARATION_LENTE_MS = 4000;

// Vrai si l'échec de l'écriture doit être traité comme une expiration du
// geste (issue #832 point 4) : soit l'exception est explicitement
// NotAllowedError (Firefox, diagnostic de l'issue #824), soit la préparation
// (fetch du texte, PAS l'attente dans la file des écritures) a dépassé
// SEUIL_PREPARATION_LENTE_MS — pure, testée sous Node.
export function gesteExpireOuPreparationLente(e, dureePreparationMs, seuilMs = SEUIL_PREPARATION_LENTE_MS) {
  return !!(e && e.name === 'NotAllowedError')
    || (typeof dureePreparationMs === 'number' && dureePreparationMs > seuilMs);
}
// Devenue SUPERFLUE pour le chemin principal depuis l'issue #858 (gardée,
// non supprimée, non branchée dans le nouveau copierModerne) : le mode
// moderne engage désormais l'écriture SYNCHRONEMENT au clic, plus après la
// préparation — une préparation lente ne peut donc plus, par construction,
// provoquer ce NotAllowedError par expiration du geste. Le cas des clics
// rapprochés (l'AUTRE cause historique de NotAllowedError, #782) est traité
// directement par generationCopieModerne/copieSupplantee ci-dessous, pas par
// cette heuristique de durée. Voir le rapport de clôture de #858.

// Enregistre/remplace le texte préparé de (projet, numero, variante) — utilisé
// par precharger() (préchargement en tâche de fond) ET par le chemin lent de
// copierModerne quand l'écriture est refusée pour geste expiré (issue #832
// point 4a : le texte déjà obtenu n'est pas perdu, le clic suivant est
// immédiat). `cleValiditeIssue` lit l'issue telle que connue de la liste
// (store.lireIssue) — pas le détail complet, voir le commentaire de
// cleValiditeIssue plus haut.
function memoriserTextePrepare(projet, numero, variante, valeur) {
  const cle = cleIC(projet, numero);
  const prep = textesPrepares.get(cle) || {};
  prep[variante] = { valeur, ts: Date.now(), cleValidite: cleValiditeIssue(store.lireIssue(projet, numero)) };
  textesPrepares.set(cle, prep);
}

// Point d'entrée du mode moderne (issue #858) : ENGAGE navigator.clipboard.write()
// SYNCHRONEMENT (au clic), avec un contenu DIFFÉRÉ — `blobP` résout vers le
// rapport une fois prêt, quelle que soit la durée. Le FEEDBACK (succès/vide/
// aucun/volumineux/échec) est décidé à partir de l'ISSUE DE LA PRÉPARATION
// (`issuePreparation`, qui ne rejette JAMAIS) et du sort RÉEL de l'écriture
// (`resultatEcriture`) — jamais de faux succès (#636/#782). Une copie
// supplantée par une plus récente (compteur `generationCopieModerne`)
// n'émet AUCUN feedback, quelle que soit l'issue de sa propre écriture
// (issue #858 point 3).
function copierModerne(projet, numero, producteur, feedback) {
  const monGen = ++generationCopieModerne;
  const variante = variantDuProducteur(producteur);
  const debut = Date.now();   // début de la copie (issue #824) : référence du délai de la ligne de détail
  const feedbackAvecDetail = envelopperFeedbackEchec(feedback, 'moderne', debut);

  // Chemin rapide (issue #832 point 2, conservé) : le texte de cette variante
  // est déjà préparé et encore valide → promesse déjà résolue. Sinon, la
  // préparation (fetch) est lancée maintenant. Dans les deux cas, l'appel à
  // navigator.clipboard.write() ci-dessous a lieu AVANT que cette promesse ne
  // soit même construite — c'est tout l'enjeu de #858 : le chemin lent n'est
  // plus traité différemment du correctif #782 (préparer PUIS écrire), il ne
  // retarde simplement plus l'ENGAGEMENT de l'écriture elle-même.
  const cle = cleIC(projet, numero);
  const prep = textesPrepares.get(cle);
  const entree = prep && prep[variante];
  const dejaValide = texteEstValide(
    entree, cleValiditeIssue(store.lireIssue(projet, numero)), Date.now(), AGE_MAX_TEXTE_PREPARE_MS);
  const promesseTexte = dejaValide
    ? Promise.resolve(entree.valeur)
    : Promise.resolve().then(() => producteur(projet, numero));

  // Issue de la préparation — NE REJETTE JAMAIS (issue #858) : pour que le
  // contenu réellement confié au presse-papier (`blobP` ci-dessous) résolve
  // toujours vers quelque chose d'exploitable (le rapport, ou une chaîne
  // vide) plutôt que de laisser l'écriture en situation d'échec pour une
  // cause qui n'a rien à voir avec le presse-papier lui-même (texte vide,
  // aucun diff, diff volumineux). Le FEEDBACK (plus bas) reste, lui,
  // entièrement fidèle à cette distinction : rien n'est perdu.
  const issuePreparation = promesseTexte.then(
    (t) => {
      if (t && t.aucun) return { statut: 'aucun' };
      if (texteVide(t)) return { statut: 'vide' };
      if (doitTelecharger(variante, t)) return { statut: 'volumineux', texte: t };
      return { statut: 'ok', texte: t };
    },
    (e) => ((e && e.aucun) ? { statut: 'aucun' } : { statut: 'echec', erreur: e }),
  );
  const blobP = issuePreparation.then(
    (r) => new Blob([r.statut === 'ok' ? r.texte : ''], { type: 'text/plain' }));

  // ENGAGEMENT SYNCHRONE, ICI, AU CLIC (issue #858) : le contenu (`blobP`)
  // peut mettre n'importe combien de temps à se résoudre, Firefox a déjà
  // accepté l'activation du geste pour CET appel. Si une copie plus récente
  // est lancée avant que celle-ci n'aboutisse, Firefox annule cette écriture
  // encore pendante (constat de l'issue #782) : `copieSupplantee` la rend
  // silencieuse ci-dessous plutôt que de la traiter comme un échec réel.
  const ecriture = navigator.clipboard.write([new ClipboardItem({ 'text/plain': blobP })])
    .then(() => ({ ok: true }), (erreurEcriture) => ({ ok: false, erreurEcriture }));

  Promise.all([ecriture, issuePreparation]).then(([resultatEcriture, r]) => {
    if (copieSupplantee(monGen)) return;   // issue #858 point 3 : silence total, succès ou échec
    if (r.statut === 'vide') { feedback.vide(); return; }
    if (r.statut === 'aucun') { feedback.aucun ? feedback.aucun() : feedback.vide(); return; }
    if (r.statut === 'volumineux') {
      const nomFichier = nomFichierCopie(projet, numero, variante);
      if (declencherTelechargement(nomFichier, r.texte)) {
        feedback.fichier(messageFichierVolumineux(variante, nombreLignes(r.texte), nomFichier));
      } else {
        feedbackAvecDetail.echec(undefined, r.texte);   // texte transmis : reste accessible (issue #782)
      }
      return;
    }
    if (r.statut === 'echec') { feedbackAvecDetail.echec(r.erreur); return; }
    // r.statut === 'ok' : le rapport était prêt — seul le sort de L'ÉCRITURE
    // elle-même décide maintenant du feedback (jamais de faux succès,
    // issue #636/#782).
    if (resultatEcriture.ok) { avertirVolumineux(r.texte); feedback.succes(); }
    else feedbackAvecDetail.echec(resultatEcriture.erreurEcriture, r.texte);
  });
}

// Valeur de repli si le navigateur refuse une chaîne COMPLÈTEMENT vide dans le
// presse-papier — la plus proche d'un presse-papier vide (issue #857).
const TEXTE_QUASI_VIDE = ' ';

// Vide le presse-papier DANS LE GESTE de clic, avant toute préparation du
// texte du rapport (issue #857) : si la préparation est lente ou si
// l'écriture finale échoue, l'ANCIEN contenu (texte ou capture d'écran) ne
// doit jamais rester en place — Alain pourrait le coller par erreur dans la
// mauvaise conversation sans remarquer l'échec. AUCUN feedback n'est levé ici
// (ni succès ni échec) : un collage vide ne déclenche rien chez Alain,
// contrairement à un message qui pourrait, lui, être collé par erreur. Si la
// copie du rapport aboutit ensuite, elle remplace ce contenu vide ; si elle
// échoue, le presse-papier reste vide (la fenêtre de secours existante
// s'ouvre toujours, issue #782).
//
// CAUSE DE L'ISSUE #865 (établie par relecture du code, pas une simple
// hypothèse) : jusqu'ici, en mode moderne, cette écriture de vidage était
// lancée SANS ATTENDRE sa fin, immédiatement suivie (même geste, lancerCopie
// ci-dessous) de l'écriture du rapport — elle-même engagée SYNCHRONEMENT,
// AVANT que la première n'ait eu la moindre chance de se résoudre. Or
// Firefox annule une écriture encore PENDANTE dès qu'une nouvelle est
// lancée avant qu'elle n'aboutisse (constat déjà établi par #782, réutilisé
// ici) : ce vidage était donc TOUJOURS annulé par l'écriture du rapport qui
// le suivait, avant même d'avoir pu remplacer l'ancien contenu. L'ancien
// commentaire ci-dessous (avant #865) jugeait cela sans conséquence au
// motif que l'écriture du rapport elle-même ne peut résoudre que vers le
// rapport ou une chaîne vide — vrai, mais seulement une fois CETTE écriture
// RÉSOLUE : tant que son contenu (`blobP` dans copierModerne) est encore en
// préparation, rien ne remplace l'ancien contenu, qui reste donc en place
// pendant TOUTE cette fenêtre — exactement le défaut que #857 devait
// empêcher. Reproduit par un test Node (voir
// static/js/tests/resultats_coches_variantes.test.js, issue #865) qui
// modélise le presse-papier RÉEL (contenu à un instant donné, pas seulement
// l'ordre des appels) ; le comportement RÉEL de Firefox (annulation d'une
// écriture pendante par une plus récente, mise à jour différée jusqu'à
// résolution du contenu) reste, lui, une hypothèse non vérifiable sous Node
// — voir l'essai ajouté à VERIFICATIONS_MANUELLES.md.
//
// CORRECTIF (#865) : `lancerCopie` ATTEND désormais la fin RÉELLE de ce
// vidage (cette fonction renvoie sa promesse) avant d'engager l'écriture du
// rapport — un vidage prend quelques millisecondes, bien en deçà de la
// fenêtre d'activation du clic qui a motivé #858 (l'engagement de l'écriture
// du rapport reste donc largement dans cette fenêtre, juste décalé de
// quelques ms). Peu importe que ce vidage réussisse ou soit lui-même annulé
// par une AUTRE copie encore plus récente (plusieurs cases cochées très
// vite, #858 point 3) : la promesse renvoyée se termine dans tous les cas
// (voir le .catch ci-dessous), lancerCopie engage alors l'écriture du
// rapport sans jamais attendre indéfiniment ni répéter le défaut de #782
// (écritures qui s'annulent mutuellement) ou de #858 (écriture refusée pour
// cause de geste expiré).
// UNE SEULE tentative, SANS repli sur TEXTE_QUASI_VIDE en cas d'échec (à la
// différence du mode repli ci-dessous) : un second appel à
// navigator.clipboard.write() ICI serait lui-même une NOUVELLE écriture, qui
// annulerait silencieusement l'écriture du rapport si elle était déjà en
// vol au moment de cet échec (reproduit par un test Node simulant
// l'annulation concurrente, issue #858) — l'échec de ce vidage, best-effort,
// est donc simplement journalisé.
// Mode repli (execCommand, synchrone) : inchangé, aucune file n'a jamais été
// nécessaire, aucune écriture concurrente n'est possible pendant l'appel —
// le repli sur TEXTE_QUASI_VIDE y reste donc sans danger ; la promesse
// renvoyée est déjà résolue (l'écriture a eu lieu avant le retour).
function viderPressePapier() {
  if (modeCopie() === 'moderne') {
    return navigator.clipboard.write([new ClipboardItem({ 'text/plain': new Blob([''], { type: 'text/plain' }) })])
      .catch((e) => {
        console.warn('resultats_coches : échec du vidage du presse-papier (chaîne vide refusée ou annulée).', e);
      });
  }
  // Mode repli : chaîne vide d'abord, espace si le navigateur la refuse.
  if (!copierExecCommand('')) copierExecCommand(TEXTE_QUASI_VIDE);
  return Promise.resolve();
}

// ─── Point d'entrée unique (issue #636, mode repli revu #782) ────────────────
//   - moderne : voir copierModerne ci-dessus. Le vidage est ATTENDU (issue
//     #865, voir viderPressePapier) avant d'engager l'écriture du rapport,
//     pour qu'il ne soit jamais annulé par elle avant d'avoir pu remplacer
//     l'ancien contenu.
//   - repli   : le texte doit déjà être préchargé et valide (textesPrepares,
//     texteEstValide) → copie synchrone execCommand ; sinon feedback « en
//     préparation » + préchargement (texte absent OU périmé, issue #832
//     point 3 : un texte périmé n'est jamais écrit tel quel).
// `variante` ∈ {all, diff, reponse}. `feedback` = { succes, echec, vide, aucun, nonPret }.
// Vide IMMÉDIATEMENT le presse-papier (issue #857, voir viderPressePapier) —
// avant même de savoir si une préparation sera nécessaire : les 4 boutons qui
// passent par ce point d'entrée (case à cocher, badges ✅/Diff/All) en
// bénéficient donc tous, sans code dupliqué.
function lancerCopie(projet, numero, producteur, feedback) {
  const videTermine = viderPressePapier();
  if (modeCopie() === 'moderne') {
    // Attend la fin RÉELLE du vidage (issue #865) avant d'engager l'écriture
    // du rapport — videTermine ne rejette jamais (voir viderPressePapier),
    // ce .then() est donc toujours atteint, que le vidage ait réussi,
    // échoué ou ait lui-même été annulé par une copie encore plus récente.
    videTermine.then(() => copierModerne(projet, numero, producteur, feedback));
    return;
  }
  const debut = Date.now();   // début de la copie (issue #824) : référence du délai de la ligne de détail
  const feedbackAvecDetail = envelopperFeedbackEchec(feedback, 'repli', debut);
  // Mode repli (--lan) : texte requis AVANT le clic.
  const cle = cleIC(projet, numero);
  const variante = variantDuProducteur(producteur);
  const prep = textesPrepares.get(cle);
  const entree = prep && prep[variante];
  if (!texteEstValide(entree, cleValiditeIssue(store.lireIssue(projet, numero)), Date.now(), AGE_MAX_TEXTE_PREPARE_MS)) {
    feedback.nonPret();
    precharger(projet, numero, variante);   // pour que le prochain clic aboutisse
    return;
  }
  const t = entree.valeur;
  if (t && t.aucun) { feedback.aucun ? feedback.aucun() : feedback.vide(); return; }
  if (texteVide(t)) { feedback.vide(); return; }
  if (telechargerOuSignalerVolumineux(projet, numero, variante, t, feedbackAvecDetail)) return;
  if (copierExecCommand(t)) feedback.succes();
  else feedbackAvecDetail.echec(undefined, t);   // texte transmis : reste accessible malgré l'échec (issue #782)
}

// ─── Copie d'un texte déjà connu, sans fetch (issue #823 : bouton « copier »
// du titre dans l'onglet En attente) — réutilise EXACTEMENT le même choix de
// mode (modeCopie/decisionModeCopie) et les deux chemins d'écriture
// (ClipboardItem chaîné / execCommand) que lancerCopie ci-dessus, mais SANS sa
// couche de préparation/cache (textesPrepares, precharger) : inutile ici, le
// texte est déjà disponible AVANT le clic (pas de requête serveur à attendre).
// `feedback` = { succes, echec } — succes() n'est appelé QUE si l'écriture a
// réellement abouti (jamais de faux succès, même contrat que lancerCopie).
export function copierTexteConnu(texte, feedback) {
  const debut = Date.now();   // début de la copie (issue #824) : référence du délai de la ligne de détail
  if (modeCopie() === 'moderne') {
    const feedbackAvecDetail = envelopperFeedbackEchec(feedback, 'moderne', debut);
    const tache = chaineCopieModerne.then(async () => {
      try {
        await navigator.clipboard.write(
          [new ClipboardItem({ 'text/plain': new Blob([texte], { type: 'text/plain' }) })]);
        feedback.succes();
      } catch (e) {
        feedbackAvecDetail.echec(e, texte);   // texte transmis : reste accessible malgré l'échec (issue #782)
      }
    });
    chaineCopieModerne = tache.catch(() => {});
    return;
  }
  const feedbackAvecDetail = envelopperFeedbackEchec(feedback, 'repli', debut);
  if (copierExecCommand(texte)) feedback.succes();
  else feedbackAvecDetail.echec(undefined, texte);
}

// Précharge le texte d'une variante pour (projet, numero) — appelée pour le
// préchargement en tâche de fond ET par lancerCopie/copierModerne quand le
// texte demandé n'est pas encore prêt (pour que le prochain clic aboutisse).
async function precharger(projet, numero, variante) {
  const producteur = variante === 'diff' ? texteDiff : variante === 'reponse' ? texteReponse : texteAll;
  let valeur = '';
  try {
    valeur = await producteur(projet, numero);
  } catch (e) {
    valeur = (e && e.aucun) ? { aucun: true } : '';
  }
  memoriserTextePrepare(projet, numero, variante, valeur);
}

// Borne totale de préparations en attente OU prêtes à la fois (issue #835
// point 1) — nommée et exportée pour rester facile à changer. Fait foi tant
// qu'aucune mesure (voir journal de charge) ne justifie une autre valeur.
export const BORNE_TOTALE_PRECHARGEMENT = 6;

// Sélection PURE des (projet, numero, variante) à précharger (issue #832
// point 1, restreinte et ordonnée par l'issue #835 point 1) : issues des
// SEULS projets dont la pastille est sélectionnée (`projetsSelectionnes`),
// bornées aux `limite` premières de chaque projet — même fenêtre que
// premieresParProjet, donc que les pastilles —, NON cochées, pas déjà
// préparées/en file. Triées de la plus ANCIENNE à la plus RÉCENTE (date de
// création croissante, à égalité le numéro), tous projets sélectionnés
// confondus — pas projet par projet, puisqu'Alain traite les issues
// affichées dans cet ordre. `borneTotale` plafonne le nombre total de
// préparations en attente ou prêtes à la fois : `dejaEnAttenteOuPretes`
// (déjà en file ou déjà préparées et valides, compté par l'appelant) réduit
// d'autant la place restante pour CET appel. `projetsSelectionnes` vide →
// aucun candidat. La variante 'reponse' (celle que la case copie, issue
// #787) est préchargée dans LES DEUX MODES ; la variante 'all' ne l'est
// qu'en mode repli (inchangé depuis #636 — Diff/All restent sur leur chemin
// existant, jamais préchargés). `estCocheFn`/`dejaPresentFn` injectées pour
// rester testable sous Node sans store ni réseau. Exclut aussi toute issue
// « en cours » (issue #838, voir issueEnCours) : aucun rapport à préparer ni
// à signaler pour une issue encore ouverte et pas en échec — le repli sur
// `estIssueEnEchecFn = () => false` traite par défaut toute issue comme pas
// en échec (seul le state CLOSED/ouvert reste alors décisif).
export function candidatsPrechargement(
  issuesTriees, limite, mode, estCocheFn, dejaPresentFn,
  projetsSelectionnes, borneTotale, dejaEnAttenteOuPretes = 0,
  estIssueEnEchecFn = () => false,
) {
  const selection = projetsSelectionnes instanceof Set
    ? projetsSelectionnes : new Set(projetsSelectionnes || []);
  if (!selection.size) return [];
  const visibles = (issuesTriees || []).filter((it) => selection.has(it.projet));
  const parProjet = premieresParProjet(visibles, limite);
  const clesFenetre = new Set();
  for (const [projet, numeros] of Object.entries(parProjet)) {
    for (const n of numeros) clesFenetre.add(projet + '|' + n);
  }
  const fenetre = visibles
    .filter((it) => clesFenetre.has(it.projet + '|' + normaliserNumero(it.number)))
    .sort((a, b) => {
      const diff = new Date(a.createdAt) - new Date(b.createdAt);
      return diff !== 0 ? diff : normaliserNumero(a.number) - normaliserNumero(b.number);
    });
  const candidats = [];
  const placeRestante = () => borneTotale - dejaEnAttenteOuPretes - candidats.length;
  for (const it of fenetre) {
    if (placeRestante() <= 0) break;
    const projet = it.projet;
    const n = normaliserNumero(it.number);
    if (estCocheFn(projet, n)) continue;
    if (issueEnCours(it, estIssueEnEchecFn)) continue;
    if (placeRestante() > 0 && !dejaPresentFn(projet, n, 'reponse')) {
      candidats.push({ projet, numero: n, variante: 'reponse' });
    }
    if (placeRestante() > 0 && mode === 'repli' && !dejaPresentFn(projet, n, 'all')) {
      candidats.push({ projet, numero: n, variante: 'all' });
    }
  }
  return candidats;
}

// File d'exécution des préchargements : UNE préparation à la fois (issue
// #832 point 1 — « ne rien changer à la préparation de all en mode repli »
// mis à part, qui tournait jusqu'ici en parallèle ; étendue aux deux modes,
// une préparation lente ne doit pas en multiplier d'autres en même temps).
// Remplace l'ancienne chaîne de promesses (issue #835 point 1) par un
// tableau explicite : la sélection des pastilles est relue à CHAQUE défilée
// d'un élément (pas seulement à son ajout), pour abandonner sans la préparer
// une entrée dont le projet a été désélectionné pendant qu'elle attendait en
// file — les préparations déjà PRÊTES (dans textesPrepares) ne sont, elles,
// jamais retirées.
let filePrechargement = [];
let prechargementActif = false;

// Mesure d'UNE série de préparations (issue #835 point 4), du premier ajout
// à la file vide : nombre d'issues réellement préparées (pas celles
// abandonnées, voir traiterFilePrechargement), durée totale et max de
// chacune, requêtes réseau faites (api.nombreRequetes(), avant/après — seul
// moyen de compter sans dupliquer un compteur dans chaque producteur de
// texte). null tant qu'aucune série n'est en cours.
let lotPrechargement = null;

function enqueuePrechargementUn(projet, numero, variante) {
  const cle = cleIC(projet, numero) + '|' + variante;
  if (prechargementEnCours.has(cle)) return;
  prechargementEnCours.add(cle);
  filePrechargement.push({ projet, numero, variante, cle });
  if (!lotPrechargement) {
    lotPrechargement = { nbIssues: 0, dureeTotaleMs: 0, dureeMaxMs: 0, requetesDebut: api.nombreRequetes() };
  }
  if (!prechargementActif) {
    prechargementActif = true;
    traiterFilePrechargement();
  }
}

function traiterFilePrechargement() {
  const item = filePrechargement.shift();
  if (!item) {
    prechargementActif = false;
    terminerLotPrechargement();
    return;
  }
  const selection = new Set(appelerAncien('projetsActifsDansFiltreResultats') || nomsProjets());
  if (!selection.has(item.projet)) {
    prechargementEnCours.delete(item.cle);
    traiterFilePrechargement();
    return;
  }
  const debutItem = Date.now();
  precharger(item.projet, item.numero, item.variante)
    .catch(() => {})
    .finally(() => {
      const dureeMs = Date.now() - debutItem;
      if (lotPrechargement) {
        lotPrechargement.nbIssues += 1;
        lotPrechargement.dureeTotaleMs += dureeMs;
        if (dureeMs > lotPrechargement.dureeMaxMs) lotPrechargement.dureeMaxMs = dureeMs;
      }
      prechargementEnCours.delete(item.cle);
      majReperesVisibles();   // repère « prêt à copier » (issue #835 point 2)
      traiterFilePrechargement();
    });
}

// Fin de série (file vide, issue #835 point 4) : envoie au serveur un résumé
// court — nombre d'issues préparées, requêtes réseau faites, durée totale et
// max, mode de copie. Échoue en silence (silencieux:true + catch), sans
// aucune incidence sur l'interface : ce n'est qu'une mesure, jamais un
// chemin critique.
function terminerLotPrechargement() {
  if (!lotPrechargement) return;
  const lot = lotPrechargement;
  lotPrechargement = null;
  api.post('/mesure-precharge', {
    nb_issues_preparees: lot.nbIssues,
    nb_requetes: api.nombreRequetes() - lot.requetesDebut,
    duree_totale_ms: lot.dureeTotaleMs,
    duree_max_ms: lot.dureeMaxMs,
    mode: modeCopie(),
  }, { silencieux: true }).catch(() => {});
}

// Nombre de préparations actuellement en attente (en file ou en cours) ou
// déjà prêtes et valides (issue #835 point 1) — réduit la place disponible
// dans candidatsPrechargement pour que la borne totale porte sur l'ensemble,
// pas sur le seul appel courant.
function compterEnAttenteOuPretes(mode) {
  let total = prechargementEnCours.size;
  const maintenant = Date.now();
  for (const [cle, prep] of textesPrepares) {
    const sep = cle.lastIndexOf('#');
    const projet = cle.slice(0, sep);
    const numero = Number(cle.slice(sep + 1));
    const cv = cleValiditeIssue(store.lireIssue(projet, numero));
    if (texteEstValide(prep.reponse, cv, maintenant, AGE_MAX_TEXTE_PREPARE_MS)) total += 1;
    if (mode === 'repli' && texteEstValide(prep.all, cv, maintenant, AGE_MAX_TEXTE_PREPARE_MS)) total += 1;
  }
  return total;
}

// Précharge en tâche de fond, dans les DEUX modes de copie, le texte copié
// par la case (variante 'reponse') des issues VISIBLES (projets dont la
// pastille est sélectionnée, fenêtre « par projet : N ») NON cochées — pour
// qu'en mode moderne (Firefox notamment), le texte soit déjà prêt AVANT le
// clic plutôt que préparé après (fenêtre d'activation du geste, issue #832).
// En mode repli, précharge EN PLUS la variante 'all' (inchangé depuis #636).
// Restreinte aux pastilles sélectionnées, ordonnée par ancienneté et bornée
// au total (issue #835 point 1). Lancée MÊME quand la page est cachée
// (document.hidden) depuis l'issue #839 : sans ce chemin, une issue qui se
// termine pendant qu'Alain lit un autre onglet n'était préparée qu'à son
// retour, trop tard pour que la copie soit immédiate (fenêtre d'activation
// du geste, issue #832) — les protections restent les mêmes (une
// préparation à la fois, borne totale, issues terminées seulement, projets
// sélectionnés, plus ancienne d'abord).
// Renommée depuis precharderVisiblesRepli (issue #832 : son nom ne disait
// plus la vérité une fois étendue au mode moderne).
function precharderVisibles() {
  const mode = modeCopie();
  const selection = new Set(appelerAncien('projetsActifsDansFiltreResultats') || nomsProjets());
  const candidats = candidatsPrechargement(
    issuesTriees(), limiteParProjet(), mode, estCoche,
    (projet, numero, variante) => {
      const cle = cleIC(projet, numero);
      const prep = textesPrepares.get(cle);
      return (prep && prep[variante] !== undefined) || prechargementEnCours.has(cle + '|' + variante);
    },
    selection, BORNE_TOTALE_PRECHARGEMENT, compterEnAttenteOuPretes(mode), estIssueEnEchecPont);
  for (const c of candidats) enqueuePrechargementUn(c.projet, c.numero, c.variante);
}

// ─── Repère « prêt à copier » sur la ligne (issue #835 point 2) ─────────────
// Avant même le clic : un petit repère discret près de la case signale que le
// texte qu'elle copie (variante 'reponse', la SEULE que la case copie, issue
// #787) est déjà préparé et valide (texteEstValide) — le prochain clic sera
// alors immédiat. Disparaît à la coche, à la péremption (âge max ou clé de
// validité qui change) ou si la ligne est retirée du DOM (rien à mettre à
// jour, elle n'existe plus). Mis à jour à la fin de chaque préparation (voir
// traiterFilePrechargement) et au plus toutes les 30s tant que la page est
// visible (voir initialiser ci-dessous).
// Vrai si le repère doit être affiché pour une issue — PURE (reçoit tout en
// argument, aucun accès store/DOM), pour rester testable sous Node comme le
// reste de la section 1 : la coche ET la validité du texte sont décidées ICI,
// un seul endroit, plutôt que dispatchées entre l'appelant et texteEstValide.
// `enCours` (issue #838, voir issueEnCours) masque le repère pour une issue
// encore ouverte et pas en échec, même si un texte préparé et valide existe
// pour elle (préparé avant cette correction, ou par un autre chemin) : la
// copie ne donnerait pas le rapport attendu tant que l'issue n'est pas
// terminée. Calculé par l'appelant (pas ici) : cette fonction reste pure et
// ignore délibérément l'état/les labels bruts de l'issue.
export function reperePretACopier(coche, entreeTexte, cleValiditeActuelle, maintenant, ageMaxMs, enCours = false) {
  return !coche && !enCours && texteEstValide(entreeTexte, cleValiditeActuelle, maintenant, ageMaxMs);
}

function majRepereLigne(ligne) {
  const span = ligne && ligne.querySelector ? ligne.querySelector('.repere-pret-copie') : null;
  if (!span) return;
  const projet = ligne.dataset.projet;
  const numero = ligne.dataset.numero;
  const cle = cleIC(projet, numero);
  const prep = textesPrepares.get(cle);
  const entree = prep && prep.reponse;
  const it = store.lireIssue(projet, numero);
  const pret = reperePretACopier(
    estCoche(projet, numero), entree, cleValiditeIssue(it),
    Date.now(), AGE_MAX_TEXTE_PREPARE_MS, issueEnCours(it, estIssueEnEchecPont));
  span.style.display = pret ? '' : 'none';
}

function majReperesVisibles() {
  if (typeof document === 'undefined') return;
  document.querySelectorAll('.ligne-issue').forEach((ligne) => majRepereLigne(ligne));
}

// ─── Feedbacks ────────────────────────────────────────────────────────────────
const MESSAGE_ECHEC_COPIE = 'Copie impossible — le presse-papier n\'a pas pu être écrit.';

// Message principal du toast quand l'écriture a été refusée pour geste
// expiré/préparation trop longue (issue #832 point 4b) — DEVENU SUPERFLU
// depuis #858 (gardé, non supprimé, non branché dans copierModerne) :
// l'écriture étant désormais engagée au clic (voir gesteExpireOuPreparationLente),
// ce cas précis ne se produit plus par construction.
export const MESSAGE_PREPARATION_TROP_LONGUE = 'Préparation trop longue pour le presse-papier : '
  + 'copie manuelle ci-dessous (Ctrl+C) ; le texte est maintenant prêt, décoche puis recoche la case.';

// Échec de copie (issue #782) : le texte n'est JAMAIS simplement perdu — quand
// il est disponible (toute cause d'échec SAUF un texte vide, déjà couvert par
// `vide`), il est joint au toast d'erreur dans une zone sélectionnable
// (`texteSecours`, voir toasts.js) pour un Ctrl+C manuel. Ce filet vaut quelle
// que soit la cause de l'échec (API presse-papier refusée, execCommand en
// échec, etc.), pas seulement celle corrigée ci-dessus.
// `detail` (issue #824) : ligne de détail technique (voir construireDetailEchecCopie)
// — journalisée par console.warn ET jointe au toast (ligne discrète + entrée
// du panneau « Messages »), sans jamais changer le message principal
// (MESSAGE_ECHEC_COPIE) ni `texteSecours` ci-dessus. `messagePrincipal` (issue
// #832 point 4b) remplace MESSAGE_ECHEC_COPIE dans le SEUL cas où l'écriture a
// été refusée pour geste expiré/préparation trop longue (voir
// gesteExpireOuPreparationLente) — absent, le message par défaut s'applique,
// inchangé pour toute autre cause d'échec.
export function signalerEchecCopie(texte, detail, messagePrincipal) {
  if (detail) console.warn(detail);
  toasts.erreur(messagePrincipal || MESSAGE_ECHEC_COPIE, true, {
    texteSecours: texte || undefined,
    detailTechnique: detail || undefined,
  });
}

// Cochage d'une case : feedback par TOAST (pas de badge sur la case). `fichier`
// n'est en pratique jamais appelé ici : la case ne copie que 'reponse' (issue
// #787), jamais soumise au téléchargement (issue #790 point 5) — gardé pour
// que l'objet reste un contrat complet, au cas où un futur appelant l'utilise.
function feedbackToast() {
  return {
    succes: () => toasts.succes('Rapport copié dans le presse-papier.', false),
    fichier: (message) => toasts.avertissement(message),
    echec: (e, texte, detail, messagePrincipal) => signalerEchecCopie(texte, detail, messagePrincipal),
    vide: () => toasts.avertissement(TITRE_COPIE_VIDE),
    nonPret: () => toasts.info('Préparation de la copie en cours — recoche dans un instant.', false),
  };
}

// ─── Journal de diagnostic de la copie (issue #878) ──────────────────────────
// Contexte commun aux deux points d'observation ci-dessous (watchdog
// mousedown/change ET résultat de l'écriture) — DÉSACTIVÉ PAR DÉFAUT, voir
// static/js/socle/diagnostic_copie.js pour l'activation et le détail des
// champs. `element` : le nœud DOM dont on veut savoir s'il est resté attaché
// (document.contains), typiquement la case cliquée elle-même.
function contexteDiagnosticCopie(projet, numero, ligne, element) {
  const redessineeA = ligne ? Number(ligne.dataset.redessineeA) : NaN;
  return {
    date: new Date().toISOString(),
    navigateur: (typeof navigator !== 'undefined' && navigator.userAgent)
      ? detecterNavigateur(navigator.userAgent) : undefined,
    projet,
    numero: normaliserNumero(numero),
    depuisDernierEvenementSseMs: sse.stream.depuisDerniereActiviteMs(),
    etatSse: sse.stream.etat(),
    elementDansDocument: element
      ? (typeof document !== 'undefined' ? document.contains(element) : undefined)
      : undefined,
    ligneRedessineeRecemment: ligneRedessineeRecemment(redessineeA, Date.now()),
  };
}

// Enveloppe feedbackToast() pour que le résultat RÉEL de l'écriture (succès,
// vide, échec, non prêt — jamais un faux succès, même contrat que le reste
// du moteur de copie) alimente aussi le journal de diagnostic, SANS changer
// aucun des toasts existants ni leur ordre d'appel (un seul appel
// supplémentaire AVANT de déléguer à l'original). NO-OP transparent si le
// journal est désactivé (diagnostiquer() ne fait rien dans ce cas).
function feedbackToastAvecDiagnostic(projet, numero, ligne, cb) {
  const original = feedbackToast();
  if (!diagnosticActif()) return original;
  const ctx = (resultat) => ({ ...contexteDiagnosticCopie(projet, numero, ligne, cb), etape: 'ecriture', resultat });
  return {
    succes: () => { diagnostiquer(ctx('succes')); original.succes(); },
    fichier: (message) => { diagnostiquer(ctx('fichier_telecharge')); original.fichier(message); },
    echec: (e, texte, detail, messagePrincipal) => {
      diagnostiquer(ctx('echec'));
      original.echec(e, texte, detail, messagePrincipal);
    },
    vide: () => { diagnostiquer(ctx('vide')); original.vide(); },
    nonPret: () => { diagnostiquer(ctx('non_pret')); original.nonPret(); },
  };
}

// Délai au-delà duquel, faute du `change` attendu après un `mousedown` sur la
// case, on considère le clic comme resté SANS EFFET (issue #878) — assez
// court pour ne retarder qu'un simple log, assez long pour ne jamais se
// déclencher sur un clic normal (y compris une préparation lente : le mode
// moderne engage l'écriture AU CLIC depuis #858, `change` fire donc toujours
// quasi immédiatement, que le rapport soit déjà prêt ou pas).
export const DELAI_ATTENTE_CHANGE_MS = 1500;

// Surveille, en DÉLÉGATION sur `document` (jamais remplacé, contrairement aux
// lignes — issue #878), chaque `mousedown` sur une case de copie : si le
// `change` attendu ne suit pas dans DELAI_ATTENTE_CHANGE_MS, le clic a été
// perdu (nœud détruit entre le `mousedown` et le `click`/`change` — voir
// static/js/app.js::coucheResultatEnInteraction pour le mécanisme). NO-OP si
// le journal est désactivé (pas de minuteur posé du tout).
function surMousedownCoucheCopie(event) {
  if (!diagnosticActif()) return;
  const cb = event && event.target && event.target.closest
    ? event.target.closest('.coche-resultat') : null;
  if (!cb) return;
  const ligne = cb.closest ? cb.closest('.ligne-issue') : null;
  const projet = ligne && ligne.dataset.projet;
  const numero = ligne && ligne.dataset.numero;
  let conclu = false;
  const surChange = () => {
    if (conclu) return;
    conclu = true;
    clearTimeout(minuteur);
    diagnostiquer({ ...contexteDiagnosticCopie(projet, numero, ligne, cb), etape: 'change', resultat: 'declenche' });
  };
  cb.addEventListener('change', surChange, { once: true });
  const minuteur = setTimeout(() => {
    if (conclu) return;
    conclu = true;
    cb.removeEventListener('change', surChange);
    diagnostiquer({
      ...contexteDiagnosticCopie(projet, numero, ligne, cb),
      etape: 'change',
      resultat: 'aucun_changement_detecte',
    });
  }, DELAI_ATTENTE_CHANGE_MS);
}

// Badge de liste (✅/Diff/All) : ✓ bref sur succès, ⚠/∅ sur vide/aucun, toast sur échec.
// `fichier` (issue #790, boutons Diff/All au-delà du seuil de lignes) : ⬇ bref
// sur le badge + toast persistant détaillant le fichier téléchargé.
function feedbackBadge(badge) {
  const original = badge ? badge.textContent : '';
  const titre = badge ? badge.title : '';
  const restaurer = () => { if (badge) { badge.textContent = original; badge.title = titre; } };
  const flash = (symbole) => { if (badge) { badge.textContent = symbole; setTimeout(restaurer, 1500); } };
  return {
    succes: () => flash('✓'),
    fichier: (message) => { flash('⬇'); toasts.avertissement(message); },
    echec: (e, texte, detail, messagePrincipal) => signalerEchecCopie(texte, detail, messagePrincipal),
    vide: () => { if (badge) { badge.textContent = '⚠'; badge.title = TITRE_COPIE_VIDE; setTimeout(restaurer, 2000); } },
    aucun: () => flash('∅'),
    nonPret: () => { toasts.info('Contenu en préparation — reclique dans un instant.', false); },
  };
}

// Badges de la liste (appelés par app.js via le pont, depuis les onclick inline).
function copierReponseBadge(event, projet, numero) {
  if (event) event.stopPropagation();
  lancerCopie(projet, numero, texteReponse, feedbackBadge(event && event.currentTarget));
}
function copierAllBadge(event, projet, numero) {
  if (event) event.stopPropagation();
  lancerCopie(projet, numero, texteAll, feedbackBadge(event && event.currentTarget));
}
function copierDiffBadge(event, projet, numero) {
  if (event) event.stopPropagation();
  lancerCopie(projet, numero, texteDiff, feedbackBadge(event && event.currentTarget));
}

// ─────────────────────────────────────────────────────────────────────────────
// 4. AMORÇAGE (appelé une fois par index.js)
// ─────────────────────────────────────────────────────────────────────────────
async function initialiser() {
  // 1) Reprise de l'existant : migrer les clés localStorage héritées vers le
  //    serveur (idempotent), AVANT de charger l'état serveur consolidé.
  await migrerLocalStorage();
  // 2) Charger l'état serveur de tous les projets connus (un GET par projet),
  //    puis resynchroniser le DOM déjà rendu (liste chargée à l'activation).
  await rechargerCases();
  // 3) Précharger le texte des issues visibles décochées à chaque changement
  //    de liste, pour une copie fiable au 1er clic — dans les DEUX modes
  //    depuis l'issue #832 (auparavant mode repli seul).
  store.abonnerCle('issues', () => setTimeout(precharderVisibles, 0));
  setTimeout(precharderVisibles, 0);
  // 4) Événement /stream `case_decochee` (issue #720, déposé dans le store par
  //    sse.js) — décoche instantanée d'un onglet Résultats déjà ouvert.
  store.abonnerCle('derniereNotifCase', (notif) => surCaseDecochee(notif));
  // 5) Repère « prêt à copier » (issue #835 point 2) : au plus toutes les 30s
  //    tant que la page est visible — en plus de la mise à jour à la fin de
  //    chaque préparation (voir traiterFilePrechargement).
  setInterval(() => {
    if (typeof document === 'undefined' || !document.hidden) majReperesVisibles();
  }, 30000);
  // 6) Retour sur la page (issue #839) : au passage caché → visible, relance
  //    immédiatement la précharge et le rafraîchissement des repères plutôt
  //    que d'attendre le prochain tour du minuteur de 30s ci-dessus — le
  //    repère « prêt à copier » doit déjà être à jour à l'instant du retour.
  if (typeof document !== 'undefined' && document.addEventListener) {
    document.addEventListener('visibilitychange', () => {
      if (!document.hidden) { precharderVisibles(); majReperesVisibles(); }
    });
  }
  // 7) Journal de diagnostic de la copie (issue #878), DÉSACTIVÉ PAR DÉFAUT —
  // voir static/js/socle/diagnostic_copie.js. Rejoue la file en attente d'une
  // session précédente (serveur injoignable au moment du clic) et pose, en
  // délégation sur `document` (jamais remplacé), le watchdog mousedown/change
  // qui détecte un clic resté sans effet (surMousedownCoucheCopie ci-dessus).
  rejouerFileEnAttente();
  if (typeof document !== 'undefined' && document.addEventListener) {
    document.addEventListener('mousedown', surMousedownCoucheCopie);
  }
}

// Objet publié sous window.Bridge.resultatsCoches (via installerPont dans index.js) :
// estCoche/basculer/cocherTout/remettreAZero/copierReponseBadge/copierAllBadge/
// copierDiffBadge sont l'API consommée par l'ancien app.js pendant la
// transition (case à cocher, badges de copie, boutons « Cocher tout » et
// remise à zéro). majReperesVisibles s'y ajoute (issue #835 point 2) : appelée
// par app.js (restaurerCasesCocheesResultats) après tout redessin/resync du
// DOM, pour que le repère reflète l'état déjà connu de ce module sur des
// lignes fraîchement reconstruites. precharderVisibles est aussi appelée
// directement par app.js (basculerFiltreProjet/basculerTousLesFiltres, issue
// #835 point 1) quand la sélection des pastilles change. initialiser/
// rechargerCases ne passent jamais par le pont (initialiser est appelée
// directement par index.js via import ES ; rechargerCases n'est utilisée
// qu'en interne à ce module) — exposées ici uniquement pour rester testables
// directement (même principe que depuis #636).
export const resultatsCoches = {
  initialiser,
  estCoche,
  basculer,
  cocherTout,
  remettreAZero,
  copierReponseBadge,
  copierAllBadge,
  copierDiffBadge,
  rechargerCases,
  precharderVisibles,
  majReperesVisibles,
};
