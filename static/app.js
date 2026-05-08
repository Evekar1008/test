const $ = (id) => document.getElementById(id);

const SIGNAL_KEYS = {
  safety: ['EmergencyStopActive', 'GatesClosed', 'ScannerClear', 'Mode'],
  leanlift: ['CurrentShelf', 'AccessPoint', 'TrayPresent', 'TrayExtended', 'DoorClosed', 'AlarmActive', 'StatusMessage'],
  robot: ['Ready', 'Busy', 'Fault', 'AtHome', 'PartInGripper', 'StationComplete', 'ActiveTask', 'StatusMessage'],
  cnc: ['MachineReady', 'CycleRunning', 'CycleComplete', 'AlarmActive', 'PartPresent', 'SelectedProgram', 'LoadedProgram', 'ProgramSource', 'ProgramTransferState', 'StatusMessage'],
};

async function getState() {
  const response = await fetch('/api/state');
  return response.json();
}

async function postJson(url, payload = {}) {
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'Request failed');
  return data;
}

async function postForm(url, formData) {
  const response = await fetch(url, {
    method: 'POST',
    body: formData,
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'Request failed');
  return data;
}

function on(id, eventName, fn) {
  const el = $(id);
  if (el) el.addEventListener(eventName, fn);
}

function makeCell(value) {
  const td = document.createElement('td');
  td.textContent = value == null ? '-' : String(value);
  return td;
}

function renderKv(id, obj, keys) {
  const el = $(id);
  if (!el) return;
  el.innerHTML = '';
  const entries = keys ? keys.map((key) => [key, obj ? obj[key] : undefined]) : Object.entries(obj || {});
  entries.forEach(([key, value]) => {
    const dt = document.createElement('dt');
    const dd = document.createElement('dd');
    dt.textContent = key;
    dd.textContent = typeof value === 'object' && value !== null ? JSON.stringify(value) : String(value ?? '-');
    el.append(dt, dd);
  });
}

function formatTarget(target) {
  if (!target) return '-';
  return `Hylle ${target.shelf}, slot ${target.slot_no}, X ${target.x_mm}, Y ${target.y_mm}, Z ${target.z_mm}`;
}

function renderStatusBadges(state) {
  const safety = state.safety?.safety_ok ? 'OK' : 'TRIP';
  if ($('safetyBadge')) {
    $('safetyBadge').textContent = safety;
    $('safetyBadge').className = state.safety?.safety_ok ? 'ok' : 'bad';
  }
  if ($('modeBadge')) $('modeBadge').textContent = state.safety?.mode_key || '-';
  if ($('opcuaBadge')) {
    $('opcuaBadge').textContent = state.opcua?.running ? 'Kjorer' : 'Stoppet';
    $('opcuaBadge').className = state.opcua?.running ? 'ok' : 'warn';
  }
  if ($('activeShelfBadge')) $('activeShelfBadge').textContent = state.active_shelf || '-';
}

function renderMachineStatus(state) {
  const robotView = {
    ...state.robot,
    next_pick: formatTarget(state.robot?.next_pick),
    place_target: formatTarget(state.robot?.place_target),
  };
  renderKv('liftStatus', state.lift, ['connection', 'current_shelf', 'access_point', 'tray_present', 'tray_extended', 'door_closed', 'alarm_active', 'status_message']);
  renderKv('robotStatus', robotView, ['connection', 'ready', 'busy', 'fault', 'at_home', 'part_in_gripper', 'station_complete', 'active_task', 'next_pick', 'place_target', 'status_message']);
  renderKv('cncStatus', state.cnc, ['connection', 'machine_state', 'selected_program', 'loaded_program', 'program_source', 'program_transfer_state', 'program_valid', 'machine_ready', 'cycle_running', 'cycle_complete', 'alarm_active', 'part_present', 'part_counter']);
  renderKv('safetyStatus', state.safety, ['safety_ok', 'emergency_stop_active', 'gates_closed', 'scanner_clear', 'mode_key', 'last_trip']);
}

function renderJobMachineStatus(state) {
  renderKv('jobMachineStatus', {
    cnc_loaded_program: state.cnc?.loaded_program,
    program_source: state.cnc?.program_source,
    transfer: state.cnc?.program_transfer_state,
    lift_shelf: state.lift?.current_shelf,
    robot_task: state.robot?.active_task,
    next_pick: formatTarget(state.robot?.next_pick),
    finished_place: formatTarget(state.robot?.place_target),
  });
}

function renderProductionStatus(order) {
  renderKv('productionStatus', {
    ...order,
    next_pick: formatTarget(order?.next_pick),
  });
}

function renderEvents(state, targetId = 'eventTable', limit = 8) {
  const body = $(targetId);
  if (!body) return;
  body.innerHTML = '';
  (state.history || []).slice(0, limit).forEach((event) => {
    const tr = document.createElement('tr');
    tr.append(makeCell(event.ts), makeCell(event.category), makeCell(event.message));
    body.appendChild(tr);
  });
}

function renderInventory(state) {
  const inventory = state.inventory || {};
  const flat = {};
  Object.entries(inventory).forEach(([partType, statuses]) => {
    flat[partType] = Object.entries(statuses).map(([status, qty]) => `${status}:${qty}`).join('  ');
  });
  renderKv('inventoryList', flat);
}

function renderShelfSvg(layout) {
  const svg = $('shelfSvg');
  if (!svg) return;
  svg.innerHTML = '';
  const viewW = 1000;
  const viewH = 450;
  const pad = 24;
  const scale = Math.min((viewW - pad * 2) / layout.shelf_width_mm, (viewH - pad * 2) / layout.shelf_depth_mm);
  const shelfW = layout.shelf_width_mm * scale;
  const shelfH = layout.shelf_depth_mm * scale;

  const tray = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
  tray.setAttribute('x', pad);
  tray.setAttribute('y', pad);
  tray.setAttribute('width', shelfW);
  tray.setAttribute('height', shelfH);
  tray.setAttribute('rx', 4);
  tray.setAttribute('fill', '#f8fafc');
  tray.setAttribute('stroke', '#475569');
  tray.setAttribute('stroke-width', '2');
  svg.appendChild(tray);

  layout.slots.forEach((slot) => {
    const cx = pad + slot.x_mm * scale;
    const cy = pad + slot.y_mm * scale;
    const status = slot.status === 'in_process' ? 'wip' : slot.status;
    const color = layout.status_colors[status] || layout.status_colors[slot.status] || '#94a3b8';
    const diameter = Number(slot.diameter_mm || 80);
    const radius = slot.occupied ? Math.max(7, Math.min(72, (diameter * scale) / 2)) : 6;

    const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
    circle.setAttribute('cx', cx);
    circle.setAttribute('cy', cy);
    circle.setAttribute('r', radius);
    circle.setAttribute('fill', slot.occupied ? color : '#ffffff');
    circle.setAttribute('stroke', slot.occupied ? '#0f172a' : '#94a3b8');
    circle.setAttribute('stroke-width', slot.occupied ? '1.5' : '1');
    svg.appendChild(circle);

    const label = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    label.setAttribute('x', cx);
    label.setAttribute('y', cy + 3);
    label.setAttribute('text-anchor', 'middle');
    label.setAttribute('font-size', '11');
    label.textContent = String(slot.slot_no);
    svg.appendChild(label);
  });

  const info = $('shelfInfo');
  if (info) {
    info.textContent = `Hylle ${layout.shelf}: ${layout.shelf_width_mm} x ${layout.shelf_depth_mm} mm, ${layout.slots.length} lokasjoner`;
  }
}

function renderCoords(layout) {
  const body = $('coordsTable');
  if (!body) return;
  body.innerHTML = '';
  layout.slots.forEach((slot) => {
    const tr = document.createElement('tr');
    tr.append(
      makeCell(slot.slot_no),
      makeCell(slot.part_type_id || '-'),
      makeCell(slot.status),
      makeCell(slot.diameter_mm || '-'),
      makeCell(slot.x_mm),
      makeCell(slot.y_mm),
      makeCell(slot.z_mm),
    );
    body.appendChild(tr);
  });
}

async function loadShelfLayout(shelf) {
  const response = await fetch(`/api/leanlift/shelf-layout/${encodeURIComponent(shelf)}`);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'Unable to load shelf');
  renderShelfSvg(data);
  renderCoords(data);
  return data;
}

