import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRng } from '../js/sim/rng.js';
import { createSite, addComponent } from '../js/sim/site.js';
import { createAttacker } from '../js/agents/attacker.js';
import { createDefender } from '../js/agents/defender.js';
import { createBuilder } from '../js/agents/builder.js';

const noop = () => {};

test('attacker learns that SQL injection works on an unprotected search box', () => {
  const site = createSite();
  addComponent(site, 'searchBox', 'Search', 1);
  const attacker = createAttacker({ rng: createRng(7), site, emit: noop, budget: 6 });
  for (let i = 0; i < 60; i++) attacker.runEpisode();
  const sqli = attacker.value('searchBox|sqlInjection');
  const upload = attacker.value('searchBox|maliciousUpload');
  assert.ok(sqli > 5, `expected high value for SQLi, got ${sqli}`);
  assert.ok(upload === null || upload < 0, `expected upload to look useless, got ${upload}`);
});

test('attacker cannot dump passwords without database access first', () => {
  const site = createSite();
  const login = addComponent(site, 'loginForm', 'Login', 1);
  login.flags.paramQueries = true; // no SQL injection possible
  login.flags.rateLimit = true;
  const attacker = createAttacker({ rng: createRng(3), site, emit: noop, budget: 8, successRate: 1 });
  for (let i = 0; i < 30; i++) {
    const { reports } = attacker.runEpisode();
    assert.ok(!reports.some((r) => r.vulnId === 'pwleak'));
  }
});

test('defender converges on the real fix and promotes it to a rule', () => {
  const site = createSite();
  const defender = createDefender({ rng: createRng(11), emit: noop });
  let rounds = 0;
  while (!defender.rules.xss && rounds++ < 50) {
    const c = addComponent(site, 'commentSection', 'Comments', 1);
    let ticket = defender.handleReport({ componentId: c.id, vulnId: 'xss' });
    while (ticket) {
      c.flags[ticket.flag] = true;
      ticket = defender.learn(ticket, ticket.flag === 'outputEncoding').retry;
    }
  }
  assert.equal(defender.rules.xss, 'outputEncoding');
});

test('builder applies defender rules to new components', () => {
  const site = createSite();
  const defender = createDefender({ rng: createRng(1), emit: noop });
  defender.rules.sqli = 'paramQueries';
  const builder = createBuilder({ rng: createRng(1), site, defender, emit: noop, regressRate: 0 });
  for (let r = 1; r <= 11; r++) builder.maybeBuild(r); // stages 1-3
  const search = site.components.find((c) => c.type === 'searchBox');
  const login = site.components.find((c) => c.type === 'loginForm');
  assert.equal(search.flags.paramQueries, true);
  assert.equal(login.flags.paramQueries, true);
  assert.equal(search.flags.outputEncoding, false, 'no XSS rule yet');
});

test('builder sometimes forgets a rule when regressRate is high', () => {
  const site = createSite();
  const defender = createDefender({ rng: createRng(1), emit: noop });
  defender.rules.sqli = 'paramQueries';
  const builder = createBuilder({ rng: createRng(1), site, defender, emit: noop, regressRate: 1 });
  for (let r = 1; r <= 11; r++) builder.maybeBuild(r);
  assert.equal(site.components.find((c) => c.type === 'searchBox').flags.paramQueries, false);
  assert.ok(builder.regressions > 0);
});
