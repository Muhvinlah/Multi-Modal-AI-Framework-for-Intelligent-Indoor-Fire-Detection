// ==============================================================================
// Tujuan       : Dashboard frontend - WebSocket, MJPEG stream, gas class, captures
// Perubahan    : Layout sidebar, fused probability chart, staleness counter, chat chips
// Dependensi   : Chart.js, html2canvas, jsPDF (CDN)
// ==============================================================================

// --- 1. View Switching (Replaces Tabs) ---
function switchView(viewId) {
  document.querySelectorAll('.view-section').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.nav-link').forEach(el => {
    el.classList.remove('bg-zinc-900', 'text-indigo-400', 'border', 'border-indigo-500/30', 'font-medium');
    el.classList.add('text-zinc-400', 'hover:bg-zinc-900');
  });
  
  document.getElementById(`view-${viewId}`).classList.add('active');
  const activeBtn = document.querySelector(`.nav-link[onclick="switchView('${viewId}')"]`);
  if (activeBtn) {
    activeBtn.classList.add('bg-zinc-900', 'text-indigo-400', 'border', 'border-indigo-500/30', 'font-medium');
    activeBtn.classList.remove('text-zinc-400', 'hover:bg-zinc-900');
  }
  
  if (viewId === 'settings') { loadCameras(); loadThresholds(); }
  if (viewId === 'events') { filterLogs(); }
}

// --- 2. Chart.js Init (Fused Probability) ---
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
  aiYoloVal: document.getElementById('ai-yolo-val'), aiYoloBar: document.getElementById('ai-yolo-bar'),
  aiXgbVal: document.getElementById('ai-xgboost-val'), aiXgbBar: document.getElementById('ai-xgboost-bar'),
  aiFusionVal: document.getElementById('ai-fusion-val'),
  sensors: {
    mq135: document.getElementById('sensor-mq135'), mq2: document.getElementById('sensor-mq2'),
    mq3: document.getElementById('sensor-mq3'), mq4: document.getElementById('sensor-mq4'),
    mq5: document.getElementById('sensor-mq5'), mq7: document.getElementById('sensor-mq7-detail')
  }
};

let selectedCameraId = null;
let lastUpdate = Date.now();
let allLogs = [];

