// Tests de logique pure de l'onglet Configuration (issue #651, refonte web
// étape 12 — sorti d'app.js vers static/js/config.js). chargerConfig/
// sauvegarderConfig et le flux de suppression de projet touchent le DOM et le
// réseau, vérifiés manuellement (voir VERIFICATIONS_MANUELLES.md) : on ne
// teste ici que les trois fonctions pures extraites, indépendantes du DOM.
import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  construireResumeIdentite,
  suppressionActivable,
  messageStatutCommitDoc,
} from '../config.js';

test('construireResumeIdentite : champs obligatoires seuls', () => {
  const html = construireResumeIdentite({ nom: 'demo', depot: 'org/demo', rep_travail: '/home/x/demo' });
  assert.equal(html, 'NOM = demo<br>DEPOT = org/demo<br>REP_TRAVAIL = /home/x/demo<br>');
});

test('construireResumeIdentite : PERIMETRE et CMD_BACKUP optionnels, ajoutés si présents', () => {
  const html = construireResumeIdentite({
    nom: 'demo', depot: 'org/demo', rep_travail: '/home/x/demo',
    perimetre: '/home/x/demo', cmd_backup: 'git commit -am backup',
  });
  assert.equal(html,
    'NOM = demo<br>DEPOT = org/demo<br>REP_TRAVAIL = /home/x/demo<br>'
    + 'PERIMETRE = /home/x/demo<br>CMD_BACKUP = git commit -am backup');
});

test('suppressionActivable : refuse tant qu\'une case n\'est pas cochée, même nom correct', () => {
  assert.equal(suppressionActivable([true, true, false], 'demo', 'demo'), false);
});

test('suppressionActivable : refuse si aucune case (rien à cocher, jamais activable)', () => {
  assert.equal(suppressionActivable([], 'demo', 'demo'), false);
});

test('suppressionActivable : refuse si le nom retapé diffère', () => {
  assert.equal(suppressionActivable([true, true, true], 'autre-projet', 'demo'), false);
});

test('suppressionActivable : accepte un nom retapé avec casse/espaces différents (issue #587)', () => {
  assert.equal(suppressionActivable([true, true, true], '  DEMO  ', 'demo'), true);
});

test('suppressionActivable : toutes cases cochées + nom exact → activable', () => {
  assert.equal(suppressionActivable([true, true, true], 'demo', 'demo'), true);
});

test('messageStatutCommitDoc : push_echoue → commande manuelle affichée', () => {
  const msg = messageStatutCommitDoc('push_echoue', 'cd ~/Bridge_Agent && git push');
  assert.match(msg, /push a.*échoué/);
  assert.match(msg, /cd ~\/Bridge_Agent && git push/);
});

test('messageStatutCommitDoc : push_echoue sans commande manuelle → repli générique', () => {
  const msg = messageStatutCommitDoc('push_echoue', null);
  assert.match(msg, /cd ~\/Bridge_Agent && git push/);
});

test('messageStatutCommitDoc : echec → message dédié', () => {
  const msg = messageStatutCommitDoc('echec', 'git push');
  assert.match(msg, /commit automatique.*a échoué/);
});

test('messageStatutCommitDoc : statut inconnu ou absent → succès automatique', () => {
  assert.match(messageStatutCommitDoc(undefined, null), /committé et poussé automatiquement/);
  assert.match(messageStatutCommitDoc('ok', null), /committé et poussé automatiquement/);
});
