import { componentStatus } from '../sim/engine.js';
import { weaknesses } from '../sim/vulns.js';
import { esc } from './util.js';

const STATUS_TEXT = {
  safe: () => 'secure',
  weak: (n) => `${n} weakness${n > 1 ? 'es' : ''}, not found yet`,
  breached: () => 'BREACHED!',
  fixing: () => 'fix in progress',
  hidden: () => 'hidden · secure',
  'hidden-weak': (n) => `hidden · ${n} weakness${n > 1 ? 'es' : ''}`,
};

export function renderSiteMap(el, engine) {
  const comps = engine.site.components;
  if (!comps.length) {
    el.innerHTML = '<div class="empty">Nothing built yet. Press Play or Step.</div>';
    return;
  }
  el.innerHTML = comps
    .map((c) => {
      const status = componentStatus(c, engine);
      const n = weaknesses(c).length;
      return `<button class="comp ${status}" data-comp="${c.id}">
        <span class="name">${esc(c.name)}</span>
        <span class="path">${esc(c.path)}</span>
        <span class="status">${STATUS_TEXT[status](n)}</span>
      </button>`;
    })
    .join('');
}
