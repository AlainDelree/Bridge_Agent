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
// fichier réécrit) soit détectable sans dérouler le diff complet. Quatre règles
// (constats de l'issue, complétées par l'issue #808) :
//   - issue for-windows (etat 'windows') → l'inventaire n'est PAS DEMANDÉ au
//     serveur (ses commits sont sur le PC fixe, le dépôt du ThinkPad ne les
//     connaît pas) : texte neutre expliquant pourquoi et où regarder à la
//     place, sans symbole d'alerte — ce n'est pas une anomalie.
//   - ligne « Commits » explicitement « aucun » (lecture seule) → aucune
//     section, aucune alerte : c'est le cas normal.
//   - ligne absente/non reconnue, OU un commit en échec (introuvable, git en
//     panne…) → le dire CLAIREMENT dans la section, jamais en silence
//     (contrairement au bouton Diff, qui ignore un diff en échec) — un bug de
//     reconnaissance des commits est déjà resté invisible deux mois (#784).
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
// 'aucun','absente'} (voir etatCommitsDeclares, app.js) ; `resultatsParCommit`
// est ignoré si `etatCommits` !== 'hashes'.
export function texteSectionFichiers(etatCommits, resultatsParCommit) {
  if (etatCommits === 'aucun') return '';
  const lignes = ['===== ' + TITRE_SECTION_FICHIERS + ' ====='];
  if (etatCommits === 'windows') {
    lignes.push('', TEXTE_INVENTAIRE_WINDOWS);
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
  if (coche) lancerCopie(projet, numero, texteReponse, feedbackToast());

  // 2) Mise à jour optimiste : store + grisage + pastilles.
  const avant = etatCases();
  store.set('casesCochees', coche
    ? ajouterDansEtat(avant, projet, numero)
    : retirerDansEtat(avant, projet, numero));
  if (ligne) ligne.classList.toggle('resultat-traite', coche);
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
// 3. MOTEUR DE COPIE FIABLE (issue #636, mode moderne revu #782, fichier #790)
//    Un seul chemin pour toutes les copies « fetch puis écriture » : cocher une
//    case, badges ✅/Diff/All. Le succès n'est signalé QUE s'il a réellement eu
//    lieu. Mode moderne (voir copierModerne) : le texte est préparé AVANT la
//    demande d'écriture et les écritures sont sérialisées — cocher plusieurs
//    cases rapprochées ne fait plus échouer toutes les copies sauf la
//    dernière (issue #782, voir le rapport pour la reproduction).
//    Diff/All au-delà de SEUIL_LIGNES_VOLUMINEUX lignes (issue #790) : ni
//    moderne ni repli ne copient — un fichier .txt est téléchargé à la place
//    (voir telechargerOuSignalerVolumineux/declencherTelechargement). 'reponse'
//    n'est jamais concernée (seul l'ancien toast d'avertissement s'applique).
// ─────────────────────────────────────────────────────────────────────────────

const TITRE_COPIE_VIDE = 'Réponse pas encore disponible — réessaie dans quelques secondes';

function texteVide(t) { return !t || !t.trim(); }

function modeCopie() {
  return decisionModeCopie(
    (typeof window !== 'undefined') ? window.isSecureContext : false,
    (typeof navigator !== 'undefined') ? navigator.clipboard : null,
    (typeof ClipboardItem !== 'undefined'));
}

// Cache de détail (économie de fetch) et textes préchargés pour le mode repli.
const DETAIL_TTL_MS = 60000;
const detailCache = new Map();          // cle → { ts, it }
const textesPrepares = new Map();       // cle → { all?, diff?, reponse? }
const prechargementEnCours = new Set(); // clés dont un préchargement 'all' est lancé

function cleIC(projet, numero) { return projet + '#' + normaliserNumero(numero); }

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
// commits. Voir texteSectionFichiers pour le détail des quatre cas.
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

// ─── Mode « moderne » : sérialisé (issue #782) ────────────────────────────────
// Diagnostic établi par reproduction (WebDriver + Firefox, voir le rapport de
// l'issue) : navigator.clipboard.write() ANNULE (NotAllowedError) une écriture
// encore PENDANTE dès qu'une NOUVELLE est lancée avant que la précédente ait
// abouti — seule la plus récente survit. Cocher plusieurs cases rapprochées
// (chacune fetchant son contenu avant d'écrire) laissait donc plusieurs
// écritures en vol en même temps, et toutes sauf la dernière échouaient. Le
// correctif tient en deux points : le texte est intégralement PRÊT avant de
// demander l'écriture (jamais de Blob en promesse pendante confié à
// ClipboardItem — testé jusqu'à 5s de latence réseau sans que la seule
// activation du clic ne soit requise au moment de l'appel), et les appels sont
// CHAÎNÉS pour qu'une seule écriture soit en vol à la fois, même si plusieurs
// textes deviennent prêts au même instant.
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

// Enveloppe le `feedback` reçu pour que son `echec(e, texte)` reçoive un 3e
// argument (la ligne de détail ci-dessus), sans toucher aux autres callbacks
// ni au contrat existant (issue #824 : les appelants de signalerEchecCopie
// ignoraient jusqu'ici l'exception `e`). Posée une fois par point d'entrée
// (copierModerne/lancerCopie/copierTexteConnu) pour que tous les appels
// internes à `feedback.echec` (y compris depuis telechargerOuSignalerVolumineux)
// portent `mode`/`debut` sans avoir à les faire transiter partout.
function envelopperFeedbackEchec(feedback, mode, debut) {
  if (!feedback || typeof feedback.echec !== 'function') return feedback;
  return {
    ...feedback,
    echec: (e, texte) => feedback.echec(e, texte, construireDetailEchecCopie(e, mode, debut, texte)),
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

function copierModerne(projet, numero, producteur, feedback) {
  const variante = variantDuProducteur(producteur);
  const debut = Date.now();   // début de la copie (issue #824) : référence du délai de la ligne de détail
  const feedbackAvecDetail = envelopperFeedbackEchec(feedback, 'moderne', debut);
  const tache = chaineCopieModerne.then(async () => {
    let t;
    try {
      t = await producteur(projet, numero);
    } catch (e) {
      if (e && e.aucun) { feedback.aucun ? feedback.aucun() : feedback.vide(); }
      else feedbackAvecDetail.echec(e);
      return;
    }
    if (texteVide(t)) { feedback.vide(); return; }
    if (telechargerOuSignalerVolumineux(projet, numero, variante, t, feedbackAvecDetail)) return;
    try {
      await navigator.clipboard.write([new ClipboardItem({ 'text/plain': new Blob([t], { type: 'text/plain' }) })]);
      feedback.succes();
    } catch (e) {
      feedbackAvecDetail.echec(e, t);   // texte transmis : reste accessible malgré l'échec (issue #782)
    }
  });
  // La chaîne continue même après un échec : un copierModerne en erreur ne doit
  // jamais bloquer les suivants.
  chaineCopieModerne = tache.catch(() => {});
}

// ─── Point d'entrée unique (issue #636, mode repli revu #782) ────────────────
//   - moderne : voir copierModerne ci-dessus.
//   - repli   : le texte doit déjà être préchargé (textesPrepares) → copie
//     synchrone execCommand ; sinon feedback « en préparation » + préchargement.
// `variante` ∈ {all, diff, reponse}. `feedback` = { succes, echec, vide, aucun, nonPret }.
function lancerCopie(projet, numero, producteur, feedback) {
  if (modeCopie() === 'moderne') {
    copierModerne(projet, numero, producteur, feedback);
    return;
  }
  const debut = Date.now();   // début de la copie (issue #824) : référence du délai de la ligne de détail
  const feedbackAvecDetail = envelopperFeedbackEchec(feedback, 'repli', debut);
  // Mode repli (--lan) : texte requis AVANT le clic.
  const cle = cleIC(projet, numero);
  const variante = variantDuProducteur(producteur);
  const prep = textesPrepares.get(cle);
  const t = prep ? prep[variante] : undefined;
  if (t === undefined) {
    feedback.nonPret();
    precharger(projet, numero, variante);   // pour que le prochain clic aboutisse
    return;
  }
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

// Précharge (mode repli) le texte d'une variante pour (projet, numero).
async function precharger(projet, numero, variante) {
  const cle = cleIC(projet, numero);
  const producteur = variante === 'diff' ? texteDiff : variante === 'reponse' ? texteReponse : texteAll;
  let valeur = '';
  try {
    valeur = await producteur(projet, numero);
  } catch (e) {
    valeur = (e && e.aucun) ? { aucun: true } : '';
  }
  const prep = textesPrepares.get(cle) || {};
  prep[variante] = valeur;
  textesPrepares.set(cle, prep);
}

// Précharge en tâche de fond, en mode repli seulement, le texte 'all' des issues
// visibles NON cochées (pour que cocher une case copie fiablement au 1er clic).
// Économe : borné aux premières issues par projet (périmètre des pastilles),
// uniquement les décochées, une seule fois par clé.
function precharderVisiblesRepli() {
  if (modeCopie() !== 'repli') return;
  const parProjet = premieresParProjet(issuesTriees(), limiteParProjet());
  for (const [projet, numeros] of Object.entries(parProjet)) {
    for (const n of numeros) {
      if (estCoche(projet, n)) continue;
      const cle = cleIC(projet, n);
      const prep = textesPrepares.get(cle);
      if ((prep && prep.all !== undefined) || prechargementEnCours.has(cle)) continue;
      prechargementEnCours.add(cle);
      precharger(projet, n, 'all').finally(() => prechargementEnCours.delete(cle));
    }
  }
}

// ─── Feedbacks ────────────────────────────────────────────────────────────────
const MESSAGE_ECHEC_COPIE = 'Copie impossible — le presse-papier n\'a pas pu être écrit.';

// Échec de copie (issue #782) : le texte n'est JAMAIS simplement perdu — quand
// il est disponible (toute cause d'échec SAUF un texte vide, déjà couvert par
// `vide`), il est joint au toast d'erreur dans une zone sélectionnable
// (`texteSecours`, voir toasts.js) pour un Ctrl+C manuel. Ce filet vaut quelle
// que soit la cause de l'échec (API presse-papier refusée, execCommand en
// échec, etc.), pas seulement celle corrigée ci-dessus.
// `detail` (issue #824) : ligne de détail technique (voir construireDetailEchecCopie)
// — journalisée par console.warn ET jointe au toast (ligne discrète + entrée
// du panneau « Messages »), sans jamais changer le message principal
// (MESSAGE_ECHEC_COPIE) ni `texteSecours` ci-dessus.
export function signalerEchecCopie(texte, detail) {
  if (detail) console.warn(detail);
  toasts.erreur(MESSAGE_ECHEC_COPIE, true, {
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
    echec: (e, texte, detail) => signalerEchecCopie(texte, detail),
    vide: () => toasts.avertissement(TITRE_COPIE_VIDE),
    nonPret: () => toasts.info('Préparation de la copie en cours — recoche dans un instant.', false),
  };
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
    echec: (e, texte, detail) => signalerEchecCopie(texte, detail),
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
  // 3) En mode repli (--lan), précharger le texte des issues visibles décochées
  //    à chaque changement de liste, pour une copie fiable au 1er clic.
  store.abonnerCle('issues', () => setTimeout(precharderVisiblesRepli, 0));
  setTimeout(precharderVisiblesRepli, 0);
  // 4) Événement /stream `case_decochee` (issue #720, déposé dans le store par
  //    sse.js) — décoche instantanée d'un onglet Résultats déjà ouvert.
  store.abonnerCle('derniereNotifCase', (notif) => surCaseDecochee(notif));
}

// Objet publié sous window.Bridge.resultatsCoches (via installerPont dans index.js) :
// estCoche/basculer/cocherTout/remettreAZero/copierReponseBadge/copierAllBadge/
// copierDiffBadge sont l'API consommée par l'ancien app.js pendant la
// transition (case à cocher, badges de copie, boutons « Cocher tout » et
// remise à zéro). initialiser et rechargerCases ne passent jamais par le pont
// (initialiser est appelée directement par index.js via import ES ;
// rechargerCases n'est utilisée qu'en interne à ce module) — exposées ici
// uniquement pour rester testables directement.
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
};
