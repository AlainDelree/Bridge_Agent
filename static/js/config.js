// config.js — onglet Configuration, sorti d'app.js (issue #651, refonte web
// étape 12 — ARCHITECTURE.md §6.7).
//
// RESPONSABILITÉ
//   Chargement/sauvegarde des paramètres du projet actif (chargerConfig/
//   sauvegarderConfig) et « Zone dangereuse » (suppression de projet, issue
//   #587) : modale de confirmation (checklist des 3 cibles + nom retapé),
//   aperçu dry-run (GET /supprimer-projet/verifier/<nom>) et soumission
//   (POST /supprimer-projet). Le son PROPRE à cet onglet a déjà été retiré à
//   l'issue #643 (les seuls réglages de son restants vivent dans le panneau
//   latéral) — rien de plus à en sortir ici.
//
// HORS PÉRIMÈTRE (volontairement laissé dans app.js) : le bouton global
// « + Nouveau projet » (bandeau supérieur, PAS dans l'onglet Configuration) et
// tout son flux (ajouterProjetAuSelecteur, modale « Nouveau projet »,
// ccwCreerProjet…) — à traiter séparément un jour si Alain le souhaite.
// retirerProjetDuSelecteur, symétrique d'ajouterProjetAuSelecteur, reste lui
// aussi dans app.js : il manipule le sélecteur global #projet du bandeau
// (pas un élément de l'onglet Configuration) et appelle onProjetChange() —
// ce module l'appelle via le pont (appelerAncien) après une suppression
// réussie plutôt que de dupliquer cette logique de bandeau ici.
//
// BRANCHEMENT (comme journal.js, issue #650, étape 11) : chargerConfig() est
// exportée pour que static/js/onglets.js l'appelle PAR IMPORT DIRECT à
// l'activation de l'onglet Configuration — plus via le pont. Particularité
// propre à cet onglet : l'ancien app.js (onProjetChange, script classique)
// rappelle aussi chargerConfig() directement quand l'onglet est DÉJÀ actif au
// moment d'un changement de projet (sélecteur global) — impossible à couvrir
// par le seul import direct d'onglets.js. chargerConfig est donc AUSSI
// publiée en window.chargerConfig (initialiserConfig ci-dessous), lue par
// app.js comme une globale ordinaire (même patron que
// window.rafraichirPanneauLateralResultats, voir panneau_lateral.js).
// initialiserConfig() (délégation des boutons/inputs) est appelée une fois
// par index.js, comme les autres modules par fonctionnalité.

import { api } from './socle/api.js';
import * as dom from './socle/dom.js';
import * as persistance from './socle/persistance.js';
import { appelerAncien } from './socle/pont.js';

// ─────────────────────────────────────────────────────────────────────────
// LOGIQUE PURE (testée sous Node — voir static/js/tests/config.test.js)
//    Aucune dépendance au DOM ni au réseau.
// ─────────────────────────────────────────────────────────────────────────

/** Résumé HTML (lecture seule) de l'identité du projet, affiché en tête de
 *  l'onglet — PERIMETRE et CMD_BACKUP sont optionnels. */
export function construireResumeIdentite(cfg) {
  return `NOM = ${cfg.nom}<br>DEPOT = ${cfg.depot}<br>` +
    `REP_TRAVAIL = ${cfg.rep_travail}<br>` +
    (cfg.perimetre  ? `PERIMETRE = ${cfg.perimetre}<br>` : '') +
    (cfg.cmd_backup ? `CMD_BACKUP = ${cfg.cmd_backup}` : '');
}

/** Le bouton « Supprimer définitivement » de la zone dangereuse ne s'active
 *  QUE si les 3 cases de la checklist sont cochées ET que le nom retapé
 *  correspond exactement (insensible à la casse et aux espaces superflus) au
 *  projet ciblé par l'ouverture de la modale — double garde-fou côté
 *  interface, la route serveur revérifie indépendamment la confirmation. */
export function suppressionActivable(casesCochees, confirmationSaisie, nomAttendu) {
  const casesOk = (casesCochees || []).every(Boolean) && (casesCochees || []).length > 0;
  const nomOk = String(confirmationSaisie || '').trim().toLowerCase()
              === String(nomAttendu || '').trim().toLowerCase();
  return casesOk && nomOk;
}

/** Message final affiché après une suppression réussie, selon le statut du
 *  commit/push automatique de BRIDGE_AGENT_DOC.md (issue #645). */