function fillSelect(id, items, valueFn, labelFn, selectedValue) {
  const el = $(id);
  if (!el) return;
  el.innerHTML = '';
  items.forEach((item) => {
    const option = document.createElement('option');
    option.value = valueFn(item);
    option.textContent = labelFn(item);
    if (selectedValue && option.value === selectedValue) option.selected = true;
    el.appendChild(option);
  });
}

function selectedPartType(state) {
  const partTypeId = $('prodPartType')?.value || state.part_types?.[0]?.part_type_id;
  return state.part_types.find((part) => part.part_type_id === partTypeId) || state.part_types[0];
}

function productForId(state, productId) {
  return state.products.find((product) => product.id === productId) || state.products[0];
}

function setupProgramControls(state) {
  fillSelect('programProduct', state.products, (p) => p.id, (p) => `${p.id} - ${p.name}`);

  function refreshProgramOptions() {
    const product = productForId(state, $('programProduct')?.value);
    fillSelect('programSelect', product.allowed_cnc_programs || [], (program) => program, (program) => program, state.cnc.selected_program);
  }

  refreshProgramOptions();
  on('programProduct', 'change', refreshProgramOptions);
  on('selectProgramBtn', 'click', async () => {
    try {
      const result = await postJson('/api/cnc/program/select', {
        product_id: $('programProduct').value,
        program: $('programSelect').value,
        operator: 'development',
      });
      renderKv('cncProgramStatus', result);
      await refreshCurrentPage();
    } catch (error) {
      alert(error.message);
    }
  });
  renderKv('cncProgramStatus', { selected_program: state.cnc.selected_program, program_valid: state.cnc.program_valid });
}

