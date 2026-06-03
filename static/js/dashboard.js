// ==============================================================================
// Tujuan       : Dashboard frontend - WebSocket, MJPEG stream, gas class, captures
// Perubahan    : Layout sidebar, fused probability chart, staleness counter, chat chips
// Dependensi   : Chart.js, html2canvas, jsPDF (CDN)
// ==============================================================================

// --- 1. View Switching (Replaces Tabs) ---
function switchView(viewId) {
  // Hide all view sections
  document.querySelectorAll('.view-section').forEach(el => el.classList.remove('active'));

  // Reset desktop sidebar nav links
  document.querySelectorAll('.nav-link').forEach(el => {
    el.classList.remove('bg-zinc-900', 'text-indigo-400', 'border', 'border-indigo-500/30', 'font-medium');
    el.classList.add('text-zinc-400', 'hover:bg-zinc-900');
  });
  const activeNav = document.getElementById(`nav-${viewId}`);
  if (activeNav) {
    activeNav.classList.add('bg-zinc-900', 'text-indigo-400', 'border', 'border-indigo-500/30', 'font-medium');
    activeNav.classList.remove('text-zinc-400', 'hover:bg-zinc-900');
  }

  // Sync mobile bottom tab bar
  document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
  const activeTab = document.getElementById(`tab-${viewId}`);
  if (activeTab) activeTab.classList.add('active');

  // Show the selected view
  const viewEl = document.getElementById(`view-${viewId}`);
  if (viewEl) viewEl.classList.add('active');

  // Scroll content back to top when switching views
  const scroller = document.getElementById('main-scroll');
  if (scroller) scroller.scrollTo({ top: 0, behavior: 'smooth' });

  if (viewId === 'settings') { loadCameras(); loadThresholds(); }
  if (viewId === 'events') { filterLogs(); }
}

// ── Theme toggle ──────────────────────────────────────────
function toggleTheme() {
  const isDark = document.documentElement.classList.toggle('dark');
  localStorage.setItem('theme', isDark ? 'dark' : 'light');
  updateThemeUI();
}

function updateThemeUI() {
  const isDark = document.documentElement.classList.contains('dark');

  // Mobile header icon
  const mobIcon = document.getElementById('theme-icon-mobile');
  if (mobIcon) mobIcon.className = isDark ? 'ph ph-moon text-lg' : 'ph ph-sun text-lg';

  // Desktop sidebar icon + label
  const deskIcon = document.getElementById('theme-icon-desktop');
  if (deskIcon) deskIcon.className = isDark ? 'ph ph-moon text-sm' : 'ph ph-sun text-sm';
}

// Apply correct icon immediately on page load
updateThemeUI();

// --- 2. Chart.js Init (Fused Probability) ---
let currentThresholds = { prob_aman: 30, prob_waspada: 70 };

const thresholdZonePlugin = {
  id: 'thresholdZones',
  beforeDraw(chart) {
    if (!chart.scales?.y || !chart.chartArea) return;
    const ctx = chart.ctx;
    const { left, right } = chart.chartArea;
    const y = chart.scales.y;
    const yAmn  = y.getPixelForValue(currentThresholds.prob_aman);
    const yWrn  = y.getPixelForValue(currentThresholds.prob_waspada);
    const yTop  = y.getPixelForValue(100);
    const width = right - left;
    ctx.save();
    ctx.fillStyle = 'rgba(239,68,68,0.06)';
    ctx.fillRect(left, yTop, width, yWrn - yTop);
    ctx.fillStyle = 'rgba(245,158,11,0.06)';
    ctx.fillRect(left, yWrn, width, yAmn - yWrn);
    ctx.setLineDash([5, 4]);
    ctx.lineWidth = 1.2;
    ctx.strokeStyle = 'rgba(245,158,11,0.5)';
    ctx.beginPath(); ctx.moveTo(left, yAmn); ctx.lineTo(right, yAmn); ctx.stroke();
    ctx.strokeStyle = 'rgba(239,68,68,0.5)';
    ctx.beginPath(); ctx.moveTo(left, yWrn); ctx.lineTo(right, yWrn); ctx.stroke();
    ctx.setLineDash([]);
    ctx.restore();
  }
};

const fusionCtx = document.getElementById('fusionChart').getContext('2d');
Chart.defaults.color = '#a1a1aa';
Chart.defaults.font.family = 'ui-sans-serif, system-ui, sans-serif';

const fusionChart = new Chart(fusionCtx, {
  type: 'line',
  data: {
    labels: [],
    datasets: [{
      label: 'Probabilitas Bahaya (Fusi) %',
      borderColor: '#8b5cf6',
      backgroundColor: 'rgba(139, 92, 246, 0.15)',
      borderWidth: 2,
      tension: 0.4,
      fill: true,
      pointRadius: 1,
      pointHoverRadius: 4,
      data: []
    }]
  },
  plugins: [thresholdZonePlugin],
  options: {
    responsive: true,
    maintainAspectRatio: false,
    animation: { duration: 300 },
    interaction: { mode: 'index', intersect: false },
    plugins: {
      legend: { display: false },
      tooltip: { backgroundColor: '#18181b', titleColor: '#e4e4e7', bodyColor: '#d4d4d8' }
    },
    scales: {
      x: { grid: { color: 'rgba(82,82,91,0.2)' }, ticks: { maxTicksLimit: 8 } },
      y: { min: 0, max: 100, grid: { color: 'rgba(82,82,91,0.3)' }, ticks: { stepSize: 20 } }
    }
  }
});

// --- 3. DOM References ---
const ui = {
  wsStatus: document.getElementById('ws-status'),
  wsDot: document.getElementById('ws-dot'),
  sensorStatus: document.getElementById('sensor-status'),
  sensorDot: document.getElementById('sensor-dot'),
  statusBar: document.getElementById('global-status-bar'),
  globalStatus: document.getElementById('global-status'),
  kpiProb: document.getElementById('kpi-prob'),
  kpiCams: document.getElementById('kpi-cams'),
  kpiUpdate: document.getElementById('kpi-update'),
  stalenessInd: document.getElementById('staleness-indicator'),
  clock: document.getElementById('clock'),
  cameraTime: document.getElementById('camera-timestamp'),
  cameraLabel: document.getElementById('camera-label'),
  cameraFrame: document.getElementById('camera-frame'),
  cameraPlaceholder: document.getElementById('camera-placeholder'),
  cameraSelect: document.getElementById('camera-select'),
  camThumbnails: document.getElementById('cam-thumbnails'),
  overlayYolo: document.getElementById('overlay-yolo'),
  overlaySensor: document.getElementById('overlay-sensor'),
  overlayFusion: document.getElementById('overlay-fusion'),
  logTable: document.getElementById('log-table-body'),
  noLog: document.getElementById('no-log-row'),
  logSearch: document.getElementById('log-search'),
  logFilter: document.getElementById('log-filter'),
  sensors: {
    mq135: document.getElementById('sensor-mq135'), mq2: document.getElementById('sensor-mq2'),
    mq3: document.getElementById('sensor-mq3'), mq4: document.getElementById('sensor-mq4'),
    mq5: document.getElementById('sensor-mq5'), mq7: document.getElementById('sensor-mq7-detail')
  }
};

let selectedCameraId = null;
let lastUpdate = Date.now();


