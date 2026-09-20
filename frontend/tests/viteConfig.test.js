import test from 'node:test';
import assert from 'node:assert/strict';
import config from '../vite.config.js';

test('API proxy allows five-minute synchronous investigations', () => {
  const proxy = config.server.proxy['/api'];
  assert.equal(proxy.target, 'http://127.0.0.1:8001');
  assert.ok(proxy.timeout >= 300000);
  assert.ok(proxy.proxyTimeout >= 300000);
});
