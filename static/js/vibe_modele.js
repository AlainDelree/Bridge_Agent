// vibe_modele.js — onglet « Agent Vibe » : modèle actif de l'agent Vibe
// (issue #766). Réglage de COMPTE (~/.vibe/config.toml, app/vibe_modele.py),
// PAS un `.conf` de projet — voir l'avertissement affiché dans
// fragments/onglet_vibe.html et le docstring du module serveur.
//
// Aucune liste de modèles n'est écrite en dur ici : GET /vibe-modele/etat
// renvoie les modèles ET le schéma du formulaire d'ajout (champs_requis/
// champs_connus), introspectés côté serveur depuis le fichier réel — même
// principe que app/projets.MODELES_VALIDES pour l'onglet Configuration
// (issue #656), mais lu dynamiquement plutôt que depuis une constante Python.
//
// BRANCHEMENT (comme config.js/journal.js) : chargerVibeModele() est appelée
// par onglets.js à l'activation de l'onglet ; initierVibeModele() installe la
// délégation des boutons une seule fois, appelée par index.js.

import { api } from './socle/api.js';
import * as dom from './socle/dom.js';

// ─────────────────────────────────────────────────────────────────────────
// LOGIQUE PURE (testée sous Node — voir static/js/tests/vibe_modele.test.js)
//    Aucune dépendance au DOM ni au réseau.
// ─────────────────────────────────────────────────────────────────────────

/** Texte d'affichage d'un modèle : son alias (ce que Vibe utilise pour le
 *  sélectionner) suivi du nom technique sous-jacent s'il diffère. */
export function libelleModele(modele) {
  if (!modele) return '';
  if (modele.name && modele.name !== modele.alias) return `${modele.alias} (${modele.name})`;
  return modele.alias;
}

/** Options de la liste déroulante « Modèle actif » : une par modèle déclaré,
 *  celle du modèle actif présélectionnée. Pur — pas de dépendance au DOM. */
export function construireOptionsActif(modeles, modeleActif) {
  return (modeles || []).map((m) => ({
    valeur: m.alias,
    libelle: libelleModele(m) + (m.alias === modeleActif ? ' — actif' : ''),
    selectionne: m.alias === modeleActif,
  }));
}

/** Un modèle ne peut être retiré que s'il n'est pas l'actif ET qu'il n'est
 *  pas le dernier restant (même règle que _retirer_modele côté serveur,
 *  dupliquée ici UNIQUEMENT pour désactiver le bouton à l'avance — le
 *  serveur revalide indépendamment). */
export function peutRetirerModele(modele, nbModeles) {
  return !modele.actif && nbModeles > 1;
}

/** Liste ordonnée des champs du formulaire d'ajout, à partir du schéma
 *  introspecté par le serveur (jamais une liste figée ici) : les champs
 *  requis d'abord, puis les champs optionnels déjà observés dans le fichier.
 *  Le serveur trie déjà champs_requis par ordre alphabétique (alias, name,
 *  provider), ce qui place opportunément ce qui identifie le modèle avant
 *  les champs accessoires (prix…) renvoyés en champs_connus — voir
 *  app.vibe_modele._schema (issue #770). */
export function champsFormulaireAjout(schema) {
  const requis = (schema && schema.champs_requis) || [];
  const connus = (schema && schema.champs_connus) || {};
  const champs = requis.map((cle) => ({ cle, type: 'texte', requis: true }));
  for (const cle of Object.keys(connus).sort()) {
    champs.push({ cle, type: connus[cle], requis: false });
  }
  return champs;
}

/** Libellés affichés dans le formulaire d'ajout, dans le même vocabulaire
 *  que les en-têtes du tableau « Modèles déclarés » juste au-dessus (issue
 *  #770) — les noms techniques ci-dessous (clés du fichier config.toml)
 *  restent inchangés, seul l'affichage change. Clé absente (champ inconnu
 *  introspecté depuis une future version de Vibe) → repli sur le nom
 *  technique tel quel. */
const LIBELLES_CHAMPS_AJOUT = {
  alias: 'Alias',
  name: 'Modèle',
  provider: 'Fournisseur',
  input_price: "Prix d'entrée",
  output_price: 'Prix de sortie',
};

export function libelleChampAjout(cle) {
  return LIBELLES_CHAMPS_AJOUT[cle] || cle;
}

/** Construit le corps JSON de POST /vibe-modele/ajouter à partir des valeurs
 *  texte saisies dans le formulaire (convertit les champs de type "nombre",
 *  ignore les champs optionnels laissés vides). */
