import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createEngine } from '../js/sim/engine.js';

const run = (seed, rounds = 200) => {
  const e = createEngine({ seed });
  for (let i = 0; i < rounds; i++) e.step();
  return e;
};

const avg = (arr, key) => arr.reduce((s, m) => s + m[key], 0) / arr.length;
const accuracy = (arr) => {
  const att = arr.reduce((s, m) => s + m.fixAttempts, 0);
  return att ? arr.reduce((s, m) => s + m.fixSuccesses, 0) / att : null;
};

for (const seed of [1, 2, 3, 1337]) {
  test(`seed ${seed}: attacker breaches go down and defender accuracy goes up`, () => {
    const { metrics, defender } = run(seed);
    const early = metrics.slice(0, 40);
    const late = metrics.slice(160);
    assert.ok(avg(late, 'breaches') < avg(early, 'breaches'), 'breaches should fall');
    assert.ok(accuracy(metrics.slice(100)) > accuracy(metrics.slice(0, 50)), 'fix accuracy should rise');
    assert.ok(Object.keys(defender.rules).length >= 4, 'defender should learn several rules');
  });
}

test('same seed reproduces the same run', () => {
  const a = run(42, 80).metrics;
  const b = run(42, 80).metrics;
  assert.deepEqual(a, b);
});

test('engine emits the full red -> blue -> builder loop', () => {
  const e = createEngine({ seed: 5 });
  const seen = new Set();
  e.bus.on((ev) => seen.add(ev.type));
  for (let i = 0; i < 60; i++) e.step();
  for (const t of ['stage', 'build', 'discover', 'breach', 'report', 'ticket', 'fix', 'retest', 'rule']) {
    assert.ok(seen.has(t), `missing event ${t}`);
  }
});
