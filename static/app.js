async function getState() {
  const r = await fetch('/api/state');
  return r.json();
}

function renderKeyValues(id, obj) {
  const el = document.getElementById(id);
  if (!el) return;
  el.innerHTML = '';
  Object.entries(obj).forEach(([k, v]) => {
    const li = document.createElement('li');
    li.textContent = `${k}: ${v}`;
    el.appendChild(li);
  });
}

function renderShelfSvg(layout) {
  const svg = document.getElementById('shelfSvg');
  if (!svg) return;
  svg.innerHTML = '';
  const viewW = 1000, viewH = 450, pad = 20;
  const scale = Math.min((viewW - pad * 2) / layout.shelf_width_mm, (viewH - pad * 2) / layout.shelf_depth_mm);
  const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
  rect.setAttribute('x', pad); rect.setAttribute('y', pad);
  rect.setAttribute('width', layout.shelf_width_mm * scale); rect.setAttribute('height', layout.shelf_depth_mm * scale);
  rect.setAttribute('fill', '#e2e8f0'); rect.setAttribute('stroke', '#334155');
  svg.appendChild(rect);
  layout.placements.forEach((p) => {
    const c = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
    c.setAttribute('cx', pad + p.x_mm * scale); c.setAttribute('cy', pad + p.y_mm * scale);
    c.setAttribute('r', (p.diameter_mm / 2) * scale); c.setAttribute('fill', '#38bdf8'); c.setAttribute('stroke', '#0f172a');
    svg.appendChild(c);
  });
  const info = document.getElementById('shelfInfo');
  if (info) info.textContent = `Aktiv hylle ${layout.shelf} | deltype ${layout.part_type_id}`;
}

