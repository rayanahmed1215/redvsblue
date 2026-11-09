// Popups: "what is this attack?" and "what does this page's security look like?"
import { VULN_BY_ID, vulnsForType, isVulnerable, relevantFlags } from '../sim/vulns.js';
import { FLAGS, COMPONENT_TYPES } from '../sim/site.js';
import { esc, vlink, flagLabel } from './util.js';

const closeBtn = '<form method="dialog"><button class="close" aria-label="Close">✕</button></form>';

export function openExplain(vulnId) {
  const v = VULN_BY_ID[vulnId];
  const dlg = document.getElementById('explain-dialog');
  const decoys = Object.entries(v.explain.decoyWhy)
    .map(([f, why]) => `<li><b>${flagLabel(f)}</b>: ${esc(why)}</li>`)
    .join('');
  const targets = v.targets.map((t) => esc(COMPONENT_TYPES[t].label)).join(', ');
  dlg.innerHTML = `${closeBtn}
    <span class="sev ${v.severity}">${v.severity}</span>
    <h3>${esc(v.name)}</h3>
    <p class="muted">Affects: ${targets}${v.requires ? ' · needs database access first (from SQL injection)' : ''}</p>
    <h4>What it is</h4><p>${esc(v.explain.what)}</p>
    <h4>Example</h4><p class="example">${esc(v.explain.example)}</p>
    <h4>The real fix: ${flagLabel(v.fix)}</h4><p>${esc(v.explain.fix)}</p>
    <h4>Fixes that sound right but don't work</h4><ul>${decoys}</ul>`;
  dlg.showModal();
}

export function openComponent(comp, engine) {
  const dlg = document.getElementById('comp-dialog');
  const flags = relevantFlags(comp.type)
    .map(
      (f) => `<li><span class="${comp.flags[f] ? 'on' : 'off'}">${comp.flags[f] ? '✓' : '✗'}</span>
        <span><b>${flagLabel(f)}</b><br><span class="muted">${esc(FLAGS[f].desc)}</span></span></li>`,
    )
    .join('');
  const vulns = vulnsForType(comp.type)
    .map((v) => {
      const weak = isVulnerable(v, comp);
      const state = comp.open.has(v.id) ? 'breached, fix in progress' : weak ? 'weak' : 'protected';
      return `<li>${vlink(v.id, weak ? '' : 'blue')}: ${state}</li>`;
    })
    .join('');
  const hist = comp.history
    .slice(-12)
    .reverse()
    .map((h) => `<li><span class="muted">R${h.round}</span> ${esc(h.text)}</li>`)
    .join('');
  const known = engine.attacker.known.has(comp.id);
  dlg.innerHTML = `${closeBtn}
    <h3>${esc(comp.name)}</h3>
    <p class="muted"><code>${esc(comp.path)}</code> · ${esc(COMPONENT_TYPES[comp.type].label)} · built round ${comp.createdRound}
      ${comp.hidden ? ` · hidden page (${known ? 'found by attacker' : 'not found yet'})` : ''}</p>
    ${flags ? `<h4>Security settings</h4><ul class="flags">${flags}</ul>` : '<p>This page has no forms or inputs, so there is nothing to attack.</p>'}
    ${vulns ? `<h4>Possible attacks</h4><ul>${vulns}</ul>` : ''}
    ${hist ? `<h4>History</h4><ul>${hist}</ul>` : ''}`;
  dlg.showModal();
}
