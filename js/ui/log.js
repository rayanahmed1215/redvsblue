// Turns engine events into readable log lines.
import { getComponent } from '../sim/site.js';
import { VULN_BY_TECHNIQUE } from '../sim/vulns.js';
import { esc, vlink, flagLabel, compLink } from './util.js';

const WHY = { explore: 'trying a guess', best: 'best known fix', rule: 'following a rule' };

export function describe(e, site) {
  const c = e.componentId ? getComponent(site, e.componentId) : e.ticket ? getComponent(site, e.ticket.componentId) : null;
  switch (e.type) {
    case 'stage':
      return { who: 'builder', html: `Starting stage ${e.stage}: <b>${esc(e.name)}</b>` };
    case 'build':
      return { who: 'builder', html: `Built ${compLink(c)} <code>${esc(c.path)}</code>` };
    case 'redesign':
      return { who: 'builder', html: `Redesigned ${compLink(c)} from scratch. Its old patches are gone!` };
    case 'regress':
      return { who: 'builder', html: `Forgot to turn on ${flagLabel(e.flag)} for ${compLink(c)}, so it is open to ${vlink(e.vulnId)}` };
    case 'discover':
      return e.how === 'recon'
        ? { who: 'attacker', kind: 'breach', html: `Recon found hidden page ${compLink(c)} <code>${esc(c.path)}</code>` }
        : { who: 'attacker', html: `Mapped ${compLink(c)} by following links` };
    case 'recon':
      return { who: 'attacker', kind: 'failed', html: 'Probed for hidden pages and found nothing' };
    case 'attack':
      return { who: 'attacker', kind: 'failed', html: `Tried ${esc(VULN_BY_TECHNIQUE[e.technique].techniqueLabel)} on ${compLink(c)} and failed` };
    case 'breach':
      return { who: 'attacker', kind: 'breach', html: `<b>BREACH:</b> ${vlink(e.vulnId)} on ${compLink(c)}. Reporting it to the Defender.` };
    case 'ticket': {
      const t = e.ticket;
      return t.kind === 'harden'
        ? { who: 'defender', html: `Harden ${compLink(c)} with ${flagLabel(t.flag)} (${WHY.rule})` }
        : { who: 'defender', html: `Fix for ${vlink(t.vulnId)} on ${compLink(c)}: turn on ${flagLabel(t.flag)} <span class="muted">(${WHY[t.why]})</span>` };
    }
    case 'retest':
      if (e.ticket.kind === 'harden') return null;
      return e.worked
        ? { who: 'attacker', html: `Retest: ${vlink(e.ticket.vulnId, 'blue')} on ${compLink(c)} is now <b class="t-blue">blocked</b> ✓` }
        : { who: 'attacker', kind: 'breach', html: `Retest: ${flagLabel(e.ticket.flag)} did <b>not</b> stop ${vlink(e.ticket.vulnId)} on ${compLink(c)} ✗` };
    case 'rule':
      return { who: 'defender', kind: 'rule', html: `<b>New rule:</b> always use ${flagLabel(e.flag)} against ${vlink(e.vulnId, 'blue')}. Hardening every page this applies to.` };
    default:
      return null;
  }
}

export function createLog(el, max = 1500) {
  let entries = [];
  return {
    clear() {
      entries = [];
    },
    add(e, site) {
      const d = describe(e, site);
      if (d) entries.push({ round: e.round, ...d });
      if (entries.length > max) {
        // Drop old failed attempts first so important events stay visible longer.
        const failed = entries.filter((x) => x.kind === 'failed');
        const excess = entries.length - max;
        if (failed.length > excess) {
          const drop = new Set(failed.slice(0, excess));
          entries = entries.filter((x) => !drop.has(x));
        } else {
          entries = entries.slice(-max);
        }
      }
    },
    render(showFailed) {
      el.innerHTML = entries
        .filter((x) => showFailed || x.kind !== 'failed')
        .slice(-200)
        .reverse()
        .map((x) => `<li class="${x.kind ?? ''}"><span class="r">R${x.round}</span><span class="who ${x.who}">${x.who}</span><span>${x.html}</span></li>`)
        .join('');
    },
  };
}
