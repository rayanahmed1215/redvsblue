// Runs the loop, one round per step():
//   1. Builder applies queued fix tickets
//   2. Attacker retests each fix, and the Defender learns from the result
//   3. Builder may build the next stage or feature
//   4. Attacker runs an episode and reports breaches
//   5. Defender turns reports into fix tickets for the Builder
import { createRng } from './rng.js';
import { createBus } from './events.js';
import { createSite, getComponent } from './site.js';
import { VULN_BY_ID, isVulnerable, weaknesses } from './vulns.js';
import { createAttacker } from '../agents/attacker.js';
import { createDefender } from '../agents/defender.js';
import { createBuilder } from '../agents/builder.js';

export function createEngine(opts = {}) {
  const seed = opts.seed ?? 1337;
  const rng = createRng(seed);
  const bus = createBus();
  const site = createSite();
  let round = 0;

  const emit = (type, data = {}) => bus.emit({ round, type, ...data });

  const defender = createDefender({ rng, emit, ...opts.defender });
  const builder = createBuilder({ rng, site, defender, emit, ...opts.builder });
  const attacker = createAttacker({ rng, site, emit, ...opts.attacker });
  const metrics = [];

  function step() {
    round++;
    let fixAttempts = 0;
    let fixSuccesses = 0;

    for (const t of builder.applyTickets(round)) {
      const comp = getComponent(site, t.componentId);
      const vuln = VULN_BY_ID[t.vulnId];
      const worked = !isVulnerable(vuln, comp);
      emit('retest', { ticket: t, worked });
      if (worked) comp.open.delete(vuln.id);
      if (t.kind !== 'harden') {
        fixAttempts++;
        if (worked) fixSuccesses++;
      }
      const { retry, newRule } = defender.learn(t, worked);
      builder.enqueue(retry);
      if (newRule) defender.hardenTickets(newRule, site).forEach(builder.enqueue);
    }

    builder.maybeBuild(round);

    const { reports, reward } = attacker.runEpisode();
    for (const r of reports) {
      const comp = getComponent(site, r.componentId);
      comp.open.add(r.vulnId);
      comp.lastBreachRound = round;
      comp.history.push({ round, text: `Breached: ${VULN_BY_ID[r.vulnId].name}` });
      emit('report', { report: r });
      builder.enqueue(defender.handleReport(r));
    }

    metrics.push({
      round,
      breaches: reports.length,
      reward,
      fixAttempts,
      fixSuccesses,
      weaknesses: site.components.reduce((n, c) => n + weaknesses(c).length, 0),
      components: site.components.length,
      epsilon: attacker.epsilon,
    });
    emit('round', { metrics: metrics.at(-1) });
  }

  return {
    seed,
    bus,
    site,
    attacker,
    defender,
    builder,
    metrics,
    step,
    get round() {
      return round;
    },
  };
}

// UI helper: what color a component card should be.
export function componentStatus(comp, engine) {
  if (comp.open.size > 0) return comp.lastBreachRound === engine.round ? 'breached' : 'fixing';
  if (comp.hidden && !engine.attacker.known.has(comp.id)) return weaknesses(comp).length ? 'hidden-weak' : 'hidden';
  return weaknesses(comp).length ? 'weak' : 'safe';
}