// ============================================================================
// IR Flame Sensor (ESP32 GPIO27) — toggle visual saat api terdeteksi
// ============================================================================
function updateFlameStatus(detected) {
  lastFlameDetected = detected;
  const card = document.getElementById('flame-card');
  const icon = document.getElementById('flame-icon');
  const status = document.getElementById('flame-status');
  const dot = document.getElementById('flame-dot');
  if (!card || !icon || !status || !dot) return;

  if (detected) {
    card.className = 'flex items-center justify-between p-3 rounded-lg border bg-red-500/15 border-red-500/60 transition-all animate-pulse';
    icon.className = 'w-10 h-10 rounded-full flex items-center justify-center bg-red-500/30 text-red-400 text-xl transition-all';
    icon.innerHTML = '<i class="ph-fill ph-flame"></i>';
    status.className = 'text-sm font-bold text-red-300';
    status.textContent = '🔥 API TERDETEKSI';
    dot.className = 'w-3 h-3 rounded-full bg-red-500 animate-pulse';
  } else {
    card.className = 'flex items-center justify-between p-3 rounded-lg border bg-zinc-900/50 border-zinc-800 transition-all';
    icon.className = 'w-10 h-10 rounded-full flex items-center justify-center bg-zinc-800 text-zinc-500 text-xl transition-all';
    icon.innerHTML = '<i class="ph ph-flame-light"></i>';
    status.className = 'text-sm font-bold text-zinc-300';
    status.textContent = 'TIDAK ADA API';
    dot.className = 'w-3 h-3 rounded-full bg-zinc-600';
  }
}
let allLogs = [];
let chatHistory = [];
let lastFlameDetected = false;   // #2 track flame state for sensor context
let lastLstmScore = null;        // #3 track LSTM score for sensor context
let lastFireStatus = 'Aman';     // #6 fire alert: previous status
let fireAlertInjected = false;   // #6 prevent duplicate alert per event
const CHAT_HISTORY_KEY = 'k3_chat_history'; // #4 localStorage key

// Clock & staleness
setInterval(() => {
  const now = new Date();
  const timeStr = now.toLocaleTimeString('id-ID', { hour12: false });
  const days = ['Min', 'Sen', 'Sel', 'Rab', 'Kam', 'Jum', 'Sab'];
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'Mei', 'Jun', 'Jul', 'Agu', 'Sep', 'Okt', 'Nov', 'Des'];
  const dateStr = `${days[now.getDay()]}, ${now.getDate()} ${months[now.getMonth()]} ${now.getFullYear()}`;
  if (ui.clock) ui.clock.textContent = timeStr;
  if (ui.cameraTime) ui.cameraTime.textContent = timeStr;
  const dateEl = document.getElementById('current-date');
  if (dateEl) dateEl.textContent = dateStr;

  // Staleness Counter
  const diff = Math.floor((Date.now() - lastUpdate) / 1000);
  if (ui.kpiUpdate) ui.kpiUpdate.textContent = `${diff}s`;
  const modal = document.getElementById('disconnect-modal');
  const updateBar = document.getElementById('kpi-update-bar');
  const updateIcon = document.getElementById('kpi-update-icon');
  const freshPct = Math.max(0, 100 - (diff / 10) * 100);
  if (diff > 10) {
    if (ui.kpiUpdate) ui.kpiUpdate.className = 'text-3xl font-black text-red-500';
    if (updateBar)  { updateBar.className = 'h-full rounded-full bg-red-500 transition-all duration-1000'; updateBar.style.width = '0%'; }
    if (updateIcon) updateIcon.className = 'ph ph-warning text-red-400 text-xl';
    modal.style.display = 'flex';
  } else {
    const barColor = diff > 6 ? 'bg-yellow-500' : 'bg-emerald-500';
    const iconColor = diff > 6 ? 'text-yellow-400' : 'text-zinc-400';
    if (ui.kpiUpdate) ui.kpiUpdate.className = 'text-3xl font-black';
    if (updateBar)  { updateBar.className = `h-full rounded-full ${barColor} transition-all duration-1000`; updateBar.style.width = freshPct + '%'; }
    if (updateIcon) updateIcon.className = `ph ph-clock ${iconColor} text-xl`;
    modal.style.display = 'none';
  }
}, 1000);

function switchCamera(camId) {
  selectedCameraId = camId || null;
  if (camId) {
    ui.cameraFrame.src = `/stream/${camId}`;
    ui.cameraFrame.classList.remove('hidden');
    ui.cameraPlaceholder.classList.add('hidden');
  } else {
    ui.cameraFrame.classList.add('hidden');
    ui.cameraFrame.src = '';
    ui.cameraPlaceholder.classList.remove('hidden');
  }
}

const _camSizes = { s: '16rem', m: '26rem', l: '40rem' };
function setCameraSize(size) {
  const vp = document.getElementById('camera-viewport');
  if (vp) vp.style.minHeight = _camSizes[size] || '16rem';
  ['s', 'm', 'l'].forEach(k => {
    const btn = document.getElementById(`cam-size-${k}`);
    if (!btn) return;
    if (k === size) {
      btn.className = 'px-2.5 py-1.5 bg-indigo-600 text-white transition cursor-pointer';
    } else {
      btn.className = 'px-2.5 py-1.5 bg-zinc-800 text-zinc-400 hover:bg-zinc-700 transition cursor-pointer';
    }
  });
}

// --- 4. Status & Gas Helpers ---
function getStatusTheme(s) {
  if (s === 'Aman') return { bg: 'status-bar-aman', text: 'text-emerald-400', kpiColor: 'text-emerald-400', kpiBorder: 'border-l-emerald-500' };
  if (s === 'Waspada') return { bg: 'status-bar-waspada', text: 'text-yellow-400', kpiColor: 'text-yellow-400', kpiBorder: 'border-l-yellow-500' };
  if (s === 'Bahaya') return { bg: 'status-bar-bahaya', text: 'text-red-500', kpiColor: 'text-red-500', kpiBorder: 'border-l-red-500' };
  return { bg: 'bg-zinc-900', text: 'text-zinc-400', kpiColor: 'text-zinc-400', kpiBorder: 'border-l-zinc-500' };
}

const gasColors = {
  'Clean': 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30',
  'Smoke': 'bg-orange-500/20 text-orange-400 border-orange-500/30',
  'Gasoline': 'bg-red-500/20 text-red-400 border-red-500/30',
  'Mixture': 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30'
};

function updateGasBadge(detected) {
  const c = gasColors[detected] || gasColors['Clean'];
  document.getElementById('gas-badge-container').innerHTML = `<span class="inline-block px-2 py-0.5 text-xs font-bold rounded border ${c}">${detected}</span>`;
}

function updateClassBars(classProbs) {
  ['Clean', 'Smoke', 'Gasoline', 'Mixture'].forEach(cls => {
    const val = classProbs[cls] || 0;
    document.getElementById(`cls-${cls.toLowerCase()}`).textContent = val.toFixed(1) + '%';
    document.getElementById(`bar-${cls.toLowerCase()}`).style.width = val + '%';
  });
}

