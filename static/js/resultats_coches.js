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
  let entrees = [];
  try {
    if (typeof localStorage !== 'undefined') {
      for (let i = 0; i < localStorage.length; i++) {
        const cle = localStorage.key(i);
        if (cle) entrees.push({ cle, valeur: localStorage.getItem(cle) });
      }
    }
  } catch (e) { return; }
  const { cases, cles } = extraireCasesLegacy(entrees);
  if (!cases.length) return;
  try {
    const rep = await api.post('/cases-cochees/importer', { cases }, { silencieux: true });
    if (rep && rep.succes) {
      for (const cle of cles) persistance.supprimer(cle);
    }
  } catch (e) { /* réseau : on retentera au prochain chargement */ }
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
  if (coche) lancerCopie(projet, numero, texteAll, feedbackToast());

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
  if (!cases.length) { toasts.info('Toutes les issues chargées sont déjà cochées.'); return; }
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
// 3. MOTEUR DE COPIE FIABLE (issue #636)
//    Un seul chemin pour toutes les copies « fetch puis écriture » : cocher une
//    case, badges ✅/Diff/All. La copie est ENGAGÉE pendant le geste ; le succès
//    n'est signalé QUE s'il a réellement eu lieu.
// ─────────────────────────────────────────────────────────────────────────────

const ERREUR_VIDE = Symbol('copie-vide');
const ERREUR_AUCUN = Symbol('copie-aucun');   // aucun diff (issue en lecture seule)
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

// Producteurs de texte (réutilisent reponseCompleteCcl/hashesDeCommit d'app.js
// via le pont — aucune duplication de la reconstruction markdown).
async function texteReponse(projet, numero) {
  const it = await detailIssue(projet, numero);
  return it ? (appelerAncien('reponseCompleteCcl', it) || '') : '';
}
async function texteAll(projet, numero) {
  const it = await detailIssue(projet, numero);
  if (!it) return '';
  let texte = appelerAncien('reponseCompleteCcl', it) || '';
  const hashes = appelerAncien('hashesDeCommit', it) || [];
  const diffs = await diffCommits(projet, hashes);
  if (diffs.length) texte += '\n\n' + diffs.join('\n\n');
  return texte;
}
async function texteDiff(projet, numero) {
  const it = await detailIssue(projet, numero);
  if (!it) return '';
  const hashes = appelerAncien('hashesDeCommit', it) || [];
  if (!hashes.length) { const e = new Error('aucun'); e.aucun = true; throw e; }
  return (await diffCommits(projet, hashes)).join('\n\n');
}

function avertirVolumineux(texte) {
  const nb = texte.split('\n').length;
  if (nb > 1000) {
    toasts.avertissement('Diff volumineux (' + nb + ' lignes) — Claude.ai pourrait ne pas le lire.');
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

// Cœur du correctif (issue #636) : engage la copie AU GESTE.
//   - moderne : navigator.clipboard.write([ClipboardItem({text: promesse})]) —
//     appelé SYNCHRONEMENT, le texte est fetché ensuite dans la promesse.
//   - repli : le texte doit déjà être préchargé (textesPrepares) → copie
//     synchrone execCommand ; sinon feedback « en préparation » + préchargement.
// `variante` ∈ {all, diff, reponse}. `feedback` = { succes, echec, vide, aucun, nonPret }.
function lancerCopie(projet, numero, producteur, feedback) {
  const cle = cleIC(projet, numero);
  const variante = producteur === texteAll ? 'all' : producteur === texteDiff ? 'diff' : 'reponse';
  if (modeCopie() === 'moderne') {
    // Le contenu est fourni de façon DIFFÉRÉE (ClipboardItem alimenté par une
    // promesse) : navigator.clipboard.write est appelé SYNCHRONEMENT au clic, le
    // texte est fetché ensuite (hors fenêtre d'activation, mais la copie est déjà
    // engagée). Un try/catch protège d'un throw synchrone (ClipboardItem/promesse
    // non supporté) → feedback d'échec honnête, jamais de faux succès.
    const traiter = (e) => {
      if (e === ERREUR_VIDE) feedback.vide();
      else if (e && e.aucun) feedback.aucun ? feedback.aucun() : feedback.vide();
      else feedback.echec(e);
    };
    try {
      const blobP = Promise.resolve().then(() => producteur(projet, numero)).then((t) => {
        if (texteVide(t)) throw ERREUR_VIDE;
        avertirVolumineux(t);
        return new Blob([t], { type: 'text/plain' });
      });
      // Éviter un rejet non capturé si write() ignore la promesse du ClipboardItem.
      blobP.catch(() => {});
      navigator.clipboard.write([new ClipboardItem({ 'text/plain': blobP })])
        .then(() => feedback.succes())
        .catch(traiter);
    } catch (e) { traiter(e); }
    return;
  }
  // Mode repli (--lan) : texte requis AVANT le clic.
  const prep = textesPrepares.get(cle);
  const t = prep ? prep[variante] : undefined;
  if (t === undefined) {
    feedback.nonPret();
    precharger(projet, numero, variante);   // pour que le prochain clic aboutisse
    return;
  }
  if (t && t.aucun) { feedback.aucun ? feedback.aucun() : feedback.vide(); return; }
  if (texteVide(t)) { feedback.vide(); return; }
  avertirVolumineux(t);
  if (copierExecCommand(t)) feedback.succes();
  else feedback.echec();
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
// Cochage d'une case : feedback par TOAST (pas de badge sur la case).
function feedbackToast() {
  return {
    succes: () => toasts.succes('Rapport copié dans le presse-papier.'),
    echec: () => toasts.erreur('Copie impossible — le presse-papier n\'a pas pu être écrit.'),
    vide: () => toasts.avertissement(TITRE_COPIE_VIDE),
    nonPret: () => toasts.info('Préparation de la copie en cours — recoche dans un instant.'),
  };
}

// Badge de liste (✅/Diff/All) : ✓ bref sur succès, ⚠/∅ sur vide/aucun, toast sur échec.
function feedbackBadge(badge) {
  const original = badge ? badge.textContent : '';
  const titre = badge ? badge.title : '';
  const restaurer = () => { if (badge) { badge.textContent = original; badge.title = titre; } };
  const flash = (symbole) => { if (badge) { badge.textContent = symbole; setTimeout(restaurer, 1500); } };
  return {
    succes: () => flash('✓'),
    echec: () => { toasts.erreur('Copie impossible — le presse-papier n\'a pas pu être écrit.'); },
    vide: () => { if (badge) { badge.textContent = '⚠'; badge.title = TITRE_COPIE_VIDE; setTimeout(restaurer, 2000); } },
    aucun: () => flash('∅'),
    nonPret: () => { toasts.info('Contenu en préparation — reclique dans un instant.'); },
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
}

// Objet publié sous window.Bridge.resultatsCoches (via installerPont dans index.js) :
// consommé par l'ancien app.js pendant la transition (case à cocher, badges de
// copie, boutons « Cocher tout » et remise à zéro).
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