function setupProductionControls(state) {
  fillSelect('prodPartType', state.part_types, (p) => p.part_type_id, (p) => `${p.part_type_id} (${p.quantity_total})`);
  on('startProductionBtn', 'click', async () => {
    try {
      const result = await postJson('/api/production/start', {
        part_type_id: $('prodPartType').value,
        mode: $('prodMode').value,
        quantity: Number($('prodQty').value),
      });
      renderProductionStatus(result);
      await refreshCurrentPage();
    } catch (error) {
      alert(error.message);
    }
  });
  on('stopProductionBtn', 'click', async () => {
    await postJson('/api/production/stop', { reason: 'Stopped from dashboard' });
    await refreshCurrentPage();
  });
  on('simStartBtn', 'click', async () => {
    await postJson('/api/simulation/start');
    await refreshCurrentPage();
  });
  on('simPauseBtn', 'click', async () => {
    await postJson('/api/simulation/pause');
    await refreshCurrentPage();
  });
  on('simStepBtn', 'click', async () => {
    await postJson('/api/simulation/step');
    await refreshCurrentPage();
  });
}

function defaultProgramForPart(state, partTypeId) {
  const part = state.part_types.find((item) => item.part_type_id === partTypeId) || state.part_types[0];
  const product = productForId(state, part?.product_id);
  return product?.required_cnc_program || state.cnc?.selected_program || '';
}

function syncJobProgramFields(state) {
  const source = $('jobProgramSource')?.value || 'uploaded';
  ['jobUploadFields', 'jobPathFields', 'jobCncFields'].forEach((id) => $(id)?.classList.add('hidden'));
  if (source === 'uploaded') $('jobUploadFields')?.classList.remove('hidden');
  if (source === 'server_path') $('jobPathFields')?.classList.remove('hidden');
  if (source === 'cnc_existing') {
    $('jobCncFields')?.classList.remove('hidden');
    if ($('jobCncProgram')) $('jobProgramName').value = $('jobCncProgram').value || defaultProgramForPart(state, $('jobPartType')?.value);
  }
}