// ── MQ Sensor threshold coloring ──────────────────────────
const MQ_THRESHOLDS = {
  mq135: { warn: 400, danger: 1000, max: 2000 },
  mq2:   { warn: 200, danger: 500,  max: 1000 },
  mq7:   { warn: 35,  danger: 100,  max: 200  },
  mq4:   { warn: 200, danger: 500,  max: 1000 },
  mq5:   { warn: 200, danger: 500,  max: 1000 },
  mq3:   { warn: 50,  danger: 200,  max: 400  },
};

function updateMQSensor(id, value) {
  const th = MQ_THRESHOLDS[id];
  const elVal  = document.getElementById(`sensor-${id}`);
  const elBar  = document.getElementById(`${id}-bar`);
  const elStat = document.getElementById(`${id}-status`);
  if (!th || !elVal) return;
  const pct = Math.min((value / th.max) * 100, 100);
  let color, barColor, label, bgColor;
  if (value >= th.danger)     { color = 'text-red-400';     barColor = 'bg-red-500';     label = 'BAHAYA';  bgColor = 'bg-red-500/20'; }
  else if (value >= th.warn)  { color = 'text-yellow-400';  barColor = 'bg-yellow-500';  label = 'WASPADA'; bgColor = 'bg-yellow-500/20'; }
  else                        { color = 'text-emerald-400'; barColor = 'bg-emerald-500'; label = 'AMAN';    bgColor = 'bg-emerald-500/20'; }
  elVal.className = `font-mono text-sm font-bold ${color}`;
  if (elBar)  { elBar.className = `h-full rounded-full ${barColor} transition-all duration-500`; elBar.style.width = pct + '%'; }
  if (elStat) { elStat.className = `text-[9px] font-bold px-1.5 py-0.5 rounded ${bgColor} ${color}`; elStat.textContent = label; }
}

function updateTempDisplay(temp) {
  const bar     = document.getElementById('temp-bar');
  const comfort = document.getElementById('temp-comfort');
  const el      = document.getElementById('sensor-temp');
  if (!el) return;
  const pct = Math.min(Math.max((temp / 50) * 100, 0), 100);
  let color, barColor, label;
  if (temp < 18)      { color = 'text-blue-400';    barColor = 'bg-blue-400';    label = 'Dingin'; }
  else if (temp <= 26){ color = 'text-emerald-400'; barColor = 'bg-emerald-500'; label = 'Nyaman ✓'; }
  else if (temp <= 35){ color = 'text-yellow-400';  barColor = 'bg-yellow-500';  label = 'Panas'; }
  else                { color = 'text-red-400';      barColor = 'bg-red-500';     label = 'Sangat Panas!'; }
  el.className = `text-2xl font-mono font-bold mt-1 ${color} transition-colors duration-300`;
  if (bar)     { bar.className = `h-full rounded-full ${barColor} transition-all duration-500`; bar.style.width = pct + '%'; }
  if (comfort) comfort.textContent = label;
}

function updateHumidDisplay(hum) {
  const bar     = document.getElementById('humid-bar');
  const comfort = document.getElementById('humid-comfort');
  const el      = document.getElementById('sensor-humid');
  if (!el) return;
  let color, barColor, label;
  if (hum < 30)      { color = 'text-yellow-400'; barColor = 'bg-yellow-500'; label = 'Terlalu Kering'; }
  else if (hum <= 65){ color = 'text-blue-400';   barColor = 'bg-blue-500';   label = 'Nyaman ✓'; }
  else               { color = 'text-blue-500';   barColor = 'bg-blue-600';   label = 'Terlalu Lembap'; }
  el.className = `text-2xl font-mono font-bold mt-1 ${color} transition-colors duration-300`;
  if (bar)     { bar.className = `h-full rounded-full ${barColor} transition-all duration-500`; bar.style.width = Math.min(hum, 100) + '%'; }
  if (comfort) comfort.textContent = label;
}

function updateKPIProb(prob, status) {
  const card   = document.getElementById('kpi-prob-card');
  const bar    = document.getElementById('kpi-prob-bar');
  const icon   = document.getElementById('kpi-prob-icon');
  const label  = document.getElementById('kpi-prob-label');
  const probEl = ui.kpiProb;
  let borderColor, barColor, iconClass, iconColor, labelText, labelColor, textColor;
  if (status === 'Bahaya') {
    borderColor = '#ef4444'; barColor = 'bg-red-500';     iconClass = 'ph ph-warning';        iconColor = 'text-red-400';
    labelText = 'BAHAYA — Tindakan segera diperlukan!';   labelColor = 'text-red-400 font-bold'; textColor = 'text-red-400';
  } else if (status === 'Waspada') {
    borderColor = '#f59e0b'; barColor = 'bg-yellow-500';  iconClass = 'ph ph-warning-circle'; iconColor = 'text-yellow-400';
    labelText = 'Waspada — Pantau kondisi ruangan';       labelColor = 'text-yellow-500';       textColor = 'text-yellow-400';
  } else {
    borderColor = '#10b981'; barColor = 'bg-emerald-500'; iconClass = 'ph ph-shield-check';   iconColor = 'text-emerald-400';
    labelText = 'Kondisi Normal';                         labelColor = 'text-emerald-600';      textColor = 'text-emerald-400';
  }
  if (card)   card.style.borderLeftColor = borderColor;
  if (bar)    { bar.className = `h-full rounded-full ${barColor} transition-all duration-500`; bar.style.width = prob + '%'; }
  if (icon)   icon.className = `${iconClass} ${iconColor} text-xl`;
  if (label)  { label.textContent = labelText; label.className = `text-[10px] mt-1.5 font-medium ${labelColor}`; }
  if (probEl) probEl.className = `text-3xl font-black ${textColor} transition-colors duration-500`;
}

function appendLog(time, status, message, yolo = '-', sensor = '-', fused = '-') {
  if (ui.noLog) { ui.noLog.remove(); ui.noLog = null; }
  const tr = document.createElement('tr');
  tr.className = 'hover:bg-zinc-800/50 transition';
  let badge = '';
  if (status === 'Waspada') badge = `<span class="px-2 py-0.5 text-[10px] rounded border font-bold bg-yellow-500/20 text-yellow-400 border-yellow-500/30">WASPADA</span>`;
  else if (status === 'Bahaya') badge = `<span class="px-2 py-0.5 text-[10px] rounded border font-bold bg-red-500/20 text-red-400 border-red-500/30">BAHAYA</span>`;
  else badge = `<span class="px-2 py-0.5 text-[10px] rounded border font-bold bg-emerald-500/20 text-emerald-400 border-emerald-500/30">AMAN</span>`;

  const scoreCell = (val, color) =>
    `<td class="px-4 py-3 text-center"><span class="font-mono text-xs font-bold ${color}">${val}</span></td>`;

  tr.innerHTML =
    `<td class="px-4 py-3 text-zinc-400 font-mono text-xs whitespace-nowrap">${time}</td>` +
    `<td class="px-4 py-3 whitespace-nowrap">${badge}</td>` +
    `<td class="px-4 py-3 text-zinc-300 text-sm">${message}</td>` +
    scoreCell(yolo !== '-' ? yolo + '%' : '-', 'text-orange-400') +
    scoreCell(sensor !== '-' ? sensor + '%' : '-', 'text-blue-400') +
    scoreCell(fused !== '-' ? fused + '%' : '-', 'text-indigo-400');

  ui.logTable.prepend(tr);
  allLogs.unshift({ time, status, message, yolo, sensor, fused });
  if (allLogs.length > 50) { ui.logTable.lastElementChild.remove(); allLogs.pop(); }
  filterLogs();
}