export function messageStatutCommitDoc(statut, commandeManuelle) {
  if (statut === 'push_echoue') {
    return ' ⚠ BRIDGE_AGENT_DOC.md a été committé en LOCAL mais le push a '
         + 'échoué (réseau, conflit avec origin…) — à repousser toi-même : '
         + (commandeManuelle || 'cd ~/Bridge_Agent && git push') + '.';
  }
  if (statut === 'echec') {
    return ' ⚠ Le commit automatique de BRIDGE_AGENT_DOC.md a échoué — '
         + 'à committer/pousser toi-même : ' + (commandeManuelle || '') + '.';
  }
  return ' BRIDGE_AGENT_DOC.md (§2) a été committé et poussé automatiquement.';
}

// ─── Chargement / sauvegarde des paramètres ────────────────────────────────

// Écrit une valeur dans un champ de l'onglet sans planter si l'élément est
// absent du DOM (page pas encore rafraîchie après un déploiement ayant ajouté
// ce champ, ou valeur absente/null/undefined renvoyée par le serveur — issue
// #570) : ignore ce champ plutôt que d'interrompre le chargement des suivants.
function majChampConfig(id, valeur, propriete = 'value') {
  const el = document.getElementById(id);
  if (el) el[propriete] = valeur;
}

/** Charge la config du projet actuellement sélectionné (sélecteur global
 *  #projet) dans les champs de l'onglet. */
export async function chargerConfig() {
  const nom = document.getElementById('projet').value;
  try {
    const cfg = await api.get('/config/' + encodeURIComponent(nom), { silencieux: true });

    majChampConfig('config-readonly', construireResumeIdentite(cfg), 'innerHTML');

    majChampConfig('conf-TOPIC_NTFY', cfg.topic_ntfy || '');
    majChampConfig('conf-LABEL', cfg.label || 'for-linux');
    majChampConfig('conf-INTERVALLE', cfg.intervalle || 10);
    majChampConfig('conf-MAX_ESSAIS', cfg.max_essais || 3);
    majChampConfig('conf-TIMEOUT_CLAUDE', cfg.timeout_claude || 300);
    majChampConfig('conf-FICHIER_CONTEXTE', cfg.fichier_contexte || '');
    majChampConfig('conf-MODELE_CCL', cfg.modele_ccl || '');
    majChampConfig('conf-LOG_TAILLE_MAX_MO', cfg.log_taille_max_mo || 1);
    majChampConfig('conf-LOG_ARCHIVES', cfg.log_archives || 5);
    // ?? et non || : 0 est une valeur valide (auto-extinction désactivée).
    majChampConfig('conf-DELAI_INACTIVITE_MIN', cfg.delai_inactivite_min ?? 20);
    majChampConfig('conf-MAX_WRITE_PARALLELE', cfg.max_write_parallele || 2);
    majChampConfig('max-write-parallele-valeur', cfg.max_write_parallele || 2, 'textContent');
    const msgConfig = document.getElementById('msg-config');
    if (msgConfig) msgConfig.style.display = 'none';
  } catch (e) {
    const msg = document.getElementById('msg-config');
    if (msg) {
      msg.textContent = 'Erreur de chargement : ' + e.message;
      msg.className = 'message erreur'; msg.style.display = 'block';
    }
  }
}