function renderJobs(state, selectedJobId) {
  const selected = selectedJobId || $('startJobSelect')?.value;
  fillSelect('startJobSelect', state.jobs || [], (job) => job.job_id, (job) => `${job.job_id} - ${job.job_name}`, selected);
  const body = $('jobsTable');
  if (body) {
    body.innerHTML = '';
    (state.jobs || []).forEach((job) => {
      const tr = document.createElement('tr');
      tr.append(
        makeCell(`${job.job_id} ${job.job_name}`),
        makeCell(`${job.part_type_id} ${job.part_name || ''}`),
        makeCell(job.program_name),
        makeCell(job.display_name || job.program_source_type),
        makeCell(job.fifo_enabled ? 'Ja' : 'Nei'),
        makeCell(job.status),
      );
      body.appendChild(tr);
    });
  }
}

async function initJobs() {
  const state = await getState();
  fillSelect('jobPartType', state.part_types, (p) => p.part_type_id, (p) => `${p.part_type_id} - ${p.name}`);
  fillSelect('jobCncProgram', state.cnc_existing_programs || [], (p) => p.program_name, (p) => `${p.program_name} - ${p.description}`);
  fillSelect('jobShelfSelect', state.shelves, (s) => s, (s) => `Hylle ${s}`, state.active_shelf);
  if ($('jobProgramName')) $('jobProgramName').value = defaultProgramForPart(state, $('jobPartType')?.value);
  syncJobProgramFields(state);
  renderJobs(state);
  renderProductionStatus(state.production_order);
  renderJobMachineStatus(state);
  await loadShelfLayout(state.active_shelf);

  on('jobPartType', 'change', () => {
    if ($('jobProgramName')) $('jobProgramName').value = defaultProgramForPart(state, $('jobPartType').value);
  });
  on('jobProgramSource', 'change', () => syncJobProgramFields(state));
  on('jobCncProgram', 'change', () => {
    if ($('jobProgramName')) $('jobProgramName').value = $('jobCncProgram').value;
  });
  on('jobShelfSelect', 'change', async () => loadShelfLayout($('jobShelfSelect').value));

  on('createJobBtn', 'click', async () => {
    try {
      const source = $('jobProgramSource').value;
      let program = {
        program_source_type: source,
        program_name: $('jobProgramName').value,
        source_path: $('jobProgramPath')?.value || '',
        original_filename: '',
      };

      if (source === 'uploaded') {
        const file = $('jobProgramFile')?.files?.[0];
        if (!file) throw new Error('Velg en NC-fil for opplasting');
        const formData = new FormData();
        formData.append('file', file);
        formData.append('program_name', $('jobProgramName').value);
        const upload = await postForm('/api/nc-programs/upload', formData);
        program = upload;
      } else if (source === 'cnc_existing') {
        program.program_name = $('jobCncProgram').value;
        program.source_path = '';
        program.original_filename = '';
      }

      const job = await postJson('/api/jobs', {
        job_name: $('jobName').value,
        part_type_id: $('jobPartType').value,
        fifo_enabled: $('jobFifo').checked,
        ...program,
      });
      renderKv('jobCreateStatus', job);
      const fresh = await getState();
      renderJobs(fresh, job.job_id);
    } catch (error) {
      alert(error.message);
    }
  });

  on('startJobBtn', 'click', async () => {
    try {
      const jobId = $('startJobSelect').value;
      if (!jobId) throw new Error('Opprett eller velg en jobb forst');
      const order = await postJson(`/api/jobs/${encodeURIComponent(jobId)}/start`, {
        mode: $('jobStartMode').value,
        quantity: Number($('jobStartQty').value),
      });
      renderProductionStatus(order);
      await refreshCurrentPage();
    } catch (error) {
      alert(error.message);
    }
  });
  on('stopProductionBtn', 'click', async () => {
    await postJson('/api/production/stop', { reason: 'Stopped from jobs page' });
    await refreshCurrentPage();
  });
  on('simStepBtn', 'click', async () => {
    await postJson('/api/simulation/step');
    await refreshCurrentPage();
  });
}