export function construireChampsAjout(valeurs, schema) {
  const champs = {};
  for (const { cle, type, requis } of champsFormulaireAjout(schema)) {
    const brut = valeurs[cle];
    if (brut === undefined || brut === null || String(brut).trim() === '') {
      if (requis) champs[cle] = '';
      continue;
    }
    champs[cle] = type === 'nombre' ? Number(brut) : String(brut).trim();
  }
  return champs;
}

/** Libellé lisible d'une entrée de journal (issue #769) — une par changement
 *  de modèle actif, déclaration ou retrait fait depuis cet onglet. Pur, pas
 *  de dépendance au DOM. */
export function libelleEntreeJournal(entree) {
  if (!entree) return '';
  const { evenement, ancien, nouveau } = entree;
  if (evenement === 'changement_actif') return `Modèle actif : ${ancien || '(aucun)'} → ${nouveau}`;
  if (evenement === 'declaration') return `Modèle déclaré : ${nouveau}`;
  if (evenement === 'retrait') return `Modèle retiré : ${ancien}`;
  return `${evenement} : ${ancien || ''} → ${nouveau || ''}`;
}

/** Date d'une entrée de journal, formatée pour l'affichage local (repli sur
 *  la valeur brute si elle n'est pas un ISO 8601 interprétable). */
export function dateEntreeJournal(entree) {
  const brute = entree && entree.date;
  if (!brute) return '';
  const d = new Date(brute);
  return Number.isNaN(d.getTime()) ? brute : d.toLocaleString();
}

/** Interprète l'échec d'un appel /vibe-modele/* : statut non-2xx → ErreurApi
 *  dont `.corps` est le texte brut (JSON) de la réponse serveur, portant le
 *  champ `erreur` (et `necessite_confirmation` pour la collision d'alias
 *  intégré) — même patron que messageEchecAttente (static/js/attente.js,
 *  issue #713). Logique pure, testée sous Node. */
export function corpsErreurApi(erreurApi) {
  if (erreurApi && erreurApi.corps) {
    try {
      return JSON.parse(erreurApi.corps) || {};
    } catch (e) { /* corps non-JSON : objet vide */ }
  }
  return {};
}

// ─────────────────────────────────────────────────────────────────────────
// DOM / RÉSEAU
// ─────────────────────────────────────────────────────────────────────────

function rendreLigneModele(modele, nbModeles) {
  const retirable = peutRetirerModele(modele, nbModeles);
  return (
    '<tr style="border-bottom:1px solid #f3f3f0">'
    + `<td style="padding:8px 12px">${dom.echapperHtml(modele.alias)}</td>`
    + `<td style="padding:8px 12px">${dom.echapperHtml(modele.name || '')}</td>`
    + `<td style="padding:8px 12px">${dom.echapperHtml(modele.provider || '')}</td>`
    + `<td style="padding:8px 12px">${modele.actif ? '✅' : ''}</td>`
    + '<td style="padding:8px 12px">'
    + (retirable
      ? `<button data-action="vibe-retirer" data-alias="${dom.echapperHtml(modele.alias)}">Retirer</button>`
      : '<span style="color:#999;font-size:12px">—</span>')
    + '</td></tr>'
  );
}

function rendreLigneJournal(entree) {
  return (
    '<li style="padding:6px 0;border-bottom:1px solid #f3f3f0">'
    + `<span style="color:#999;margin-right:8px">${dom.echapperHtml(dateEntreeJournal(entree))}</span>`
    + dom.echapperHtml(libelleEntreeJournal(entree))
    + '</li>'
  );
}

function rendreChampsAjout(schema) {
  return champsFormulaireAjout(schema).map(({ cle, type, requis }) => (
    '<div class="champ" style="margin-bottom:8px">'
    + `<label>${dom.echapperHtml(libelleChampAjout(cle))}${requis ? ' *' : ''}</label>`
    + `<input type="${type === 'nombre' ? 'number' : 'text'}" `
    + `${type === 'nombre' ? 'step="any"' : ''} id="vibe-champ-${dom.echapperHtml(cle)}" `
    + `data-champ-ajout="${dom.echapperHtml(cle)}">`
    + (cle === 'alias'
      ? '<div style="font-size:11px;color:#999;margin-top:2px">'
        + 'Un alias identique à un modèle intégré de Vibe sera écrasé par '
        + "l'outil à son prochain démarrage."
        + '</div>'
      : '')
    + '</div>'
  )).join('');
}

let dernierSchema = { champs_requis: [], champs_connus: {} };

function afficherMessage(el, texte, type) {
  if (!el) return;
  el.textContent = texte;
  el.className = `message ${type}`;
  el.style.display = 'block';
}

