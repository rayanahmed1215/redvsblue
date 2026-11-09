import { VULN_BY_ID } from '../sim/vulns.js';
import { FLAGS } from '../sim/site.js';

export const esc = (s) =>
  String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);

export const vlink = (vulnId, cls = '') =>
  `<button class="vlink ${cls}" data-vuln="${vulnId}">${esc(VULN_BY_ID[vulnId].name)}</button>`;

export const flagLabel = (flag) => esc(FLAGS[flag]?.label ?? flag);

export const compLink = (comp) => (comp ? `<b>${esc(comp.name)}</b>` : '?');