function renderDashboardState(state) {
  renderStatusBadges(state);
  renderMachineStatus(state);
  renderProductionStatus(state.production_order);
  renderEvents(state);
}

async function sendCommand(command) {
  const state = await postJson('/api/opcua/signal', { command });
  renderDashboardState(state);
  await loadShelfLayout(state.active_shelf);
  return state;
}

async function initDashboard() {
  const state = await getState();
  fillSelect('dashboardShelfSelect', state.shelves, (s) => s, (s) => `Hylle ${s}`, state.active_shelf);
  setupProgramControls(state);
  setupProductionControls(state);
  renderDashboardState(state);
  await loadShelfLayout(state.active_shelf);

  on('dashboardShelfSelect', 'change', async () => {
    await sendCommand(`GET_SHELF ${$('dashboardShelfSelect').value}`);
  });
  document.querySelectorAll('.sim-command').forEach((button) => {
    button.addEventListener('click', async () => sendCommand(button.dataset.command));
  });
  on('sendShelfCommandBtn', 'click', async () => {
    await sendCommand($('shelfCommandInput').value);
  });
}

async function initShelves() {
  const state = await getState();
  fillSelect('shelfSelect', state.shelves, (s) => s, (s) => `Hylle ${s}`, state.active_shelf);
  fillSelect('layoutPartType', state.part_types, (p) => p.part_type_id, (p) => p.part_type_id);
  fillSelect('manualPartType', state.part_types, (p) => p.part_type_id, (p) => p.part_type_id);
  if ($('shelfWidth')) $('shelfWidth').value = state.settings.shelf_width_mm;
  if ($('shelfDepth')) $('shelfDepth').value = state.settings.shelf_depth_mm;
  if ($('shelfHeight')) $('shelfHeight').value = state.settings.shelf_height_mm;
  await loadShelfLayout($('shelfSelect').value);

  on('shelfSelect', 'change', async () => loadShelfLayout($('shelfSelect').value));
  on('saveSettingsBtn', 'click', async () => {
    await postJson('/api/settings', {
      shelf_width_mm: Number($('shelfWidth').value),
      shelf_depth_mm: Number($('shelfDepth').value),
      shelf_height_mm: Number($('shelfHeight').value),
    });
    await loadShelfLayout($('shelfSelect').value);
  });
  on('generateLayoutBtn', 'click', async () => {
    try {
      const layout = await postJson('/api/shelf/configure-graphic', {
        shelf: $('shelfSelect').value,
        part_type_id: $('layoutPartType').value,
        cols: Number($('layoutCols').value),
        rows: Number($('layoutRows').value),
        z_mm: Number($('layoutZ').value),
      });
      renderShelfSvg(layout);
      renderCoords(layout);
      renderKv('shelfResult', { shelf: layout.shelf, slots: layout.slots.length });
    } catch (error) {
      alert(error.message);
    }
  });
  on('manualLoadBtn', 'click', async () => {
    await postJson('/api/shelf/slot/update', {
      shelf: $('shelfSelect').value,
      slot_no: Number($('manualSlotNo').value),
      occupied: true,
      status: $('manualStatus').value,
      part_type_id: $('manualPartType').value,
    });
    await loadShelfLayout($('shelfSelect').value);
  });
  on('manualUnloadBtn', 'click', async () => {
    await postJson('/api/shelf/slot/update', {
      shelf: $('shelfSelect').value,
      slot_no: Number($('manualSlotNo').value),
      occupied: false,
      status: 'empty',
      part_type_id: '',
    });
    await loadShelfLayout($('shelfSelect').value);
  });
  on('bulkStatusBtn', 'click', async () => {
    try {
      const result = await postJson('/api/shelf/status-bulk', {
        shelf: $('shelfSelect').value,
        status: $('bulkStatus').value,
        include_empty: Boolean($('bulkIncludeEmpty')?.checked),
      });
      renderKv('shelfResult', result);
      await loadShelfLayout($('shelfSelect').value);
    } catch (error) {
      alert(error.message);
    }
  });
}

