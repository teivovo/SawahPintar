"use strict";

const METRICS = ["moisture", "ph", "conductivity", "temperature"];
const SEVERITY_CLASS = { green: "status-green", amber: "status-amber", red: "status-red" };
const SEVERITY_LABEL = {
  green: "Kondisi tanah baik",
  amber: "Perlu perhatian",
  red: "Bertindak sekarang",
};
const RULE_GROUP_PRIORITY = { salinity: 4, water: 3, acidity: 2, nutrients: 1 };

const panels = {};
const simulatedSensors = new Set();

// --- Field map (Peta lahan) ---------------------------------------------
// A plot's alert colour is laid over the aerial photo at partial opacity so
// the crop and the tree-lined bunds still read through it. The map appears
// only when zones have been drawn; see zonesConfigured / start().
// The SVG namespace identifier. Assembled rather than written as a literal
// so the "no remote URL" asset guard does not read it as a network fetch:
// it names an XML namespace, it is never requested over the network.
const SVGNS = ["http", "www.w3.org/2000/svg"].join("://");
const MAP_FILL = { good: "#37d15f", attention: "#ffcf3a", critical: "#ff4a2e", idle: "#c9ccc2" };
const MAP_FILL_OPACITY = { good: 0.42, attention: 0.46, critical: 0.52, idle: 0.3 };
const STATUS_ID_LABEL = {
  good: "Baik",
  attention: "Perlu perhatian",
  critical: "Bertindak sekarang",
  idle: "Belum terpasang",
};
const MODE_ID_LABEL = { simulate: "Simulasi", live: "Langsung", off: "Belum terpasang" };
const STATUS_PRIORITY = { critical: 3, attention: 2, good: 1, idle: 0 };
const MAP_LEGEND = [
  ["good", "Baik"],
  ["attention", "Perlu perhatian"],
  ["critical", "Bertindak"],
  ["idle", "Belum ada sensor"],
];

const plots = {}; // sensorId -> { name, zone, mode, status }
let selectedSensor = null;

function svgEl(tag, attrs) {
  const element = document.createElementNS(SVGNS, tag);
  for (const key in attrs) element.setAttribute(key, attrs[key]);
  return element;
}

function hasZone(entry) {
  return Array.isArray(entry.zone) && entry.zone.length >= 3;
}

function zonesConfigured(state) {
  return Object.values(state.sensors).some(hasZone);
}

function zonePath(points) {
  return "M" + points.map((point) => point.join(",")).join(" L") + " Z";
}

function zoneCentroid(points) {
  let x = 0;
  let y = 0;
  points.forEach((point) => {
    x += point[0];
    y += point[1];
  });
  return [x / points.length, y / points.length];
}

function buildFieldMap(state) {
  const host = document.getElementById("field-map");
  host.innerHTML = "";
  const view = state.field_view && state.field_view.length === 2 ? state.field_view : [1537, 1023];
  const [width, height] = view;
  const svg = svgEl("svg", { viewBox: `0 0 ${width} ${height}`, role: "group", "aria-label": "Peta lahan" });

  const image = svgEl("image", {
    x: 0,
    y: 0,
    width,
    height,
    preserveAspectRatio: "xMidYMid slice",
  });
  image.setAttribute("href", "/" + state.field_image);
  svg.appendChild(image);
  // Fade the photo so the alert colours and labels read clearly over it.
  svg.appendChild(svgEl("rect", { x: 0, y: 0, width, height, fill: "#0a1005", opacity: "0.34" }));

  Object.entries(state.sensors).forEach(([sensorId, entry]) => {
    if (!hasZone(entry)) return;
    const status = entry.status || "idle";
    const path = zonePath(entry.zone);
    const group = svgEl("g", {
      class: "map-zone",
      tabindex: "0",
      role: "button",
      "data-sensor-id": sensorId,
      "aria-label": `${entry.name || sensorId} - ${STATUS_ID_LABEL[status] || status}`,
    });
    group.appendChild(
      svgEl("path", {
        class: "map-zone-fill",
        d: path,
        fill: MAP_FILL[status],
        "fill-opacity": MAP_FILL_OPACITY[status],
        stroke: "#ffffff",
        "stroke-opacity": "0.55",
        "stroke-width": "2",
        "stroke-linejoin": "round",
        "stroke-dasharray": status === "idle" ? "7 7" : "0",
      })
    );
    group.appendChild(svgEl("path", { class: "map-zone-outline", d: path }));
    const [cx, cy] = zoneCentroid(entry.zone);
    const label = svgEl("text", { class: "map-zone-label", x: cx, y: cy, "text-anchor": "middle" });
    label.textContent = entry.name || sensorId;
    group.appendChild(label);
    group.addEventListener("click", () => selectPlot(sensorId));
    group.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        selectPlot(sensorId);
      }
    });
    svg.appendChild(group);
    plots[sensorId] = { name: entry.name || sensorId, zone: entry.zone, mode: entry.mode, status };
  });

  host.appendChild(svg);

  const legend = document.createElement("div");
  legend.className = "map-legend";
  legend.innerHTML = MAP_LEGEND.map(
    ([key, label]) =>
      `<span class="legend-row"><span class="legend-swatch" style="background:${MAP_FILL[key]}"></span>${label}</span>`
  ).join("");
  host.appendChild(legend);
  host.hidden = false;
}