// --- 5. WebSocket + Heartbeat ---
let ws;
function connectWebSocket() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  ws = new WebSocket(`${protocol}//${window.location.host}/ws/monitor`);

  ws.onopen = () => {
    ui.wsStatus.textContent = 'TERHUBUNG';
    ui.wsStatus.className = 'text-xs px-2 py-0.5 rounded bg-emerald-500/20 border border-emerald-500/50 text-emerald-400 font-bold';
    ui.wsDot.className = 'w-2 h-2 rounded-full bg-emerald-500 animate-pulse';
  };

  ws.onmessage = (event) => {
    lastUpdate = Date.now(); // Reset staleness
    const data = JSON.parse(event.data);

    // Ignore keepalive pings from server
    if (data.type === 'ping') return;

    const cameras = data.cameras || [];

    ui.kpiCams.textContent = `${cameras.length} Online`;
    updateCameraSelector(cameras);

    let cam = cameras.find(c => c.cam_id === selectedCameraId) || cameras[0];
    if (!cam) return;

    // Sensor connection badge — blue=ok, yellow=stale, grey=no data
    const hasSensor = cam.sensor_raw !== null && cam.sensor_raw !== undefined;
    const sensorStale = cam.sensor_stale === true;
    if (ui.sensorStatus) {
      if (hasSensor && !sensorStale) {
        ui.sensorStatus.textContent = 'ESP32 OK';
        ui.sensorStatus.className = 'hidden md:inline text-xs px-2 py-0.5 rounded bg-blue-500/20 border border-blue-500/50 text-blue-400 font-bold';
      } else if (sensorStale) {
        ui.sensorStatus.textContent = '⚠ SENSOR OFFLINE';
        ui.sensorStatus.className = 'hidden md:inline text-xs px-2 py-0.5 rounded bg-yellow-500/20 border border-yellow-500/50 text-yellow-400 font-bold';
      } else {
        ui.sensorStatus.textContent = 'SENSOR --';
        ui.sensorStatus.className = 'hidden md:inline text-xs px-2 py-0.5 rounded bg-zinc-800/50 border border-zinc-700 text-zinc-400 font-bold';
      }
    }
    if (ui.sensorDot) {
      if (hasSensor && !sensorStale) {
        ui.sensorDot.className = 'hidden md:inline-block w-2 h-2 rounded-full bg-blue-500 animate-pulse shrink-0';
      } else if (sensorStale) {
        ui.sensorDot.className = 'hidden md:inline-block w-2 h-2 rounded-full bg-yellow-500 shrink-0';
      } else {
        ui.sensorDot.className = 'hidden md:inline-block w-2 h-2 rounded-full bg-zinc-500 shrink-0';
      }
    }

    if (!selectedCameraId && cam) {
      selectedCameraId = cam.cam_id;
      ui.cameraSelect.value = cam.cam_id;
      switchCamera(cam.cam_id);
    }

    // Update status bar
    const theme = getStatusTheme(cam.status);
    ui.statusBar.className = `${theme.bg} w-full h-14 flex items-center justify-between px-6 transition-all duration-500`;
    ui.globalStatus.textContent = `STATUS: ${cam.status.toUpperCase()}`;

    ui.kpiProb.textContent = cam.prob_akhir + '%';
    updateKPIProb(cam.prob_akhir, cam.status);
    ui.overlayYolo.textContent = cam.prob_yolo + '%';
    ui.overlaySensor.textContent = cam.prob_sensor + '%';
    ui.overlayFusion.textContent = cam.prob_akhir + '%';

    // AI Model Scores — direct getElementById, same pattern as updateClassBars
    const _aiYolo  = parseFloat(cam.prob_yolo  ?? 0).toFixed(1);
    const _aiXgb   = parseFloat(cam.prob_sensor ?? 0).toFixed(1);
    const _aiFuse  = parseFloat(cam.prob_akhir  ?? 0).toFixed(1);
    document.getElementById('ai-yolo-val').textContent     = _aiYolo + '%';
    document.getElementById('ai-yolo-bar').style.width     = _aiYolo + '%';
    document.getElementById('ai-xgboost-val').textContent  = _aiXgb  + '%';
    document.getElementById('ai-xgboost-bar').style.width  = _aiXgb  + '%';
    document.getElementById('ai-fusion-val').textContent   = _aiFuse + '%';
    const _fusBar = document.getElementById('ai-fusion-bar');
    if (_fusBar) _fusBar.style.width = _aiFuse + '%';

    // #6 Proactive fire alert — inject once per Bahaya event
    if (cam.status === 'Bahaya' && lastFireStatus !== 'Bahaya' && !fireAlertInjected) {
      fireAlertInjected = true;
      injectFireAlert(cam.cam_name || cam.cam_id, cam.prob_akhir, cam.detected_class || 'Api/Asap');
    }
    if (cam.status !== 'Bahaya') fireAlertInjected = false;
    lastFireStatus = cam.status;

    updateGasBadge(cam.detected_class || 'Clean');
    if (cam.class_probs) updateClassBars(cam.class_probs);

    ui.cameraSelect.value = selectedCameraId;
    ui.cameraLabel.textContent = `REC • ${cam.cam_name || cam.cam_id}`;

    // Sensors
    const temp = cam.temperature !== undefined ? cam.temperature : data.temperature;
    const hum = cam.humidity !== undefined ? cam.humidity : data.humidity;
    const tempVal = temp ?? 0;
    const humVal  = hum  ?? 0;
    document.getElementById('sensor-temp').textContent  = tempVal.toFixed(1) + '°C';
    document.getElementById('sensor-humid').textContent = humVal.toFixed(1)  + '%';
    updateTempDisplay(tempVal);
    updateHumidDisplay(humVal);

    const ppm = cam.sensor_ppm || {};
    const mq135v = ppm.mq135?.ppm || 0; ui.sensors.mq135.textContent = mq135v.toFixed(1); updateMQSensor('mq135', mq135v);
    const mq2v   = ppm.mq2?.ppm   || 0; ui.sensors.mq2.textContent   = mq2v.toFixed(1);   updateMQSensor('mq2',   mq2v);
    const mq7v   = ppm.mq7?.ppm   || 0; ui.sensors.mq7.textContent   = mq7v.toFixed(1);   updateMQSensor('mq7',   mq7v);
    const mq4v   = ppm.mq4?.ppm   || 0; ui.sensors.mq4.textContent   = mq4v.toFixed(1);   updateMQSensor('mq4',   mq4v);
    const mq5v   = ppm.mq5?.ppm   || 0; ui.sensors.mq5.textContent   = mq5v.toFixed(1);   updateMQSensor('mq5',   mq5v);
    const mq3v   = ppm.mq3?.ppm   || 0; ui.sensors.mq3.textContent   = mq3v.toFixed(1);   updateMQSensor('mq3',   mq3v);

    // IR Flame Sensor — sinyal binary kritis dari ESP32 GPIO27
    updateFlameStatus(cam.flame_detected === true);

    // Fused Chart
    fusionChart.data.labels.push(data.timestamp);
    fusionChart.data.datasets[0].data.push(cam.prob_akhir);
    if (fusionChart.data.labels.length > 30) {
      fusionChart.data.labels.shift();
      fusionChart.data.datasets[0].data.shift();
    }
    fusionChart.update();

    // Logs & Captures
    cameras.forEach(c => {
      if (c.status !== 'Aman') appendLog(data.timestamp, c.status, `${c.cam_name}: ${c.detected_class}`, c.prob_yolo, c.prob_sensor, c.prob_akhir);
      if (c.capture) addCaptureEvent(c.capture, c.status, c.detected_class, data.timestamp);
    });


  };

  ws.onclose = () => {
    ui.wsStatus.textContent = 'TERPUTUS';
    ui.wsStatus.className = 'text-xs px-2 py-0.5 rounded bg-red-500/20 border border-red-500/50 text-red-400 font-bold';
    ui.wsDot.className = 'w-2 h-2 rounded-full bg-red-500';
    if (ui.sensorStatus) {
      ui.sensorStatus.textContent = 'SENSOR --';
      ui.sensorStatus.className = 'text-xs px-2 py-0.5 rounded bg-zinc-800/50 border border-zinc-700 text-zinc-400 font-bold';
    }
    if (ui.sensorDot) {
      ui.sensorDot.className = 'w-2 h-2 rounded-full bg-zinc-500';
    }
    setTimeout(connectWebSocket, 3000);
  };
}