async function initParts() {
  const state = await getState();
  renderInventory(state);
  const body = $('partsTable');
  if (body) {
    body.innerHTML = '';
    state.part_types.forEach((part) => {
      const tr = document.createElement('tr');
      tr.append(
        makeCell(part.part_type_id),
        makeCell(part.name),
        makeCell(part.product_id),
        makeCell(part.diameter_mm),
        makeCell(part.length_mm),
        makeCell(part.height_mm),
        makeCell(part.quantity_total),
      );
      body.appendChild(tr);
    });
  }
  on('savePartBtn', 'click', async () => {
    try {
      await postJson('/api/parts', {
        part_type_id: $('partTypeId').value,
        name: $('partName').value,
        product_id: $('partProductId').value,
        quantity_total: Number($('partQty').value),
        diameter_mm: Number($('partDia').value),
        length_mm: Number($('partLen').value),
        height_mm: Number($('partHeight').value),
      });
      await refreshCurrentPage();
    } catch (error) {
      alert(error.message);
    }
  });
}

function renderDynamicFields(containerId, paramNames) {
  const container = $(containerId);
  if (!container) return;
  container.innerHTML = '';
  (paramNames || []).forEach((name) => {
    const label = document.createElement('label');
    label.textContent = name;
    const input = document.createElement('input');
    input.dataset.name = name;
    input.placeholder = name;
    label.appendChild(input);
    container.appendChild(label);
  });
}

function readDynamicFields(containerId) {
  const out = {};
  const container = $(containerId);
  if (!container) return out;
  container.querySelectorAll('input').forEach((input) => {
    out[input.dataset.name] = input.value;
  });
  return out;
}

async function initCnc() {
  const state = await getState();
  renderMachineStatus(state);
  setupProgramControls(state);
  fillSelect('focasFunction', state.available_focas_functions, (fn) => fn, (fn) => fn);
  const paramMap = state.focas_function_params || {};
  renderDynamicFields('focasFields', paramMap[$('focasFunction')?.value]);
  on('focasFunction', 'change', () => renderDynamicFields('focasFields', paramMap[$('focasFunction').value]));
  on('runFocasBtn', 'click', async () => {
    try {
      const data = await postJson('/api/cnc/focas', {
        function_name: $('focasFunction').value,
        params: readDynamicFields('focasFields'),
      });
      $('focasResponse').textContent = JSON.stringify(data, null, 2);
      await refreshCurrentPage();
    } catch (error) {
      alert(error.message);
    }
  });
}

async function initLift() {
  const state = await getState();
  renderMachineStatus(state);
  fillSelect('liftFunction', state.available_leanlift_rest_commands, (fn) => fn, (fn) => fn);
  const paramMap = state.leanlift_command_params || {};
  renderDynamicFields('liftFields', paramMap[$('liftFunction')?.value]);
  on('liftFunction', 'change', () => renderDynamicFields('liftFields', paramMap[$('liftFunction').value]));
  on('runLiftBtn', 'click', async () => {
    try {
      const data = await postJson('/api/lift/command', {
        function_name: $('liftFunction').value,
        params: readDynamicFields('liftFields'),
      });
      $('liftResponse').textContent = JSON.stringify(data, null, 2);
      await refreshCurrentPage();
    } catch (error) {
      alert(error.message);
    }
  });
  on('quickGetShelfBtn', 'click', async () => {
    const data = await postJson('/api/lift/command', { function_name: 'get_shelf', params: { pm01_shelfNumber: $('quickShelfNo').value } });
    $('liftResponse').textContent = JSON.stringify(data, null, 2);
    await refreshCurrentPage();
  });
  on('quickTransferBtn', 'click', async () => {
    const data = await postJson('/api/lift/command', { function_name: 'shelf_transfer', params: { pm01_destinationAccessNumber: $('quickAccessPoint').value } });
    $('liftResponse').textContent = JSON.stringify(data, null, 2);
    await refreshCurrentPage();
  });
}

