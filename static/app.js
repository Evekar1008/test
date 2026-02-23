async function getState() {
  const r = await fetch('/api/state');
  return r.json();
}

function renderKeyValues(id, obj) {
  const el = document.getElementById(id);
  if (!el) return;
  el.innerHTML = '';
  Object.entries(obj || {}).forEach(([k, v]) => {
    const li = document.createElement('li');
    li.textContent = `${k}: ${typeof v === 'object' ? JSON.stringify(v) : v}`;
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
  rect.setAttribute('x', pad);
  rect.setAttribute('y', pad);
  rect.setAttribute('width', layout.shelf_width_mm * scale);
  rect.setAttribute('height', layout.shelf_depth_mm * scale);
  rect.setAttribute('fill', '#e2e8f0');
  rect.setAttribute('stroke', '#334155');
  svg.appendChild(rect);

  layout.slots.forEach((slot) => {
    const color = layout.status_colors[slot.status] || '#94a3b8';
    const r = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
    r.setAttribute('cx', pad + slot.x_mm * scale);
    r.setAttribute('cy', pad + slot.y_mm * scale);
    r.setAttribute('r', 18);
    r.setAttribute('fill', color);
    r.setAttribute('stroke', '#0f172a');
    svg.appendChild(r);

    const t = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    t.setAttribute('x', pad + slot.x_mm * scale);
    t.setAttribute('y', pad + slot.y_mm * scale);
    t.setAttribute('text-anchor', 'middle');
    t.setAttribute('dominant-baseline', 'middle');
    t.setAttribute('font-size', '11');
    t.textContent = String(slot.slot_no);
    svg.appendChild(t);
  });

  const info = document.getElementById('shelfInfo');
  if (info) info.textContent = `Hylle ${layout.shelf} (${layout.slots.length} sloter)`;
}

function renderCoords(layout) {
  const body = document.getElementById('coordsTable');
  if (!body) return;
  body.innerHTML = '';
  layout.slots.forEach((slot) => {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${slot.slot_no}</td><td>${slot.part_type_id || '-'}</td><td>${slot.x_mm}</td><td>${slot.y_mm}</td><td>${slot.z_mm}</td><td>${slot.status}</td>`;
    body.appendChild(tr);
  });
}

async function loadShelfLayout(shelf) {
  const r = await fetch(`/api/leanlift/shelf-layout/${encodeURIComponent(shelf)}`);
  const data = await r.json();
  if (!r.ok) return alert(data.error || 'Feil');
  renderShelfSvg(data);
  renderCoords(data);
  return data;
}

function focasFieldSchema(name) {
  const map = {
    cnc_rdparam: [{ name: 'number', placeholder: 'Parameter nr' }],
    cnc_wrparam: [{ name: 'number', placeholder: 'Parameter nr' }, { name: 'value', placeholder: 'Verdi' }],
    cnc_rdmacro: [{ name: 'address', placeholder: '#100' }],
    cnc_wrmacro: [{ name: 'address', placeholder: '#100' }, { name: 'value', placeholder: 'Verdi' }],
    cnc_start: [], cnc_stop: [], cnc_reset: [], cnc_statinfo: [], cnc_rdalmmsg2: [], cnc_rdprognum: [], cnc_pdf_rdmain: [],
    cnc_rdspmeter: [], cnc_rdsvmeter: [], cnc_rdposition: [], cnc_rdexecprog: [], cnc_rdspeed: [], cnc_rdopmsg: [],
  };
  return map[name] || [];
}

function liftFieldSchema(name) {
  const map = {
    Login: [{ name: 'user', placeholder: 'user' }, { name: 'password', placeholder: 'password' }],
    Logoff: [], GetSystemStatus: [], GetInventory: [], AcknowledgeAlarm: [{ name: 'alarm_id', placeholder: 'alarm id' }],
    GetTrayInfo: [{ name: 'shelf', placeholder: '1-50' }],
    RequestTray: [{ name: 'shelf', placeholder: '1-50' }],
    StoreTray: [{ name: 'shelf', placeholder: '1-50' }],
    MoveToTray: [{ name: 'shelf', placeholder: '1-50' }],
    CreateBooking: [{ name: 'shelf', placeholder: '1-50' }, { name: 'part', placeholder: 'part id' }],
    DeleteBooking: [{ name: 'booking_id', placeholder: 'booking id' }],
    SetAutoMode: [], SetManualMode: [],
  };
  return map[name] || [];
}

function renderDynamicFields(containerId, schema) {
  const c = document.getElementById(containerId);
  if (!c) return;
  c.innerHTML = '';
  schema.forEach((f) => {
    const i = document.createElement('input');
    i.dataset.name = f.name;
    i.placeholder = f.placeholder;
    c.appendChild(i);
  });
}

function readDynamicFields(containerId) {
  const c = document.getElementById(containerId);
  const out = {};
  if (!c) return out;
  c.querySelectorAll('input').forEach((i) => (out[i.dataset.name] = i.value));
  return out;
}

async function initDashboard() {
  const state = await getState();
  const partSel = document.getElementById('prodPartType');
  state.part_types.forEach((pt) => {
    const o = document.createElement('option');
    o.value = pt.part_type_id;
    o.textContent = `${pt.part_type_id} (${pt.quantity_total})`;
    partSel.appendChild(o);
  });
  ['empty', 'raw', 'in_process', 'finished', 'blocked'].forEach((k) => {
    const el = document.getElementById(`color_${k}`);
    if (el) el.value = state.settings.status_colors[k];
  });

  renderKeyValues('productionStatus', state.production_order);
  renderKeyValues('simulationStatus', state.simulation);
  await loadShelfLayout(state.active_shelf);

  document.getElementById('saveColorsBtn').addEventListener('click', async () => {
    const payload = {
      status_colors: {
        empty: document.getElementById('color_empty').value,
        raw: document.getElementById('color_raw').value,
        in_process: document.getElementById('color_in_process').value,
        finished: document.getElementById('color_finished').value,
        blocked: document.getElementById('color_blocked').value,
      },
    };
    await fetch('/api/settings', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    const s = await getState();
    await loadShelfLayout(s.active_shelf);
  });

  document.getElementById('startProductionBtn').addEventListener('click', async () => {
    const payload = { part_type_id: partSel.value, mode: document.getElementById('prodMode').value, quantity: Number(document.getElementById('prodQty').value) };
    const r = await fetch('/api/production/start', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    const d = await r.json();
    if (!r.ok) return alert(d.error || 'Feil');
    renderKeyValues('productionStatus', d);
  });

  document.getElementById('simStartBtn').addEventListener('click', async () => { await fetch('/api/simulation/start', { method: 'POST' }); const s = await getState(); renderKeyValues('simulationStatus', s.simulation); await loadShelfLayout(s.active_shelf); });
  document.getElementById('simPauseBtn').addEventListener('click', async () => { await fetch('/api/simulation/pause', { method: 'POST' }); const s = await getState(); renderKeyValues('simulationStatus', s.simulation); await loadShelfLayout(s.active_shelf); });
  document.getElementById('simStepBtn').addEventListener('click', async () => { await fetch('/api/simulation/step', { method: 'POST' }); const s = await getState(); renderKeyValues('simulationStatus', s.simulation); renderKeyValues('productionStatus', s.production_order); await loadShelfLayout(s.active_shelf); });
}

async function initShelves() {
  const state = await getState();
  const shelfSel = document.getElementById('shelfSelect');
  const p1 = document.getElementById('layoutPartType');
  const p2 = document.getElementById('manualPartType');

  state.shelves.forEach((s) => {
    const o = document.createElement('option');
    o.value = s;
    o.textContent = `Hylle ${s}`;
    shelfSel.appendChild(o);
  });
  state.part_types.forEach((pt) => {
    const a = document.createElement('option'); a.value = pt.part_type_id; a.textContent = pt.part_type_id;
    const b = document.createElement('option'); b.value = pt.part_type_id; b.textContent = pt.part_type_id;
    p1.appendChild(a); p2.appendChild(b);
  });

  await loadShelfLayout(shelfSel.value || state.active_shelf);

  document.getElementById('loadShelfBtn').addEventListener('click', async () => {
    await loadShelfLayout(shelfSel.value);
  });

  document.getElementById('generateLayoutBtn').addEventListener('click', async () => {
    const payload = {
      shelf: shelfSel.value,
      part_type_id: p1.value,
      cols: Number(document.getElementById('layoutCols').value),
      rows: Number(document.getElementById('layoutRows').value),
      z_mm: Number(document.getElementById('layoutZ').value),
    };
    const r = await fetch('/api/shelf/configure-graphic', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    const d = await r.json();
    if (!r.ok) return alert(d.error || 'Feil');
    renderShelfSvg(d);
    renderCoords(d);
    renderKeyValues('shelfResult', { shelf: d.shelf, slots: d.slots.length, part_type: payload.part_type_id });
  });

  document.getElementById('manualLoadBtn').addEventListener('click', async () => {
    const payload = { shelf: shelfSel.value, slot_no: Number(document.getElementById('manualSlotNo').value), occupied: true, status: document.getElementById('manualStatus').value, part_type_id: p2.value };
    const r = await fetch('/api/shelf/slot/update', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    const d = await r.json();
    if (!r.ok) return alert(d.error || 'Feil');
    await loadShelfLayout(shelfSel.value);
    renderKeyValues('shelfResult', d);
  });

  document.getElementById('manualUnloadBtn').addEventListener('click', async () => {
    const payload = { shelf: shelfSel.value, slot_no: Number(document.getElementById('manualSlotNo').value), occupied: false, status: 'empty', part_type_id: '' };
    const r = await fetch('/api/shelf/slot/update', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    const d = await r.json();
    if (!r.ok) return alert(d.error || 'Feil');
    await loadShelfLayout(shelfSel.value);
    renderKeyValues('shelfResult', d);
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
  state.available_focas_functions.forEach((fn) => {
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
  state.available_leanlift_rest_commands.forEach((fn) => {
    const o = document.createElement('option'); o.value = fn; o.textContent = fn; sel.appendChild(o);
  });
  renderDynamicFields('liftFields', liftFieldSchema(sel.value));
  sel.addEventListener('change', () => renderDynamicFields('liftFields', liftFieldSchema(sel.value)));
  document.getElementById('runLiftBtn').addEventListener('click', async () => {
    const payload = { function_name: sel.value, params: readDynamicFields('liftFields') };
    const r = await fetch('/api/lift/command', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    const d = await r.json();
    document.getElementById('liftResponse').textContent = JSON.stringify(d, null, 2);
    const s = await getState();
    renderKeyValues('liftStatus', s.lift);
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

async function initDiagnostics() {
  const r = await fetch('/api/diagnostics');
  const data = await r.json();
  const body = document.getElementById('diagTable');
  body.innerHTML = '';
  data.forEach((d) => {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${d.ts}</td><td>${d.channel}</td><td>${d.direction}</td><td><pre>${JSON.stringify(d.raw)}</pre></td>`;
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
  if (page === 'diagnostics') await initDiagnostics();
})();