function updateCameraSelector(cameras) {
  const sel = ui.cameraSelect;

  // Guard: only rebuild thumbnails if the camera set actually changed
  const newFingerprint = cameras.map(c => c.cam_id).sort().join(',');
  if (window._camFingerprint !== newFingerprint) {
    window._camFingerprint = newFingerprint;

    // Update <select> options
    const current = new Set([...sel.options].map(o => o.value));
    cameras.forEach(cam => {
      if (!current.has(cam.cam_id)) {
        const opt = document.createElement('option');
        opt.value = cam.cam_id;
        opt.textContent = cam.cam_name || cam.cam_id;
        sel.appendChild(opt);
      }
    });

    // Stop old timers, rebuild thumbnails and start fresh timers
    if (window._thumbTimers) window._thumbTimers.forEach(clearInterval);
    window._thumbTimers = [];

    const THUMB_INTERVAL = 5000;
    ui.camThumbnails.innerHTML = cameras.map(c =>
      `<div onclick="switchCamera('${c.cam_id}')"
            class="flex-shrink-0 w-20 h-14 bg-zinc-800 rounded border border-zinc-700 cursor-pointer hover:border-indigo-500 transition overflow-hidden relative group"
            title="${c.cam_name || c.cam_id}">
         <img id="thumb-${c.cam_id}" src="/snapshot/${c.cam_id}?t=${Date.now()}"
              class="w-full h-full object-cover" onerror="this.style.opacity='0.3'">
         <span class="absolute bottom-0 left-0 right-0 text-center text-[9px] bg-black/60 text-zinc-300 py-0.5 truncate px-1 opacity-0 group-hover:opacity-100 transition">
           ${c.cam_name || c.cam_id}
         </span>
       </div>`
    ).join('');

    cameras.forEach(c => {
      const timer = setInterval(() => {
        const img = document.getElementById(`thumb-${c.cam_id}`);
        if (img) img.src = `/snapshot/${c.cam_id}?t=${Date.now()}`;
      }, THUMB_INTERVAL);
      window._thumbTimers.push(timer);
    });
  }
}

connectWebSocket();

// --- 6. Captures & Logs ---
async function manualCapture() {
  if (!selectedCameraId) return alert('Pilih kamera terlebih dahulu!');
  try {
    const res = await fetch(`/api/capture/${selectedCameraId}`);
    const data = await res.json();
    if (data.path) addCaptureEvent(data.path, 'Manual', '-', new Date().toISOString());
  } catch (e) { alert('Gagal capture: ' + e); }
}

function addCaptureEvent(path, status, gasType, timestamp) {
  const feed = document.getElementById('events-feed');
  if (!feed) return;
  const placeholder = feed.querySelector('p');
  if (placeholder) placeholder.remove();

  const card = document.createElement('div');
  card.className = 'flex-shrink-0 w-48 bg-zinc-900 border border-zinc-800 rounded-lg overflow-hidden hover:border-zinc-600 transition cursor-pointer';
  const t = timestamp ? new Date(timestamp).toLocaleTimeString('id-ID', { hour12: false }) : '--:--';
  const color = status === 'Bahaya' ? 'bg-red-500' : status === 'Waspada' ? 'bg-yellow-500' : 'bg-zinc-500';
  card.innerHTML = `
    <img src="${path}" class="w-full h-28 object-cover" loading="lazy" onclick="window.open('${path}','_blank')">
    <div class="p-2">
      <div class="flex items-center gap-1 mb-1">
        <span class="w-2 h-2 rounded-full ${color}"></span>
        <span class="text-[10px] font-bold text-zinc-300">${status}</span>
        <span class="text-[10px] text-zinc-500 ml-auto">${t}</span>
      </div>
      <p class="text-[9px] text-zinc-500">${gasType}</p>
    </div>`;
  feed.prepend(card);
  if (feed.children.length > 20) feed.lastElementChild.remove();
}

function filterLogs() {
  const search = ui.logSearch.value.toLowerCase();
  const filter = ui.logFilter.value;
  const rows = ui.logTable.querySelectorAll('tr');
  rows.forEach(row => {
    const text = row.textContent.toLowerCase();
    const showSearch = text.includes(search);
    const showFilter = filter === 'all' || text.includes(filter.toLowerCase());
    row.style.display = (showSearch && showFilter) ? '' : 'none';
  });
}

// --- 7. Settings & Chatbot ---
async function loadCameras() {
  try {
    const res = await fetch('/api/cameras');
    const data = await res.json();
    const list = document.getElementById('camera-list');
    const cameras = data.cameras || {};
    if (Object.keys(cameras).length === 0) {
      list.innerHTML = '<p class="text-xs text-zinc-500 italic">Belum ada kamera terdaftar.</p>';
      return;
    }
    list.innerHTML = '';
    for (const [id, cfg] of Object.entries(cameras)) {
      const div = document.createElement('div');
      div.className = 'flex items-center justify-between bg-zinc-900/80 border border-zinc-800 rounded-lg px-4 py-3';
      div.innerHTML = `<div class="flex-grow"><span class="text-sm font-bold text-zinc-200">${cfg.name || id}</span><span class="text-xs text-zinc-500 ml-2">[${id}]</span><p class="text-xs text-zinc-500 font-mono mt-0.5">${cfg.rtsp_url}</p></div><button onclick="deleteCamera('${id}')" class="bg-red-700 hover:bg-red-600 text-white px-3 py-1 rounded text-xs font-semibold ml-4">Hapus</button>`;
      list.appendChild(div);
    }
  } catch (e) { console.error('Error loading cameras:', e); }
}