function parseSignalValue(value) {
  const text = String(value).trim();
  if (['true', 'false'].includes(text.toLowerCase())) return text.toLowerCase() === 'true';
  if (text !== '' && !Number.isNaN(Number(text))) return Number(text);
  return text;
}

function fillSignalKeys() {
  const group = $('signalGroup')?.value || 'safety';
  fillSelect('signalKey', SIGNAL_KEYS[group] || [], (key) => key, (key) => key);
}

async function initOpcua() {
  const state = await getState();
  renderKv('opcuaStatus', state.opcua);
  renderKv('opcuaLiveStatus', { endpoint: state.opcua.endpoint, namespace: state.opcua.namespace, nodes: state.opcua.node_count });
  renderMachineStatus(state);
  fillSignalKeys();
  on('signalGroup', 'change', fillSignalKeys);
  on('startOpcuaBtn', 'click', async () => {
    const data = await postJson('/api/opcua/start');
    renderKv('opcuaStatus', data);
  });
  on('sendOpcuaCommandBtn', 'click', async () => {
    const data = await postJson('/api/opcua/signal', { command: $('opcuaCommandInput').value });
    $('opcuaCommandResponse').textContent = JSON.stringify(data.production_order, null, 2);
    renderMachineStatus(data);
  });
  on('sendSignalBtn', 'click', async () => {
    const data = await postJson('/api/opcua/signal', {
      group: $('signalGroup').value,
      key: $('signalKey').value,
      value: parseSignalValue($('signalValue').value),
    });
    renderMachineStatus(data);
    renderKv('opcuaStatus', data.opcua);
  });
}

async function initStats() {
  const state = await getState();
  renderKv('statsList', state.stats);
  renderProductionStatus(state.production_order);
  renderEvents(state, 'historyTable', 150);
}

async function initDiagnostics() {
  async function loadDiagnostics() {
    const response = await fetch('/api/diagnostics');
    const data = await response.json();
    const body = $('diagTable');
    if (!body) return;
    body.innerHTML = '';
    data.forEach((item) => {
      const tr = document.createElement('tr');
      const pre = document.createElement('pre');
      pre.textContent = JSON.stringify(item.raw);
      tr.append(makeCell(item.ts), makeCell(item.channel), makeCell(item.direction));
      const payload = document.createElement('td');
      payload.appendChild(pre);
      tr.appendChild(payload);
      body.appendChild(tr);
    });
  }
  on('refreshDiagnosticsBtn', 'click', loadDiagnostics);
  await loadDiagnostics();
}

async function refreshCurrentPage() {
  const page = document.body.dataset.page;
  const state = await getState();
  if (page === 'dashboard') {
    renderDashboardState(state);
    await loadShelfLayout(state.active_shelf);
  }
  if (page === 'opcua') {
    renderKv('opcuaStatus', state.opcua);
    renderMachineStatus(state);
  }
  if (page === 'parts') {
    renderInventory(state);
  }
  if (page === 'jobs') {
    renderJobs(state);
    renderProductionStatus(state.production_order);
    renderJobMachineStatus(state);
    if ($('jobShelfSelect')) $('jobShelfSelect').value = state.active_shelf;
    await loadShelfLayout(state.active_shelf);
  }
  if (page === 'cnc' || page === 'lift') {
    renderMachineStatus(state);
  }
}

(async function boot() {
  const page = document.body.dataset.page;
  if (page === 'dashboard') await initDashboard();
  if (page === 'shelves') await initShelves();
  if (page === 'parts') await initParts();
  if (page === 'jobs') await initJobs();
  if (page === 'cnc') await initCnc();
  if (page === 'lift') await initLift();
  if (page === 'opcua') await initOpcua();
  if (page === 'stats') await initStats();
  if (page === 'diagnostics') await initDiagnostics();

  if (page === 'dashboard' || page === 'opcua' || page === 'jobs') {
    setInterval(refreshCurrentPage, 2500);
  }
})().catch((error) => {
  console.error(error);
  alert(error.message);
});
