import { createEngine } from './sim/engine.js';
import { getComponent, STAGES } from './sim/site.js';
import { renderSiteMap } from './ui/siteMap.js';
import { renderBuilder, renderAttacker, renderDefender } from './ui/panels.js';
import { renderBreachChart, renderAccuracyChart } from './ui/charts.js';
import { createLog } from './ui/log.js';
import { openExplain, openComponent } from './ui/explain.js';

const $ = (id) => document.getElementById(id);
const log = createLog($('log'));
let engine;
let timer = null;

function settings() {
  return {
    seed: Number($('seed').value) || 1,
    alpha: Number($('alpha').value),
    minEpsilon: Number($('min-eps').value),
  };
}

function reset() {
  pause();
  const s = settings();
  engine = createEngine({ seed: s.seed, attacker: { alpha: s.alpha, minEpsilon: s.minEpsilon } });
  log.clear();
  engine.bus.on((e) => log.add(e, engine.site));
  render();
}

function render() {
  const stage = engine.builder.stageIndex;
  $('round-label').textContent = `Round ${engine.round}${stage ? ` · Stage ${Math.min(stage, STAGES.length)}/${STAGES.length}` : ''}`;
  renderSiteMap($('sitemap'), engine);
  renderBuilder($('panel-builder'), engine);
  renderAttacker($('panel-attacker'), engine);
  renderDefender($('panel-defender'), engine);
  renderBreachChart($('chart-breaches'), engine.metrics);
  renderAccuracyChart($('chart-accuracy'), engine.metrics);
  log.render($('show-failed').checked);
}

function step() {
  engine.step();
  render();
}

function play() {
  if (timer) return;
  timer = setInterval(step, 1000 / Number($('speed').value));
  $('btn-play').textContent = '⏸ Pause';
}

function pause() {
  clearInterval(timer);
  timer = null;
  $('btn-play').textContent = '▶ Play';
}

$('btn-play').addEventListener('click', () => (timer ? pause() : play()));
$('btn-step').addEventListener('click', () => {
  pause();
  step();
});
$('btn-reset').addEventListener('click', reset);
$('seed').addEventListener('change', reset);
$('show-failed').addEventListener('change', render);

$('speed').addEventListener('input', () => {
  $('speed-out').textContent = `${$('speed').value}/s`;
  if (timer) {
    pause();
    play();
  }
});
$('alpha').addEventListener('input', () => {
  engine.attacker.alpha = Number($('alpha').value);
  $('alpha-out').textContent = Number($('alpha').value).toFixed(2);
});
$('min-eps').addEventListener('input', () => {
  const v = Number($('min-eps').value);
  engine.attacker.minEpsilon = v;
  engine.attacker.epsilon = Math.max(engine.attacker.epsilon, v);
  $('min-eps-out').textContent = v.toFixed(2);
  render();
});

$('btn-theme').addEventListener('click', () => {
  const root = document.documentElement;
  const dark = root.dataset.theme ? root.dataset.theme === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches;
  root.dataset.theme = dark ? 'light' : 'dark';
  try {
    localStorage.setItem('rvb-theme', root.dataset.theme);
  } catch {}
});
try {
  const saved = localStorage.getItem('rvb-theme');
  if (saved) document.documentElement.dataset.theme = saved;
} catch {}

// Clicking any attack name or site-map card opens an explanation.
document.addEventListener('click', (ev) => {
  const v = ev.target.closest('[data-vuln]');
  if (v) return openExplain(v.dataset.vuln);
  const c = ev.target.closest('[data-comp]');
  if (c) openComponent(getComponent(engine.site, c.dataset.comp), engine);
});
// Click outside a dialog to close it.
for (const d of document.querySelectorAll('dialog')) {
  d.addEventListener('click', (ev) => ev.target === d && d.close());
}

reset();