async function addCamera(e) {
  if (e) e.preventDefault();
  const id = document.getElementById('new-cam-id').value.trim();
  const name = document.getElementById('new-cam-name').value.trim();
  const url = document.getElementById('new-cam-url').value.trim();
  if (!id || !name || !url) { alert('Semua field harus diisi!'); return; }
  try {
    await fetch('/api/cameras', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ cam_id: id, name: name, rtsp_url: url }) });
    document.getElementById('new-cam-id').value = '';
    document.getElementById('new-cam-name').value = '';
    document.getElementById('new-cam-url').value = '';
    loadCameras();
  } catch (err) { alert('Gagal menambah kamera: ' + err); }
}

function fillWebcam(index) {
  document.getElementById('new-cam-id').value = `webcam_${index}`;
  document.getElementById('new-cam-name').value = `Webcam ${index}`;
  document.getElementById('new-cam-url').value = String(index);
}

async function deleteCamera(camId) {
  if (!confirm(`Hapus kamera ${camId}?`)) return;
  try { await fetch(`/api/cameras/${camId}`, { method: 'DELETE' }); loadCameras(); } catch (e) { alert('Gagal: ' + e); }
}

async function loadThresholds() {
  try {
    const res = await fetch('/api/thresholds');
    const th = (await res.json()).thresholds || {};
    document.getElementById('th-prob-aman').value = th.prob_aman ?? 30;
    document.getElementById('th-prob-waspada').value = th.prob_waspada ?? 70;
    document.getElementById('th-yolo-threshold').value = th.yolo_threshold ?? 50;
    document.getElementById('th-yolo-weight-high').value = th.yolo_weight_high ?? 0.7;
    document.getElementById('th-yolo-weight-low').value = th.yolo_weight_low ?? 0.3;
    document.getElementById('th-yolo-interval').value = th.yolo_interval ?? 3;
    currentThresholds.prob_aman    = th.prob_aman    ?? 30;
    currentThresholds.prob_waspada = th.prob_waspada ?? 70;
    fusionChart.update();
  } catch (e) { console.error('Error loading thresholds:', e); }
}

async function saveThresholds(e) {
  if (e) e.preventDefault();
  const payload = {
    prob_aman: parseFloat(document.getElementById('th-prob-aman').value),
    prob_waspada: parseFloat(document.getElementById('th-prob-waspada').value),
    yolo_threshold: parseFloat(document.getElementById('th-yolo-threshold').value),
    yolo_weight_high: parseFloat(document.getElementById('th-yolo-weight-high').value),
    yolo_weight_low: parseFloat(document.getElementById('th-yolo-weight-low').value),
    yolo_interval: parseFloat(document.getElementById('th-yolo-interval').value),
  };
  try {
    await fetch('/api/thresholds', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    const st = document.getElementById('threshold-status');
    st.classList.remove('hidden');
    setTimeout(() => st.classList.add('hidden'), 2000);
  } catch (err) { alert('Gagal menyimpan: ' + err); }
}

async function downloadPDF() {
  const el = document.querySelector('.view-section.active');
  if (!el) return;
  const canvas = await html2canvas(el, { scale: 2, backgroundColor: '#09090b' });
  const pdf = new jspdf.jsPDF('landscape', 'mm', 'a4');
  const pw = pdf.internal.pageSize.getWidth() - 20;
  const ph = (canvas.height * pw) / canvas.width;
  pdf.addImage(canvas.toDataURL('image/png'), 'PNG', 10, 10, pw, ph);
  pdf.save(`Dashboard_FireAI_${Date.now()}.pdf`);
}

// #1 Markdown renderer — converts bot markdown to safe HTML
function markdownToHtml(text) {
  const esc = s => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  const inline = s => esc(s)
    .replace(/\*\*(.+?)\*\*/g, '<strong class="text-zinc-100 font-semibold">$1</strong>')
    .replace(/\*(.+?)\*/g, '<em class="text-zinc-300">$1</em>')
    .replace(/`(.+?)`/g, '<code class="bg-zinc-700 px-1 rounded text-xs font-mono text-zinc-200">$1</code>');

  const out = [];
  let inSection = false;
  for (const line of text.split('\n')) {
    // Numbered list
    const olM = line.match(/^(\d+)\.\s+(.+)$/);
    if (olM) {
      out.push(`<div class="flex gap-2 text-sm my-1 items-start"><span class="font-bold text-indigo-400 shrink-0 min-w-[1.25rem] text-right leading-relaxed">${esc(olM[1])}.</span><span class="flex-1 leading-relaxed">${inline(olM[2])}</span></div>`);
      continue;
    }

    // Sub letter list (  a. )
    const subLetM = line.match(/^\s{2,}([a-zA-Z])\.\s+(.+)$/);
    if (subLetM) {
      out.push(`<div class="flex gap-2 text-sm my-0.5 ml-5 items-start"><span class="text-violet-400 shrink-0 min-w-[1rem] text-right leading-relaxed">${esc(subLetM[1])}.</span><span class="flex-1 leading-relaxed text-zinc-300">${inline(subLetM[2])}</span></div>`);
      continue;
    }

    // Sub bullet (  - or  *)
    const subBulM = line.match(/^\s{2,}[-*]\s+(.+)$/);
    if (subBulM) {
      out.push(`<div class="flex gap-2 text-sm my-0.5 ml-5 items-start"><span class="text-violet-400 shrink-0 leading-relaxed">◦</span><span class="flex-1 leading-relaxed text-zinc-300">${inline(subBulM[1])}</span></div>`);
      continue;
    }

    // Top-level bullet
    const ulM = line.match(/^[-*]\s+(.+)$/);
    if (ulM) {
      out.push(`<div class="flex gap-2 text-sm my-1 items-start"><span class="text-indigo-400 shrink-0 leading-relaxed">•</span><span class="flex-1 leading-relaxed">${inline(ulM[1])}</span></div>`);
      continue;
    }

    // #### heading (h4)
    if (line.startsWith('#### ')) {
      out.push(`<p class="font-semibold text-violet-300 text-xs uppercase tracking-wider mt-3 mb-1">${inline(line.slice(5))}</p>`);
      continue;
    }

    // ### heading (h3)
    if (line.startsWith('### ')) {
      out.push(`<p class="font-semibold text-zinc-300 text-xs uppercase tracking-wide mt-2 mb-0.5">${inline(line.slice(4))}</p>`);
      continue;
    }

    // ## heading (h2) — main section heading with divider
    if (line.startsWith('## ')) {
      out.push(`<div class="mt-3 mb-1.5 pb-1 border-b border-zinc-700/60"><p class="font-bold text-zinc-100 text-sm">${inline(line.slice(3))}</p></div>`);
      continue;
    }

    // # heading (h1)
    if (line.startsWith('# ')) {
      out.push(`<p class="font-bold text-indigo-300 text-sm mt-4 mb-1">${inline(line.slice(2))}</p>`);
      continue;
    }

    // Empty line
    if (line.trim() === '') { out.push('<div class="h-2"></div>'); continue; }

    // Paragraph
    out.push(`<p class="text-sm leading-relaxed text-zinc-200">${inline(line)}</p>`);
  }
  return `<div class="space-y-0.5">${out.join('')}</div>`;
}

// #6 Proactive fire alert — auto-opens chat and injects warning message
function injectFireAlert(camName, prob, detectedClass) {
  const chatWindow = document.getElementById('chat-window');
  if (chatWindow?.classList.contains('hidden')) toggleChat();
  const alertMsg = `⚠️ **PERINGATAN KEBAKARAN!**\n\n**Kamera:** ${camName}\n**Probabilitas:** ${prob}%\n**Deteksi:** ${detectedClass}\n\nSegera hubungi tim K3. Tanya saya prosedur evakuasi atau cara menggunakan APAR.`;
  appendMessage(alertMsg, 'bot');
  const msgs = document.getElementById('chat-messages');
  if (msgs) msgs.scrollTop = msgs.scrollHeight;
}

// Chatbot
function appendMessage(content, who, opts = {}) {
  const msgs = document.getElementById('chat-messages');
  if (!msgs) return;
  const wrap = document.createElement('div');
  wrap.className = 'flex ' + (who === 'user' ? 'justify-end' : 'justify-start') + ' w-full mb-2';
  const bubble = document.createElement('div');
  bubble.className = who === 'user'
    ? 'bg-indigo-600 text-white text-sm rounded-2xl rounded-tr-none px-3 py-2 max-w-[85%]'
    : 'bg-zinc-800 text-zinc-100 text-sm rounded-2xl rounded-tl-none px-3 py-2 max-w-[90%] border border-zinc-700';
  if (opts.isHtml) {
    bubble.innerHTML = content;
  } else if (who === 'bot') {
    bubble.innerHTML = markdownToHtml(content); // #1 render markdown
  } else {
    bubble.textContent = content;
  }

  // Feedback buttons — cuma untuk bot message yang punya messageId
  if (who === 'bot' && opts.messageId) {
    const fbDiv = document.createElement('div');
    fbDiv.className = 'mt-2 pt-2 border-t border-zinc-700 flex gap-2 text-xs opacity-60 hover:opacity-100 transition';
    fbDiv.innerHTML = `
      <button class="thumb-btn px-2 py-0.5 rounded hover:bg-green-500/20" data-rating="1" title="Bagus">👍</button>
      <button class="thumb-btn px-2 py-0.5 rounded hover:bg-red-500/20" data-rating="-1" title="Kurang bagus">👎</button>
    `;
    fbDiv.querySelectorAll('.thumb-btn').forEach(btn => {
      btn.addEventListener('click', () => submitFeedback(btn, fbDiv, opts));
    });
    bubble.appendChild(fbDiv);
  }

  wrap.appendChild(bubble);
  msgs.appendChild(wrap);
  msgs.scrollTop = msgs.scrollHeight;
}

async function submitFeedback(btn, fbDiv, msgOpts) {
  const rating = parseInt(btn.dataset.rating);
  let reason = null;
  if (rating === -1) {
    reason = prompt('Apa yang kurang dari jawaban ini? (opsional)');
  }
  try {
    const res = await fetch('/api/feedback', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message_id: msgOpts.messageId,
        user_message: msgOpts.userMessage || '',
        bot_reply: msgOpts.botReply || '',
        rating: rating,
        reason: reason,
        intent: msgOpts.intent || null,
        context_used: msgOpts.contextUsed || null,
      }),
    });
    if (res.ok) {
      fbDiv.innerHTML = `<span class="text-xs opacity-60">${rating === 1 ? '✅ Thanks!' : '📝 Noted, will improve'}</span>`;
    }
  } catch (e) {
    console.error('Feedback error:', e);
  }
}

