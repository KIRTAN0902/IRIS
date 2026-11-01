'use strict';

const path = require('path');

function isTrustedAppUrl(rawUrl) {
  try {
    const url = new URL(rawUrl);
    return url.protocol === 'iris:' && url.hostname === 'app' && !url.port && !url.username && !url.password;
  } catch {
    return false;
  }
}

function normalizeExternalUrl(rawUrl) {
  try {
    const url = new URL(String(rawUrl));
    if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) return null;
    return url.href;
  } catch {
    return null;
  }
}

function resolveFrontendAssetPath(distDir, requestPath) {
  const root = path.resolve(distDir);
  let decoded;
  try {
    decoded = decodeURIComponent(String(requestPath || '/'));
  } catch {
    return null;
  }
  if (decoded.includes('\0')) return null;

  const relative = decoded.replace(/^[/\\]+/, '').replace(/[\\/]+/g, path.sep);
  const target = path.resolve(root, relative || 'index.html');
  const fromRoot = path.relative(root, target);
  if (fromRoot === '..' || fromRoot.startsWith(`..${path.sep}`) || path.isAbsolute(fromRoot)) return null;
  return target;
}

function isWithinDirectory(root, target) {
  const fromRoot = path.relative(path.resolve(root), path.resolve(target));
  return fromRoot === '' || (fromRoot !== '..' && !fromRoot.startsWith(`..${path.sep}`) && !path.isAbsolute(fromRoot));
}

module.exports = { isTrustedAppUrl, normalizeExternalUrl, resolveFrontendAssetPath, isWithinDirectory };
