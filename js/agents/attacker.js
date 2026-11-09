// Red team: learns by trial and error which techniques break which component
// types. This is a simple form of Q-learning: every (situation, action) pair
// has a value, and values move toward the rewards actually received.
import { TECHNIQUES, VULN_BY_TECHNIQUE } from '../sim/vulns.js';

export const REWARDS = { breach: 10, discover: 1, fail: -0.5, reconEmpty: -0.2 };

export function createAttacker({
  rng,
  site,
  emit,
  alpha = 0.3,
  epsilon = 1,
  epsilonDecay = 0.95,
  minEpsilon = 0.05,
  budget = 12,
  successRate = 0.9,
  hiddenFindChance = 0.4,
}) {
  const q = {}; // key -> { value, n }
  const known = new Set(); // component ids the attacker has found
  const self = {
    alpha,
    epsilon,
    epsilonDecay,
    minEpsilon,
    budget,
    q,
    known,
    episodes: 0,
    totalBreaches: 0,
    lastEpisode: null,
  };

  const qKey = (type, technique, state) => {
    const v = VULN_BY_TECHNIQUE[technique];
    return v.requires && state[v.requires] ? `${type}|${technique}+${v.requires}` : `${type}|${technique}`;
  };
  const qGet = (key) => (q[key] ??= { value: 0, n: 0 });
  const update = (key, reward) => {
    const e = qGet(key);
    e.n++;
    e.value += self.alpha * (reward - e.value);
  };

  // Following links finds every visible page for free. Hidden pages need recon.
  function crawl() {
    let found = 0;
    for (const c of site.components) {
      if (!c.hidden && !known.has(c.id)) {
        known.add(c.id);
        found++;
        emit('discover', { componentId: c.id, how: 'crawl' });
      }
    }
    return found;
  }

  function recon() {
    const hidden = site.components.filter((c) => c.hidden && !known.has(c.id));
    if (hidden.length && rng.chance(hiddenFindChance)) {
      const c = rng.pick(hidden);
      known.add(c.id);
      emit('discover', { componentId: c.id, how: 'recon' });
      return REWARDS.discover;
    }
    emit('recon', { found: false });
    return REWARDS.reconEmpty;
  }

  function attack(comp, technique, state, reports) {
    const vuln = VULN_BY_TECHNIQUE[technique];
    const applies = vuln.targets.includes(comp.type);
    const prereqOk = !vuln.requires || state[vuln.requires];
    const weak = applies && prereqOk && !comp.flags[vuln.fix];
    if (weak && rng.chance(successRate)) {
      if (vuln.grants) state[vuln.grants] = true;
      self.totalBreaches++;
      reports.push({ componentId: comp.id, vulnId: vuln.id, technique });
      emit('breach', { componentId: comp.id, vulnId: vuln.id, technique });
      return REWARDS.breach;
    }
    emit('attack', { componentId: comp.id, technique, vulnId: vuln.id, success: false });
    return REWARDS.fail;
  }

  self.runEpisode = function runEpisode() {
    crawl();
    const state = {};
    const tried = new Set();
    const reports = [];
    let reward = 0;
    for (let step = 0; step < self.budget; step++) {
      const actions = [{ kind: 'recon', key: 'recon' }];
      for (const c of site.components) {
        if (!known.has(c.id)) continue;
        for (const t of TECHNIQUES) {
          if (tried.has(`${c.id}|${t}`)) continue;
          actions.push({ kind: 'attack', comp: c, technique: t, key: qKey(c.type, t, state) });
        }
      }
      let action;
      if (rng.chance(self.epsilon)) {
        action = rng.pick(actions);
      } else {
        const best = Math.max(...actions.map((a) => qGet(a.key).value));
        action = rng.pick(actions.filter((a) => qGet(a.key).value === best));
      }
      let r;
      if (action.kind === 'recon') {
        r = recon();
      } else {
        tried.add(`${action.comp.id}|${action.technique}`);
        r = attack(action.comp, action.technique, state, reports);
      }
      update(action.key, r);
      reward += r;
    }
    self.episodes++;
    self.epsilon = Math.max(self.minEpsilon, self.epsilon * self.epsilonDecay);
    self.lastEpisode = { reports, reward };
    return self.lastEpisode;
  };

  self.value = (key) => q[key]?.value ?? null;

  return self;
}