async function sauvegarderConfig(relancer) {
  const nom = document.getElementById('projet').value;
  const data = {
    TOPIC_NTFY:        document.getElementById('conf-TOPIC_NTFY').value,
    LABEL:             document.getElementById('conf-LABEL').value,
    INTERVALLE:        document.getElementById('conf-INTERVALLE').value,
    MAX_ESSAIS:        document.getElementById('conf-MAX_ESSAIS').value,
    TIMEOUT_CLAUDE:    document.getElementById('conf-TIMEOUT_CLAUDE').value,
    FICHIER_CONTEXTE:  document.getElementById('conf-FICHIER_CONTEXTE').value,
    MODELE_CCL:        document.getElementById('conf-MODELE_CCL').value,
    LOG_TAILLE_MAX_MO: document.getElementById('conf-LOG_TAILLE_MAX_MO').value,
    LOG_ARCHIVES:      document.getElementById('conf-LOG_ARCHIVES').value,
    DELAI_INACTIVITE_MIN: document.getElementById('conf-DELAI_INACTIVITE_MIN').value,
    MAX_WRITE_PARALLELE: document.getElementById('conf-MAX_WRITE_PARALLELE').value,
  };
  const msg = document.getElementById('msg-config');
  let json;
  try {
    // Contrairement à l'ancien fetch() en dur (jamais try/catch ici avant
    // #651 : une panne réseau restait totalement silencieuse), api.post
    // remonte toute erreur de façon VISIBLE (toast), en plus du message
    // inline ci-dessous sur succès/échec métier.
    json = await api.post('/config/' + encodeURIComponent(nom), data);
  } catch (e) {
    return; // déjà signalé par api.post (toast)
  }
  msg.textContent = json.message;
  msg.className   = 'message ' + (json.succes ? 'succes' : 'erreur');
  msg.style.display = 'block';
  if (json.succes && relancer) {
    let jsonW;
    try {
      jsonW = await api.post('/lancer-watcher', { projet: nom, relancer: true });
    } catch (e) {
      return; // déjà signalé par api.post (toast)
    }
    // Issue #609 : un redémarrage forcé pendant qu'une tâche est en cours
    // n'est jamais exécuté tout de suite (il la couperait) — il est différé
    // jusqu'à sa fin (app.watchers.demarrer_watcher_ou_differer), et
    // l'interface doit le dire clairement plutôt que de laisser croire à un
    // redémarrage immédiat.
    msg.textContent += jsonW.differe
      ? ' ⏳ Watcher occupé (tâche en cours) — redémarrage différé, appliqué automatiquement à la fin de la tâche en cours.'
      : ' Watcher relancé.';
  }
}

// ─── Zone dangereuse : suppression de projet (issue #587) ──────────────────
// Modal symétrique à « Nouveau projet » (app.js, hors périmètre), côté
// CCL/local uniquement (dépôt GitHub distant + côté CCW jamais touchés ici).
// L'aperçu (dry-run, GET /supprimer-projet/verifier/<nom>) se charge
// automatiquement à l'ouverture ; le bouton de suppression réelle reste
// désactivé tant que suppressionActivable() (logique pure ci-dessus) ne
// renvoie pas true.
let spNomCourant = '';

function ouvrirSupprimerProjet() {
  const nom = document.getElementById('projet').value;
  if (!nom) return;
  spNomCourant = nom;
  document.getElementById('sp-nom-titre').textContent = nom;
  document.getElementById('sp-nom-confirmation-attendu').textContent = nom;
  document.getElementById('sp-conf-nom').textContent = 'configs/' + nom + '.conf';
  document.getElementById('sp-chargement').textContent = 'Chargement de l\'aperçu…';
  document.getElementById('sp-chargement').style.display = 'block';
  document.getElementById('sp-contenu').style.display = 'none';
  document.getElementById('sp-compte-rendu').style.display = 'none';
  document.getElementById('sp-message').style.display = 'none';
  document.getElementById('sp-nom-confirmation').value = '';
  document.querySelectorAll('.sp-case').forEach(c => c.checked = false);
  const btn = document.getElementById('sp-supprimer');
  btn.style.display = '';
  btn.disabled = true;
  btn.textContent = 'Supprimer définitivement';
  document.getElementById('sp-fermer').textContent = 'Fermer';
  document.getElementById('modal-supprimer-projet').classList.add('actif');
  spChargerApercu(nom);
}

function fermerSupprimerProjet() {
  document.getElementById('modal-supprimer-projet').classList.remove('actif');
}

async function spChargerApercu(nom) {
  const chargement = document.getElementById('sp-chargement');
  const contenu = document.getElementById('sp-contenu');
  let r;
  try {
    r = await api.get('/supprimer-projet/verifier/' + encodeURIComponent(nom), { silencieux: true });
  } catch (e) {
    chargement.textContent = 'Erreur réseau : ' + e.message;
    return;
  }
  if (!r.existe) {
    chargement.textContent = '❌ configs/' + nom + '.conf introuvable — rien à supprimer.';
    return;
  }
  chargement.style.display = 'none';
  contenu.style.display = 'block';
  document.getElementById('sp-depot').textContent = r.depot || '(inconnu)';

  let html = '<div>Répertoire de travail : <b>' + dom.echapperHtml(r.rep_travail || '') + '</b>'
    + (r.rep_existe
        ? ' (' + r.nb_fichiers + ' élément(s)' + (r.git_local ? ', dépôt git local inclus' : '') + ')'
        : ' — déjà absent')
    + '</div>';
  if (r.apercu_fichiers && r.apercu_fichiers.length) {
    html += '<div style="margin-top:6px;font-size:12px;color:#666">'
      + r.apercu_fichiers.map(dom.echapperHtml).join('<br>') + '</div>';
  }
  document.getElementById('sp-apercu').innerHTML = html;
  spMajBoutonEtat();
}