// ============ Chat Window Control ============
function toggleChat() {
  const w = document.getElementById('chat-window');
  const fab = document.getElementById('chat-fab');
  const isHidden = w.classList.contains('hidden');

  if (isHidden) {
    w.classList.remove('hidden');
    if (fab) fab.classList.add('hidden');         // sembunyiin FAB saat chat kebuka
    setTimeout(() => document.getElementById('chat-input')?.focus(), 50);

    // #4 Restore history from localStorage or show greeting
    const msgs = document.getElementById('chat-messages');
    if (msgs && msgs.children.length === 0) {
      const saved = localStorage.getItem(CHAT_HISTORY_KEY);
      if (saved) {
        try {
          chatHistory = JSON.parse(saved);
          chatHistory.slice(-6).forEach(t => appendMessage(t.content, t.role === 'user' ? 'user' : 'bot'));
          appendMessage('— Riwayat percakapan dipulihkan —', 'bot');
        } catch { chatHistory = []; }
      }
      if (chatHistory.length === 0) {
        appendMessage(
          'Halo! Saya Asisten K3 yang terhubung ke sensor ruangan kamu. Bisa tanya kondisi sensor, prosedur evakuasi, cara pakai APAR, atau hal K3 lainnya.',
          'bot'
        );
      }
    }
  } else {
    w.classList.add('hidden');
    if (fab) fab.classList.remove('hidden');
  }
}

function toggleChatExpand() {
  const w = document.getElementById('chat-window');
  const btn = document.getElementById('chat-expand-btn');
  const expanded = w.dataset.expanded === '1';

  if (expanded) {
    w.style.width = '420px';
    w.style.height = '600px';
    w.dataset.expanded = '0';
    btn.innerHTML = '<i class="ph ph-arrows-out text-base"></i>';
    btn.title = 'Perbesar';
  } else {
    w.style.width = 'calc(100vw - 48px)';
    w.style.height = 'calc(100vh - 48px)';
    w.dataset.expanded = '1';
    btn.innerHTML = '<i class="ph ph-arrows-in text-base"></i>';
    btn.title = 'Perkecil';
  }
}

function clearChat() {
  const msgs = document.getElementById('chat-messages');
  if (msgs) msgs.innerHTML = '';
  chatHistory = [];
  localStorage.removeItem(CHAT_HISTORY_KEY); // #4
  appendMessage(
    'Chat direset. Halo! Bisa tanya kondisi sensor, prosedur evakuasi, cara pakai APAR, atau hal K3 lainnya.',
    'bot'
  );
}

function handleChatEnter(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendChatMessage();
  }
}

function sendQuickChat(text) {
  const input = document.getElementById('chat-input');
  if (!input) return;
  input.value = text;
  sendChatMessage();
}

// --- Helper: kumpulin sensor context dari DOM untuk chatbot ---
function buildSensorContext() {
  const num = (id) => parseFloat(document.getElementById(id)?.textContent) || 0;
  const txt = (id) => document.getElementById(id)?.textContent?.trim() || null;
  const camSel = document.getElementById('camera-select');
  const probTxt = txt('kpi-prob') || '0%';
  const statusTxt = (txt('global-status') || '').replace('STATUS:', '').trim();

  // Ambil detected_class dari badge gas (cari yang aktif)
  let detected = 'Clean';
  ['cls-clean', 'cls-smoke', 'cls-gasoline', 'cls-mixture'].forEach(id => {
    const el = document.getElementById(id);
    if (el && parseFloat(el.textContent) > 50) {
      detected = id.replace('cls-', '').replace(/^./, c => c.toUpperCase());
    }
  });

  return {
    camera_id: camSel?.value || null,
    camera_name: camSel?.options[camSel.selectedIndex]?.text || null,
    mq135: num('sensor-mq135'),
    mq2: num('sensor-mq2'),
    mq3: num('sensor-mq3'),
    mq4: num('sensor-mq4'),
    mq5: num('sensor-mq5'),
    mq7: num('sensor-mq7-detail'),
    temperature: num('sensor-temp'),
    humidity: num('sensor-humid'),
    prob_akhir: parseFloat(probTxt.replace('%', '')) || 0,
    status: statusTxt || null,
    detected_class: detected,
    flame_detected: lastFlameDetected,                             // #2
    lstm_score: lastLstmScore !== null ? lastLstmScore : undefined, // #3
  };
}

