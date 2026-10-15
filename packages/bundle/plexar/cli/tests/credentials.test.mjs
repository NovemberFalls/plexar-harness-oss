// credentials.mjs against a mocked `Entry` (the keyring binding is not exercised): resolveKey's
// env-vs-keyring precedence, store/load/delete round-trip, and the not-found-reads-as-absent case.
// Usage: node --test packages/bundle/plexar/cli/tests/credentials.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { _withEntryFactory, deleteKey, loadKey, resolveKey, storeKey } from '../credentials.mjs';

/** A fake `Entry` backed by an in-memory map, keyed by `service:user`. */
function fakeEntryFactory(store) {
  return (service, user) => {
    const key = `${service}:${user}`;
    return {
      setPassword: (password) => { store.set(key, password); },
      getPassword: () => {
        if (!store.has(key)) throw new Error('No matching entry found in secure storage');
        return store.get(key);
      },
      deletePassword: () => {
        if (!store.has(key)) throw new Error('No matching entry found in secure storage');
        store.delete(key);
      },
    };
  };
}

test('storeKey/loadKey/deleteKey: round-trip through the mocked entry', () => {
  const store = new Map();
  const restore = _withEntryFactory(fakeEntryFactory(store));
  try {
    assert.equal(loadKey(), undefined);
    storeKey('secret-key');
    assert.equal(loadKey(), 'secret-key');
    deleteKey();
    assert.equal(loadKey(), undefined);
  } finally {
    restore();
  }
});

test('deleteKey: a missing entry is not an error', () => {
  const restore = _withEntryFactory(fakeEntryFactory(new Map()));
  try {
    assert.doesNotThrow(() => deleteKey());
  } finally {
    restore();
  }
});

test('resolveKey: the keyring wins over PLEXAR_HARNESS_KEY', () => {
  const store = new Map();
  const restore = _withEntryFactory(fakeEntryFactory(store));
  const previous = process.env.PLEXAR_HARNESS_KEY;
  process.env.PLEXAR_HARNESS_KEY = 'env-key';
  storeKey('keyring-key');
  try {
    assert.deepEqual(resolveKey(), { key: 'keyring-key', source: 'keyring' });
  } finally {
    restore();
    if (previous === undefined) delete process.env.PLEXAR_HARNESS_KEY;
    else process.env.PLEXAR_HARNESS_KEY = previous;
  }
});

test('resolveKey: falls back to PLEXAR_HARNESS_KEY when the keyring is empty', () => {
  const store = new Map();
  const restore = _withEntryFactory(fakeEntryFactory(store));
  const previous = process.env.PLEXAR_HARNESS_KEY;
  process.env.PLEXAR_HARNESS_KEY = 'env-key';
  try {
    assert.deepEqual(resolveKey(), { key: 'env-key', source: 'env' });
  } finally {
    restore();
    if (previous === undefined) delete process.env.PLEXAR_HARNESS_KEY;
    else process.env.PLEXAR_HARNESS_KEY = previous;
  }
});

test('resolveKey: neither set -> undefined', () => {
  const restore = _withEntryFactory(fakeEntryFactory(new Map()));
  const previous = process.env.PLEXAR_HARNESS_KEY;
  delete process.env.PLEXAR_HARNESS_KEY;
  try {
    assert.equal(resolveKey(), undefined);
  } finally {
    restore();
    if (previous !== undefined) process.env.PLEXAR_HARNESS_KEY = previous;
  }
});
