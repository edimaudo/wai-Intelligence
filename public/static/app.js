(function () {
  const root = document.documentElement;
  const themeToggle = document.getElementById('theme-toggle');
  const themeIcon = document.getElementById('theme-icon');
  const fontSelect = document.getElementById('font-size-select');
  const navToggle = document.getElementById('nav-toggle');
  const nav = document.getElementById('app-navigation');

  function applyTheme(theme) {
    const next = theme === 'dark' ? 'dark' : 'light';
    root.setAttribute('data-theme', next);
    if (themeIcon) themeIcon.textContent = next === 'dark' ? '☼' : '◐';
    if (themeToggle) themeToggle.setAttribute('aria-pressed', next === 'dark' ? 'true' : 'false');
  }
  function applyFontSize(size) {
    const permitted = ['small', 'medium', 'large'];
    const next = permitted.includes(size) ? size : 'medium';
    root.setAttribute('data-font-size', next);
    if (fontSelect) fontSelect.value = next;
  }

  let savedTheme = 'light';
  let savedSize = 'medium';
  try {
    savedTheme = localStorage.getItem('wai-theme') || 'light';
    savedSize = localStorage.getItem('wai-font-size') || 'medium';
  } catch (_) { /* Browser storage may be disabled; controls still work for this page. */ }
  applyTheme(savedTheme);
  applyFontSize(savedSize);

  if (themeToggle) themeToggle.addEventListener('click', function () {
    const next = root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    applyTheme(next);
    try { localStorage.setItem('wai-theme', next); } catch (_) {}
  });
  if (fontSelect) fontSelect.addEventListener('change', function () {
    applyFontSize(fontSelect.value);
    try { localStorage.setItem('wai-font-size', fontSelect.value); } catch (_) {}
  });
  if (navToggle && nav) navToggle.addEventListener('click', function () {
    const open = nav.classList.toggle('is-open');
    navToggle.setAttribute('aria-expanded', open ? 'true' : 'false');
  });
})();

(function () {
  const ids = ['cost-source-count', 'cost-review-frequency-days', 'cost-minutes-per-source', 'cost-hourly-rate', 'cost-leads-month', 'cost-review-minutes', 'cost-tool-cost', 'cost-extra-award'];
  const nodes = ids.map(id => document.getElementById(id));
  const output = {
    annual: document.getElementById('cost-annual-total'),
    perLead: document.getElementById('cost-per-lead'),
    breakEven: document.getElementById('cost-break-even')
  };
  if (!nodes.some(Boolean) || !output.annual || !output.perLead || !output.breakEven) return;
  const currency = new Intl.NumberFormat(document.documentElement.lang === 'fr-CA' ? 'fr-CA' : 'en-CA', {style: 'currency', currency: 'CAD', maximumFractionDigits: 0});
  function value(id) {
    const node = document.getElementById(id);
    const parsed = node ? Number(node.value) : 0;
    return Number.isFinite(parsed) && parsed > 0 ? parsed : 0;
  }
  function calculate() {
    // Estimate source-checking labour, lead-review labour and the monthly tool budget.
    const sources = value('cost-source-count');
    const reviewDays = Math.max(1, value('cost-review-frequency-days'));
    const minutesPerSource = value('cost-minutes-per-source');
    const hourlyRate = value('cost-hourly-rate');
    const leadsMonthly = value('cost-leads-month');
    const reviewMinutes = value('cost-review-minutes');
    const toolsMonthly = value('cost-tool-cost');
    const extraAwardValue = value('cost-extra-award');
    const annualSourceChecks = sources * (365 / reviewDays);
    const monitoringHours = annualSourceChecks * minutesPerSource / 60;
    const reviewHours = leadsMonthly * 12 * reviewMinutes / 60;
    const annual = (monitoringHours + reviewHours) * hourlyRate + toolsMonthly * 12;
    output.annual.textContent = currency.format(annual);
    output.perLead.textContent = leadsMonthly > 0 ? currency.format(annual / (leadsMonthly * 12)) : '—';
    output.breakEven.textContent = extraAwardValue > 0 ? String(Math.ceil(annual / extraAwardValue)) : '—';
  }
  nodes.filter(Boolean).forEach(node => node.addEventListener('input', calculate));
  calculate();
})();