export async function chargerVibeModele() {
  const indisponible = dom.$('#vibe-indisponible');
  const contenu = dom.$('#vibe-contenu');
  if (!indisponible || !contenu) return; // onglet pas encore dans le DOM (tests)

  const etat = await api.get('/vibe-modele/etat', { silencieux: true }).catch(() => null);
  if (!etat || !etat.disponible) {
    indisponible.style.display = '';
    contenu.style.display = 'none';
    return;
  }
  indisponible.style.display = 'none';
  contenu.style.display = '';
  dernierSchema = etat.schema || dernierSchema;

  const select = dom.$('#vibe-select-actif');
  if (select) {
    select.innerHTML = construireOptionsActif(etat.modeles, etat.modele_actif)
      .map((o) => `<option value="${dom.echapperHtml(o.valeur)}"${o.selectionne ? ' selected' : ''}>`
        + `${dom.echapperHtml(o.libelle)}</option>`)
      .join('');
  }

  const corps = dom.$('#vibe-corps-modeles');
  if (corps) {
    corps.innerHTML = (etat.modeles || [])
      .map((m) => rendreLigneModele(m, etat.modeles.length))
      .join('');
  }

  const champsAjout = dom.$('#vibe-champs-ajout');
  if (champsAjout) champsAjout.innerHTML = rendreChampsAjout(etat.schema);

  const listeJournal = dom.$('#vibe-liste-journal');
  const msgJournal = dom.$('#vibe-msg-journal');
  if (listeJournal) {
    const journal = etat.journal || [];
    listeJournal.innerHTML = journal.map(rendreLigneJournal).join('');
    if (msgJournal) msgJournal.textContent = journal.length ? '' : 'Aucun changement journalisé pour l\'instant.';
  }
}

async function activerModeleChoisi() {
  const select = dom.$('#vibe-select-actif');
  const msg = dom.$('#vibe-msg-actif');
  if (!select || !select.value) return;
  try {
    await api.post('/vibe-modele/activer', { alias: select.value }, { silencieux: true });
    afficherMessage(msg, `Modèle actif : ${select.value}`, 'succes');
    await chargerVibeModele();
  } catch (e) {
    afficherMessage(msg, corpsErreurApi(e).erreur || e.message || 'Échec', 'erreur');
  }
}

async function retirerModele(alias) {
  const msg = dom.$('#vibe-msg-modeles');
  try {
    await api.post('/vibe-modele/retirer', { alias }, { silencieux: true });
    afficherMessage(msg, `Modèle ${alias} retiré.`, 'succes');
    await chargerVibeModele();
  } catch (e) {
    afficherMessage(msg, corpsErreurApi(e).erreur || e.message || 'Échec', 'erreur');
  }
}

function lireValeursFormulaireAjout() {
  const valeurs = {};
  for (const { cle } of champsFormulaireAjout(dernierSchema)) {
    const input = dom.$(`#vibe-champ-${cle}`);
    if (input) valeurs[cle] = input.value;
  }
  return valeurs;
}

async function ajouterModele(forcer) {
  const msg = dom.$('#vibe-msg-ajout');
  const champs = construireChampsAjout(lireValeursFormulaireAjout(), dernierSchema);
  try {
    await api.post('/vibe-modele/ajouter', { champs, forcer: !!forcer }, { silencieux: true });
    afficherMessage(msg, `Modèle ${champs.alias} ajouté.`, 'succes');
    await chargerVibeModele();
  } catch (e) {
    const corpsJson = corpsErreurApi(e);
    // Collision avec un alias intégré connu (409 + necessite_confirmation) :
    // redemande confirmation plutôt que d'écraser silencieusement (voir
    // app/vibe_modele.py::_ajouter_modele).
    if (e.statut === 409 && corpsJson.necessite_confirmation && !forcer) {
      const confirme = window.confirm(
        `${corpsJson.erreur || 'Cet alias correspond à un modèle intégré de Vibe.'} `
        + 'Ajouter quand même ?'
      );
      if (confirme) return ajouterModele(true);
      return;
    }
    afficherMessage(msg, corpsJson.erreur || e.message || 'Échec', 'erreur');
  }
}

export function initierVibeModele() {
  dom.surAction('[data-action="vibe-activer"]', 'click', () => activerModeleChoisi());
  dom.surAction('[data-action="vibe-ajouter"]', 'click', () => ajouterModele(false));
  dom.surAction('[data-action="vibe-retirer"]', 'click', (e, el) => retirerModele(el.dataset.alias));
}
