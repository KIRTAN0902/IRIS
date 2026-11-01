'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const os = require('node:os');
const path = require('node:path');
const fs = require('node:fs');
const {
  isTrustedAppUrl,
  normalizeExternalUrl,
  resolveFrontendAssetPath,
  isWithinDirectory,
} = require('./security.cjs');

test('only the IRIS app origin is trusted for renderer navigation', () => {
  assert.equal(isTrustedAppUrl('iris://app/index.html'), true);
  assert.equal(isTrustedAppUrl('iris://attacker/index.html'), false);
  assert.equal(isTrustedAppUrl('iris://app:444/index.html'), false);
  assert.equal(isTrustedAppUrl('iris://app@attacker/index.html'), false);
  assert.equal(isTrustedAppUrl('https://example.com'), false);
  assert.equal(isTrustedAppUrl('javascript:alert(1)'), false);
});

test('external links permit ordinary web URLs only', () => {
  assert.equal(normalizeExternalUrl('https://example.com/path'), 'https://example.com/path');
  assert.equal(normalizeExternalUrl('http://localhost:8000/health'), 'http://localhost:8000/health');
  assert.equal(normalizeExternalUrl('file:///C:/Users/test/secret.txt'), null);
  assert.equal(normalizeExternalUrl('javascript:alert(1)'), null);
  assert.equal(normalizeExternalUrl('https://user:password@example.com'), null);
});

test('frontend asset resolution rejects traversal and stays under the build directory', (t) => {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'iris-assets-'));
  t.after(() => fs.rmSync(temp, { recursive: true, force: true }));
  const root = path.join(temp, 'dist');
  fs.mkdirSync(root);

  const safe = resolveFrontendAssetPath(root, '/assets/main.js');
  assert.equal(isWithinDirectory(root, safe), true);
  assert.equal(resolveFrontendAssetPath(root, '/../../secret.txt'), null);
  assert.equal(resolveFrontendAssetPath(root, '/%2e%2e/%2e%2e/secret.txt'), null);
  assert.equal(resolveFrontendAssetPath(root, '/%zz'), null);
});