(function () {
  const host = document.querySelector('.email-engagement-line-chart');
  if (!host) return;
  let series = [];
  try { series = JSON.parse(host.getAttribute('data-series') || '[]'); } catch (_) { series = []; }
  series = series.filter(row => row && /^\d{4}$/.test(String(row.year)));
  if (!series.length) {
    const empty = document.createElement('p');
    empty.className = 'empty-state';
    empty.textContent = document.documentElement.lang === 'fr-CA' ? 'Aucune année d’envoi disponible dans les données chargées.' : 'No send-year data is available in the loaded records.';
    host.appendChild(empty);
    return;
  }
  const ns = 'http://www.w3.org/2000/svg';
  const width = 760, height = 250, left = 48, right = 20, top = 16, bottom = 40;
  const plotWidth = width - left - right, plotHeight = height - top - bottom;
  const values = series.flatMap(row => [row.open_rate, row.click_rate]).filter(value => value !== null && value !== undefined && Number.isFinite(Number(value))).map(Number);
  const maxValue = Math.min(100, Math.max(10, Math.ceil(Math.max(...values, 0) / 10) * 10));
  const x = index => left + (series.length === 1 ? plotWidth / 2 : index * plotWidth / (series.length - 1));
  const y = value => top + plotHeight - (Number(value || 0) / maxValue) * plotHeight;
  const svg = document.createElementNS(ns, 'svg');
  svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
  svg.setAttribute('role', 'img');
  svg.setAttribute('aria-label', document.documentElement.lang === 'fr-CA' ? 'Taux d’ouverture et de clics par année' : 'Open and click rates by year');
  for (let tick = 0; tick <= 2; tick++) {
    const value = maxValue * tick / 2;
    const line = document.createElementNS(ns, 'line');
    line.setAttribute('x1', left); line.setAttribute('x2', width - right);
    line.setAttribute('y1', y(value)); line.setAttribute('y2', y(value));
    line.setAttribute('class', 'chart-grid-line'); svg.appendChild(line);
    const label = document.createElementNS(ns, 'text');
    label.setAttribute('x', left - 9); label.setAttribute('y', y(value) + 4);
    label.setAttribute('text-anchor', 'end'); label.setAttribute('class', 'chart-axis-label');
    label.textContent = `${Math.round(value)}%`; svg.appendChild(label);
  }
  const buildLine = (field, className, label) => {
    const points = series.map((row, index) => ({row, index, value: row[field]})).filter(point => point.value !== null && point.value !== undefined && Number.isFinite(Number(point.value)));
    if (!points.length) return;
    const path = document.createElementNS(ns, 'polyline');
    path.setAttribute('points', points.map(point => `${x(point.index)},${y(point.value)}`).join(' '));
    path.setAttribute('class', `engagement-line ${className}`); svg.appendChild(path);
    points.forEach(point => {
      const circle = document.createElementNS(ns, 'circle');
      circle.setAttribute('cx', x(point.index)); circle.setAttribute('cy', y(point.value)); circle.setAttribute('r', 4);
      circle.setAttribute('class', `engagement-point ${className}`);
      const title = document.createElementNS(ns, 'title'); title.textContent = `${point.row.year} ${label}: ${point.value}%`;
      circle.appendChild(title); svg.appendChild(circle);
    });
  };
  buildLine('open_rate', 'open-rate-line', 'open rate');
  buildLine('click_rate', 'click-rate-line', 'click-through rate');
  series.forEach((row, index) => {
    const label = document.createElementNS(ns, 'text');
    label.setAttribute('x', x(index)); label.setAttribute('y', height - 14);
    label.setAttribute('text-anchor', 'middle'); label.setAttribute('class', 'chart-axis-label');
    label.textContent = row.year; svg.appendChild(label);
  });
  host.replaceChildren(svg);
})();
