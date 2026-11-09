import { test } from 'node:test';
import assert from 'node:assert/strict';
import { VULNS, isVulnerable, fixOptions } from '../js/sim/vulns.js';
import { createSite, addComponent, COMPONENT_TYPES, FLAGS } from '../js/sim/site.js';

test('every vulnerability references real component types and flags', () => {
  for (const v of VULNS) {
    for (const t of v.targets) assert.ok(COMPONENT_TYPES[t], `${v.id}: unknown type ${t}`);
    for (const f of fixOptions(v)) assert.ok(FLAGS[f], `${v.id}: unknown flag ${f}`);
    assert.ok(!v.decoys.includes(v.fix), `${v.id}: fix is listed as a decoy`);
    for (const d of v.decoys) assert.ok(v.explain.decoyWhy[d], `${v.id}: missing decoy explanation for ${d}`);
  }
});

test('a fresh component is weak to every vulnerability that targets it', () => {
  const site = createSite();
  for (const v of VULNS) {
    for (const type of v.targets) {
      const c = addComponent(site, type, type, 1);
      assert.equal(isVulnerable(v, c), true, `${v.id} on ${type}`);
    }
  }
});

test('only the real fix closes a vulnerability; decoys do not', () => {
  const site = createSite();
  for (const v of VULNS) {
    const c = addComponent(site, v.targets[0], 'x', 1);
    for (const d of v.decoys) c.flags[d] = true;
    assert.equal(isVulnerable(v, c), true, `${v.id}: decoys should not fix it`);
    c.flags[v.fix] = true;
    assert.equal(isVulnerable(v, c), false, `${v.id}: real fix should close it`);
  }
});

test('vulnerabilities do not apply to unrelated component types', () => {
  const site = createSite();
  const landing = addComponent(site, 'landingPage', 'Home', 1);
  for (const v of VULNS) assert.equal(isVulnerable(v, landing), false);
});
