// Tests de logique pure de l'onglet « Agent Vibe » (issue #766). Le
// chargement/l'écriture réels touchent le réseau et le DOM (vérifiés
// manuellement) : on ne teste ici que les fonctions pures extraites,
// indépendantes du DOM — même patron que static/js/tests/config.test.js.
import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  libelleModele,
  construireOptionsActif,
  peutRetirerModele,
  champsFormulaireAjout,
  construireChampsAjout,
  corpsErreurApi,
  libelleEntreeJournal,
  dateEntreeJournal,
} from '../vibe_modele.js';

test('libelleModele : alias seul si le nom technique lui est identique', () => {
  assert.equal(libelleModele({ alias: 'rapide', name: 'rapide' }), 'rapide');
});

test('libelleModele : alias + nom technique entre parenthèses s\'ils diffèrent', () => {
  assert.equal(
    libelleModele({ alias: 'devstral2', name: 'mistral-vibe-cli-latest' }),
    'devstral2 (mistral-vibe-cli-latest)',
  );
});

test('construireOptionsActif : une option par modèle, celle de l\'actif présélectionnée', () => {
  const modeles = [
    { alias: 'devstral2', name: 'mistral-vibe-cli-latest' },
    { alias: 'rapide', name: 'autre-model' },
  ];
  const options = construireOptionsActif(modeles, 'rapide');
  assert.deepEqual(options.map((o) => o.valeur), ['devstral2', 'rapide']);
  assert.deepEqual(options.map((o) => o.selectionne), [false, true]);
  assert.ok(options[1].libelle.includes('actif'));
});

test('peutRetirerModele : refuse le modèle actif même seul restant', () => {
  assert.equal(peutRetirerModele({ actif: true }, 2), false);
});

test('peutRetirerModele : refuse le dernier modèle restant, même inactif', () => {
  assert.equal(peutRetirerModele({ actif: false }, 1), false);
});

test('peutRetirerModele : autorise un modèle inactif tant qu\'un autre existe', () => {
  assert.equal(peutRetirerModele({ actif: false }, 2), true);
});

test('champsFormulaireAjout : requis d\'abord, puis connus triés par clé, rien de figé en dur', () => {
  const schema = {
    champs_requis: ['name', 'provider', 'alias'],
    champs_connus: { output_price: 'nombre', input_price: 'nombre' },
  };
  const champs = champsFormulaireAjout(schema);
  assert.deepEqual(champs.map((c) => c.cle), ['name', 'provider', 'alias', 'input_price', 'output_price']);
  assert.deepEqual(champs.map((c) => c.requis), [true, true, true, false, false]);
  assert.deepEqual(champs.map((c) => c.type), ['texte', 'texte', 'texte', 'nombre', 'nombre']);
});

test('champsFormulaireAjout : schéma vide (aucun modèle encore déclaré) → liste vide', () => {
  assert.deepEqual(champsFormulaireAjout({ champs_requis: [], champs_connus: {} }), []);
});

test('construireChampsAjout : convertit les champs "nombre", ignore les optionnels vides', () => {
  const schema = {
    champs_requis: ['name', 'provider', 'alias'],
    champs_connus: { input_price: 'nombre' },
  };
  const champs = construireChampsAjout(
    { name: 'x', provider: 'mistral', alias: 'nouveau', input_price: '0.4' },
    schema,
  );
  assert.deepEqual(champs, { name: 'x', provider: 'mistral', alias: 'nouveau', input_price: 0.4 });
});

test('construireChampsAjout : un champ optionnel laissé vide est absent du corps envoyé', () => {
  const schema = { champs_requis: ['alias'], champs_connus: { input_price: 'nombre' } };
  const champs = construireChampsAjout({ alias: 'nouveau', input_price: '' }, schema);
  assert.deepEqual(champs, { alias: 'nouveau' });
});

test('corpsErreurApi : relit le champ erreur/necessite_confirmation du corps JSON', () => {
  const corps = corpsErreurApi({ corps: '{"erreur":"alias requis","necessite_confirmation":true}' });
  assert.deepEqual(corps, { erreur: 'alias requis', necessite_confirmation: true });
});

test('corpsErreurApi : corps non-JSON ou absent → objet vide, pas d\'exception', () => {
  assert.deepEqual(corpsErreurApi({ corps: 'pas du json' }), {});
  assert.deepEqual(corpsErreurApi({}), {});
  assert.deepEqual(corpsErreurApi(null), {});
});

test('libelleEntreeJournal : changement_actif affiche ancien → nouveau', () => {
  const texte = libelleEntreeJournal({ evenement: 'changement_actif', ancien: 'rapide', nouveau: 'devstral2' });
  assert.equal(texte, 'Modèle actif : rapide → devstral2');
});

test('libelleEntreeJournal : changement_actif sans ancien connu (premier réglage)', () => {
  const texte = libelleEntreeJournal({ evenement: 'changement_actif', ancien: null, nouveau: 'devstral2' });
  assert.equal(texte, 'Modèle actif : (aucun) → devstral2');
});

test('libelleEntreeJournal : declaration et retrait', () => {
  assert.equal(libelleEntreeJournal({ evenement: 'declaration', ancien: null, nouveau: 'rapide' }), 'Modèle déclaré : rapide');
  assert.equal(libelleEntreeJournal({ evenement: 'retrait', ancien: 'rapide', nouveau: null }), 'Modèle retiré : rapide');
});

test('libelleEntreeJournal : entrée absente → chaîne vide, pas d\'exception', () => {
  assert.equal(libelleEntreeJournal(null), '');
});

test('dateEntreeJournal : repli sur la valeur brute si non interprétable', () => {
  assert.equal(dateEntreeJournal({ date: 'pas-une-date' }), 'pas-une-date');
  assert.equal(dateEntreeJournal({}), '');
});
