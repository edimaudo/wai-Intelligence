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
