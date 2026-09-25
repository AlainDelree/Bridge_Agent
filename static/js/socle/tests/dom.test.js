// Tests de la logique pure de dom.js (issue #625, étape 1).
// On ne teste ici que ce qui ne dépend PAS du DOM (echapperHtml) : les
// utilitaires DOM et la délégation sont vérifiés manuellement dans le navigateur
// (cf. VERIFICATIONS_MANUELLES.md), Node n'ayant pas de document.
import { test } from 'node:test';
import assert from 'node:assert/strict';

import { echapperHtml } from '../dom.js';

test('echapperHtml neutralise les 5 caractères sensibles', () => {
  assert.equal(echapperHtml('<a href="x">& \'quote\'</a>'),
    '&lt;a href=&quot;x&quot;&gt;&amp; &#39;quote&#39;&lt;/a&gt;');
});

test('echapperHtml : injection de balise script neutralisée', () => {
  assert.equal(echapperHtml('<script>alert(1)</script>'),
    '&lt;script&gt;alert(1)&lt;/script&gt;');
});

test('echapperHtml : nombres et valeurs non-chaîne', () => {
  assert.equal(echapperHtml(42), '42');
  assert.equal(echapperHtml(null), 'null');
});
