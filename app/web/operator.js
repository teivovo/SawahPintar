"use strict";

async function postJson(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const text = await response.text();
  let data;
  try {
    data = JSON.parse(text);
  } catch (error) {
    data = { detail: text };
  }
  if (!response.ok) {
    throw new Error(data.detail || `request failed: ${response.status}`);
  }
  return data;
}

function setStatus(elementId, message) {
  document.getElementById(elementId).textContent = message;
}

function numberOrNull(elementId) {
  const raw = document.getElementById(elementId).value;
  return raw === "" ? null : Number(raw);
}

async function loadPortsAndProfiles() {
  const portsResponse = await fetch("/api/ports");
  const ports = (await portsResponse.json()).ports;
  const portSelect = document.getElementById("bind-port");
  portSelect.innerHTML = "";
  ports.forEach((port) => {
    const option = document.createElement("option");
    option.value = port.device;
    option.textContent = `${port.device} (${port.description})`;
    portSelect.appendChild(option);
  });

  const profilesResponse = await fetch("/api/profiles");
  const profiles = (await profilesResponse.json()).profiles;
  const profileSelect = document.getElementById("bind-profile");
  profileSelect.innerHTML = "";
  profiles.forEach((profile) => {
    const option = document.createElement("option");
    option.value = profile.path;
    option.textContent = profile.label;
    profileSelect.appendChild(option);
  });
}

function wireBind() {
  document.getElementById("bind-button").addEventListener("click", async () => {
    const sensorId = document.getElementById("bind-sensor-id").value;
    const body = {
      port: document.getElementById("bind-port").value,
      profile: document.getElementById("bind-profile").value,
      mode: document.getElementById("bind-mode").value,
    };
    try {
      await postJson(`/api/sensors/${sensorId}/bind`, body);
      setStatus("bind-status", `Tersambung: ${sensorId}`);
    } catch (error) {
      setStatus("bind-status", `Gagal: ${error.message}`);
    }
  });
}

function wireInspector() {
  document.getElementById("inspect-button").addEventListener("click", async () => {
    const body = {
      port: document.getElementById("inspect-port").value,
      baud: Number(document.getElementById("inspect-baud").value),
      address: Number(document.getElementById("inspect-address").value),
      function: Number(document.getElementById("inspect-function").value),
      start: Number(document.getElementById("inspect-start").value),
      count: Number(document.getElementById("inspect-count").value),
    };
    const resultBox = document.getElementById("inspect-result");
    try {
      const data = await postJson("/api/registers/read", body);
      resultBox.textContent = JSON.stringify(data.registers);
    } catch (error) {
      resultBox.textContent = `Gagal: ${error.message}`;
    }
  });
}

function wireConfig(initialLanguage) {
  document.getElementById("growth-stage-button").addEventListener("click", async () => {
    const growthStage = document.getElementById("growth-stage").value;
    try {
      await postJson("/api/config", { growth_stage: growthStage });
      setStatus("config-status", "Tahap pertumbuhan disimpan");
    } catch (error) {
      setStatus("config-status", `Gagal: ${error.message}`);
    }
  });

  document.getElementById("site-name-button").addEventListener("click", async () => {
    const siteName = document.getElementById("site-name").value;
    try {
      await postJson("/api/config", { site_name: siteName });
      setStatus("config-status", "Nama lokasi disimpan");
    } catch (error) {
      setStatus("config-status", `Gagal: ${error.message}`);
    }
  });

  // Started from the workshop's real current language rather than a
  // hardcoded "id", so the first press of this button toggles away from
  // whatever language is actually active instead of always assuming "id"
  // regardless of what a previous session left it on.
  let currentLanguage = initialLanguage;
  document.getElementById("language-toggle-button").addEventListener("click", async () => {
    currentLanguage = currentLanguage === "id" ? "en" : "id";
    try {
      await postJson("/api/config", { language: currentLanguage });
      setStatus("config-status", `Bahasa: ${currentLanguage}`);
    } catch (error) {
      setStatus("config-status", `Gagal: ${error.message}`);
    }
  });
}

function wireFieldCard() {
  document.getElementById("field-card-button").addEventListener("click", async () => {
    const body = {
      field_size_ha: numberOrNull("field-size"),
      variety: document.getElementById("field-variety").value,
      seedling_age_days: numberOrNull("field-seedling-age"),
      water_source: document.getElementById("field-water-source").value,
      previous_yield_t_ha: numberOrNull("field-previous-yield"),
      fertiliser_available: document.getElementById("field-fertiliser").value,
    };
    try {
      await postJson("/api/field-card", body);
      setStatus("field-card-status", "Kartu lahan disimpan");
    } catch (error) {
      setStatus("field-card-status", `Gagal: ${error.message}`);
    }
  });
}