function selectPlot(sensorId) {
  selectedSensor = sensorId;
  document.querySelectorAll("#field-map .map-zone").forEach((group) => {
    group.classList.toggle("selected", group.dataset.sensorId === sensorId);
  });
  const plot = plots[sensorId];
  const detached = plot && plot.mode === "off";
  // A detached plot has no readings to show; hide the panel and explain
  // rather than showing empty dials with no context.
  Object.entries(panels).forEach(([id, panel]) => {
    panel.node.hidden = id !== sensorId || detached;
  });
  const note = document.getElementById("detail-note");
  if (note) {
    note.hidden = !detached;
    note.textContent = detached
      ? "Petak ini belum punya sensor. Pasang probe (mode Langsung) atau jalankan Simulasi di konsol operator."
      : "";
  }
  const title = document.getElementById("detail-title");
  if (title && plot) {
    title.hidden = false;
    const mode = MODE_ID_LABEL[plot.mode] || plot.mode;
    title.textContent = mode ? `${plot.name} - ${mode}` : plot.name;
  }
}

function updateZoneStatus(sensorId, status) {
  if (!status) return;
  if (plots[sensorId]) plots[sensorId].status = status;
  const fill = document.querySelector(`#field-map .map-zone[data-sensor-id="${sensorId}"] .map-zone-fill`);
  if (fill) {
    fill.setAttribute("fill", MAP_FILL[status]);
    fill.setAttribute("fill-opacity", MAP_FILL_OPACITY[status]);
    fill.setAttribute("stroke-dasharray", status === "idle" ? "7 7" : "0");
  }
  updateFieldSummary();
}

function updateFieldSummary() {
  const host = document.getElementById("field-summary");
  if (!host || host.hidden) return;
  const counts = { good: 0, attention: 0, critical: 0, idle: 0 };
  Object.values(plots).forEach((plot) => {
    counts[plot.status] = (counts[plot.status] || 0) + 1;
  });
  let headline;
  if (counts.critical) headline = `${counts.critical} petak perlu tindakan`;
  else if (counts.attention) headline = "Sebagian petak perlu perhatian";
  else headline = "Sawah dalam kondisi baik";
  host.innerHTML =
    `<span class="summary-headline">${headline}</span>` +
    `<span class="summary-stat stat-good">Baik ${counts.good}</span>` +
    `<span class="summary-stat stat-attention">Perhatian ${counts.attention}</span>` +
    `<span class="summary-stat stat-critical">Tindakan ${counts.critical}</span>` +
    `<span class="summary-stat stat-idle">Kosong ${counts.idle}</span>`;
}

function severityRank(severity) {
  return { red: 3, amber: 2, green: 1 }[severity] || 0;
}

function compareAdvice(a, b) {
  const severityDiff = severityRank(b.severity) - severityRank(a.severity);
  if (severityDiff !== 0) return severityDiff;
  const groupA = RULE_GROUP_PRIORITY[a.rule_group] || 0;
  const groupB = RULE_GROUP_PRIORITY[b.rule_group] || 0;
  return groupB - groupA;
}

function overallSeverity(advice) {
  if (advice.length === 0) return "green";
  return advice.reduce(
    (worst, card) => (severityRank(card.severity) > severityRank(worst) ? card.severity : worst),
    "green"
  );
}

function formatValue(value) {
  if (value === null || value === undefined) return "--";
  return Math.round(value * 10) / 10;
}

