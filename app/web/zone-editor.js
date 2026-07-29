"use strict";

// Operator tool: draw one plot per sensor on the field photo, then save the
// layout to /api/zones. Coordinates are in the field image's own space
// (config.field_view), so they map straight onto the farmer map.

const SVGNS = ["http", "www.w3.org/2000/svg"].join("://");
const MODE_FILL = { simulate: "#2f6f8f", live: "#c0392b", off: "#8b9580" };
const DEFAULT_PROFILE = "data/profiles/sn3002.json";

let view = [1537, 1023];
let fieldImage = "assets/field-default.jpg";
let zones = []; // { id, name, mode, port, pts: [[x,y], ...] }
let activeId = null;
let drag = null; // { kind: 'vertex'|'zone', id, index, last:[x,y] }

const host = document.getElementById("mapHost");

function svgEl(tag, attrs) {
  const element = document.createElementNS(SVGNS, tag);
  for (const key in attrs) element.setAttribute(key, attrs[key]);
  return element;
}

function centroid(points) {
  let x = 0;
  let y = 0;
  points.forEach((point) => {
    x += point[0];
    y += point[1];
  });
  return [Math.round(x / points.length), Math.round(y / points.length)];
}

function toSVG(event) {
  const svg = host.querySelector("svg");
  const point = svg.createSVGPoint();
  point.x = event.clientX;
  point.y = event.clientY;
  const mapped = point.matrixTransform(svg.getScreenCTM().inverse());
  return [
    Math.round(Math.max(0, Math.min(view[0], mapped.x))),
    Math.round(Math.max(0, Math.min(view[1], mapped.y))),
  ];
}

function activeZone() {
  return zones.find((zone) => zone.id === activeId);
}

function render() {
  host.innerHTML = "";
  const [width, height] = view;
  const svg = svgEl("svg", { viewBox: `0 0 ${width} ${height}` });
  const image = svgEl("image", { x: 0, y: 0, width, height, preserveAspectRatio: "xMidYMid slice" });
  image.setAttribute("href", "/" + fieldImage);
  svg.appendChild(image);
  svg.appendChild(svgEl("rect", { x: 0, y: 0, width, height, fill: "#0a1005", opacity: "0.3" }));

  zones.forEach((zone) => {
    const active = zone.id === activeId;
    const points = zone.pts.map((point) => point.join(",")).join(" ");
    const polygon = svgEl("polygon", {
      points,
      fill: MODE_FILL[zone.mode] || "#2f6f8f",
      "fill-opacity": active ? 0.5 : 0.32,
      stroke: active ? "#ffffff" : "rgba(255,255,255,0.6)",
      "stroke-width": active ? 3 : 2,
      "stroke-dasharray": zone.mode === "off" ? "8 8" : "0",
    });
    polygon.style.cursor = active ? "move" : "pointer";
    if (active) {
      polygon.addEventListener("pointerdown", (event) => {
        event.preventDefault();
        drag = { kind: "zone", id: zone.id, last: toSVG(event) };
      });
    } else {
      polygon.addEventListener("pointerdown", (event) => {
        event.preventDefault();
        setActive(zone.id);
      });
    }
    svg.appendChild(polygon);

    const [cx, cy] = centroid(zone.pts);
    const label = svgEl("text", {
      x: cx,
      y: cy,
      "text-anchor": "middle",
      "font-family": "Segoe UI, Arial, sans-serif",
      "font-weight": "700",
      "font-size": "26",
      fill: "#16210c",
      stroke: "rgba(255,255,255,0.9)",
      "stroke-width": "4",
      "paint-order": "stroke",
    });
    label.textContent = zone.name || zone.id;
    label.style.pointerEvents = "none";
    svg.appendChild(label);
  });

  const zone = activeZone();
  if (zone) {
    // Edge midpoints (drag to add a vertex).
    zone.pts.forEach((point, index) => {
      const next = zone.pts[(index + 1) % zone.pts.length];
      const mid = [Math.round((point[0] + next[0]) / 2), Math.round((point[1] + next[1]) / 2)];
      const ghost = svgEl("circle", { cx: mid[0], cy: mid[1], r: 8, fill: "rgba(255,255,255,0.55)", stroke: "#2a3520", "stroke-width": 1.5 });
      ghost.style.cursor = "copy";
      ghost.addEventListener("pointerdown", (event) => {
        event.preventDefault();
        zone.pts.splice(index + 1, 0, mid.slice());
        drag = { kind: "vertex", id: zone.id, index: index + 1 };
        render();
      });
      svg.appendChild(ghost);
    });
    // Vertices (drag to move, double-click to delete).
    zone.pts.forEach((point, index) => {
      const handle = svgEl("circle", { cx: point[0], cy: point[1], r: 12, fill: "#ffffff", stroke: MODE_FILL[zone.mode] || "#2f6f8f", "stroke-width": 4 });
      handle.style.cursor = "grab";
      handle.addEventListener("pointerdown", (event) => {
        event.preventDefault();
        drag = { kind: "vertex", id: zone.id, index };
      });
      handle.addEventListener("dblclick", (event) => {
        event.preventDefault();
        if (zone.pts.length > 3) {
          zone.pts.splice(index, 1);
          render();
          renderList();
        }
      });
      svg.appendChild(handle);
    });
  }

  host.appendChild(svg);
}