function wirePuts() {
  document.getElementById("puts-button").addEventListener("click", async () => {
    const body = {
      nitrogen_class: document.getElementById("puts-nitrogen").value,
      phosphorus_class: document.getElementById("puts-phosphorus").value,
      potassium_class: document.getElementById("puts-potassium").value,
      ph: numberOrNull("puts-ph"),
    };
    try {
      const data = await postJson("/api/puts", body);
      // Design spec 8.1: a dose appears the moment PUTS classes are
      // entered, sourced from Permentan 13 of 2022, never the probe. Shown
      // only here, in the operator console, never on the farmer display,
      // and this wording has not yet been reviewed by Hasanuddin faculty
      // - treat it as a draft, like every other string in this console.
      if (data.phosphorus_dose) {
        const dose = data.phosphorus_dose;
        setStatus(
          "puts-status",
          `Hasil PUTS dicatat. Dosis fosfor (status ${dose.status}, ${dose.source}): ` +
            `${dose.p2o5_kg_per_ha} kg P2O5/ha (${dose.sp36_kg_per_ha} kg SP-36/ha).`
        );
      } else {
        setStatus("puts-status", "Hasil PUTS dicatat");
      }
    } catch (error) {
      setStatus("puts-status", `Gagal: ${error.message}`);
    }
  });
}

function wireScenario() {
  const run = async (action) => {
    const sensorId = document.getElementById("scenario-sensor-id").value;
    try {
      await postJson("/api/scenario", { sensor_id: sensorId, action: action });
      setStatus("scenario-status", `${action}: ${sensorId}`);
    } catch (error) {
      setStatus("scenario-status", `Gagal: ${error.message}`);
    }
  };
  document.getElementById("scenario-insert-button").addEventListener("click", () => run("insert"));
  document.getElementById("scenario-withdraw-button").addEventListener("click", () => run("withdraw"));
}

function wireSession() {
  document.getElementById("reset-button").addEventListener("click", async () => {
    if (!window.confirm("Atur ulang data sesi ini? Riwayat contoh tidak akan terhapus.")) return;
    try {
      const data = await postJson("/api/demo-reset", {});
      setStatus("session-status", `Baris dihapus: ${data.deleted}`);
    } catch (error) {
      setStatus("session-status", `Gagal: ${error.message}`);
    }
  });

  document.getElementById("export-button").addEventListener("click", async () => {
    try {
      const data = await postJson("/api/export", {});
      setStatus("session-status", `Tersimpan: ${data.parquet} dan ${data.csv}`);
    } catch (error) {
      setStatus("session-status", `Gagal: ${error.message}`);
    }
  });
}

function ensureOption(select, value, label) {
  // Select `value`, adding it as an option first if the enumerated list
  // does not contain it. A saved COM port or profile that is not present
  // on this machine right now still shows as the current selection rather
  // than silently falling back to the first listed option.
  if (!select || !value) return;
  const exists = Array.from(select.options).some((option) => option.value === value);
  if (!exists) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = label || value;
    select.appendChild(option);
  }
  select.value = value;
}

function populateSensorSelect(selectId, sensors, selectedId) {
  const select = document.getElementById(selectId);
  if (!select) return;
  const ids = Object.keys(sensors);
  if (ids.length === 0) return;
  select.innerHTML = "";
  ids.forEach((id) => {
    const option = document.createElement("option");
    option.value = id;
    const name = sensors[id] && sensors[id].name ? sensors[id].name : id;
    option.textContent = name && name !== id ? `${name} (${id})` : id;
    select.appendChild(option);
  });
  if (selectedId && ids.includes(selectedId)) select.value = selectedId;
}

function fillBindFields(sensor) {
  if (!sensor) return;
  ensureOption(document.getElementById("bind-port"), sensor.port, sensor.port);
  ensureOption(document.getElementById("bind-profile"), sensor.profile, sensor.profile);
  if (sensor.mode) ensureOption(document.getElementById("bind-mode"), sensor.mode, sensor.mode);
}

function prefillSettings(state) {
  // Show what is actually saved. Before this, the console opened with every
  // field blank or on its first option, over live values, so an operator
  // could not tell what the current growth stage, site name or per-sensor
  // binding was without changing it. Now each control reflects config.json.
  if (state.growth_stage) document.getElementById("growth-stage").value = state.growth_stage;
  document.getElementById("site-name").value = state.site_name || "";

  const sensors = state.sensors || {};
  const firstId = Object.keys(sensors)[0];
  populateSensorSelect("bind-sensor-id", sensors, firstId);
  populateSensorSelect("scenario-sensor-id", sensors, firstId);
  if (firstId) fillBindFields(sensors[firstId]);

  const bindSensor = document.getElementById("bind-sensor-id");
  if (bindSensor) {
    bindSensor.addEventListener("change", () => fillBindFields(sensors[bindSensor.value]));
  }
}

async function start() {
  // A failing /api/ports (no dongle driver installed, or the port list
  // enumeration throwing on this machine) must not take down every other
  // control on this page. This console is the operator's recovery
  // surface; the one call most likely to fail on a broken machine is
  // exactly the one that must not be allowed to sink the rest of it.
  try {
    await loadPortsAndProfiles();
  } catch (error) {
    setStatus("bind-status", `Gagal memuat daftar port/profil: ${error.message}`);
  }

  let state = null;
  let initialLanguage = "id";
  try {
    const stateResponse = await fetch("/api/state");
    state = await stateResponse.json();
    initialLanguage = state.language;
  } catch (error) {
    // Falls back to "id", the application default, if /api/state cannot
    // be reached either.
  }

  wireBind();
  wireInspector();
  wireConfig(initialLanguage);
  wireFieldCard();
  wirePuts();
  wireScenario();
  wireSession();

  // Pre-fill after the controls are wired and the port/profile option
  // lists are loaded, so the current selection lands on real options.
  if (state) prefillSettings(state);
}

start();