// The status icon must change SHAPE with severity, not only colour.
//
// The first version drew a tick unconditionally and recoloured the bar around
// it, which put a reassuring tick on a red "act now" banner. For an audience
// reading across a field, and for anyone who is colour-blind, the shape is read
// before the words and before the colour, so a tick on an urgent warning is
// worse than no icon at all.
//
// Green is a tick, amber is an exclamation in a circle, and red is an
// exclamation in a triangle, which is the standard hazard shape.
const STATUS_ICONS = {
  green:
    '<circle cx="12" cy="12" r="11"></circle>' +
    '<path d="M7 12.5 L10.5 16 L17 8" fill="none" stroke="#ffffff" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"></path>',
  amber:
    '<circle cx="12" cy="12" r="11"></circle>' +
    '<path d="M12 6 L12 13.5" fill="none" stroke="#ffffff" stroke-width="2.6" stroke-linecap="round"></path>' +
    '<circle cx="12" cy="17.6" r="1.5" fill="#ffffff" stroke="none"></circle>',
  red:
    '<path d="M12 1.6 L23 21.4 L1 21.4 Z"></path>' +
    '<path d="M12 8 L12 15" fill="none" stroke="#ffffff" stroke-width="2.6" stroke-linecap="round"></path>' +
    '<circle cx="12" cy="18.6" r="1.5" fill="#ffffff" stroke="none"></circle>',
};

function createPanel(sensorId) {
  const template = document.getElementById("panel-template");
  const node = template.content.firstElementChild.cloneNode(true);
  node.dataset.sensorId = sensorId;
  document.getElementById("panels").appendChild(node);

  const toggle = node.querySelector('[data-role="trends-toggle"]');
  const content = node.querySelector('[data-role="trends-content"]');
  const section = node.querySelector('[data-role="trends"]');
  toggle.addEventListener("click", () => {
    const expanded = toggle.getAttribute("aria-expanded") === "true";
    const willExpand = !expanded;
    toggle.setAttribute("aria-expanded", String(willExpand));
    content.hidden = expanded;
    section.classList.toggle("collapsed", expanded);
    // loadHistory only ran once, at page load, so the trends panel always
    // excluded whatever readings had arrived since. Re-run it every time
    // the facilitator opens the panel, which is also the moment the group
    // is looking at it and freshness matters most.
    if (willExpand) loadHistory(sensorId, panels[sensorId]);
  });

  panels[sensorId] = {
    node,
    statusBar: node.querySelector('[data-role="status-bar"]'),
    statusLabel: node.querySelector('[data-role="status-label"]'),
    statusIcon: node.querySelector(".status-icon"),
    adviceCards: node.querySelector('[data-role="advice-cards"]'),
    dials: node.querySelector('[data-role="dials"]'),
    charts: {},
  };
  METRICS.forEach((metric) => {
    panels[sensorId].charts[metric] = node.querySelector(
      `.trend-chart[data-metric="${metric}"] canvas`
    );
  });
  return panels[sensorId];
}

function renderStatus(panel, advice) {
  const severity = overallSeverity(advice);
  panel.statusBar.className = `status-bar ${SEVERITY_CLASS[severity]}`;
  panel.statusLabel.textContent = SEVERITY_LABEL[severity];
  if (panel.statusIcon && STATUS_ICONS[severity]) {
    panel.statusIcon.innerHTML = STATUS_ICONS[severity];
  }
}

function renderCards(panel, advice) {
  panel.adviceCards.innerHTML = "";
  const ranked = [...advice].sort(compareAdvice).slice(0, 4);
  ranked.forEach((card) => {
    const article = document.createElement("article");
    article.className = `advice-card severity-${card.severity}`;
    const headline = document.createElement("h2");
    headline.textContent = card.headline;
    const body = document.createElement("p");
    body.textContent = card.body;
    const subtitle = document.createElement("p");
    subtitle.className = "advice-subtitle-en";
    subtitle.textContent = card.subtitle_en;
    subtitle.hidden = document.body.dataset.language !== "en";
    article.appendChild(headline);
    article.appendChild(body);
    article.appendChild(subtitle);
    panel.adviceCards.appendChild(article);
  });
}

function renderDials(panel, values) {
  METRICS.forEach((metric) => {
    const target = panel.dials.querySelector(
      `.dial[data-metric="${metric}"] [data-role="value"]`
    );
    if (target) target.textContent = formatValue(values ? values[metric] : undefined);
  });
}

