async function getState() {
  const res = await fetch('/api/state');
  return res.json();
}

function renderKeyValues(elementId, obj) {
  const ul = document.getElementById(elementId);
  ul.innerHTML = '';
  Object.entries(obj).forEach(([k, v]) => {
    const li = document.createElement('li');
    li.textContent = `${k}: ${Array.isArray(v) ? v.join(', ') : v}`;
    ul.appendChild(li);
  });
}

function renderProducts(products, active) {
  const select = document.getElementById('productSelect');
  select.innerHTML = '';
  products.forEach((p) => {
    const option = document.createElement('option');
    option.value = p.id;
    option.textContent = `${p.id} - ${p.name}`;
    if (p.id === active) option.selected = true;
    select.appendChild(option);
  });
  const activeProduct = products.find((p) => p.id === active);
  document.getElementById('activeProduct').textContent = activeProduct
    ? `Aktivt produkt: ${activeProduct.name} / CNC ${activeProduct.required_cnc_program}`
    : 'Ingen';
}

function renderShelvesAndTemplates(state) {
  const shelfSelect = document.getElementById('shelfSelect');
  shelfSelect.innerHTML = '';
  state.shelves.forEach((s) => {
    const o = document.createElement('option');
    o.value = s;
    o.textContent = `Hylle ${s}`;
    shelfSelect.appendChild(o);
  });

  const templateSelect = document.getElementById('templateSelect');
  templateSelect.innerHTML = '';
  state.layout_templates.forEach((t) => {
    const o = document.createElement('option');
    o.value = t.template_name;
    o.textContent = t.template_name;
    templateSelect.appendChild(o);
  });
}

function renderCoordsTable(layout) {
  const body = document.getElementById('coordsTable');
  body.innerHTML = '';
  layout.placements.forEach((p) => {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${p.name}</td><td>${p.product_id}</td><td>${p.diameter_mm}</td><td>${p.x_mm}</td><td>${p.y_mm}</td><td>${p.z_mm}</td><td>${p.status}</td>`;
    body.appendChild(tr);
  });
}

function renderShelfSvg(layout) {
  const svg = document.getElementById('shelfSvg');
  svg.innerHTML = '';

  const viewW = 1000;
  const viewH = 450;
  const pad = 20;
  const scale = Math.min((viewW - pad * 2) / layout.shelf_width_mm, (viewH - pad * 2) / layout.shelf_depth_mm);

  const shelfRect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
  shelfRect.setAttribute('x', pad);
  shelfRect.setAttribute('y', pad);
  shelfRect.setAttribute('width', layout.shelf_width_mm * scale);
  shelfRect.setAttribute('height', layout.shelf_depth_mm * scale);
  shelfRect.setAttribute('fill', '#e2e8f0');
  shelfRect.setAttribute('stroke', '#334155');
  svg.appendChild(shelfRect);

  layout.placements.forEach((p) => {
    const c = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
    c.setAttribute('cx', pad + p.x_mm * scale);
    c.setAttribute('cy', pad + p.y_mm * scale);
    c.setAttribute('r', (p.diameter_mm / 2) * scale);
    c.setAttribute('fill', '#38bdf8');
    c.setAttribute('stroke', '#0f172a');
    svg.appendChild(c);

    const t = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    t.setAttribute('x', pad + p.x_mm * scale);
    t.setAttribute('y', pad + p.y_mm * scale);
    t.setAttribute('text-anchor', 'middle');
    t.setAttribute('dominant-baseline', 'middle');
    t.setAttribute('font-size', '12');
    t.textContent = p.part_type_id;
    svg.appendChild(t);
  });

  document.getElementById('shelfInfo').textContent =
    `Hylle ${layout.shelf} | Mal ${layout.template_name} | Deltype ${layout.part_type_id} | ${layout.shelf_width_mm}x${layout.shelf_depth_mm} mm | Z vises i tabellen`;
}

async function refresh() {
  const state = await getState();
  renderProducts(state.products, state.active_product_id);
  renderShelvesAndTemplates(state);
  renderKeyValues('robotStatus', state.robot);
  renderKeyValues('cncStatus', state.cnc);
  document.getElementById('shelfWidth').value = state.settings.shelf_width_mm;
  document.getElementById('shelfDepth').value = state.settings.shelf_depth_mm;

  const shelf = document.getElementById('shelfSelect').value || state.shelves[0];
  await loadShelfLayout(shelf);
}

async function loadShelfLayout(shelf) {
  const res = await fetch(`/api/leanlift/shelf-layout/${encodeURIComponent(shelf)}`);
  const layout = await res.json();
  if (!res.ok) {
    alert(layout.error || 'Feil ved lasting av hylle');
    return;
  }
  renderShelfSvg(layout);
  renderCoordsTable(layout);
}

async function saveSettings() {
  const payload = {
    shelf_width_mm: Number(document.getElementById('shelfWidth').value),
    shelf_depth_mm: Number(document.getElementById('shelfDepth').value),
  };
  const res = await fetch('/api/settings', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (!res.ok) return alert(data.error || 'Feil');
  await refresh();
}

async function saveTemplate() {
  let placements;
  try {
    placements = JSON.parse(document.getElementById('templateJson').value || '[]');
  } catch {
    return alert('Ugyldig JSON');
  }
  const payload = { template_name: document.getElementById('templateNameInput').value, placements };
  const res = await fetch('/api/layout-templates', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (!res.ok) return alert(data.error || 'Feil');
  document.getElementById('templateNameInput').value = data.template_name;
  await refresh();
}

async function applyTemplate() {
  const payload = {
    shelf: document.getElementById('shelfSelect').value,
    template_name: document.getElementById('templateSelect').value,
  };
  const res = await fetch('/api/shelf/apply-template', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (!res.ok) return alert(data.error || 'Feil');
  renderShelfSvg(data);
  renderCoordsTable(data);
}

async function selectProduct() {
  await fetch('/api/select-product', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ product_id: document.getElementById('productSelect').value }),
  });
  await refresh();
}

async function selectProgram() {
  const res = await fetch('/api/cnc/select-program', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ program_number: document.getElementById('programInput').value }),
  });
  const data = await res.json();
  if (!res.ok) return alert(data.error || 'Feil');
  await refresh();
}

document.getElementById('saveSettingsBtn').addEventListener('click', saveSettings);
document.getElementById('saveTemplateBtn').addEventListener('click', saveTemplate);
document.getElementById('applyTemplateBtn').addEventListener('click', applyTemplate);
document.getElementById('selectProductBtn').addEventListener('click', selectProduct);
document.getElementById('selectProgramBtn').addEventListener('click', selectProgram);
document.getElementById('shelfSelect').addEventListener('change', (e) => loadShelfLayout(e.target.value));

refresh();