function onMove(event) {
  if (!drag) return;
  const zone = zones.find((candidate) => candidate.id === drag.id);
  if (!zone) return;
  const current = toSVG(event);
  if (drag.kind === "vertex") {
    zone.pts[drag.index] = current;
  } else if (drag.kind === "zone") {
    const dx = current[0] - drag.last[0];
    const dy = current[1] - drag.last[1];
    zone.pts = zone.pts.map((point) => [
      Math.max(0, Math.min(view[0], point[0] + dx)),
      Math.max(0, Math.min(view[1], point[1] + dy)),
    ]);
    drag.last = current;
  }
  render();
}

function onUp() {
  if (drag) {
    drag = null;
    render();
    renderList();
  }
}
window.addEventListener("pointermove", onMove);
window.addEventListener("pointerup", onUp);

function renderList() {
  const list = document.getElementById("zoneList");
  list.innerHTML = "";
  zones.forEach((zone) => {
    const row = document.createElement("div");
    row.className = "zrow" + (zone.id === activeId ? " active" : "");
    row.onclick = (event) => {
      if (event.target.classList.contains("del")) return;
      setActive(zone.id);
    };
    const swatch = MODE_FILL[zone.mode] || "#2f6f8f";
    row.innerHTML =
      `<span class="sw" style="background:${swatch}"></span>` +
      `<span class="zrow-name">${escapeHtml(zone.name || zone.id)}</span>` +
      `<span class="zrow-meta">${zone.mode} - ${zone.pts.length} titik</span>` +
      `<button class="del" title="Hapus">&times;</button>`;
    row.querySelector(".del").addEventListener("click", (event) => {
      event.stopPropagation();
      if (zones.length <= 1) return;
      zones = zones.filter((candidate) => candidate.id !== zone.id);
      if (activeId === zone.id) activeId = zones[0].id;
      render();
      renderList();
      renderActive();
    });
    list.appendChild(row);
  });
}

function renderActive() {
  const panel = document.getElementById("activePanel");
  const zone = activeZone();
  if (!zone) {
    panel.hidden = true;
    return;
  }
  panel.hidden = false;
  document.getElementById("active-name").value = zone.name || "";
  document.getElementById("active-mode").value = zone.mode;
  document.getElementById("active-port").value = zone.port || "COM9";
  document.getElementById("port-field").hidden = zone.mode !== "live";
  document.getElementById("activeMeta").textContent =
    `${zone.id}: ${zone.pts.length} sudut, pusat (${centroid(zone.pts).join(", ")})`;
}

function setActive(id) {
  activeId = id;
  render();
  renderList();
  renderActive();
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"]/g, (character) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[character])
  );
}

function nextId() {
  let max = 0;
  zones.forEach((zone) => {
    const match = /^S(\d+)$/.exec(zone.id);
    if (match) max = Math.max(max, Number(match[1]));
  });
  return "S" + (max + 1);
}

function defaultShape() {
  const [w, h] = view;
  return [
    [Math.round(w / 2 - 130), Math.round(h / 2 - 100)],
    [Math.round(w / 2 + 130), Math.round(h / 2 - 100)],
    [Math.round(w / 2 + 130), Math.round(h / 2 + 100)],
    [Math.round(w / 2 - 130), Math.round(h / 2 + 100)],
  ];
}

async function loadFromState() {
  const response = await fetch("/api/state");
  const state = await response.json();
  view = state.field_view && state.field_view.length === 2 ? state.field_view : [1537, 1023];
  fieldImage = state.field_image || "assets/field-default.jpg";
  zones = Object.entries(state.sensors).map(([id, entry]) => ({
    id,
    name: entry.name || id,
    mode: entry.mode || "simulate",
    port: entry.port || "COM9",
    pts:
      Array.isArray(entry.zone) && entry.zone.length >= 3
        ? entry.zone.map((point) => point.slice())
        : defaultShape(),
  }));
  activeId = zones.length ? zones[0].id : null;
  render();
  renderList();
  renderActive();
}

document.getElementById("addBtn").addEventListener("click", () => {
  const id = nextId();
  zones.push({ id, name: "Blok " + id, mode: "simulate", port: "COM9", pts: defaultShape() });
  setActive(id);
});

document.getElementById("reloadBtn").addEventListener("click", () => {
  loadFromState();
  setStatus("Dimuat ulang dari konfigurasi tersimpan.");
});

document.getElementById("active-name").addEventListener("input", (event) => {
  const zone = activeZone();
  if (zone) {
    zone.name = event.target.value;
    render();
    renderList();
  }
});
document.getElementById("active-mode").addEventListener("change", (event) => {
  const zone = activeZone();
  if (zone) {
    zone.mode = event.target.value;
    render();
    renderList();
    renderActive();
  }
});
document.getElementById("active-port").addEventListener("input", (event) => {
  const zone = activeZone();
  if (zone) zone.port = event.target.value;
});

function setStatus(message) {
  document.getElementById("saveStatus").textContent = message;
}

document.getElementById("saveBtn").addEventListener("click", async () => {
  const payload = {
    field_image: fieldImage,
    field_view: view,
    zones: zones.map((zone) => ({
      id: zone.id,
      name: zone.name || zone.id,
      mode: zone.mode,
      port: zone.port || "COM9",
      profile: DEFAULT_PROFILE,
      zone: zone.pts,
    })),
  };
  setStatus("Menyimpan...");
  try {
    const response = await fetch("/api/zones", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) throw new Error(`gagal: ${response.status}`);
    setStatus(`Tersimpan. ${zones.length} petak. Buka tampilan petani untuk melihat peta.`);
  } catch (error) {
    setStatus(`Gagal menyimpan: ${error.message}`);
  }
});

loadFromState();