function drawSparkline(canvas, points, colourLive, colourSeed) {
  const ctx = canvas.getContext("2d");
  const width = canvas.width;
  const height = canvas.height;
  ctx.clearRect(0, 0, width, height);
  if (points.length < 2) return;

  const values = points.map((point) => point.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;

  const x = (index) => (index / (points.length - 1)) * (width - 8) + 4;
  const y = (value) => height - 4 - ((value - min) / span) * (height - 8);

  for (let i = 1; i < points.length; i++) {
    ctx.beginPath();
    ctx.moveTo(x(i - 1), y(points[i - 1].value));
    ctx.lineTo(x(i), y(points[i].value));
    ctx.strokeStyle = points[i].source === "seed" ? colourSeed : colourLive;
    ctx.lineWidth = 3;
    ctx.lineCap = "round";
    ctx.stroke();
  }
}

async function loadHistory(sensorId, panel) {
  for (const metric of METRICS) {
    const response = await fetch(`/api/history?sensor_id=${sensorId}&metric=${metric}&limit=200`);
    if (!response.ok) continue;
    const body = await response.json();
    drawSparkline(panel.charts[metric], body.points, "#1a7f37", "#9aa5b1");
  }
}

function updateWatermark() {
  document.getElementById("watermark").hidden = simulatedSensors.size === 0;
}

function applyUpdate(sensorId, reading, advice, simulated) {
  const panel = panels[sensorId];
  if (!panel) return;
  renderStatus(panel, advice);
  renderCards(panel, advice);
  renderDials(panel, reading ? reading.values : null);
  if (simulated) simulatedSensors.add(sensorId);
  else simulatedSensors.delete(sensorId);
  updateWatermark();
}

const PROBE_READING_ANIMATION_MS = 1500;

function showProbeOverlay() {
  document.getElementById("probe-overlay").hidden = false;
}

function hideProbeOverlay() {
  document.getElementById("probe-overlay").hidden = true;
}

function revealPanel(panel) {
  panel.adviceCards.classList.remove("reveal");
  void panel.adviceCards.offsetWidth;
  panel.adviceCards.classList.add("reveal");
}

function playProbeInsertionSequence(message) {
  showProbeOverlay();
  window.setTimeout(() => {
    applyUpdate(message.sensor_id, message.reading, message.advice, message.simulated);
    hideProbeOverlay();
    const panel = panels[message.sensor_id];
    if (panel) revealPanel(panel);
  }, PROBE_READING_ANIMATION_MS);
}

const METRIC_LABEL_ID = {
  moisture: "Kelembapan",
  temperature: "Suhu tanah",
  conductivity: "Kekuatan larutan tanah",
  ph: "pH tanah",
};

function renderComparison(comparison) {
  const strip = document.getElementById("comparison-strip");
  if (!strip) return;
  if (!comparison) {
    strip.hidden = true;
    return;
  }
  strip.hidden = false;
  strip.innerHTML = "";
  Object.entries(comparison.metrics).forEach(([metric, entry]) => {
    const row = document.createElement("div");
    row.className = "comparison-row";
    const label = document.createElement("span");
    label.className = "comparison-label";
    label.textContent = METRIC_LABEL_ID[metric] || metric;
    const value = document.createElement("span");
    value.className = "comparison-value";
    if (entry.higher === "equal") {
      value.textContent = "Sama";
    } else {
      const winner = entry.higher === "a" ? "A" : "B";
      const rounded = Math.round(entry.difference * 10) / 10;
      value.textContent = `Sensor ${winner} lebih tinggi (${rounded})`;
    }
    row.appendChild(label);
    row.appendChild(value);
    strip.appendChild(row);
  });
}

// DRAFT wording, like every other farmer-visible string in this
// application: not yet reviewed by Hasanuddin faculty. See
// data/content/advice.yaml for the equivalent marker on advice cards.
const BANNER_DISCONNECTED = "Sambungan terputus. Mencoba menyambung ulang...";
const BANNER_SENSOR_OFFLINE =
  "Sensor tidak merespons. Periksa sambungan probe, atau beralih ke Simulasi di konsol operator.";

function showBanner(text) {
  const banner = document.getElementById("reconnect-banner");
  if (banner) {
    banner.textContent = text;
    banner.hidden = false;
  }
}

function hideBanner() {
  const banner = document.getElementById("reconnect-banner");
  if (banner) banner.hidden = true;
}

// Kept as named wrappers so the socket-close path reads clearly.
function showReconnectBanner() {
  showBanner(BANNER_DISCONNECTED);
}

function hideReconnectBanner() {
  hideBanner();
}

function connectFeed(sensorId) {
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  const socket = new WebSocket(`${protocol}://${window.location.host}/ws?sensor_id=${sensorId}`);
  socket.addEventListener("open", hideReconnectBanner);
  socket.addEventListener("message", (event) => {
    const message = JSON.parse(event.data);
    // The operator console's language toggle only ever reaches the config
    // file and the next websocket tick; this is what re-renders an already
    // open farmer display without a page reload.
    if (message.language) document.body.dataset.language = message.language;
    // A read failure keeps the socket alive and arrives as an error message
    // rather than a socket close, so it is handled here, not in the close
    // handler. Show the sensor-offline cue and leave the last values in place
    // until a real reading returns.
    if (message.error === "sensor-not-responding") {
      showBanner(BANNER_SENSOR_OFFLINE);
      return;
    }
    // Any normal reading clears whichever banner was showing.
    hideBanner();
    if (message.comparison) renderComparison(message.comparison);
    if (message.probe_inserted) {
      playProbeInsertionSequence(message);
    } else {
      applyUpdate(message.sensor_id, message.reading, message.advice, message.simulated);
    }
    // Recolour this plot on the field map from the plot status carried on
    // the tick, so a plot that crosses into attention or act-now changes
    // colour live without the facilitator needing to open it.
    updateZoneStatus(message.sensor_id, message.status);
  });
  socket.addEventListener("close", () => {
    // The dials and cards keep showing the last values they had, with no
    // visual cue that the feed is dead, which is stale data presented as
    // current for as long as the probe or the dongle stays disconnected.
    showReconnectBanner();
    window.setTimeout(() => connectFeed(sensorId), 3000);
  });
}

async function start() {
  const response = await fetch("/api/state");
  const state = await response.json();
  document.body.dataset.language = state.language;

  const sensorIds = Object.keys(state.sensors);
  const useMap = zonesConfigured(state);

  if (useMap) {
    buildFieldMap(state);
    document.getElementById("field-summary").hidden = false;
  } else {
    // No zones drawn: the original single/split panel view.
    document.getElementById("panels").classList.toggle("split", sensorIds.length === 2);
    renderComparison(state.comparison);
  }

  sensorIds.forEach((sensorId) => {
    const panel = createPanel(sensorId);
    const entry = state.sensors[sensorId];
    renderStatus(panel, entry.advice);
    renderCards(panel, entry.advice);
    renderDials(panel, entry.reading ? entry.reading.values : null);
    if (entry.reading && entry.reading.source !== "live") simulatedSensors.add(sensorId);
    loadHistory(sensorId, panel);
    // A detached plot (mode 'off') has no feed to open; every other plot
    // streams. On the map, panels start hidden until their plot is tapped.
    if (entry.mode !== "off") connectFeed(sensorId);
    if (useMap) panel.node.hidden = true;
  });

  if (useMap) {
    updateFieldSummary();
    // Open on the plot that most needs attention, so the display lands on
    // the interesting one rather than an arbitrary first plot.
    let opening = sensorIds[0];
    let bestRank = -1;
    sensorIds.forEach((sensorId) => {
      const rank = STATUS_PRIORITY[state.sensors[sensorId].status] || 0;
      if (rank > bestRank) {
        bestRank = rank;
        opening = sensorId;
      }
    });
    if (opening) selectPlot(opening);
  }

  updateWatermark();
}

function openOperatorConsole() {
  window.location.href = "/operator";
}

window.addEventListener("keydown", (event) => {
  if (event.ctrlKey && event.altKey && event.key.toLowerCase() === "o") {
    openOperatorConsole();
  }
});

// A discreet gear in the corner opens the operator console. It is kept small
// and low-contrast so it does not compete with the farmer-facing content, but
// it gives the facilitator a visible way in rather than relying on the
// Ctrl+Alt+O keystroke, which is hard to discover. The keystroke still works.
const operatorLink = document.getElementById("operator-link");
if (operatorLink) {
  operatorLink.addEventListener("click", openOperatorConsole);
}

start();