function renderCoords(layout) {
  const body = document.getElementById('coordsTable');
  if (!body) return;
  body.innerHTML = '';
  layout.placements.forEach((p) => {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${p.part_type_id}</td><td>${p.x_mm}</td><td>${p.y_mm}</td><td>${p.z_mm}</td><td>${p.status}</td>`;
    body.appendChild(tr);
  });
}

async function loadShelfLayout(shelf) {
  const r = await fetch(`/api/leanlift/shelf-layout/${encodeURIComponent(shelf)}`);
  const data = await r.json();
  if (!r.ok) return alert(data.error || 'Feil');
  renderShelfSvg(data);
  renderCoords(data);
}

function focasFieldSchema(fn) {
  return {
    read_alarm: [],
    read_status: [],
    set_program: [{ name: 'program_number', placeholder: 'O1234' }],
    set_feed_override: [{ name: 'value', placeholder: '100' }],
    read_macro: [{ name: 'address', placeholder: '#100' }],
  }[fn] || [];
}

function liftFieldSchema(fn) {
  return {
    move_to_shelf: [{ name: 'shelf', placeholder: '1-50' }],
    pick_tray: [{ name: 'shelf', placeholder: '1-50' }],
    store_tray: [{ name: 'shelf', placeholder: '1-50' }],
    inventory_status: [],
  }[fn] || [];
}

function renderDynamicFields(containerId, schema) {
  const c = document.getElementById(containerId);
  c.innerHTML = '';
  schema.forEach((f) => {
    const i = document.createElement('input');
    i.placeholder = f.placeholder;
    i.dataset.name = f.name;
    c.appendChild(i);
  });
}

function readDynamicFields(containerId) {
  const c = document.getElementById(containerId);
  const out = {};
  c.querySelectorAll('input').forEach((i) => { out[i.dataset.name] = i.value; });
  return out;
}

async function initDashboard() {
  const state = await getState();
  const sel = document.getElementById('prodPartType');
  state.part_types.forEach((pt) => {
    const o = document.createElement('option');
    o.value = pt.part_type_id; o.textContent = `${pt.part_type_id} (${pt.quantity_total})`;
    sel.appendChild(o);
  });
  renderKeyValues('productionStatus', state.production_order);
  renderKeyValues('simulationStatus', state.simulation);
  await loadShelfLayout(state.simulation.active_shelf);

  document.getElementById('startProductionBtn').addEventListener('click', async () => {
    const payload = { part_type_id: sel.value, mode: document.getElementById('prodMode').value, quantity: Number(document.getElementById('prodQty').value) };
    const r = await fetch('/api/production/start', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    const d = await r.json();
    if (!r.ok) return alert(d.error || 'Feil');
    renderKeyValues('productionStatus', d);
  });

  document.getElementById('simStartBtn').addEventListener('click', async () => { await fetch('/api/simulation/start', { method: 'POST' }); const s = await getState(); renderKeyValues('simulationStatus', s.simulation); await loadShelfLayout(s.simulation.active_shelf); });
  document.getElementById('simPauseBtn').addEventListener('click', async () => { await fetch('/api/simulation/pause', { method: 'POST' }); const s = await getState(); renderKeyValues('simulationStatus', s.simulation); });
  document.getElementById('simStepBtn').addEventListener('click', async () => { await fetch('/api/simulation/step', { method: 'POST' }); const s = await getState(); renderKeyValues('simulationStatus', s.simulation); renderKeyValues('productionStatus', s.production_order); await loadShelfLayout(s.simulation.active_shelf); });
}

async function initShelves() {
  const state = await getState();
  const shelf = document.getElementById('shelfSelect');
  state.shelves.forEach((s) => { const o = document.createElement('option'); o.value = s; o.textContent = `Hylle ${s}`; shelf.appendChild(o); });

  document.getElementById('saveTemplateBtn').addEventListener('click', async () => {
    let placements = [];
    try { placements = JSON.parse(document.getElementById('templateJson').value || '[]'); } catch { return alert('Ugyldig JSON'); }
    const payload = { template_name: document.getElementById('templateNameInput').value, placements };
    const r = await fetch('/api/layout-templates', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    const d = await r.json();
    if (!r.ok) return alert(d.error || 'Feil');
    renderKeyValues('shelfResult', d);
  });

  document.getElementById('applyTemplateBtn').addEventListener('click', async () => {
    const payload = { shelf: shelf.value, template_name: document.getElementById('templateNameInput').value };
    const r = await fetch('/api/shelf/apply-template', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    const d = await r.json();
    if (!r.ok) return alert(d.error || 'Feil');
    renderKeyValues('shelfResult', { applied_shelf: d.shelf, template: d.template_name, part_type_id: d.part_type_id });
  });
}

async function initParts() {
  const state = await getState();
  const body = document.getElementById('partsTable');
  state.part_types.forEach((p) => {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${p.part_type_id}</td><td>${p.name}</td><td>${p.diameter_mm}</td><td>${p.length_mm}</td><td>${p.height_mm}</td><td>${p.quantity_total}</td>`;
    body.appendChild(tr);
  });
  document.getElementById('savePartBtn').addEventListener('click', async () => {
    const payload = {
      part_type_id: document.getElementById('partTypeId').value,
      name: document.getElementById('partName').value,
      product_id: document.getElementById('partProductId').value,
      quantity_total: Number(document.getElementById('partQty').value),
      diameter_mm: Number(document.getElementById('partDia').value),
      length_mm: Number(document.getElementById('partLen').value),
      height_mm: Number(document.getElementById('partHeight').value),
    };
    const r = await fetch('/api/parts', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    const d = await r.json();
    if (!r.ok) return alert(d.error || 'Feil');
    location.reload();
  });
}

async function initCnc() {
  const state = await getState();
  renderKeyValues('cncStatus', state.cnc);
  const sel = document.getElementById('focasFunction');
  ['read_alarm', 'read_status', 'set_program', 'set_feed_override', 'read_macro'].forEach((fn) => {
    const o = document.createElement('option'); o.value = fn; o.textContent = fn; sel.appendChild(o);
  });
  renderDynamicFields('focasFields', focasFieldSchema(sel.value));
  sel.addEventListener('change', () => renderDynamicFields('focasFields', focasFieldSchema(sel.value)));
  document.getElementById('runFocasBtn').addEventListener('click', async () => {
    const payload = { function_name: sel.value, params: readDynamicFields('focasFields') };
    const r = await fetch('/api/cnc/focas', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    const d = await r.json();
    document.getElementById('focasResponse').textContent = JSON.stringify(d, null, 2);
  });
}

async function initLift() {
  const state = await getState();
  renderKeyValues('liftStatus', state.lift);
  const sel = document.getElementById('liftFunction');
  ['move_to_shelf', 'pick_tray', 'store_tray', 'inventory_status'].forEach((fn) => {
    const o = document.createElement('option'); o.value = fn; o.textContent = fn; sel.appendChild(o);
  });
  renderDynamicFields('liftFields', liftFieldSchema(sel.value));
  sel.addEventListener('change', () => renderDynamicFields('liftFields', liftFieldSchema(sel.value)));
  document.getElementById('runLiftBtn').addEventListener('click', async () => {
    const payload = { function_name: sel.value, params: readDynamicFields('liftFields') };
    const r = await fetch('/api/lift/command', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    const d = await r.json();
    document.getElementById('liftResponse').textContent = JSON.stringify(d, null, 2);
    const s = await getState(); renderKeyValues('liftStatus', s.lift);
  });
}

async function initStats() {
  const state = await getState();
  renderKeyValues('statsList', state.stats);
  const body = document.getElementById('historyTable');
  body.innerHTML = '';
  state.history.forEach((h) => {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${h.ts}</td><td>${h.category}</td><td>${h.message}</td>`;
    body.appendChild(tr);
  });
}

(async function boot() {
  const page = document.body.dataset.page;
  if (page === 'dashboard') await initDashboard();
  if (page === 'shelves') await initShelves();
  if (page === 'parts') await initParts();
  if (page === 'cnc') await initCnc();
  if (page === 'lift') await initLift();
  if (page === 'stats') await initStats();
})();