// Clock & staleness
setInterval(() => {
  const now = new Date();
  const timeStr = now.toLocaleTimeString('id-ID', { hour12: false });
  const days = ['Min','Sen','Sel','Rab','Kam','Jum','Sab'];
  const months = ['Jan','Feb','Mar','Apr','Mei','Jun','Jul','Agu','Sep','Okt','Nov','Des'];
  const dateStr = `${days[now.getDay()]}, ${now.getDate()} ${months[now.getMonth()]} ${now.getFullYear()}`;
  if (ui.clock) ui.clock.textContent = timeStr;
  if (ui.cameraTime) ui.cameraTime.textContent = timeStr;
  const dateEl = document.getElementById('current-date');
  if (dateEl) dateEl.textContent = dateStr;

  // Staleness Counter
  const diff = Math.floor((Date.now() - lastUpdate) / 1000);
  if (ui.stalenessInd) {
    const staleText = `${diff}s ago`;
    ui.stalenessInd.textContent = staleText;
    if (ui.kpiUpdate) ui.kpiUpdate.textContent = staleText;
    const modal = document.getElementById('disconnect-modal');
    if (diff > 10) {
      ui.stalenessInd.classList.add('text-red-500', 'font-bold');
      if (ui.kpiUpdate) ui.kpiUpdate.classList.add('text-red-500');
      modal.style.display = 'flex';
    } else {
      ui.stalenessInd.classList.remove('text-red-500', 'font-bold');
      if (ui.kpiUpdate) ui.kpiUpdate.classList.remove('text-red-500');
      modal.style.display = 'none';
    }
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
    const cameras = data.cameras || [];

    ui.kpiCams.textContent = `${cameras.length} Online`;
    updateCameraSelector(cameras);

    let cam = cameras.find(c => c.cam_id === selectedCameraId) || cameras[0];
    if (!cam) return;

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
    ui.overlayYolo.textContent = cam.prob_yolo + '%';
    ui.overlaySensor.textContent = cam.prob_sensor + '%';
    ui.overlayFusion.textContent = cam.prob_akhir + '%';

    updateGasBadge(cam.detected_class || 'Clean');
    if (cam.class_probs) updateClassBars(cam.class_probs);

    ui.cameraSelect.value = selectedCameraId;
    ui.cameraLabel.textContent = `REC • ${cam.cam_name || cam.cam_id}`;

    // Sensors
    const temp = cam.temperature !== undefined ? cam.temperature : data.temperature;
    const hum = cam.humidity !== undefined ? cam.humidity : data.humidity;
    document.getElementById('sensor-temp').textContent = temp?.toFixed(1) || '0.0';
    document.getElementById('sensor-humid').textContent = hum?.toFixed(1) || '0.0';

    const ppm = cam.sensor_ppm || {};
    ui.sensors.mq135.textContent = ppm.mq135?.ppm.toFixed(1) || 0;
    ui.sensors.mq2.textContent = ppm.mq2?.ppm.toFixed(1) || 0;
    ui.sensors.mq7.textContent = ppm.mq7?.ppm.toFixed(1) || 0;
    ui.sensors.mq4.textContent = ppm.mq4?.ppm.toFixed(1) || 0;
    ui.sensors.mq5.textContent = ppm.mq5?.ppm.toFixed(1) || 0;
    ui.sensors.mq3.textContent = ppm.mq3?.ppm.toFixed(1) || 0;

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
  const t = timestamp ? new Date(timestamp).toLocaleTimeString('id-ID', {hour12: false}) : '--:--';
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

// Chatbot
const chatWindow = document.getElementById('chat-window');
const chatMessages = document.getElementById('chat-messages');
const chatInput = document.getElementById('chat-input');

function toggleChat() {
  chatWindow.classList.toggle('hidden');
  if (!chatWindow.classList.contains('hidden')) chatInput.focus();
}

function sendQuickChat(msg) {
  chatInput.value = msg;
  sendChatMessage();
}

function handleChatEnter(e) { if (e.key === 'Enter') sendChatMessage(); }

function appendMessage(text, sender) {
  const w = document.createElement('div');
  w.className = `flex flex-col ${sender === 'user' ? 'items-end' : 'items-start'} w-full`;
  const b = document.createElement('div');
  b.className = sender === 'user' 
    ? 'bg-indigo-600 text-white text-sm rounded-2xl rounded-tr-none px-4 py-3 max-w-[90%] shadow-md'
    : 'bg-zinc-800 text-zinc-200 text-sm rounded-2xl rounded-tl-none px-4 py-3 max-w-[95%] border border-zinc-700 shadow-md whitespace-pre-wrap';
  w.appendChild(b);
  chatMessages.appendChild(w);
  chatMessages.scrollTop = chatMessages.scrollHeight;
  if (sender === 'bot') {
    let fmt = text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    typeWriterEffect(b, fmt, 0);
  } else { b.textContent = text; }
}

function typeWriterEffect(el, html, i) {
  if (i < html.length) {
    let c = html.charAt(i);
    if (c === '<') { 
      let end = html.indexOf('>', i); 
      if (end !== -1) { el.innerHTML += html.substring(i, end + 1); i = end + 1; } 
      else { el.innerHTML += c; i++; } 
    } else { el.innerHTML += c; i++; }
    chatMessages.scrollTop = chatMessages.scrollHeight;
    setTimeout(() => typeWriterEffect(el, html, i), 12);
  }
}

async function sendChatMessage() {
  const msg = chatInput.value.trim();
  if (!msg) return;
  appendMessage(msg, 'user');
  chatInput.value = '';
  const lid = 'loading-' + Date.now();
  chatMessages.innerHTML += `<div id="${lid}" class="flex items-start w-full mt-2"><div class="bg-zinc-800 px-3 py-2 rounded-xl border border-zinc-700 text-zinc-400 text-xs flex gap-1.5"><div class="w-1.5 h-1.5 bg-zinc-400 rounded-full animate-bounce"></div><div class="w-1.5 h-1.5 bg-zinc-400 rounded-full animate-bounce" style="animation-delay:0.2s"></div><div class="w-1.5 h-1.5 bg-zinc-400 rounded-full animate-bounce" style="animation-delay:0.4s"></div></div></div>`;
  chatMessages.scrollTop = chatMessages.scrollHeight;
  
  try {
    const res = await fetch('/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message: msg }) });
    const data = await res.json();
    document.getElementById(lid).remove();
    appendMessage(data.reply, 'bot');
  } catch (e) { document.getElementById(lid).remove(); appendMessage('Gagal terhubung ke AI.', 'bot'); }
}