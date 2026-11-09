import { STAGES, COMPONENT_TYPES, getComponent } from '../sim/site.js';
import { VULNS, VULN_BY_ID } from '../sim/vulns.js';
import { REWARDS } from '../agents/attacker.js';
import { esc, vlink, flagLabel } from './util.js';

const stat = (k, v) => `<div class="stat"><div class="k">${k}</div><div class="v">${v}</div></div>`;

export function renderBuilder(el, engine) {
  const b = engine.builder;
  const stage = b.stageIndex === 0
    ? 'Not started'
    : b.stageIndex < STAGES.length
      ? `${b.stageIndex}/${STAGES.length}: ${esc(STAGES[b.stageIndex - 1].name)}`
      : 'All stages done, now adding features';
  const rules = Object.entries(engine.defender.rules);
  const queue = b.queue
    .map((t) => {
      const c = getComponent(engine.site, t.componentId);
      return `<li>${t.kind === 'harden' ? 'Harden' : 'Patch'} <b>${esc(c.name)}</b>: turn on ${flagLabel(t.flag)}</li>`;
    })
    .join('');
  el.innerHTML = `
    <div class="stats">${stat('Pages', engine.site.components.length)}${stat('Fix queue', b.queue.length)}${stat('Forgot a rule', b.regressions)}</div>
    <div class="muted">Stage ${stage}</div>
    <div class="sub">Secure coding rules followed</div>
    ${rules.length ? `<div class="chips">${rules.map(([v, f]) => `<span class="chip blue">${flagLabel(f)} (${esc(VULN_BY_ID[v].name)})</span>`).join('')}</div>` : '<div class="muted">None yet. New pages are built with zero security.</div>'}
    <div class="sub">Work queue</div>
    ${queue ? `<ul class="queue">${queue}</ul>` : '<div class="muted">Empty</div>'}`;
}

function heatColor(v) {
  if (v === null) return 'transparent';
  if (v > 0) return `color-mix(in srgb, var(--red) ${Math.min(100, 15 + v * 9)}%, transparent)`;
  return `color-mix(in srgb, var(--grey) ${Math.min(50, 10 + -v * 40)}%, transparent)`;
}

export function renderAttacker(el, engine) {
  const a = engine.attacker;
  const types = [...new Set(engine.site.components.filter((c) => a.known.has(c.id)).map((c) => c.type))];
  const head = VULNS.map((v) => `<th title="${esc(v.name)}">${esc(v.techniqueLabel)}</th>`).join('');
  const rows = types
    .map((type) => {
      const cells = VULNS.map((v) => {
        const key = v.requires ? `${type}|${v.technique}+${v.requires}` : `${type}|${v.technique}`;
        const val = a.value(key);
        return `<td style="background:${heatColor(val)}" title="${esc(COMPONENT_TYPES[type].label)} × ${esc(v.techniqueLabel)}">${val === null ? '' : val.toFixed(1)}</td>`;
      }).join('');
      return `<tr><th title="${esc(COMPONENT_TYPES[type].label)}">${esc(COMPONENT_TYPES[type].label)}</th>${cells}</tr>`;
    })
    .join('');
  const last = a.lastEpisode;
  el.innerHTML = `
    <div class="stats">
      ${stat('Exploring', `${Math.round(a.epsilon * 100)}%`)}
      ${stat('Breaches', a.totalBreaches)}
      ${stat('Last reward', last ? last.reward.toFixed(1) : '—')}
    </div>
    <div class="muted" style="font-size:12px">"Exploring" is how often it tries something random instead of its best-known attack. Rewards: breach +${REWARDS.breach}, failed try ${REWARDS.fail}.</div>
    <div class="sub">What it has learned (expected reward)</div>
    ${types.length ? `<div class="heat-wrap"><table class="heat"><thead><tr><th></th>${head}</tr></thead><tbody>${rows}</tbody></table></div>` : '<div class="muted">No pages discovered yet.</div>'}`;
}

export function renderDefender(el, engine) {
  const d = engine.defender;
  const acc = d.attempts ? `${Math.round((100 * d.successes) / d.attempts)}%` : '—';
  const seen = VULNS.filter((v) => d.values[v.id]);
  const rows = seen
    .map((v) => {
      const opts = Object.entries(d.values[v.id])
        .map(([flag, { value, tries }]) => {
          const zero = (2 / 7) * 100; // value range is about -2..5
          const pct = (Math.abs(value) / 7) * 100;
          const fill = value >= 0
            ? `<span class="fill pos" style="left:${zero}%;width:${pct}%"></span>`
            : `<span class="fill neg" style="left:${zero - pct}%;width:${pct}%"></span>`;
          return `<div class="opt"><span>${flagLabel(flag)}</span><span class="track">${fill}<span class="zero" style="left:${zero}%"></span></span><span class="val">${tries ? value.toFixed(1) : '?'}</span></div>`;
        })
        .join('');
      const rule = d.rules[v.id] ? '<span class="chip blue">rule learned</span>' : '<span class="chip">learning</span>';
      return `<div class="vuln-row"><div class="head">${vlink(v.id)}${rule}</div>${opts}</div>`;
    })
    .join('');
  el.innerHTML = `
    <div class="stats">${stat('Fixes tried', d.attempts)}${stat('Worked', acc)}${stat('Rules', Object.keys(d.rules).length)}</div>
    <div class="sub">Which fix works? (learned score)</div>
    ${rows || '<div class="muted">No breach reports yet.</div>'}`;
}
