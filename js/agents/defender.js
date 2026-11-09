// Blue team: receives breach reports and has to learn which fix actually stops
// each kind of attack. Fixes that pass the retest gain value; fixes that fail
// lose value. A fix that keeps working becomes a "secure coding rule".
import { VULN_BY_ID, fixOptions } from '../sim/vulns.js';

export const DEFENDER_REWARDS = { fixed: 5, failed: -2 };

export function createDefender({ rng, emit, epsilon = 0.1, lr = 0.5, promoteAfter = 2 }) {
  const values = {}; // vulnId -> { flag: { value, tries } }
  const streak = {}; // vulnId -> { flag, count }
  const rules = {}; // vulnId -> flag
  const open = new Set(); // `${componentId}|${vulnId}` with a ticket in flight
  let nextTicket = 1;

  const self = { values, rules, open, attempts: 0, successes: 0, epsilon };

  const table = (vuln) =>
    (values[vuln.id] ??= Object.fromEntries(fixOptions(vuln).map((f) => [f, { value: 0, tries: 0 }])));

  function chooseFix(vuln) {
    if (rules[vuln.id]) return { flag: rules[vuln.id], why: 'rule' };
    const t = table(vuln);
    const opts = Object.keys(t);
    const best = Math.max(...opts.map((f) => t[f].value));
    const bestOpts = opts.filter((f) => t[f].value === best);
    if (best > 0 && !rng.chance(self.epsilon)) return { flag: rng.pick(bestOpts), why: 'best' };
    const untried = opts.filter((f) => t[f].tries === 0);
    if (untried.length) return { flag: rng.pick(untried), why: 'explore' };
    return { flag: rng.pick(bestOpts), why: 'best' };
  }

  function makeTicket(componentId, vulnId, kind = 'fix') {
    const vuln = VULN_BY_ID[vulnId];
    const { flag, why } = kind === 'harden' ? { flag: rules[vulnId], why: 'rule' } : chooseFix(vuln);
    const ticket = { id: nextTicket++, componentId, vulnId, flag, kind, why };
    open.add(`${componentId}|${vulnId}`);
    emit('ticket', { ticket });
    return ticket;
  }

  // A breach report from the attacker. Returns a fix ticket (or null if one is already in flight).
  self.handleReport = function handleReport(report) {
    if (open.has(`${report.componentId}|${report.vulnId}`)) return null;
    return makeTicket(report.componentId, report.vulnId);
  };

  self.hasOpenTicket = (componentId, vulnId) => open.has(`${componentId}|${vulnId}`);

  // Called after the attacker replays the exploit against the patched component.
  // Returns { retry, newRule }.
  self.learn = function learn(ticket, worked) {
    open.delete(`${ticket.componentId}|${ticket.vulnId}`);
    if (ticket.kind === 'harden') return { retry: null, newRule: null };

    const vuln = VULN_BY_ID[ticket.vulnId];
    const entry = table(vuln)[ticket.flag];
    const reward = worked ? DEFENDER_REWARDS.fixed : DEFENDER_REWARDS.failed;
    entry.tries++;
    entry.value += lr * (reward - entry.value);
    self.attempts++;
    if (worked) self.successes++;

    const s = (streak[vuln.id] ??= { flag: null, count: 0 });
    if (worked && s.flag === ticket.flag) s.count++;
    else if (worked) Object.assign(s, { flag: ticket.flag, count: 1 });
    else Object.assign(s, { flag: null, count: 0 });

    let newRule = null;
    if (worked && !rules[vuln.id] && s.count >= promoteAfter) {
      rules[vuln.id] = ticket.flag;
      newRule = vuln.id;
      emit('rule', { vulnId: vuln.id, flag: ticket.flag });
    }
    const retry = worked ? null : makeTicket(ticket.componentId, ticket.vulnId);
    return { retry, newRule };
  };

  // After learning a rule, harden every existing component it applies to.
  self.hardenTickets = function hardenTickets(vulnId, site) {
    const vuln = VULN_BY_ID[vulnId];
    const flag = rules[vulnId];
    return site.components
      .filter((c) => vuln.targets.includes(c.type) && !c.flags[flag] && !open.has(`${c.id}|${vulnId}`))
      .map((c) => makeTicket(c.id, vulnId, 'harden'));
  };

  // Flags the Builder should turn on for a new component of this type.
  self.rulesForType = function rulesForType(type) {
    return Object.entries(rules)
      .filter(([vulnId]) => VULN_BY_ID[vulnId].targets.includes(type))
      .map(([vulnId, flag]) => ({ vulnId, flag }));
  };

  self.confidence = (vulnId, flag) => values[vulnId]?.[flag] ?? null;

  return self;
}