// Rappelée à chaque case cochée/décochée et à chaque frappe dans le champ de
// confirmation (délégation, voir installerDelegationConfig ci-dessous).
function spMajBoutonEtat() {
  const casesCochees = [...document.querySelectorAll('.sp-case')].map(c => c.checked);
  const confirmationSaisie = document.getElementById('sp-nom-confirmation').value;
  document.getElementById('sp-supprimer').disabled =
    !suppressionActivable(casesCochees, confirmationSaisie, spNomCourant);
}

function spMsg(texte, type) {
  const el = document.getElementById('sp-message');
  el.textContent = texte;
  el.className = 'message ' + type;
  el.style.display = 'block';
}

async function soumettreSupprimerProjet() {
  const confirmation = document.getElementById('sp-nom-confirmation').value.trim().toLowerCase();
  const cr = document.getElementById('sp-compte-rendu');
  document.getElementById('sp-message').style.display = 'none';
  cr.style.display = 'none';
  const btn = document.getElementById('sp-supprimer');
  const avant = btn.textContent;
  btn.disabled = true;
  btn.textContent = 'Suppression…';

  let res;
  try {
    res = await api.post('/supprimer-projet', { nom: spNomCourant, confirmation }, { silencieux: true });
  } catch (e) {
    btn.disabled = false;
    btn.textContent = avant;
    spMsg('Erreur réseau : ' + e.message, 'erreur');
    return;
  }

  if (res.etapes && res.etapes.length) {
    cr.innerHTML = res.etapes.map(e =>
      (e.ok ? '✓ ' : '❌ ') + '<b>' + dom.echapperHtml(e.etape) + '</b> — ' + dom.echapperHtml(e.detail || '')
    ).join('<br>');
    cr.style.display = 'block';
  }

  if (res.succes) {
    btn.style.display = 'none';
    // spMsg pose le texte via textContent (pas innerHTML) : pas d'échappement
    // HTML ici, ce serait affiché littéralement (ex. « &amp; » au lieu de « & »).
    const msgDoc = messageStatutCommitDoc(res.doc_commit_statut, res.doc_commit_commande_manuelle);
    spMsg('✅ Projet « ' + res.nom + ' » supprimé côté CCL/local. Reste à faire à la main : '
        + 'dépôt GitHub + labels (hors scope, cf. issue #587).' + msgDoc, 'succes');
    // Purge ses clés localStorage (cache détail + entrée dans le filtre
    // Résultats) — fuite corrigée à l'issue #644.
    persistance.purgerProjet(res.nom);
    // retirerProjetDuSelecteur reste dans app.js (sélecteur global #projet du
    // bandeau, hors périmètre de cet onglet — voir en-tête de ce fichier).
    appelerAncien('retirerProjetDuSelecteur', res.nom);
  } else {
    btn.disabled = false;
    btn.textContent = avant;
    spMsg('❌ ' + (res.erreur || 'Échec.'), 'erreur');
  }
}

// ─── Délégation d'événements (remplace les onclick=/onchange=/oninput=
// inline de onglet_config.html et modale_supprimer_projet.html) ───────────
function installerDelegationConfig() {
  dom.surAction('[data-action="config-enregistrer"]', 'click', () => sauvegarderConfig(false));
  dom.surAction('[data-action="config-enregistrer-relancer"]', 'click', () => sauvegarderConfig(true));
  dom.surAction('[data-action="config-max-write-parallele"]', 'input', (e, el) => {
    const span = document.getElementById('max-write-parallele-valeur');
    if (span) span.textContent = el.value;
  });
  dom.surAction('[data-action="config-ouvrir-suppression"]', 'click', () => ouvrirSupprimerProjet());

  dom.surAction('[data-action="sp-case"]', 'change', () => spMajBoutonEtat());
  dom.surAction('[data-action="sp-nom-confirmation"]', 'input', () => spMajBoutonEtat());
  dom.surAction('[data-action="sp-fermer"]', 'click', () => fermerSupprimerProjet());
  dom.surAction('[data-action="sp-supprimer"]', 'click', () => soumettreSupprimerProjet());
}

/** Point d'entrée, appelé une fois par index.js. */
export function initialiserConfig() {
  installerDelegationConfig();
  // Voir en-tête de ce fichier : l'ancien app.js (onProjetChange, script
  // classique) appelle encore chargerConfig() directement quand l'onglet
  // Configuration est déjà actif au moment d'un changement de projet.
  window.chargerConfig = chargerConfig;
}