async function sendChatMessage() {
  const chatInput = document.getElementById('chat-input');
  const chatMessages = document.getElementById('chat-messages');
  const sendBtn = document.getElementById('chat-send-btn');
  if (!chatInput || !chatMessages) return;

  const msg = chatInput.value.trim();
  if (!msg) return;

  if (sendBtn) { sendBtn.disabled = true; sendBtn.classList.add('opacity-50'); }
  appendMessage(msg, 'user');
  chatInput.value = '';

  const lid = 'loading-' + Date.now();
  chatMessages.insertAdjacentHTML('beforeend',
    `<div id="${lid}" class="flex items-start w-full mt-2">
       <div class="bg-zinc-800 px-3 py-2 rounded-xl border border-zinc-700 text-zinc-400 text-xs flex gap-1.5">
         <div class="w-1.5 h-1.5 bg-zinc-400 rounded-full animate-bounce"></div>
         <div class="w-1.5 h-1.5 bg-zinc-400 rounded-full animate-bounce" style="animation-delay:0.2s"></div>
         <div class="w-1.5 h-1.5 bg-zinc-400 rounded-full animate-bounce" style="animation-delay:0.4s"></div>
       </div>
     </div>`);
  chatMessages.scrollTop = chatMessages.scrollHeight;

  let sensor_context = null;
  try { sensor_context = buildSensorContext(); }
  catch (err) { console.warn('[Chat] buildSensorContext gagal:', err); }

  try {
    const res = await fetch('/api/chat/stream', {  // #5 streaming endpoint
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pertanyaan: msg, history: chatHistory.slice(-6), sensor_context }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);

    // Remove loading indicator, create streaming bubble
    document.getElementById(lid)?.remove();
    const wrap = document.createElement('div');
    wrap.className = 'flex justify-start w-full mb-2';
    const bubble = document.createElement('div');
    bubble.className = 'bg-zinc-800 text-zinc-100 text-sm rounded-2xl rounded-tl-none px-3 py-2 max-w-[90%] border border-zinc-700 whitespace-pre-wrap';
    wrap.appendChild(bubble);
    chatMessages.appendChild(wrap);

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let fullText = '';
    let msgId = null, intent = null, contextUsed = null;
    let reportUrl = null, reportFilename = null;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop();
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        try {
          const parsed = JSON.parse(line.slice(6));
          if (parsed.token) {
            fullText += parsed.token;
            bubble.textContent = fullText; // raw during stream
            chatMessages.scrollTop = chatMessages.scrollHeight;
          }
          if (parsed.done) {
            msgId = parsed.message_id;
            intent = parsed.intent;
            contextUsed = parsed.context_used || null;
            reportUrl = parsed.report_url || null;
            reportFilename = parsed.report_filename || null;
          }
          if (parsed.error) bubble.textContent = `❌ Error: ${parsed.error}`;
        } catch {}
      }
    }

    // #1 Apply markdown after stream completes
    bubble.classList.remove('whitespace-pre-wrap');
    bubble.innerHTML = markdownToHtml(fullText);

    // Append DOCX download button if a report was generated
    if (reportUrl) {
      const dlDiv = document.createElement('div');
      dlDiv.className = 'mt-3 pt-2 border-t border-zinc-700';
      const fname = reportFilename || 'laporan.docx';
      dlDiv.innerHTML = `
        <a href="${reportUrl}" download="${fname}"
           class="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-medium transition-colors">
            <i class="ph ph-file-doc text-sm"></i>
          Unduh Laporan (DOCX)
        </a>
        <span class="ml-2 text-zinc-500 text-xs">${fname}</span>
      `;
      bubble.appendChild(dlDiv);
    }

    // Add feedback buttons
    if (msgId) {
      const fbDiv = document.createElement('div');
      fbDiv.className = 'mt-2 pt-2 border-t border-zinc-700 flex gap-2 text-xs opacity-60 hover:opacity-100 transition';
      fbDiv.innerHTML = `
        <button class="thumb-btn px-2 py-0.5 rounded hover:bg-green-500/20" data-rating="1" title="Bagus">👍</button>
        <button class="thumb-btn px-2 py-0.5 rounded hover:bg-red-500/20" data-rating="-1" title="Kurang bagus">👎</button>
      `;
      fbDiv.querySelectorAll('.thumb-btn').forEach(btn => {
        btn.addEventListener('click', () => submitFeedback(btn, fbDiv, {
          messageId: msgId, userMessage: msg, botReply: fullText, intent, contextUsed,
        }));
      });
      bubble.appendChild(fbDiv);
    }

    // #4 Save to history + localStorage
    chatHistory.push({ role: 'user', content: msg });
    chatHistory.push({ role: 'assistant', content: fullText });
    if (chatHistory.length > 20) chatHistory = chatHistory.slice(-20);
    localStorage.setItem(CHAT_HISTORY_KEY, JSON.stringify(chatHistory));

  } catch (e) {
    console.error('[Chat] Error:', e);
    document.getElementById(lid)?.remove();
    appendMessage(`❌ Gagal: ${e.message}. Cek console & terminal server.`, 'bot');
  } finally {
    if (sendBtn) { sendBtn.disabled = false; sendBtn.classList.remove('opacity-50'); }
    chatInput.focus();
  }
}

async function pollChatbotHealth() {
  const indicator = document.getElementById('chatbot-indicator');
  const label = document.getElementById('chatbot-status');
  try {
    const res = await fetch('/api/chat/health');
    const data = await res.json();
    if (indicator) {
      indicator.className = indicator.className
        .replace(/bg-\S+/g, '')
        .trim();
      if (data.available) {
        indicator.classList.add('bg-green-400', 'animate-pulse');
        indicator.classList.remove('bg-zinc-500', 'bg-yellow-400', 'opacity-50');
      } else {
        indicator.classList.add('bg-zinc-500', 'opacity-50');
        indicator.classList.remove('bg-green-400', 'bg-yellow-400', 'animate-pulse');
      }
    }
    if (label) label.textContent = data.available ? '● Online' : '● Offline';
  } catch {
    if (indicator) {
      indicator.classList.remove('bg-green-400', 'bg-yellow-400', 'animate-pulse');
      indicator.classList.add('bg-zinc-500', 'opacity-50');
    }
    if (label) label.textContent = '● Offline';
  }
}

function initChatbotHealthIndicator() {
  const indicator = document.getElementById('chatbot-indicator');
  const label = document.getElementById('chatbot-status');
  if (indicator) {
    indicator.classList.remove('bg-green-400', 'bg-zinc-500', 'animate-pulse');
    indicator.classList.add('bg-yellow-400', 'animate-pulse');
  }
  if (label) label.textContent = '⟳ Loading...';
}

// Wire camera size buttons via addEventListener (more reliable than inline onclick)
['s', 'm', 'l'].forEach(size => {
  const btn = document.getElementById(`cam-size-${size}`);
  if (btn) btn.addEventListener('click', () => setCameraSize(size));
});
setInterval(pollChatbotHealth, 30000);
initChatbotHealthIndicator();
pollChatbotHealth();