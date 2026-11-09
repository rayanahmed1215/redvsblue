// The Builder only thinks about features. It adds pages in stages, applies the
// Defender's fix tickets, and follows the Defender's secure coding rules when
// it builds something new (but sometimes forgets one).
import { STAGES, FEATURE_NAMES, MAX_COMPONENTS, FLAGS, addComponent, getComponent, makeFlags } from '../sim/site.js';

export function createBuilder({ rng, site, defender, emit, buildEvery = 5, regressRate = 0.15 }) {
  const queue = [];
  const featureCount = {};
  const self = { queue, stageIndex: 0, regressions: 0, buildEvery, regressRate, version: 1 };

  self.enqueue = (ticket) => ticket && queue.push(ticket);

  function applyRules(comp) {
    for (const { vulnId, flag } of defender.rulesForType(comp.type)) {
      if (comp.flags[flag]) continue;
      if (rng.chance(self.regressRate)) {
        self.regressions++;
        emit('regress', { componentId: comp.id, vulnId, flag });
      } else {
        comp.flags[flag] = true;
      }
    }
  }

  function build(type, name, stage, round) {
    const comp = addComponent(site, type, name, stage, round);
    applyRules(comp);
    comp.history.push({ round, text: 'Built' });
    emit('build', { componentId: comp.id });
    return comp;
  }

  // Apply every queued ticket. Returns the tickets so the engine can retest them.
  self.applyTickets = function applyTickets(round) {
    const applied = queue.splice(0);
    for (const t of applied) {
      const comp = getComponent(site, t.componentId);
      comp.flags[t.flag] = true;
      comp.history.push({ round, text: `${t.kind === 'harden' ? 'Hardened' : 'Patched'}: ${FLAGS[t.flag].label}` });
      emit('fix', { ticket: t });
    }
    return applied;
  };

  self.maybeBuild = function maybeBuild(round) {
    if ((round - 1) % self.buildEvery !== 0) return;
    if (self.stageIndex < STAGES.length) {
      const stage = STAGES[self.stageIndex++];
      emit('stage', { stage: self.stageIndex, name: stage.name });
      for (const [type, name] of stage.components) build(type, name, self.stageIndex, round);
      return;
    }
    if ((round - 1) % (self.buildEvery * 2) !== 0) return;
    if (site.components.length < MAX_COMPONENTS) {
      const type = rng.pick(Object.keys(FEATURE_NAMES));
      const names = FEATURE_NAMES[type];
      const n = (featureCount[type] = (featureCount[type] ?? 0) + 1);
      const name = names[(n - 1) % names.length] + (n > names.length ? ` ${Math.ceil(n / names.length)}` : '');
      emit('feature', { name });
      build(type, name, self.stageIndex + 1, round);
    } else {
      // Site is full: redesign an existing page from scratch, losing its patches.
      const candidates = site.components.filter((c) => c.type !== 'landingPage');
      const comp = rng.pick(candidates);
      comp.flags = makeFlags();
      comp.open.clear();
      self.version++;
      applyRules(comp);
      comp.history.push({ round, text: 'Redesigned from scratch' });
      emit('redesign', { componentId: comp.id });
    }
  };

  return self;
}
