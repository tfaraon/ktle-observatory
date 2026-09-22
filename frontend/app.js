/* Kati Thanda – Lake Eyre Observatory — front-end logic */

(function () {
  "use strict";

  const state = {
    data: null,
    site: null,        // selected site (object)
    map: null,
    markers: {},       // name -> L.marker
    baseKey: "topo",   // "topo" ou index dans imagery.layers
    baseLayer: null,
    imagery: null,     // GIBS layers (config.yaml or defaults)
    imgTime: "default", // "default" = most recent GIBS image
    wxMarkers: [],
    scenario: null,    // last match received
    fieldVar: null,    // displayed Delft3D field
    fieldSource: null, // "wave" ou "flow"
    fieldLayer: null,  // vertical layer index
    fieldTime: null,   // time-step index
    modelLayer: "none", // none | currents | hsign | wlength | period
    modelRaster: null, modelShafts: null, modelHeads: null,
    areaIdx: 0,
    modelData: null,
    field: null,          // grid used for the hover readout
    scaleMode: "auto",    // colour scale fitted to the scenario
    arrowPx: 16,       // arrow length in screen pixels
    staticMode: false, // no server: pre-rendered layers
    manifest: null, staticIndex: null, paramGrid: null,
    staticArrows: null, staticArrowsKey: null,
    methodsLoaded: false,
    loadedPages: {},
    ebird: null,
    birdsLayer: null,
    lastTab: { lake: "natural-history", catchment: "catchment", climate: "weather",
               "fauna-flora": "fauna-flora", culture: "culture" },
    rain: null, rivers: null, rainMap: null, flowMap: null, rainOverlay: null, flowStations: null, rrView: "sum7",
    birdsMap: null,
    inat: null,
    inatMap: null,
    catchmentMap: null,
    weather: null, area: null, extent: null,
    rosePeriod: "h24",
    canvasRenderer: null,
    timeline: [],      // BOM timestamps available for time travel
    timeIdx: 0,
    playTimer: null,
  };

  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const $ = (id) => document.getElementById(id);

  // ── Date helpers ─────────────────────────────────────────

  function parseUTC(iso) {
    // SWOT timestamps are UTC; the JSON carries no trailing "Z".
    return new Date(iso.endsWith("Z") ? iso : iso + "Z");
  }

  function fmtDate(iso) {
    const d = parseUTC(iso);
    const date = d.toLocaleDateString("en-GB",
      { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
    const time = d.toLocaleTimeString("en-GB",
      { hour: "2-digit", minute: "2-digit", timeZone: "UTC" });
    return `${date}, ${time} UTC`;
  }

  function fmtDateShort(iso) {
    return parseUTC(iso).toLocaleDateString("en-GB",
      { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
  }

  function relativeAge(iso) {
    const days = Math.floor((Date.now() - parseUTC(iso).getTime()) / 86400000);
    if (days <= 0) return "today";
    if (days === 1) return "yesterday";
    return `${days} days ago`;
  }

  // ── Data loading ─────────────────────────────────────────

  async function loadData() {
    const sources = [
      { url: "/api/wse", viaApi: true },
      { url: "data/swot_wse.json", viaApi: false },
    ];
    for (const s of sources) {
      try {
        const res = await fetch(s.url, { cache: "no-store" });
        if (res.ok) return { data: await res.json(), viaApi: s.viaApi };
      } catch (_) { /* try the next source */ }
    }
    return { data: null, viaApi: false };
  }

  // ── On-demand refresh ────────────────────────────────────

  function setRefreshStatus(text, isError) {
    const el = $("refresh-status");
    el.hidden = !text;
    el.textContent = text || "";
    el.classList.toggle("error", Boolean(isError));
  }

  async function startRefresh() {
    const btn = $("refresh-btn");
    btn.disabled = true;
    setRefreshStatus("Searching for new data…", false);
    try {
      const res = await fetch("/api/refresh", { method: "POST" });
      if (res.status === 409) {
        setRefreshStatus("An update is already running…", false);
      } else if (!res.ok) {
        throw new Error("HTTP " + res.status);
      }
      pollRefresh();
    } catch (e) {
      setRefreshStatus("Could not start the update (" + e.message + ").", true);
      btn.disabled = false;
    }
  }

  function pollRefresh() {
    const btn = $("refresh-btn");
    const timer = setInterval(async () => {
      let st;
      try {
        st = await (await fetch("/api/refresh/status", { cache: "no-store" })).json();
      } catch (_) { return; } // retry on the next tick
      if (st.running) {
        setRefreshStatus("Downloading and extracting…", false);
        return;
      }
      clearInterval(timer);
      if (st.last && st.last.ok) {
        setRefreshStatus(st.last.message + ", reloading…", false);
        setTimeout(() => location.reload(), 900);
      } else {
        setRefreshStatus(st.last ? st.last.message : "Update failed.", true);
        btn.disabled = false;
      }
    }, 3000);
  }

  // ── Map: base layers and NASA GIBS imagery ───────────────

  const GIBS_TEMPLATE =
    "https://gibs-{s}.earthdata.nasa.gov/wmts/epsg3857/best/" +
    "{layer}/default/{time}/{tileMatrixSet}/{z}/{y}/{x}.{fmt}";

  // Used when /api/config is unavailable (statically served site).
  const DEFAULT_IMAGERY = {
    matrix: "GoogleMapsCompatible_Level9",
    max_native_zoom: 9,
    format: "jpg",
    layers: [
      { label: "MODIS 7-2-1", layer: "MODIS_Terra_CorrectedReflectance_Bands721" },
      { label: "MODIS true colour", layer: "MODIS_Terra_CorrectedReflectance_TrueColor" },
      { label: "VIIRS 7-2-1", layer: "VIIRS_SNPP_CorrectedReflectance_BandsM11-I2-I1" },
    ],
  };

  async function loadImageryConfig() {
    if (state.manifest && state.manifest.imagery
        && state.manifest.imagery.layers) {
      return Object.assign({}, DEFAULT_IMAGERY, state.manifest.imagery);
    }
    try {
      const res = await fetch("/api/config", { cache: "no-store" });
      if (res.ok) {
        const cfg = (await res.json()).imagery;
        if (cfg && cfg.layers && cfg.layers.length) {
          return Object.assign({}, DEFAULT_IMAGERY, cfg);
        }
      }
    } catch (_) { /* static mode: fall back to defaults */ }
    return DEFAULT_IMAGERY;
  }

  function topoLayer() {
    return L.tileLayer("https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png", {
      maxZoom: 15,
      attribution: "© OpenTopoMap (CC-BY-SA), © OpenStreetMap",
    });
  }

  function gibsLayer(spec, time) {
    const img = state.imagery;
    return L.tileLayer(GIBS_TEMPLATE, {
      layer: spec.layer,
      tileMatrixSet: spec.matrix || img.matrix,
      fmt: spec.format || img.format || "jpg",
      time: time, // "default" = most recent available image
      tileSize: 256,
      subdomains: "abc",
      noWrap: true,
      maxNativeZoom: spec.max_native_zoom || img.max_native_zoom || 9,
      maxZoom: 15,
      bounds: [[-85.0511, -179.9999], [85.0511, 179.9999]],
      attribution: `${spec.layer}, NASA EOSDIS GIBS / Worldview`,
    });
  }

  function todayUTC() { return new Date().toISOString().slice(0, 10); }

  function shiftDay(iso, delta) {
    const d = new Date(iso + "T00:00:00Z");
    d.setUTCDate(d.getUTCDate() + delta);
    return d.toISOString().slice(0, 10);
  }

  function buildBaseButtons() {
    const seg = $("base-seg");
    state.imagery.layers.forEach((spec, i) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "seg-btn";
      b.dataset.base = String(i);
      b.textContent = spec.label || spec.layer;
      b.title = spec.layer;
      seg.appendChild(b);
    });
    seg.querySelectorAll(".seg-btn").forEach((b) =>
      b.addEventListener("click", () => setBase(b.dataset.base)));
  }

  function setBase(key) {
    state.baseKey = key;
    if (state.baseLayer) state.map.removeLayer(state.baseLayer);
    state.baseLayer = key === "topo"
      ? topoLayer()
      : gibsLayer(state.imagery.layers[+key], state.imgTime);
    state.baseLayer.addTo(state.map);

    document.querySelectorAll(".seg-btn").forEach((b) =>
      b.classList.toggle("active", b.dataset.base === key));
    $("imagery-controls").hidden = key === "topo";
  }

  function setImgTime(time) {
    state.imgTime = time; // "default" ou "YYYY-MM-DD"
    $("imagery-latest").classList.toggle("active", time === "default");
    $("imagery-date").value = time === "default" ? "" : time;
    $("imagery-next").disabled = time !== "default" && time >= todayUTC();
    if (state.baseKey !== "topo") setBase(state.baseKey); // reload the layer
  }

  function wireScaleToggle() {
    const btn = $("scale-toggle");
    if (!btn) return;
    // En statique l'image est déjà colorée : l'échelle ne peut plus
    // changer à l'affichage.
    if (state.staticMode) { btn.hidden = true; return; }
    btn.addEventListener("click", () => {
      state.scaleMode = state.scaleMode === "auto" ? "fixed" : "auto";
      btn.textContent = state.scaleMode === "auto" ? "Auto scale" : "Fixed scale";
      btn.classList.toggle("active", state.scaleMode === "auto");
      if (currentKey()) drawModelLayer();
    });
  }

  function wireMapBar() {
    const input = $("imagery-date");
    input.max = todayUTC();
    input.addEventListener("change", () => {
      if (input.value) setImgTime(input.value);
    });
    $("imagery-latest").addEventListener("click", () => setImgTime("default"));
    $("imagery-prev").addEventListener("click", () => {
      const cur = state.imgTime === "default" ? todayUTC() : state.imgTime;
      setImgTime(shiftDay(cur, -1));
    });
    $("imagery-next").addEventListener("click", () => {
      if (state.imgTime === "default") return;
      const next = shiftDay(state.imgTime, 1);
      setImgTime(next >= todayUTC() ? todayUTC() : next);
    });
  }

  function initMap(lake, sites) {
    const map = L.map("map", { scrollWheelZoom: false })
      .setView([lake.center.lat, lake.center.lon], lake.zoom || 8);
    state.map = map;
    state.canvasRenderer = L.canvas({ padding: 0.3 });
    buildBaseButtons();
    if (!state.staticMode || state.manifest) buildModelButtons();
    setBase("topo");
    map.on("zoomend", () => {
      if (state.modelData && state.modelLayer !== "none") {
        const d = state.modelData;
        drawArrows(d, d.vmax != null ? d.vmax : (d.zmax || 1));
      }
    });

    sites.forEach((site) => {
      const icon = L.divIcon({
        className: "marker-halo",
        html: '<div class="marker-dot"></div>',
        iconSize: [14, 14],
        iconAnchor: [7, 7],
      });
      const m = L.marker([site.lat, site.lon], { icon }).addTo(map);
      const latest = site.latest
        ? `${site.latest.wse.toFixed(2)} m, ${fmtDateShort(site.latest.date)}`
        : "no data";
      m.bindTooltip(`<strong>${site.name}</strong><br>${latest}`);
      m.on("click", () => selectSite(site.name));
      state.markers[site.name] = m;
    });

    wireMapBar();
    wireScaleToggle();
    wireHover(map);
  }

  function refreshMarkers() {
    Object.entries(state.markers).forEach(([name, m]) => {
      const el = m.getElement()?.querySelector(".marker-dot");
      if (el) el.classList.toggle("selected", state.site && name === state.site.name);
    });
  }

  // ── Staff gauge (SVG) ────────────────────────────────────

  function drawGauge(site) {
    const svg = $("gauge");
    svg.innerHTML = "";
    if (!site || !site.stats) return;

    const { min, max } = site.stats;
    const now = site.latest.wse;
    const lo = Math.floor((Math.min(min, now) - 0.4) * 2) / 2;
    const hi = Math.ceil((Math.max(max, now) + 0.4) * 2) / 2;

    const top = 16, bottom = 284, x = 44;
    const y = (v) => top + ((hi - v) / (hi - lo)) * (bottom - top);
    const NS = "http://www.w3.org/2000/svg";
    const el = (tag, attrs) => {
      const e = document.createElementNS(NS, tag);
      Object.entries(attrs).forEach(([k, v]) => e.setAttribute(k, v));
      return e;
    };

    // observed min–max band
    svg.appendChild(el("rect", {
      x: x, y: y(max), width: 18,
      height: Math.max(1, y(min) - y(max)), class: "gauge-range",
    }));

    // axe vertical
    svg.appendChild(el("line", { x1: x, y1: top, x2: x, y2: bottom, class: "gauge-axis" }));

    // ticks: minor every 0.5 m, major every 1 m and labelled
    const step = (hi - lo) > 6 ? 1 : 0.5;
    for (let v = lo; v <= hi + 1e-9; v += step) {
      const major = Math.abs(v - Math.round(v)) < 1e-9;
      const len = major ? 12 : 7;
      svg.appendChild(el("line", {
        x1: x - len, y1: y(v), x2: x, y2: y(v),
        class: major ? "gauge-tick" : "gauge-tick-minor",
      }));
      if (major) {
        const t = el("text", { x: x - 16, y: y(v) + 3.5,
          "text-anchor": "end", class: "gauge-label" });
        t.textContent = v.toFixed(0);
        svg.appendChild(t);
      }
    }

    // current level: line, marker and value (halite)
    svg.appendChild(el("line", {
      x1: x - 6, y1: y(now), x2: x + 30, y2: y(now), class: "gauge-now",
    }));
    svg.appendChild(el("path", {
      d: `M ${x + 30} ${y(now)} l 9 -5 v 10 z`, class: "gauge-now-marker",
    }));
    const label = el("text", {
      x: x + 44, y: y(now) + 3.5, class: "gauge-now-label",
    });
    label.textContent = now.toFixed(2);
    svg.appendChild(label);
  }

  // ── Lake surface area (Rai et al. 2026) ──────────────────

  async function loadExtent() {
    const sources = state.staticMode
      ? ["data/water_extent.json"]
      : ["/api/extent", "data/water_extent.json"];
    for (const url of sources) {
      try {
        const res = await fetch(url, { cache: "no-store" });
        if (res.ok) return await res.json();
      } catch (_) { /* source suivante */ }
    }
    return null;
  }

  async function loadArea() {
    const sources = state.staticMode
      ? ["data/lake_area.json"]
      : ["/api/area", "data/lake_area.json"];
    for (const url of sources) {
      try {
        const res = await fetch(url, { cache: "no-store" });
        if (res.ok) return await res.json();
      } catch (_) { /* try the next source */ }
    }
    return null;
  }

  function drawAreaChart() {
    const card = $("area-card");
    const el = $("area-chart");
    const a = state.area;
    if (!card || !el || !a || !a.series || !a.series.length) {
      if (card) card.hidden = true;
      return;
    }
    card.hidden = false;

    const solid = a.series.filter((r) => !r.partial);
    const partial = a.series.filter((r) => r.partial);
    const trace = (rows, name, open) => ({
      x: rows.map((r) => r.date), y: rows.map((r) => r.area_km2),
      error_y: {
        type: "data", visible: rows.some((r) => r.uncert_km2),
        array: rows.map((r) => r.uncert_km2 || 0),
        color: "#A8702D", thickness: 1, width: 3,
      },
      mode: "markers", type: "scatter", name,
      marker: {
        color: open ? "rgba(0,0,0,0)" : "#A8702D", size: 8,
        line: { color: "#A8702D", width: open ? 1.5 : 0 },
      },
      hovertemplate: "%{x|%d %b %Y}<br>%{y:,.0f} km²"
        + (open ? "<extra>partial pass</extra>" : "<extra></extra>"),
    });

    const traces = [];
    if (solid.length) traces.push(trace(solid, "Full pass", false));
    if (partial.length) traces.push(trace(partial, "Partial pass", true));

    Plotly.newPlot(el, traces, {
      margin: { l: 64, r: 18, t: 8, b: 42 },
      paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
      font: { family: "Archivo, sans-serif", size: 12, color: "#241F1A" },
      xaxis: { gridcolor: "#E9E3D6", tickfont: { family: "IBM Plex Mono" } },
      yaxis: {
        title: { text: "water area (km²)" }, rangemode: "tozero",
        gridcolor: "#E9E3D6", tickfont: { family: "IBM Plex Mono" },
      },
      showlegend: partial.length > 0,
      legend: { orientation: "h", y: 1.14, x: 0, font: { size: 10.5 } },
      hovermode: "closest",
    }, { displayModeBar: false, responsive: true });
  }

  // ── Plotly time series ───────────────────────────────────

  function drawChart(site) {
    const chart = $("chart");
    if (!site || !site.series.length) {
      Plotly.purge(chart);
      chart.innerHTML = '<p class="chart-note" style="padding:24px">No data for this site.</p>';
      return;
    }
    chart.innerHTML = "";

    const x = site.series.map((r) => r.date);
    const yv = site.series.map((r) => r.wse);
    const n = yv.length;

    const past = {
      x: x.slice(0, n - 1), y: yv.slice(0, n - 1),
      mode: "markers", type: "scatter", name: "SWOT observations",
      marker: { color: "#1E5F6B", size: 7, opacity: 0.85 },
      hovertemplate: "%{x|%d %b %Y}<br>WSE: %{y:.2f} m<extra></extra>",
    };
    const latest = {
      x: [x[n - 1]], y: [yv[n - 1]],
      mode: "markers", type: "scatter", name: "Latest observation",
      marker: { color: "#C4536B", size: 11,
                line: { color: "#FFFFFF", width: 1.5 } },
      hovertemplate: "%{x|%d %b %Y}<br>WSE: %{y:.2f} m<extra>latest</extra>",
    };

    const traces = [past, latest];

    Plotly.newPlot(chart, traces, {
      margin: { l: 58, r: 18, t: 8, b: 42 },
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "rgba(0,0,0,0)",
      font: { family: "Archivo, sans-serif", size: 12, color: "#241F1A" },
      xaxis: { gridcolor: "#E9E3D6", tickfont: { family: "IBM Plex Mono" } },
      yaxis: {
        title: { text: state.data.datum_label || "WSE (m)" },
        gridcolor: "#E9E3D6", zeroline: false,
        tickfont: { family: "IBM Plex Mono" },
      },
      showlegend: false,
      legend: { orientation: "h", y: 1.12, x: 0, font: { size: 10.5 } },
      hovermode: "closest",
    }, { displayModeBar: false, responsive: true });
  }

  // ── Animated counter ─────────────────────────────────────

  function setValue(target) {
    const node = $("wse-value");
    if (reduceMotion) { node.textContent = minus(target, 2); return; }
    const from = parseFloat(node.textContent.replace("\u2212", "-")) || target;
    const t0 = performance.now(), dur = 550;
    (function tick(t) {
      const p = Math.min(1, (t - t0) / dur);
      const eased = 1 - Math.pow(1 - p, 3);
      node.textContent = minus(from + (target - from) * eased, 2);
      if (p < 1) requestAnimationFrame(tick);
    })(t0);
  }

  // ── Site selection ───────────────────────────────────────

  function selectSite(name) {
    const site = state.data.sites.find((s) => s.name === name);
    if (!site) return;
    state.site = site;
    try { sessionStorage.setItem("lke-site", name); } catch (_) { /* ignore */ }
    $("site-select").value = name;

    if (site.latest) {
      setValue(site.latest.wse);
      $("latest-date").textContent = fmtDate(site.latest.date);
      $("latest-age").textContent = relativeAge(site.latest.date);
      $("series-span").textContent =
        `${site.stats.n} obs, ${site.stats.min.toFixed(2)} to ${site.stats.max.toFixed(2)} m`;
    } else {
      $("wse-value").textContent = "—";
      $("latest-date").textContent = "no data";
      $("latest-age").textContent = "—";
      $("series-span").textContent = "—";
    }
    $("site-coords").textContent =
      `${site.lat.toFixed(3)}, ${site.lon.toFixed(3)}`;
    $("chart-title").textContent = `SWOT water surface elevation at ${site.name}`;

    drawGauge(site);
    drawChart(site);
    refreshMarkers();
    if (state.map) state.map.panTo([site.lat, site.lon]);
  }

  // ── BOM weather ──────────────────────────────────────────

  function bomAge(utc) {
    // BOM timestamp: "YYYYMMDDHHMMSS" in UTC
    if (!utc || utc.length < 14) return null;
    const d = Date.UTC(+utc.slice(0, 4), +utc.slice(4, 6) - 1, +utc.slice(6, 8),
                       +utc.slice(8, 10), +utc.slice(10, 12));
    const min = Math.round((Date.now() - d) / 60000);
    if (min < 60) return `${Math.max(0, min)} min ago`;
    const h = Math.round(min / 60);
    return h < 48 ? `${h} h ago` : `${Math.round(h / 24)} days ago`;
  }

  function windArrow(deg) {
    // Arrow points in the direction the wind is blowing towards
    // (BOM reports where it comes from, hence +180°).
    if (deg === null || deg === undefined) {
      return '<svg width="20" height="20" viewBox="0 0 20 20">'
           + '<circle cx="10" cy="10" r="4" fill="none" stroke="#7C7466"/></svg>';
    }
    return '<svg width="20" height="20" viewBox="0 0 20 20">'
         + `<g transform="rotate(${deg + 180} 10 10)">`
         + '<path class="arr" d="M10 2 L14.5 16 L10 12.8 L5.5 16 Z"/></g></svg>';
  }

  function fmtNum(v, unit, digits) {
    return v === null || v === undefined
      ? "—" : `${v.toFixed(digits || 0)}${unit || ""}`;
  }

  function stationCard(st) {
    if (!st.ok || !st.latest) {
      return `<div class="wx-card"><div class="wx-head">`
           + `<span class="wx-name">${st.name}</span></div>`
           + `<p class="wx-error">Unavailable${st.error ? ": " + st.error : ""}</p></div>`;
    }
    const l = st.latest;
    const dir = l.wind_dir || "variable";
    const age = bomAge(l.utc) || "";
    const ageTxt = st.stale ? `${age}, last known reading` : age;
    return `<div class="wx-card">
      <div class="wx-head">
        <span class="wx-name">${st.name}</span>
        <span class="wx-age${st.stale ? " warn" : ""}">${ageTxt}</span>
      </div>
      <div class="wx-wind">
        <span class="wx-arrow">${windArrow(l.wind_dir_deg)}</span>
        <span>
          <b class="wx-wind-main">${dir} ${fmtNum(l.wind_spd_kmh, " km/h")}</b>
          <span class="wx-gust">gusts ${fmtNum(l.gust_kmh, " km/h")}</span>
        </span>
      </div>
      <p class="wx-meta">
        <span><b>${fmtNum(l.air_temp, " °C", 1)}</b> air</span>
        <span><b>${fmtNum(l.rel_hum, " %")}</b> RH</span>
        <span><b>${fmtNum(l.press_hpa, " hPa", 1)}</b></span>
        <span><b>${fmtNum(l.rain_since_9am, " mm", 1)}</b> since 9am</span>
      </p>
    </div>`;
  }

  function addWeatherMarkers(stations) {
    state.wxMarkers.forEach((m) => state.map.removeLayer(m));
    state.wxMarkers = [];
    if (!state.map) return;
    stations.forEach((st) => {
      if (!st.lat || !st.lon) return;
      const icon = L.divIcon({
        className: "marker-halo", html: '<div class="marker-wx"></div>',
        iconSize: [11, 11], iconAnchor: [5.5, 5.5],
      });
      const l = st.latest;
      const txt = st.ok && l
        ? `${l.wind_dir || "variable"} ${fmtNum(l.wind_spd_kmh, " km/h")}, `
          + `${fmtNum(l.air_temp, " °C", 1)}`
        : "unavailable";
      const m = L.marker([st.lat, st.lon], { icon }).addTo(state.map);
      m.bindTooltip(`<strong>${st.name}</strong><br>${txt}`);
      state.wxMarkers.push(m);
    });
  }

  const WX_COLOURS = ["#1E5F6B", "#A8702D", "#C4536B", "#4E7A3E"];

  function bomToDate(utc) {
    if (!utc || utc.length < 14) return null;
    return new Date(Date.UTC(
      +utc.slice(0, 4), +utc.slice(4, 6) - 1, +utc.slice(6, 8),
      +utc.slice(8, 10), +utc.slice(10, 12)));
  }

  function drawWeatherHistory(stations, hours) {
    const box = $("weather-history");
    const traces = [];
    stations.forEach((st, i) => {
      const hist = (st.history || []).filter((r) => r.wind_spd_kmh !== null);
      if (hist.length < 2) return;
      traces.push({
        type: "scatter", mode: "lines", name: st.name,
        x: hist.map((r) => bomToDate(r.utc)),
        y: hist.map((r) => r.wind_spd_kmh),
        line: { color: WX_COLOURS[i % WX_COLOURS.length], width: 1.6 },
        customdata: hist.map((r) => [r.gust_kmh, r.wind_dir || "—"]),
        hovertemplate: "%{x|%a %H:%M}<br>%{y:.0f} km/h"
          + ", gusts %{customdata[0]:.0f}"
          + ", %{customdata[1]}<extra>" + st.name + "</extra>",
      });
    });

    if (!traces.length) { box.hidden = true; return; }
    box.hidden = false;
    Plotly.newPlot(box, traces, {
      margin: { l: 48, r: 12, t: 6, b: 34 },
      height: 190,
      paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
      font: { family: "Archivo, sans-serif", size: 11, color: "#241F1A" },
      xaxis: { gridcolor: "#E9E3D6", tickfont: { family: "IBM Plex Mono" } },
      yaxis: {
        title: { text: "wind (km/h)" }, rangemode: "tozero",
        gridcolor: "#E9E3D6", tickfont: { family: "IBM Plex Mono" },
      },
      legend: { orientation: "h", y: 1.18, x: 0, font: { size: 10.5 } },
      hovermode: "closest",
    }, { displayModeBar: false, responsive: true });
  }

  // ── Wind roses ───────────────────────────────────────────
  //
  // Day and night follow the actual solar elevation at the lake, not
  // clock hours: the split is meant to separate the well-mixed daytime
  // boundary layer from the decoupled night-time one.

  const ROSE_COLOURS = ["#BFD9DD", "#7FB3BC", "#3F8C9B", "#1E5F6B", "#0E3C45"];

  function roseTraces(rose) {
    return rose.series.map((row, k) => ({
      type: "barpolar", r: row, theta: rose.sectors,
      name: rose.labels[k] + " km/h",
      marker: { color: ROSE_COLOURS[k], line: { color: "#FFF", width: 0.5 } },
      hovertemplate: "%{theta}, %{r:.1f} %<extra>"
        + rose.labels[k] + " km/h</extra>",
    })).filter((t) => t.r.some((v) => v > 0));
  }

  function drawRose(cell, station, records) {
    const rose = WindRose.binRose(records);
    const title = document.createElement("p");
    title.className = "rose-title";
    cell.appendChild(title);

    if (!rose.total) {
      title.textContent = station.name;
      const empty = document.createElement("div");
      empty.className = "rose-empty";
      empty.textContent = "no observations in this period";
      cell.appendChild(empty);
      return 0;
    }
    title.textContent = `${station.name}, ${rose.total} obs`
      + (rose.calm > 0 ? `, ${rose.calmPercent.toFixed(0)} % calm` : "");

    const plot = document.createElement("div");
    plot.className = "rose-plot";
    cell.appendChild(plot);

    Plotly.newPlot(plot, roseTraces(rose), {
      // autosize + resize différé : Plotly mesure son conteneur au
      // moment du tracé, et une largeur non encore établie le fait
      // retomber sur 700 px, qui débordent de la cellule.
      autosize: true,
      margin: { l: 26, r: 26, t: 10, b: 18 },
      height: 240,
      paper_bgcolor: "rgba(0,0,0,0)",
      font: { family: "Archivo, sans-serif", size: 9, color: "#241F1A" },
      polar: {
        bgcolor: "rgba(0,0,0,0)",
        hole: 0.06,
        radialaxis: { ticksuffix: "%", angle: 45, nticks: 4,
                      tickfont: { size: 8, color: "#7C7466" },
                      gridcolor: "#E9E3D6", linecolor: "#E9E3D6" },
        angularaxis: { direction: "clockwise", rotation: 90,
                       tickfont: { size: 8.5 }, gridcolor: "#E9E3D6",
                       linecolor: "#E4DDD0" },
      },
      barmode: "stack",
      showlegend: false,
    }, { displayModeBar: false, responsive: true });
    return rose.total;
  }

  function roseLegend() {
    return WindRose.SPEED_LABELS.map((lab, k) =>
      `<span class="rose-key"><i style="background:${ROSE_COLOURS[k]}"></i>`
      + `${lab}</span>`).join("") + '<span class="rose-key-unit">km/h</span>';
  }

  function drawWindRoses() {
    const wx = state.weather;
    const block = $("rose-block");
    if (!wx || !wx.stations || typeof WindRose === "undefined") {
      block.hidden = true;
      return;
    }
    const stations = wx.stations.filter((s) => s.ok && (s.history || []).length);
    if (!stations.length) { block.hidden = true; return; }
    block.hidden = false;

    const centre = (state.data && state.data.lake && state.data.lake.center)
      || (state.manifest && state.manifest.lake && state.manifest.lake.center)
      || { lat: -28.9, lon: 137.35 };

    const grid = $("rose-grid");
    grid.innerHTML = "";
    let shown = 0;
    stations.forEach((st) => {
      const cell = document.createElement("div");
      cell.className = "rose-cell";
      grid.appendChild(cell);
      shown += drawRose(cell, st,
        WindRose.selectPeriod(st.history, state.rosePeriod,
                              centre.lat, centre.lon));
    });
    $("rose-legend").innerHTML = roseLegend();

    // Une fois toutes les cellules posées, la grille a sa largeur
    // définitive : c'est là que Plotly peut mesurer juste.
    requestAnimationFrame(() => {
      grid.querySelectorAll(".rose-plot").forEach((el) => {
        if (el.data) Plotly.Plots.resize(el);
      });
    });

    // L'archive se construit au fil des relevés : dire franchement
    // ce que la période couvre réellement évite de sur-interpréter
    // une rose bâtie sur quelques heures.
    const span = archiveSpanHours(stations);
    const spec = WindRose.PERIODS[state.rosePeriod] || {};
    const note = $("rose-note");
    const bits = [`direction the wind blows from, ${shown} observations`];
    if (span !== null) bits.push(`archive spans ${span.toFixed(0)} h`);
    const short = spec.hours && span !== null && span < spec.hours * 0.9;
    if (short) {
      bits.push(`this period needs ${spec.hours} h; it will fill in as `
        + `observations accumulate`);
    }
    note.textContent = bits.join(", ");
    note.classList.toggle("warn", Boolean(short));
  }

  function archiveSpanHours(stations) {
    let lo = null, hi = null;
    stations.forEach((st) => (st.history || []).forEach((r) => {
      const d = WindRose.obsDate(r);
      if (!d) return;
      if (lo === null || d < lo) lo = d;
      if (hi === null || d > hi) hi = d;
    }));
    return lo && hi ? (hi - lo) / 3600000 : null;
  }

  function buildRoseButtons() {
    const seg = $("rose-seg");
    if (!seg || seg.childElementCount || typeof WindRose === "undefined") return;
    Object.entries(WindRose.PERIODS).forEach(([id, spec]) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "seg-btn" + (id === state.rosePeriod ? " active" : "");
      b.dataset.period = id;
      b.textContent = spec.label;
      seg.appendChild(b);
    });
    seg.querySelectorAll(".seg-btn").forEach((b) =>
      b.addEventListener("click", () => {
        state.rosePeriod = b.dataset.period;
        seg.querySelectorAll(".seg-btn").forEach((o) =>
          o.classList.toggle("active", o === b));
        drawWindRoses();
      }));
  }

  async function loadWeather() {
    const strip = $("weather-strip");
    let wx;
    try {
      let res = state.staticMode
        ? await fetch("data/weather.json", { cache: "no-store" })
        : await fetch("/api/weather", { cache: "no-store" });
      if (!res.ok && !state.staticMode) {
        res = await fetch("data/weather.json", { cache: "no-store" });
      }
      if (!res.ok) throw new Error("HTTP " + res.status);
      wx = await res.json();
    } catch (e) {
      strip.innerHTML = '<p class="weather-empty mono">BOM observations '
        + 'unavailable (the Flask server must be running).</p>';
      return;
    }
    if (!wx.stations || !wx.stations.length) {
      strip.innerHTML = '<p class="weather-empty mono">No stations '
        + 'configured (<code>weather</code> section of config.yaml).</p>';
      return;
    }

    state.weather = wx;
    refreshDownloadButtons();
    strip.innerHTML = wx.stations.map(stationCard).join("");

    const note = $("weather-updated");
    const parts = [];
    if (wx.demo) parts.push("demonstration data");
    if (wx.stale) parts.push("cached, BOM unreachable");
    parts.push("fetched " + fmtDate(wx.fetched_at.replace("Z", "")));
    note.textContent = parts.join(", ");
    note.classList.toggle("warn", Boolean(wx.demo || wx.stale));

    const okStations = wx.stations.filter((s) => s.ok);
    drawWeatherHistory(okStations, wx.history_hours || 48);
    buildRoseButtons();
    drawWindRoses();
    buildTimeline(okStations);
    addWeatherMarkers(wx.stations);
  }

  // ══════════════════════════════════════════════════════════
  // Mode statique (GitHub Pages) : aucun serveur.
  //
  // Les couches sont pré-calculées (PNG + flèches), et l'appariement
  // des scénarios — une recherche du plus proche voisin sur quatre
  // paramètres — est refait ici, avec exactement la même métrique que
  // le serveur : normalisation par l'étendue et direction circulaire.
  // ══════════════════════════════════════════════════════════

  async function loadManifest() {
    try {
      const res = await fetch("manifest.json", { cache: "no-store" });
      if (res.ok) return await res.json();
    } catch (_) { /* pas de site statique */ }
    return null;
  }

  async function loadStaticIndex() {
    const res = await fetch("data/scenarios.json", { cache: "no-store" });
    if (!res.ok) throw new Error("scenario index unavailable");
    return await res.json();
  }

  function circularDelta(a, b) {
    return ((a - b + 180) % 360 + 360) % 360 - 180;
  }

  function paramGrid(scenarios) {
    const grid = {};
    ["wind_speed", "wind_dir", "wlvl", "salinity"].forEach((k) => {
      const set = new Set();
      scenarios.forEach((s) => {
        if (s.params[k] !== undefined) set.add(s.params[k]);
      });
      if (set.size) grid[k] = Array.from(set).sort((a, b) => a - b);
    });
    return grid;
  }

  function paramScales(grid) {
    const scales = {};
    Object.entries(grid).forEach(([k, vals]) => {
      if (k === "wind_dir") { scales[k] = 180; return; }
      const span = vals.length > 1 ? vals[vals.length - 1] - vals[0] : 0;
      scales[k] = span > 0 ? span : 1;
    });
    return scales;
  }

  function matchStatic(scenarios, grid, target, weights, wlvlMode) {
    const scales = paramScales(grid);

    // Même règle que le serveur : ne jamais retenir un scénario dont le
    // niveau dépasse celui observé, sous peine de simuler plus d'eau
    // qu'il n'y en a.
    let pool = scenarios, capped = false;
    if (wlvlMode === "down" && target.wlvl !== undefined
        && target.wlvl !== null) {
      const below = scenarios.filter((s) => s.params.wlvl !== undefined
        && s.params.wlvl <= target.wlvl + 1e-6);
      if (below.length) { pool = below; capped = true; }
    }
    const deltasOf = (p) => {
      const d = {};
      Object.entries(target).forEach(([k, v]) => {
        if (v === null || v === undefined || p[k] === undefined) return;
        d[k] = k === "wind_dir" ? circularDelta(v, p[k]) : v - p[k];
      });
      return d;
    };
    const distance = (p) => {
      let total = 0;
      Object.entries(deltasOf(p)).forEach(([k, d]) => {
        const w = (weights && weights[k] !== undefined) ? weights[k] : 1;
        total += Math.pow((w * d) / (scales[k] || 1), 2);
      });
      return Math.sqrt(total);
    };

    let best = pool[0], bestD = Infinity;
    pool.forEach((s) => {
      const d = distance(s.params);
      if (d < bestD) { bestD = d; best = s; }
    });

    const deltas = {}, envelope = {}, warnings = [];
    const labels = state.staticIndex.labels || {};
    const units = state.staticIndex.units || {};
    Object.entries(deltasOf(best.params)).forEach(([k, d]) => {
      deltas[k] = Math.round(d * 1000) / 1000;
    });
    Object.entries(target).forEach(([k, v]) => {
      if (v === null || v === undefined || best.params[k] === undefined) return;
      const vals = grid[k] || [];
      const unit = units[k] ? " " + units[k] : "";
      if (k === "wind_dir" || !vals.length) { envelope[k] = "in"; return; }
      if (v < vals[0]) {
        envelope[k] = "below";
        warnings.push(`${labels[k] || k} (${v} ${unit}) below the simulated `
          + `range [${vals[0]} – ${vals[vals.length - 1]}${unit}]`);
      } else if (v > vals[vals.length - 1]) {
        envelope[k] = "above";
        warnings.push(`${labels[k] || k} (${v}${unit}) above the simulated `
          + `range [${vals[0]} – ${vals[vals.length - 1]}${unit}]`);
      } else {
        envelope[k] = "in";
      }
    });

    return {
      scenario: { key: best.key, params: best.params, files: {} },
      deltas, distance: Math.round(bestD * 1000) / 1000,
      wlvl_capped: capped, envelope, warnings, alternatives: [],
    };
  }

  function bomDate(utc) {
    if (!utc || utc.length < 14) return null;
    return new Date(Date.UTC(+utc.slice(0, 4), +utc.slice(4, 6) - 1,
      +utc.slice(6, 8), +utc.slice(8, 10), +utc.slice(10, 12)));
  }

  function staticConditions(at) {
    // Mêmes conversions que le serveur : km/h -> m/s, convention de
    // direction, décalage de datum.
    const cfg = (state.manifest && state.manifest.matching) || {};
    const target = {}, origin = {};

    const wx = state.weather;
    if (wx && wx.stations) {
      const ok = wx.stations.filter((s) => s.ok && s.latest);
      const st = ok.find((s) => s.name === cfg.wind_station) || ok[0];
      if (st) {
        let obs = st.latest;
        if (at) {
          const hist = (st.history || []).filter((r) => r.utc);
          if (hist.length) {
            obs = hist.reduce((b, r) => {
              const db = Math.abs(bomDate(b.utc) - at);
              const dr = Math.abs(bomDate(r.utc) - at);
              return dr < db ? r : b;
            }, hist[hist.length - 1]);
          }
        }
        if (obs.wind_spd_kmh !== null && obs.wind_spd_kmh !== undefined) {
          target.wind_speed = Math.round(obs.wind_spd_kmh / 3.6 * 100) / 100;
        }
        if (obs.wind_dir_deg !== null && obs.wind_dir_deg !== undefined) {
          let d = obs.wind_dir_deg;
          if (cfg.wind_dir_convention === "to") d = (d + 180) % 360;
          target.wind_dir = d;
        }
        origin.wind = { station: st.name, utc: obs.utc,
                        wind_dir: obs.wind_dir,
                        wind_spd_kmh: obs.wind_spd_kmh,
                        stale: Boolean(st.stale) };
      }
    }

    const data = state.data;
    if (data && data.sites) {
      const withData = data.sites.filter((s) => s.latest);
      const site = withData.find((s) => s.name === cfg.wlvl_site)
        || withData[0];
      if (site) {
        let obs = site.latest;
        if (at) {
          const past = site.series.filter(
            (r) => new Date(r.date + "Z") <= at);
          if (past.length) obs = past[past.length - 1];
        }
        target.wlvl = Math.round((obs.wse + (cfg.wlvl_offset || 0)) * 1000)
          / 1000;
        origin.wlvl = { site: site.name, date: obs.date, wse: obs.wse };
      }
    }

    if (cfg.salinity !== null && cfg.salinity !== undefined) {
      target.salinity = cfg.salinity;
      origin.salinity = { source: "config" };
    }
    return { target, origin };
  }

  // ── Delft3D scenario ─────────────────────────────────────

  function fmtParam(key, v, units) {
    if (v === null || v === undefined) return "—";
    const u = units[key] ? " " + units[key] : "";
    const digits = key === "wind_dir" ? 0 : (key === "wlvl" ? 2 : 1);
    return v.toFixed(digits) + u;
  }

  function matchItem(key, target, params, deltas, envelope, labels, units) {
    const out = envelope[key] && envelope[key] !== "in";
    const d = deltas[key];
    const dTxt = d === undefined ? ""
      : `offset ${d > 0 ? "+" : ""}${d.toFixed(key === "wind_dir" ? 0 : 2)}`
        + (units[key] ? " " + units[key] : "");
    return `<div class="match-item${out ? " out" : ""}">
      <span class="match-label">${labels[key] || key}</span>
      <span class="match-values">
        <span class="match-obs">${fmtParam(key, target[key], units)}</span>
        <span class="match-arrow">→</span>
        <span class="match-sim">${fmtParam(key, params[key], units)}</span>
      </span>
      <span class="match-delta">${out ? "outside simulated range, " : ""}${dTxt}</span>
    </div>`;
  }

  function originNote(origin, demo, at) {
    const bits = [];
    if (at) {
      const d = new Date(at);
      bits.push("conditions at " + d.toLocaleString("en-GB", {
        weekday: "short", day: "numeric", month: "short",
        hour: "2-digit", minute: "2-digit", timeZone: "UTC" }) + " UTC");
    }
    if (origin.wind) {
      const w = origin.wind;
      bits.push(`wind ${w.station} (${w.wind_dir || "?"} `
        + `${w.wind_spd_kmh != null ? w.wind_spd_kmh.toFixed(0) : "?"} km/h`
        + `${w.stale ? ", last known reading" : ""})`);
    }
    if (origin.wlvl) {
      bits.push(`level ${origin.wlvl.site} `
        + `${origin.wlvl.wse.toFixed(2)} m on ${fmtDateShort(origin.wlvl.date)}`);
    }
    if (demo) bits.push("demo index");
    return bits.join(", ");
  }

  // ── Model layers on the map (Alplakes-style overlay) ─────
  //
  // The model works in projected metres; the server resamples each
  // field onto a regular lon/lat grid so it can be laid straight over
  // the base map, and returns arrows as position + true bearing.

  const TURBO = [
    [0.00, [48, 18, 59]], [0.13, [65, 69, 171]], [0.25, [70, 117, 237]],
    [0.38, [57, 162, 252]], [0.50, [27, 207, 212]], [0.63, [98, 252, 107]],
    [0.75, [210, 233, 53]], [0.88, [254, 155, 45]], [0.96, [234, 74, 19]],
    [1.00, [122, 4, 3]],
  ];

  function turboColour(t) {
    t = Math.max(0, Math.min(1, t));
    for (let i = 1; i < TURBO.length; i++) {
      if (t <= TURBO[i][0]) {
        const [t0, c0] = TURBO[i - 1], [t1, c1] = TURBO[i];
        const f = (t - t0) / (t1 - t0 || 1);
        return [0, 1, 2].map((k) => Math.round(c0[k] + f * (c1[k] - c0[k])));
      }
    }
    return TURBO[TURBO.length - 1][1];
  }

  function rasterDataURL(z, vmin, vmax) {
    const ny = z.length, nx = z[0].length;
    const cv = document.createElement("canvas");
    cv.width = nx; cv.height = ny;
    const ctx = cv.getContext("2d");
    const img = ctx.createImageData(nx, ny);
    const span = (vmax - vmin) || 1;
    for (let iy = 0; iy < ny; iy++) {
      // Latitude increases upwards, canvas rows downwards.
      const row = z[ny - 1 - iy];
      for (let ix = 0; ix < nx; ix++) {
        const o = 4 * (iy * nx + ix);
        const val = row[ix];
        if (val === null || val === undefined) { img.data[o + 3] = 0; continue; }
        const [r, g, b] = turboColour((val - vmin) / span);
        img.data[o] = r; img.data[o + 1] = g; img.data[o + 2] = b;
        img.data[o + 3] = 205;
      }
    }
    ctx.putImageData(img, 0, 0);
    return cv.toDataURL();
  }

  function arrowShapes(arrows, refLen, scaled, vmax) {
    const shafts = [], heads = [];
    for (let i = 0; i < arrows.lat.length; i++) {
      const mag = arrows.value[i];
      const f = scaled ? Math.min(1.3, (mag / (vmax || 1))) : 0.85;
      const len = refLen * Math.max(0.18, f);
      const br = (arrows.bearing[i] * Math.PI) / 180;
      const lat = arrows.lat[i], lon = arrows.lon[i];
      const kx = 1 / Math.max(0.2, Math.cos((lat * Math.PI) / 180));
      const dLat = Math.cos(br) * len;
      const dLon = Math.sin(br) * len * kx;
      const lat0 = lat - dLat / 2, lon0 = lon - dLon / 2;
      const lat1 = lat0 + dLat, lon1 = lon0 + dLon;
      // Head base, set back along the shaft
      const hb = 0.42;
      const bLat = lat1 - dLat * hb, bLon = lon1 - dLon * hb;
      const pLat = -dLon * hb * 0.5 / kx / kx, pLon = dLat * hb * 0.5 * kx;
      shafts.push([[lat0, lon0], [bLat, bLon]]);
      heads.push([[bLat + pLat, bLon + pLon], [lat1, lon1],
                  [bLat - pLat, bLon - pLon]]);
    }
    return { shafts, heads };
  }

  const LAYER_LABELS = {
    currents: "Currents", hsign: "Wave height",
    wlength: "Wavelength", period: "Period",
  };

  function showMapMessage(text) {
    const el = $("map-message");
    if (!el) return;
    el.textContent = text;
    el.hidden = false;
  }

  function hideMapMessage() {
    const el = $("map-message");
    if (el) el.hidden = true;
  }

  // ── Value under the cursor ───────────────────────────────
  //
  // The grid is kept client-side so the readout works without a round
  // trip. Behind Flask the full field is available; the static site
  // carries a coarser grid, exported alongside the image.

  function sampleField(lat, lon) {
    const f = state.field;
    if (!f || !f.v) return null;
    const fy = (lat - f.lat0) / ((f.lat1 - f.lat0) || 1);
    const fx = (lon - f.lon0) / ((f.lon1 - f.lon0) || 1);
    if (fy < 0 || fy > 1 || fx < 0 || fx > 1) return null;
    const iy = Math.round(fy * (f.n_y - 1));
    const ix = Math.round(fx * (f.n_x - 1));
    const v = f.v[iy * f.n_x + ix];
    return (v === null || v === undefined) ? null : v;
  }

  function setField(d) {
    // Le champ complet (Flask) ou la grille allégée (statique).
    if (d && d.z && d.lat && d.lon) {
      state.field = {
        n_x: d.lon.length, n_y: d.lat.length,
        lat0: d.lat[0], lat1: d.lat[d.lat.length - 1],
        lon0: d.lon[0], lon1: d.lon[d.lon.length - 1],
        v: [].concat.apply([], d.z), coarse: false,
      };
    } else if (d && d.coarse) {
      state.field = Object.assign({ coarse: true }, d.coarse);
    } else {
      state.field = null;
    }
  }

  function showReadout(lat, lon) {
    const el = $("map-readout");
    if (!el) return;
    const d = state.modelData;
    if (!d || !state.field) { el.hidden = true; return; }
    const v = sampleField(lat, lon);
    if (v === null) { el.hidden = true; return; }
    const digits = Math.abs(v) < 1 ? 3 : 2;
    el.innerHTML = `<b>${v.toFixed(digits)}</b> ${d.units || ""}`
      + `<span class="dim">, ${d.label}</span>`
      + (state.field.coarse ? '<span class="dim">, nearest sample</span>' : "");
    el.hidden = false;
  }

  function wireHover(map) {
    map.on("mousemove", (e) => showReadout(e.latlng.lat, e.latlng.lng));
    map.on("mouseout", () => { const el = $("map-readout"); if (el) el.hidden = true; });
  }

  function clearModelLayer() {
    state.field = null;
    const ro = $("map-readout");
    if (ro) ro.hidden = true;
    state.modelData = null;
    refreshDownloadButtons();
    ["modelRaster", "modelShafts", "modelHeads"].forEach((k) => {
      if (state[k]) { state.map.removeLayer(state[k]); state[k] = null; }
    });
    $("map-legend").hidden = true;
  }

  function showLegend(d, lo, hi) {
    const bar = document.querySelector(".legend-bar");
    if (bar) bar.style.background = "";
    $("legend-title").textContent = `${d.label}${d.units ? " (" + d.units + ")" : ""}`;
    $("legend-min").textContent = lo.toFixed(hi < 2 ? 2 : 0);
    $("legend-max").textContent = hi.toFixed(hi < 2 ? 2 : 0);
    $("map-legend").hidden = false;
  }

  async function drawModelLayer() {
    if (!state.map) return;
    if (state.modelLayer === "none") {
      clearModelLayer();
      hideMapMessage();
      $("model-controls").hidden = true;
      return;
    }
    // L'étendue en eau vient de SWOT, pas d'un scénario apparié.
    if (state.modelLayer === "water") return drawWaterExtent();
    if (!state.scenario) {
      clearModelLayer();
      hideMapMessage();
      $("model-controls").hidden = true;
      return;
    }
    const key = currentKey();
    if (!key) return;

    let d;
    try {
      d = state.staticMode
        ? await staticLayer(key)
        : await apiLayer(key);
    } catch (e) {
      clearModelLayer();
      // Le panneau des scénarios est loin sous la carte : le message
      // doit apparaître là où l'utilisateur regarde.
      showMapMessage(`${LAYER_LABELS[state.modelLayer] || "Layer"} `
        + `unavailable: ${e.message}`);
      setModelNote("Layer unavailable: " + e.message, true);
      return;
    }
    hideMapMessage();

    clearModelLayer();
    const lo = d.vmin != null ? d.vmin : (d.zmin || 0);
    const hi = d.vmax != null ? d.vmax : (d.zmax || 1);

    // En statique l'image est déjà colorée côté serveur d'export ;
    // sinon elle est peinte ici à partir du champ reçu.
    const src = d.image ? d.image : rasterDataURL(d.z, lo, hi);
    state.modelRaster = L.imageOverlay(
      src, d.bounds, { opacity: 1, interactive: false }
    ).addTo(state.map);

    state.modelData = d;
    setField(d);
    refreshDownloadButtons();
    drawArrows(d, hi);
    showLegend(d, lo, hi);
    buildModelSelectors(d);
    if (!d.zmax) {
      showMapMessage(`${d.label} is zero everywhere in this scenario `
        + `(calm conditions); the lake outline is still shown.`);
    }
    setModelNote(`${d.label}, ${d.n_arrows} arrows`
      + (d.warning ? ", " + d.warning : ""), Boolean(d.warning));
  }

  // Arrow length is set in screen pixels rather than in degrees:
  // a geographic length would balloon as soon as the map is zoomed in.
  function degreesPerPixel() {
    const b = state.map.getBounds();
    const h = state.map.getSize().y || 1;
    return (b.getNorth() - b.getSouth()) / h;
  }

  function drawArrows(d, hi) {
    ["modelShafts", "modelHeads"].forEach((k) => {
      if (state[k]) { state.map.removeLayer(state[k]); state[k] = null; }
    });
    if (d.n_arrows) {
      const refLen = state.arrowPx * degreesPerPixel();
      const { shafts, heads } = arrowShapes(d.arrows, refLen,
                                            d.arrow_scaled, hi);
      state.modelShafts = L.polyline(shafts, {
        color: "#FFFFFF", weight: 1.2, opacity: 0.95, interactive: false,
        renderer: state.canvasRenderer,
      }).addTo(state.map);
      state.modelHeads = L.polygon(heads, {
        color: "#FFFFFF", weight: 0.5, fillColor: "#FFFFFF",
        fillOpacity: 1, interactive: false, renderer: state.canvasRenderer,
      }).addTo(state.map);
    }
  }

  async function apiLayer(key) {
    const url = "/api/scenario/maplayer?key=" + encodeURIComponent(key)
      + "&layer=" + encodeURIComponent(state.modelLayer)
      + (state.fieldLayer !== null ? "&layer_index=" + state.fieldLayer : "")
      + (state.fieldTime !== null ? "&time=" + state.fieldTime : "")
      + "&scale=" + state.scaleMode;
    const res = await fetch(url, { cache: "no-store" });
    const d = await res.json();
    if (!res.ok) throw new Error(d.message || d.error);
    return d;
  }

  // Reconstruit la même charge utile que l'API à partir des fichiers
  // pré-calculés : image déjà colorée, flèches sur grille régulière.
  async function staticLayer(key) {
    const man = state.manifest;
    const spec = man.layers.find((l) => l.id === state.modelLayer);
    if (!spec) throw new Error("unknown layer");
    const vertical = spec.mode === "vector";
    const li = vertical ? (state.fieldLayer || 0) : 0;
    const fileId = vertical ? `${spec.id}_${li}` : spec.id;

    if (state.staticArrowsKey !== key) {
      const res = await fetch(`layers/${encodeURIComponent(key)}.json`,
                              { cache: "force-cache" });
      if (!res.ok) throw new Error("no pre-rendered layers for this scenario");
      state.staticArrows = await res.json();
      state.staticArrowsKey = key;
    }
    const packed = state.staticArrows[fileId];
    if (!packed) throw new Error("layer not pre-rendered for this scenario");

    const bounds = man.bounds[spec.source];
    // Les flèches suivent `extent` (emprise des points), pas `bounds`
    // (cadre de l'image, élargi d'une demi-maille).
    const ext = (man.extent || {})[spec.source] || bounds;
    const n = man.n_arrows;
    const [lat0, lon0] = ext[0], [lat1, lon1] = ext[1];
    const arrows = { lat: [], lon: [], bearing: [], value: [] };
    packed.i.forEach((flat, k) => {
      const iy = Math.floor(flat / n), ix = flat % n;
      arrows.lat.push(lat0 + (lat1 - lat0) * (iy / (n - 1)));
      arrows.lon.push(lon0 + (lon1 - lon0) * (ix / (n - 1)));
      arrows.bearing.push(packed.b[k]);
      arrows.value.push(packed.v[k]);
    });

    // Bornes propres au scénario si l'export les a enregistrées,
    // sinon celles du manifeste.
    const [vmin, vmax] = (packed.vmin !== undefined && packed.vmax !== undefined)
      ? [packed.vmin, packed.vmax]
      : (man.scales[fileId] || [0, 1]);
    const axes = vertical && man.layer_indices.length > 1
      ? [{ dim: "layer", kind: "layer", size: man.layer_indices.length,
           index: li, values: man.layer_indices,
           total: man.n_layers_source || null }]
      : [];
    return {
      layer: spec.id, label: spec.label, units: spec.units,
      bounds, arrows, n_arrows: arrows.lat.length,
      arrow_scaled: vertical, vmin, vmax,
      zmax: packed.zmax, zmin: 0, axes, source: "static",
      coarse: packed.coarse || null,
      image: `img/${encodeURIComponent(key)}__${fileId}.png`,
    };
  }

  function buildModelSelectors(d) {
    const axes = d.axes || [];
    const setup = (id, kind, labeller) => {
      const sel = $(id);
      const ax = axes.find((a) => a.kind === kind);
      if (!ax || ax.size < 2) { sel.hidden = true; return; }
      sel.innerHTML = Array.from({ length: ax.size }, (_, i) =>
        `<option value="${i}"${i === ax.index ? " selected" : ""}>`
        + labeller(i, ax) + `</option>`).join("");
      sel.hidden = false;
    };
    // When the data comes from the compact file only a few layers are
    // kept: label them with their original number, not their rank.
    setup("model-layer-idx", "layer", (i, ax) => ax.values
      ? `layer ${ax.values[i]}${ax.total ? "/" + ax.total : ""}`
      : `layer ${i + 1}/${ax.size}`);
    setup("model-time", "time", (i, ax) => `step ${i + 1}/${ax.size}`);
    const any = !$("model-layer-idx").hidden || !$("model-time").hidden;
    $("model-controls").hidden = !any;
  }

  function setModelNote(text, isError) {
    const el = $("scenario-note");
    if (!el) return;
    el.textContent = text || "";
    el.classList.toggle("warn", Boolean(isError));
  }

  // ── SWOT water extent on the map ─────────────────────────

  function areaDates() {
    const e = state.extent;
    return (e && e.series) ? e.series.filter((r) => r.map) : [];
  }

  function areaBase() {
    // Chemin des masques : servi par Flask ou copié dans le site.
    return state.staticMode ? "data/" : "/data/";
  }

  function drawWaterExtent() {
    clearModelLayer();
    hideMapMessage();
    const dates = areaDates();
    const a = state.extent;
    if (!dates.length || !a || !a.map_bounds) {
      showMapMessage("No water extent available. Run "
        + "pipeline/water_extent.py");
      return;
    }
    const idx = Math.min(Math.max(0, state.areaIdx), dates.length - 1);
    state.areaIdx = idx;
    const entry = dates[idx];

    state.modelRaster = L.imageOverlay(
      areaBase() + entry.map, a.map_bounds,
      { opacity: 1, interactive: false }).addTo(state.map);

    $("legend-title").textContent = "Water depth (m)";
    $("legend-min").textContent = "shallow";
    $("legend-max").textContent = "deep";
    $("map-legend").hidden = false;
    // La palette du modèle n'a pas de sens ici : une seule teinte,
    // dont l'opacité suit la fraction d'eau de la maille.
    const bar = document.querySelector(".legend-bar");
    if (bar) {
      bar.style.background =
        "linear-gradient(to right, rgba(30,95,107,0.08), rgba(30,95,107,0.85))";
    }

    buildAreaDateControls(dates, idx, entry);
    // L'étendue vient du niveau mesuré, pas de la classification du
    // radar : c'est ce que la note doit dire.
    setModelNote(`${entry.date}, level ${entry.level_m.toFixed(2)} m, `
      + `${entry.area_km2.toLocaleString("en-GB")} km², `
      + `${entry.volume_km3.toFixed(3)} km³, derived from the SWOT level`
      + (a.wlvl_offset ? "" : ", datum offset not yet applied"),
      !a.wlvl_offset);
  }

  function buildAreaDateControls(dates, idx, entry) {
    const box = $("model-controls");
    box.hidden = false;
    box.innerHTML =
      `<button type="button" id="area-prev" class="date-btn" `
      + `${idx === 0 ? "disabled" : ""}>◀</button>`
      + `<select id="area-date" class="site-select">`
      + dates.map((r, k) => `<option value="${k}"${k === idx ? " selected" : ""}>`
          + `${r.date}${r.partial ? " (partial)" : ""}</option>`).join("")
      + `</select>`
      + `<button type="button" id="area-next" class="date-btn" `
      + `${idx >= dates.length - 1 ? "disabled" : ""}>▶</button>`;
    const go = (k) => { state.areaIdx = k; drawWaterExtent(); };
    $("area-prev").addEventListener("click", () => go(idx - 1));
    $("area-next").addEventListener("click", () => go(idx + 1));
    $("area-date").addEventListener("change",
      (e) => go(parseInt(e.target.value, 10)));
  }

  function buildModelButtons() {
    const seg = $("model-seg");
    const specs = [
      { id: "water", label: "Water extent" },
      { id: "currents", label: "Currents" },
      { id: "hsign", label: "Wave height" },
      { id: "wlength", label: "Wavelength" },
      { id: "period", label: "Period" },
    ];
    specs.forEach((sp) => {
      const b = document.createElement("button");
      b.type = "button"; b.className = "seg-btn";
      b.dataset.model = sp.id; b.textContent = sp.label;
      seg.appendChild(b);
    });
    seg.querySelectorAll(".seg-btn").forEach((b) =>
      b.addEventListener("click", () => {
        state.modelLayer = b.dataset.model;
        state.fieldLayer = null; state.fieldTime = null;
        seg.querySelectorAll(".seg-btn").forEach((o) =>
          o.classList.toggle("active", o === b));
        drawModelLayer();
      }));
    const size = $("arrow-size");
    if (size) {
      size.value = String(state.arrowPx);
      size.addEventListener("input", (e) => {
        state.arrowPx = parseInt(e.target.value, 10);
        if (state.modelData && state.modelLayer !== "none") {
          const d = state.modelData;
          drawArrows(d, d.vmax != null ? d.vmax : (d.zmax || 1));
        }
      });
    }
    ["model-layer-idx", "model-time"].forEach((id, k) =>
      $(id).addEventListener("change", (e) => {
        const v = parseInt(e.target.value, 10);
        if (k === 0) state.fieldLayer = v; else state.fieldTime = v;
        drawModelLayer();
      }));
  }

  async function loadScenario(query) {
    const body = $("scenario-body");
    if (state.staticMode) return loadScenarioStatic(query, body);
    const qs = new URLSearchParams(query || {}).toString();
    let m;
    try {
      const res = await fetch("/api/scenario/match" + (qs ? "?" + qs : ""),
                             { cache: "no-store" });
      m = await res.json();
      if (!res.ok) {
        body.innerHTML = `<p class="scenario-error">${m.message
          || "Scenarios unavailable."}</p>`;
        return;
      }
    } catch (e) {
      body.innerHTML = '<p class="scenario-error">Scenarios unavailable '
        + '(the Flask server must be running).</p>';
      return;
    }

    renderScenario(body, m);
  }

  function renderScenario(body, m) {
    state.scenario = m;
    const { target, match, labels, units } = m;
    const params = match.scenario.params;
    const keys = ["wind_speed", "wind_dir", "wlvl", "salinity"]
      .filter((k) => k in target || k in params);

    body.innerHTML =
      `<div class="match-grid">`
      + keys.map((k) => matchItem(k, target, params, match.deltas,
                                  match.envelope, labels, units)).join("")
      + `</div>`
      + (match.warnings.length
          ? `<ul class="scenario-warnings">`
            + match.warnings.map((w) => `<li>${w}</li>`).join("") + `</ul>`
          : "")
      + `<p class="scenario-file"><span id="shown-key">${match.scenario.key}</span>`
      + `<br>Conditions: ${originNote(m.origin, m.demo, m.at)}${coverageNote(m)}${roundingNote(m)}`
      + `<br><span id="scenario-note"></span></p>`;


    $("scenario-reset").hidden = !Object.keys(m.overrides || {}).length;
    // The matched run drives whatever model layer is shown on the map.
    drawModelLayer();
  }


  function roundingNote(m) {
    return m.match && m.match.wlvl_capped
      ? ', water level rounded down to the nearest simulated level' : "";
  }

  function coverageNote(m) {
    const c = m.coverage;
    if (!c || !c.n_missing) return "";
    return `, design: ${c.n_done}/${c.n_design_unique} runs present`;
  }

  function currentKey() {
    const shown = $("shown-key");
    if (shown && shown.textContent) return shown.textContent;
    return state.scenario ? state.scenario.match.scenario.key : null;
  }

  // ── Timeline over the observed weather archive ───────────
  //
  // Each Delft3D run is a separate steady state, not a time series:
  // moving back in time changes WHICH scenario matches the conditions,
  // it does not step through a simulation.

  function buildTimeline(stations) {
    const seen = new Set();
    stations.forEach((st) => (st.history || []).forEach((r) => {
      if (r.utc && r.wind_spd_kmh !== null) seen.add(r.utc);
    }));
    state.timeline = Array.from(seen).sort();
    const tl = $("timeline");
    const range = $("tl-range");
    if (state.timeline.length < 2) { tl.hidden = true; return; }
    tl.hidden = false;
    range.max = String(state.timeline.length - 1);
    range.value = range.max;
    state.timeIdx = state.timeline.length - 1;
    updateTimeLabel();
  }

  function timelineISO(idx) {
    const utc = state.timeline[idx];
    const d = bomToDate(utc);
    return d ? d.toISOString() : null;
  }

  function updateTimeLabel() {
    const atNow = state.timeIdx >= state.timeline.length - 1;
    const d = bomToDate(state.timeline[state.timeIdx]);
    $("tl-label").textContent = !d ? "—" : atNow ? "now"
      : d.toLocaleString("en-GB", { weekday: "short", hour: "2-digit",
                                    minute: "2-digit", timeZone: "UTC" })
        + " UTC";
    $("tl-now").classList.toggle("active", atNow);
  }

  let tlTimer = null;

  function applyTimeline() {
    updateTimeLabel();
    clearTimeout(tlTimer);
    tlTimer = setTimeout(() => {
      const atNow = state.timeIdx >= state.timeline.length - 1;
      loadScenario(atNow ? null : { at: timelineISO(state.timeIdx) });
    }, 220);            // laisse le curseur glisser sans saturer le serveur
  }

  function stopPlayback() {
    if (state.playTimer) clearInterval(state.playTimer);
    state.playTimer = null;
    $("tl-play").textContent = "▶";
  }

  function togglePlayback() {
    if (state.playTimer) { stopPlayback(); return; }
    $("tl-play").textContent = "❚❚";
    state.playTimer = setInterval(() => {
      if (state.timeIdx >= state.timeline.length - 1) {
        state.timeIdx = 0;
      } else {
        state.timeIdx += 1;
      }
      $("tl-range").value = String(state.timeIdx);
      applyTimeline();
    }, 900);
  }

  function wireTimeline() {
    $("tl-range").addEventListener("input", (e) => {
      stopPlayback();
      state.timeIdx = parseInt(e.target.value, 10);
      applyTimeline();
    });
    $("tl-now").addEventListener("click", () => {
      stopPlayback();
      state.timeIdx = state.timeline.length - 1;
      $("tl-range").value = String(state.timeIdx);
      applyTimeline();
    });
    $("tl-play").addEventListener("click", togglePlayback);
  }

  async function loadScenarioStatic(query, body) {
    const at = query && query.at ? new Date(query.at) : null;
    const { target, origin } = staticConditions(at);
    if (!Object.keys(target).length) {
      body.innerHTML = '<p class="scenario-error">No observed conditions '
        + 'available.</p>';
      return;
    }
    const idx = state.staticIndex;
    if (!idx || !Array.isArray(idx.scenarios)) {
      body.innerHTML = '<p class="scenario-error">Scenario library unavailable.</p>';
      return;
    }
    const cfgm = (state.manifest && state.manifest.matching) || {};
    const match = matchStatic(idx.scenarios, state.paramGrid, target,
                              cfgm.weights, cfgm.wlvl_rounding);
    renderScenario(body, {
      target, origin, match, at: query && query.at ? query.at : null,
      overrides: {}, demo: false,
      units: idx.units || {}, labels: idx.labels || {},
    });
  }

  function wireScenario() {
    $("scenario-reset").addEventListener("click", () => loadScenario(null));
  }

  // ── CSV downloads ────────────────────────────────────────
  //
  // Files are built in the browser from data already loaded, so the
  // buttons behave identically behind Flask and on the static site.

  function wireDownloads() {
    const bind = (id, build, ready) => {
      const btn = $(id);
      if (!btn) return;
      btn.addEventListener("click", () => {
        if (!ready()) return;
        try {
          Download.save(build());
        } catch (e) {
          btn.textContent = "Export failed";
          setTimeout(() => { btn.textContent = "Download CSV"; }, 2500);
        }
      });
    };

    bind("dl-wse", () => Download.wseCSV(state.data), () => Boolean(state.data));
    bind("dl-weather", () => Download.weatherCSV(state.weather),
         () => Boolean(state.weather));
    bind("dl-area", () => Download.areaCSV(state.area),
         () => Boolean(state.area));
    bind("dl-area2", () => Download.areaCSV(state.area),
         () => Boolean(state.area));

    const layerBtn = $("dl-layer");
    if (layerBtn) {
      layerBtn.addEventListener("click", () => {
        if (!state.modelData) return;
        Download.save(Download.layerCSV(state.modelData,
          state.scenario ? state.scenario.match.scenario : null));
      });
    }
  }

  function refreshDownloadButtons() {
    const wse = $("dl-wse");
    if (wse) wse.disabled = !state.data;
    const wx = $("dl-weather");
    if (wx) wx.disabled = !state.weather;
    const areaBtn = $("dl-area");
    if (areaBtn) areaBtn.hidden = !state.area;
    const layer = $("dl-layer");
    if (layer) {
      layer.hidden = !state.modelData;
      // La grille complète n'est disponible que derrière Flask ; le site
      // statique n'a que l'image, d'où l'export des flèches.
      layer.textContent = state.modelData && state.modelData.z
        ? "Download grid" : "Download arrows";
    }
  }

  // ── Tabs ─────────────────────────────────────────────────

  // Trois parties : Natural History et Aboriginal Culture, des lectures
  // référencées, et Observatory, qui regroupe le tableau de bord, les
  // méthodes et les publications. Chaque onglet appartient à une partie.
  const SECTION_OF = {
    home: "home",
    "natural-history": "lake",
    modelling: "lake",
    methods: "lake",
    publications: "lake",
    catchment: "catchment",
    "river-flow": "catchment",
    weather: "climate",
    rainfall: "climate",
    "fauna-flora": "fauna-flora",
    birds: "fauna-flora",
    inaturalist: "fauna-flora",
    culture: "culture",
    stories: "culture",
  };
  // Anciennes adresses, pour que les liens déjà partagés continuent de marcher
  const ALIASES = { observatory: "modelling", "rain-rivers": "river-flow" };
  // Contenus injectés à la première ouverture, et préfixes des ancres
  // qu'ils portent : sections et références de chaque page.
  // Un « const » global n'est pas une propriété de window : window[nom]
  // renverrait undefined. On lit donc chaque contenu par son nom, typeof
  // restant sûr si le fichier n'a pas été chargé.
  const LAZY_PAGES = {
    "natural-history": {
      html: () => (typeof NATURAL_HISTORY_HTML === "string" ? NATURAL_HISTORY_HTML : null),
      anchors: /^(nh|ref)-/,
    },
    culture: {
      html: () => (typeof ABORIGINAL_CULTURE_HTML === "string" ? ABORIGINAL_CULTURE_HTML : null),
      anchors: /^(ac|acref)-/,
    },
    "fauna-flora": {
      html: () => (typeof FAUNA_FLORA_HTML === "string" ? FAUNA_FLORA_HTML : null),
      anchors: /^(ff|ffref)-/,
    },
    catchment: {
      html: () => (typeof CATCHMENT_HTML === "string" ? CATCHMENT_HTML : null),
      anchors: /^(ct|ctref)-/,
    },
    stories: {
      html: () => (typeof STORIES_HTML === "string" ? STORIES_HTML : null),
      anchors: /^(st|stref)-/,
    },
  };

  function lazyPage(name) {
    const spec = LAZY_PAGES[name];
    if (!spec || state.loadedPages[name]) return;
    const box = $("tab-" + name);
    const html = spec.html();
    box.innerHTML = html !== null ? html
      : '<article class="panel"><div class="prose-body">'
        + "<p>This content is unavailable.</p></div></article>";
    // Sommaire et renvois : défilement doux dans la page, et adresse mise
    // à jour pour qu'un lien reste partageable. Un lien vers une autre
    // partie du site suit son cours et passe par le routage.
    box.addEventListener("click", (e) => {
      const a = e.target.closest('a[href^="#"]');
      if (!a) return;
      const target = document.getElementById(a.getAttribute("href").slice(1));
      if (!target) return;
      e.preventDefault();
      target.scrollIntoView({ behavior: "smooth", block: "start" });
      try { history.replaceState(null, "", a.getAttribute("href")); } catch (_) { /* ignore */ }
    });
    state.loadedPages[name] = true;
    if (name === "catchment") initCatchmentMap();
    if (name === "fauna-flora") renderGroupBlocks();
  }

  function showTab(name, anchor) {
    name = ALIASES[name] || name;
    if (!SECTION_OF[name]) name = "home";
    const section = SECTION_OF[name];
    state.lastTab[section] = name;

    document.querySelectorAll(".section-btn").forEach((b) => {
      const on = b.dataset.section === section;
      b.classList.toggle("active", on);
      b.setAttribute("aria-current", on ? "page" : "false");
    });
    document.querySelectorAll("[data-for]").forEach((n) => {
      n.hidden = n.dataset.for !== section;
    });
    document.querySelectorAll(".tab").forEach((b) => {
      const on = b.dataset.tab === name;
      b.classList.toggle("active", on);
      b.setAttribute("aria-selected", on ? "true" : "false");
    });
    document.querySelectorAll(".tab-panel").forEach((p) => {
      p.hidden = p.id !== "tab-" + name;
    });

    if (name === "methods" && !state.methodsLoaded) {
      const box = $("tab-methods");
      // METHODS_HTML vient de methods.js, chargé avant ce fichier
      box.innerHTML = typeof METHODS_HTML === "string" ? METHODS_HTML
        : '<article class="panel"><div class="prose-body">'
          + "<p>Methods documentation unavailable.</p></div></article>";
      state.methodsLoaded = true;
    }
    lazyPage(name);

    // Leaflet et Plotly calculent leurs dimensions au moment du rendu :
    // masqués, ils mesurent zéro et restent figés au retour.
    requestAnimationFrame(() => {
      if (name === "modelling" && state.map) state.map.invalidateSize();
      const panel = $("tab-" + name);
      if (panel) panel.querySelectorAll(".js-plotly-plot").forEach((el) => Plotly.Plots.resize(el));
    });

    try { history.replaceState(null, "", "#" + (anchor || name)); } catch (_) { /* ignore */ }
    if (anchor) {
      requestAnimationFrame(() => {
        const el = document.getElementById(anchor);
        if (el) el.scrollIntoView({ block: "start" });
      });
    } else if (LAZY_PAGES[name] || name === "home") {
      window.scrollTo({ top: 0 });
    }
    if (name === "catchment" && state.catchmentMap) {
      requestAnimationFrame(() => state.catchmentMap.invalidateSize());
    }
    if (name === "rainfall") {
      requestAnimationFrame(() => {
        initRainMap();
        if (state.rainMap) state.rainMap.invalidateSize();
      });
    }
    if (name === "river-flow") {
      requestAnimationFrame(() => {
        initFlowMap();
        if (state.flowMap) state.flowMap.invalidateSize();
      });
    }
    if (name === "inaturalist") {
      requestAnimationFrame(() => {
        initInatMap();
        if (state.inatMap) state.inatMap.invalidateSize();
      });
    }
    if (name === "birds") {
      requestAnimationFrame(() => {
        initBirdsMap();
        if (state.birdsMap) state.birdsMap.invalidateSize();
      });
    }
  }

  // Adresses reconnues : le nom d'un onglet (#natural-history, #culture,
  // #methods...) ou une ancre d'une page référencée (#nh-geology,
  // #acref-dodd2012...), qui ouvre la bonne partie puis y défile.
  function route(hash) {
    const h = (hash || "").replace("#", "");
    if (!h) return false;
    const t = ALIASES[h] || h;
    if (SECTION_OF[t]) { showTab(t); return true; }
    for (const [name, spec] of Object.entries(LAZY_PAGES)) {
      if (spec.anchors.test(h)) { showTab(name, h); return true; }
    }
    return false;
  }

  function wireTabs() {
    document.querySelectorAll(".tab").forEach((b) =>
      b.addEventListener("click", () => showTab(b.dataset.tab)));
    document.querySelectorAll(".section-btn").forEach((b) =>
      b.addEventListener("click", () => {
        const section = b.dataset.section;
        showTab(state.lastTab[section] || section);
      }));
    window.addEventListener("hashchange", () => route(location.hash));
    if (!route(location.hash)) showTab("home");
  }



  // ── Initialisation ───────────────────────────────────────

  // ── Bird sightings (eBird) ───────────────────────────────
  //
  // data/ebird.json is fetched server-side by pipeline/fetch_ebird.py:
  // the API key never reaches the browser. Location names are free text
  // typed by observers, so everything taken from the file is escaped
  // before it goes into the page.

  function esc(v) {
    return String(v === null || v === undefined ? "" : v)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  async function loadEbird() {
    const sources = state.staticMode ? ["data/ebird.json"]
      : ["/api/ebird", "data/ebird.json"];
    for (const url of sources) {
      try {
        const res = await fetch(url, { cache: "no-store" });
        if (res.ok) return await res.json();
      } catch (_) { /* next source */ }
    }
    return null;
  }

  function renderBirds(data) {
    const card = $("birds-card");
    const ok = card && data && Array.isArray(data.species) && typeof EBird !== "undefined";
    if ($("birds-empty")) $("birds-empty").hidden = Boolean(ok);
    if (!ok) {
      if (card) card.hidden = true;
      return;
    }
    card.hidden = false;
    const sum = EBird.summary(data);

    $("birds-updated").textContent = data.fetched_at
      ? "fetched " + data.fetched_at.replace("T", " ").replace("Z", " UTC") : "";

    const where = data.area ? "around the lake, from William Creek to Marree,"
      : `within ${esc(data.dist_km)} km of ${(data.points || []).length} points on the lake`;
    const notes = [
      `The most recent sighting of each species ${where} over the last `
      + `${esc(data.back_days)} days: a list of species reported, not a count of birds.`,
    ];
    const nHot = (data.hotspots || []).length;
    if (nHot) {
      notes.push(`${spell(nHot)} eBird hotspot${nHot > 1 ? "s lie" : " lies"} in this area; those visited `
        + "in the period are filled on the map.");
    }
    if (sum.nPrivate) {
      notes.push(sum.nPrivate === 1
        ? "One sighting from a private location is listed without its location."
        : `${sum.nPrivate} sightings from private locations are listed without `
          + "their location.");
    }
    if (data.demo) notes.push("Demonstration data, not real observations.");
    if (data.stale) notes.push("eBird could not be reached: showing the last valid set.");
    else if (data.partial) notes.push("Some points could not be queried.");
    $("birds-note").innerHTML = notes.join(" ");

    $("birds-indicators").innerHTML = (data.indicators || []).map((i) => {
      const name = esc(i.comName || i.sciName);
      return i.present
        ? `<div class="bird-chip present"><b>${name}</b>`
          + `<span class="mono">last seen ${esc(EBird.formatDate(i.lastSeen))}</span></div>`
        : `<div class="bird-chip absent"><b><i>${esc(i.sciName)}</i></b>`
          + `<span class="mono">not reported</span></div>`;
    }).join("");

    const rows = EBird.sortSpecies(data.species).map((sp) => {
      const tags = (sp.indicator ? '<span class="bird-tag indicator">waterbird</span>' : "")
        + (sp.notable ? '<span class="bird-tag notable">notable</span>' : "");
      const age = EBird.daysAgo(sp.obsDt);
      const ageText = age === null ? "" : age === 0 ? "today" : `${age} d ago`;
      const where = sp.locationPrivate ? "<i>private location</i>" : esc(sp.locName);
      return `<tr><td><a href="${esc(EBird.speciesUrl(sp.speciesCode))}" target="_blank"`
        + ` rel="noopener">${esc(sp.comName)}</a>${tags}`
        + `<span class="sci">${esc(sp.sciName)}</span></td>`
        + `<td>${esc(EBird.formatDate(sp.obsDt))}<span class="sci">${ageText}</span></td>`
        + `<td>${esc(EBird.formatCount(sp.howMany))}</td><td>${where}</td></tr>`;
    });
    const hot = EBird.hotspotList(data);
    $("birds-hotspots").innerHTML = hot.map((h) =>
      `<tr><td><a href="${esc(h.url)}" target="_blank" rel="noopener">${esc(h.name)}</a></td>`
      + `<td>${esc(EBird.formatDate(h.latest))}</td>`
      + `<td>${h.active ? h.recent.length : ""}${h.waterbirds ? `<span class="rr-date">${h.waterbirds} waterbird${h.waterbirds > 1 ? "s" : ""}</span>` : ""}</td>`
      + `<td>${esc(h.allTime)}</td></tr>`).join("");
    $("birds-hotspot-block").hidden = !hot.length;
    $("birds-body").innerHTML = rows.join("")
      || '<tr><td colspan="4">No sightings reported in this period.</td></tr>';

    initBirdsMap();
  }

  // Bird sightings have their own map on the Bird sightings tab. Positions
  // are those eBird publishes; private locations carry none and are not
  // mapped.
  function initBirdsMap() {
    const el = $("birds-map");
    if (!el || typeof L === "undefined" || el.offsetParent === null) return;
    if (!state.birdsMap) {
      state.birdsMap = L.map(el, { scrollWheelZoom: false }).setView([-28.6, 137.3], 7);
      L.tileLayer("https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png", {
        maxZoom: 13,
        attribution: "&copy; OpenTopoMap (CC-BY-SA), &copy; OpenStreetMap contributors, "
          + 'bird records &copy; <a href="https://ebird.org">eBird.org</a>',
      }).addTo(state.birdsMap);
    }
    if (state.birdsLayer) state.birdsMap.removeLayer(state.birdsLayer);
    state.birdsLayer = null;
    if (!state.ebird || typeof EBird === "undefined") return;
    const layer = L.layerGroup();
    const back = esc(state.ebird.back_days || 30);
    // Every hotspot in the area: filled if visited in the period, hollow otherwise
    EBird.hotspotList(state.ebird).forEach((h) => {
      const list = h.recent.slice(0, 10).map((r) => esc(r.comName)).join(", ")
        + (h.recent.length > 10 ? `, and ${h.recent.length - 10} more` : "");
      const body = h.active
        ? `${h.recent.length} species in the last ${back} days<br><small>${list}</small>`
        : `Last visited ${esc(EBird.formatDate(h.latest)) || "some time ago"}`;
      L.circleMarker([h.lat, h.lng], {
        radius: h.active ? Math.min(6 + h.recent.length / 2, 15) : 6,
        color: "#134450", weight: 1.8,
        fillColor: h.active ? "#1F6470" : "#FFFFFF", fillOpacity: h.active ? 0.6 : 0.9,
      }).bindPopup(`<b>${esc(h.name)}</b><br>${body}<br><small>${esc(h.allTime)} species `
        + `recorded all time. <a href="${esc(h.url)}" target="_blank" rel="noopener">Open on `
        + "eBird</a></small>").addTo(layer);
    });
    // Public sightings away from hotspots, as small dots
    EBird.otherLocations(state.ebird).forEach((g) => {
      const list = g.species.slice(0, 8).map((sp) => esc(sp.comName)).join(", ");
      L.circleMarker([g.lat, g.lng], {
        radius: 4, color: "#134450", weight: 1, fillColor: "#134450", fillOpacity: 0.5,
      }).bindPopup(`<b>${esc(g.name)}</b><br>${g.species.length} species, latest `
        + `${esc(EBird.formatDate(g.last))}<br><small>${list}</small>`
        + '<br><small>Source: <a href="https://ebird.org" target="_blank" '
        + 'rel="noopener">eBird.org</a></small>').addTo(layer);
    });
    if (state.ebird.area && !state.birdsFitted) {
      const [w, sth, e, n] = state.ebird.area;
      state.birdsMap.fitBounds([[sth, w], [n, e]]);
      state.birdsFitted = true;
    }
    layer.addTo(state.birdsMap);
    state.birdsLayer = layer;
  }


  // ── Home: the lake now ───────────────────────────────────
  //
  // Everything on the home page is read from data already loaded for the
  // observatory. Sentences appear only for what the data support.

  const GIBS_WMS = "https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi";
  // The home page shows the lake as a map sheet, wide enough to take in
  // the rivers' lower reaches. Plate carrée: at 28.7° S a degree of
  // longitude is 0.877 of a degree of latitude, and 1600 by 995 pixels
  // keeps that ratio over 4.4° by 2.4° so shapes stay true.
  const HERO = { bbox: [135.1, -29.9, 139.5, -27.5], w: 1600, h: 995 };

  function isoDaysAgo(n) {
    const d = new Date(Date.now() - n * 86400000);
    return d.toISOString().slice(0, 10);
  }

  function heroImageUrl(day) {
    const q = new URLSearchParams({
      SERVICE: "WMS", REQUEST: "GetMap", VERSION: "1.1.1",
      LAYERS: "MODIS_Terra_CorrectedReflectance_Bands721", STYLES: "",
      SRS: "EPSG:4326", BBOX: HERO.bbox.join(","), WIDTH: String(HERO.w), HEIGHT: String(HERO.h),
      FORMAT: "image/jpeg", TIME: day,
    });
    return `${GIBS_WMS}?${q}`;
  }

  // The most recent complete day is usually two days back; if that image
  // fails, step back a day at a time, up to a week.
  function loadHeroImage() {
    const img = $("hero-image");
    const fallback = $("hero-fallback");
    const caption = $("hero-caption");
    if (!img) return;
    let back = 2;
    const attempt = () => {
      const day = isoDaysAgo(back);
      img.onload = () => {
        img.hidden = false;
        fallback.hidden = true;
        caption.textContent = `MODIS Terra, ${fmtLongDate(day)}, shortwave infrared composite `
          + "(bands 7, 2, 1): water appears dark and the salt crust pale. "
          + "Graticule, places and SWOT sites are drawn at their coordinates. "
          + "Image from NASA EOSDIS GIBS.";
        drawHeroOverlay();
      };
      img.onerror = () => {
        back += 1;
        if (back <= 7) { attempt(); return; }
        fallback.textContent = "The satellite image could not be loaded. "
          + "Recent imagery is available on the observatory map.";
      };
      img.src = heroImageUrl(day);
    };
    attempt();
  }

  function fmtLongDate(iso) {
    const d = new Date(String(iso).slice(0, 10) + "T00:00:00Z");
    if (Number.isNaN(d.getTime())) return String(iso);
    return d.toLocaleDateString("en-AU", { day: "numeric", month: "long",
                                          year: "numeric", timeZone: "UTC" });
  }

  function referenceSite() {
    const sites = (state.data && state.data.sites) || [];
    return sites.find((x) => x.name === "Belt Bay" && x.latest)
      || sites.find((x) => x.latest) || null;
  }

  function monthBefore(site) {
    const t = new Date(site.latest.date).getTime() - 25 * 86400000;
    const earlier = (site.series || []).filter((r) => new Date(r.date).getTime() <= t);
    return earlier.length ? earlier[earlier.length - 1] : null;
  }

  const minus = (v, d) => v.toFixed(d).replace("-", "\u2212");
  const WORDS = ["No", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten"];
  const spell = (n, lower) => {
    const w = n < WORDS.length ? WORDS[n] : String(n);
    return lower ? w.toLowerCase() : w;
  };

  function renderHome() {
    const box = $("lake-now");
    if (!box) return;
    const lines = [];
    const site = referenceSite();
    if (site) {
      const wse = site.latest.wse;
      let s = `SWOT last measured the water surface at ${esc(site.name)} on `
        + `${fmtLongDate(site.latest.date)}, at ${minus(wse, 2)}&nbsp;m relative to the EGM2008 geoid`;
      const prev = monthBefore(site);
      if (prev) {
        const dz = wse - prev.wse;
        s += Math.abs(dz) < 0.02 ? ", unchanged from a month earlier"
          : `, ${Math.abs(dz).toFixed(2)}&nbsp;m ${dz > 0 ? "higher" : "lower"} than a month earlier`;
      }
      lines.push(s + ".");
    }
    const area = state.area && Array.isArray(state.area.series)
      ? state.area.series.filter((r) => !r.partial && r.area_km2 > 0) : [];
    if (area.length) {
      const a = area[area.length - 1];
      lines.push(`On ${fmtLongDate(a.date)}, water covered about `
        + `${Math.round(a.area_km2).toLocaleString("en-AU")}&nbsp;km&sup2; of the lake.`);
    }
    const birds = state.ebird && Array.isArray(state.ebird.indicators) ? state.ebird.indicators : [];
    if (birds.length) {
      const seen = birds.filter((b) => b.present).length;
      lines.push(seen
        ? `${spell(seen)} of the ${spell(birds.length, true)} waterbirds that gather when the lake `
          + `holds water ${seen === 1 ? "has" : "have"} been reported nearby in the last `
          + `${esc(state.ebird.back_days)} days.`
        : `None of the ${spell(birds.length, true)} waterbirds that gather when the lake holds `
          + `water has been reported nearby in the last ${esc(state.ebird.back_days)} days.`);
    }
    if (state.data && state.data.demo) lines.push("These are demonstration data.");
    box.innerHTML = lines.length
      ? lines.map((l) => `<p>${l}</p>`).join("")
      : "<p>No observations are available yet. The observatory explains how to add them.</p>";
    drawHeroGauge(site);
    drawHeroOverlay();
  }

  // The map sheet: everything is placed from coordinates, so labels,
  // graticule and scale stay true to the image.
  const MAP_LABELS = [
    { text: "Lake Eyre North", lon: 137.30, lat: -28.32, kind: "water" },
    { text: "Lake Eyre South", lon: 137.33, lat: -29.36, kind: "water" },
    { text: "Marree", lon: 138.064, lat: -29.648, kind: "town" },
    { text: "William Creek", lon: 136.340, lat: -28.909, kind: "town" },
  ];

  function drawHeroOverlay() {
    const svg = $("hero-overlay");
    if (!svg || $("hero-image").hidden) return;
    const [x0, y0, x1, y1] = HERO.bbox;
    const W = HERO.w, H = HERO.h;
    const px = (lon) => (lon - x0) / (x1 - x0) * W;
    const py = (lat) => (y1 - lat) / (y1 - y0) * H;
    const deg = (v, pos, neg) => {
      const a = Math.abs(v), d = Math.floor(a + 1e-9), m = Math.round((a - d) * 60);
      return `${d}\u00b0${m ? String(m).padStart(2, "0") + "\u2032" : ""}${v < 0 ? neg : pos}`;
    };
    let g = "";
    // Graticule: ticks every half degree on the neatline, labels every degree
    for (let lon = Math.ceil(x0 * 2) / 2; lon <= x1; lon += 0.5) {
      const x = px(lon);
      g += `<line class="o-tick" x1="${x}" x2="${x}" y1="0" y2="12"/>`
        + `<line class="o-tick" x1="${x}" x2="${x}" y1="${H - 12}" y2="${H}"/>`;
      if (Math.abs(lon - Math.round(lon)) < 1e-9) {
        g += `<text class="o-grid" x="${x}" y="30" text-anchor="middle">${deg(lon, "E", "W")}</text>`;
      }
    }
    for (let lat = Math.ceil(y0 * 2) / 2; lat <= y1; lat += 0.5) {
      const y = py(lat);
      g += `<line class="o-tick" x1="0" x2="12" y1="${y}" y2="${y}"/>`
        + `<line class="o-tick" x1="${W - 12}" x2="${W}" y1="${y}" y2="${y}"/>`;
      if (Math.abs(lat - Math.round(lat)) < 1e-9) {
        g += `<text class="o-grid" x="18" y="${y + 5}">${deg(lat, "N", "S")}</text>`;
      }
    }
    MAP_LABELS.forEach((l) => {
      const x = px(l.lon), y = py(l.lat);
      g += l.kind === "water"
        ? `<text class="o-water" x="${x}" y="${y}" text-anchor="middle">${esc(l.text)}</text>`
        : `<circle class="o-town" cx="${x}" cy="${y}" r="4"/>`
          + `<text class="o-place" x="${x + 9}" y="${y + 5}">${esc(l.text)}</text>`;
    });
    // SWOT sites, with the reference site's latest level
    const ref = referenceSite();
    ((state.data && state.data.sites) || []).forEach((site) => {
      if (typeof site.lon !== "number") return;
      const x = px(site.lon), y = py(site.lat);
      g += `<circle class="o-site" cx="${x}" cy="${y}" r="7"/>`;
      if (ref && site.name === ref.name && site.latest) {
        // Above the marker, starting from it: William Creek sits at almost
        // the same latitude to the west, Madigan Gulf to the east.
        g += `<line class="o-leader" x1="${x}" x2="${x}" y1="${y - 9}" y2="${y - 22}"/>`
          + `<text class="o-site-label" x="${x - 6}" y="${y - 50}">`
          + `${esc(site.name)} ${minus(site.latest.wse, 2)}\u00a0m</text>`
          + `<text class="o-site-date" x="${x - 6}" y="${y - 28}">`
          + `SWOT, ${esc(fmtLongDate(site.latest.date))}</text>`;
      } else {
        g += `<text class="o-place" x="${x + 12}" y="${y + 5}">${esc(site.name)}</text>`;
      }
    });
    // Scale bar: 50 km at the latitude of the sheet's centre
    const kmPerPx = (x1 - x0) * 111.32 * Math.cos(((y0 + y1) / 2) * Math.PI / 180) / W;
    const bar = 50 / kmPerPx, bx = 36, by = H - 40;
    g += `<rect class="o-scale-bg" x="${bx - 12}" y="${by - 30}" width="${bar + 60}" height="46"/>`
      + `<line class="o-scale" x1="${bx}" x2="${bx + bar}" y1="${by}" y2="${by}"/>`
      + `<line class="o-scale" x1="${bx}" x2="${bx}" y1="${by - 7}" y2="${by + 7}"/>`
      + `<line class="o-scale" x1="${bx + bar}" x2="${bx + bar}" y1="${by - 7}" y2="${by + 7}"/>`
      + `<text class="o-scale-label" x="${bx}" y="${by - 12}">0</text>`
      + `<text class="o-scale-label" x="${bx + bar}" y="${by - 12}" text-anchor="middle">50 km</text>`;
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    svg.innerHTML = g;
    svg.toggleAttribute("hidden", false);
    // When the sheet is wider than the screen, open it centred on the lake
    const frame = svg.closest(".plate-frame");
    if (frame && frame.scrollWidth > frame.clientWidth + 4 && !frame.dataset.centred) {
      const shown = frame.scrollWidth * px(137.3) / W;
      frame.scrollLeft = Math.max(0, shown - frame.clientWidth / 2);
      frame.dataset.centred = "1";
    }
  }

  // Vertical gauge: the SWOT record at the reference site, from its lowest
  // to its highest measurement, with today's water surface drawn across it.
  // No datum conversion is implied: the scale is the record itself.
  function drawHeroGauge(site) {
    const svg = $("hero-gauge");
    if (!svg) return;
    if (!site || !site.stats || !(site.stats.max > site.stats.min)) { svg.toggleAttribute("hidden", true); return; }
    // Redraw only when the measurement changes: the home page re-renders as
    // each dataset arrives, and redrawing would replay the rising waterline.
    const sig = `${site.name}|${site.latest.date}|${site.latest.wse}|${site.stats.min}|${site.stats.max}`;
    if (svg.dataset.sig === sig) return;
    svg.dataset.sig = sig;
    const W = 96, H = 520, top = 34, bottom = H - 34, x = 30;
    const { min, max } = site.stats;
    const y = (v) => bottom - (v - min) / (max - min) * (bottom - top);
    const now = site.latest.wse;
    const step = (max - min) > 2.5 ? 1 : 0.5;
    let ticks = "";
    for (let v = Math.ceil(min / step) * step; v <= max + 1e-9; v += step) {
      ticks += `<line class="g-tick" x1="${x}" x2="${x + 8}" y1="${y(v)}" y2="${y(v)}"/>`
        + `<text class="g-tick-label" x="${x + 12}" y="${y(v) + 4}">${minus(v, step < 1 ? 1 : 0)}</text>`;
    }
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    svg.innerHTML = svg.querySelector("title").outerHTML
      + `<text class="g-end" x="${x}" y="${top - 14}">highest</text>`
      + `<text class="g-end" x="${x}" y="${bottom + 24}">lowest</text>`
      + `<line class="g-axis" x1="${x}" x2="${x}" y1="${top}" y2="${bottom}"/>`
      + ticks
      + `<rect class="g-water" x="${x - 12}" width="12" y="${y(now)}" height="${bottom - y(now)}"/>`
      + `<g class="g-line" style="--rise:${bottom - y(now)}px">`
      + `<line x1="${x - 18}" x2="${W - 4}" y1="${y(now)}" y2="${y(now)}"/>`
      + `<text x="${W - 4}" y="${y(now) - 7}" text-anchor="end">${minus(now, 2)}</text></g>`;
    svg.toggleAttribute("hidden", false);
  }

  // ── Catchment map ─────────────────────────────────────────
  //
  // Places named on the Catchment page. Positions are approximate and the
  // map says so; the topographic base map carries the rivers.
  const CATCHMENT_PLACES = [
    { name: "Kati Thanda\u2013Lake Eyre", lat: -28.40, lng: 137.30, note: "Terminal lake of the basin" },
    { name: "Birdsville", lat: -25.90, lng: 139.35, note: "Diamantina River" },
    { name: "Goyder Lagoon", lat: -26.70, lng: 139.30, note: "Diamantina River" },
    { name: "Boulia", lat: -22.91, lng: 139.91, note: "Burke River, Georgina system" },
    { name: "Longreach", lat: -23.44, lng: 144.25, note: "Thomson River" },
    { name: "Windorah", lat: -25.42, lng: 142.66, note: "Cooper Creek" },
    { name: "Nappa Merrie", lat: -27.60, lng: 141.11, note: "Cooper Creek gauge, station 003103A" },
    { name: "Innamincka", lat: -27.75, lng: 140.74, note: "Cooper Creek" },
    { name: "Coongie Lakes", lat: -27.18, lng: 140.16, note: "Ramsar wetland, listed 1987" },
    { name: "Alice Springs", lat: -23.70, lng: 133.88, note: "Todd River" },
    { name: "Oodnadatta", lat: -27.55, lng: 135.45, note: "Neales River" },
    { name: "Marree", lat: -29.65, lng: 138.06, note: "South of the lake" },
  ];

  function initCatchmentMap() {
    const el = document.getElementById("ct-map");
    if (!el || state.catchmentMap || typeof L === "undefined") return;
    const map = L.map(el, { scrollWheelZoom: false, attributionControl: true })
      .setView([-26.3, 138.6], 5);
    L.tileLayer("https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png", {
      maxZoom: 12,
      attribution: "&copy; OpenTopoMap (CC-BY-SA), &copy; OpenStreetMap contributors",
    }).addTo(map);
    CATCHMENT_PLACES.forEach((p) => {
      L.circleMarker([p.lat, p.lng], {
        radius: p.name.startsWith("Kati") ? 8 : 5,
        color: "#134450", weight: 1.5, fillColor: "#1F6470", fillOpacity: 0.8,
      }).bindTooltip(`<b>${esc(p.name)}</b><br>${esc(p.note)}`).addTo(map);
    });
    state.catchmentMap = map;
  }


  // ── iNaturalist ──────────────────────────────────────────
  //
  // data/inaturalist.json is fetched daily by pipeline/fetch_inaturalist.py.
  // Photos in it are already limited to those their observers licensed;
  // each is shown with the attribution iNaturalist provides.

  async function loadInat() {
    const sources = state.staticMode ? ["data/inaturalist.json"]
      : ["/api/inaturalist", "data/inaturalist.json"];
    for (const url of sources) {
      try {
        const res = await fetch(url, { cache: "no-store" });
        if (res.ok) return await res.json();
      } catch (_) { /* next source */ }
    }
    return null;
  }

  function inatName(o) {
    const n = INat.names(o);
    const first = n.primaryIsScientific ? `<i>${esc(n.primary)}</i>` : esc(n.primary);
    return { first, sci: n.scientific ? `<i>${esc(n.scientific)}</i>` : "" };
  }

  function renderInat(data) {
    const ok = data && Array.isArray(data.recent) && typeof INat !== "undefined";
    $("inat-empty").hidden = Boolean(ok);
    if (!ok) return;
    const sum = INat.summary(data);
    const where = data.project ? "in the Kati Thanda\u2013Lake Eyre project" : "around the lake";
    $("inat-now").innerHTML = sum.observations
      ? `So far, ${sum.observations.toLocaleString("en-AU")} observation${sum.observations === 1 ? "" : "s"} `
        + `of ${sum.species.toLocaleString("en-AU")} species have been shared by `
        + `${sum.observers.toLocaleString("en-AU")} observer${sum.observers === 1 ? "" : "s"} ${where}.`
        + (data.demo ? " These are demonstration data." : "")
      : "No observation has been shared here yet. Yours could be the first.";
    const links = data.links || {};
    if (links.explore) $("inat-explore").href = links.explore;
    if (links.project) {
      $("inat-project").href = links.project;
      $("inat-join").hidden = false;
    }

    $("inat-gallery").innerHTML = data.recent.map((o) => {
      const nm = inatName(o);
      const pic = o.photo
        ? `<img src="${esc(o.photo.medium)}" alt="${esc(INat.names(o).primary)}" loading="lazy">`
        : `<span class="inat-nophoto">${esc(INat.groupLabel(o.taxon && o.taxon.group))}</span>`;
      const meta = [INat.formatDate(o.observed_on), o.observer ? esc(o.observer) : "",
                    INat.qualityLabel(o.quality), o.obscured ? "location blurred" : ""]
        .filter(Boolean).join(", ");
      return `<figure class="inat-obs"><a href="${esc(o.url)}" target="_blank" rel="noopener">${pic}</a>`
        + `<figcaption><a class="inat-name" href="${esc(o.url)}" target="_blank" rel="noopener">`
        + `${nm.first}</a>${nm.sci ? `<span class="inat-sci">${nm.sci}</span>` : ""}`
        + `<span class="inat-meta">${meta}</span>`
        + (o.photo ? `<span class="inat-credit">${esc(o.photo.attribution)}</span>` : "")
        + "</figcaption></figure>";
    }).join("") || "<p>No recent observations.</p>";

    $("inat-species").innerHTML = (data.species || []).slice(0, data.top_species || 12).map((sp) => {
      const nm = inatName(sp);
      const pic = sp.photo
        ? `<img src="${esc(sp.photo.square)}" alt="" loading="lazy" title="${esc(sp.photo.attribution)}">`
        : '<span class="inat-thumb-empty"></span>';
      const name = sp.url
        ? `<a class="inat-sp-name" href="${esc(sp.url)}" target="_blank" rel="noopener">${nm.first}</a>`
        : `<span class="inat-sp-name">${nm.first}</span>`;
      return `<li>${pic}<span class="inat-sp">${name}${nm.sci ? `<span class="inat-sci">${nm.sci}</span>` : ""}`
        + `<span class="inat-meta">${sp.count} observation${sp.count === 1 ? "" : "s"}</span></span></li>`;
    }).join("");
    initInatMap();
  }

  function initInatMap() {
    const el = $("inat-map");
    if (!el || typeof L === "undefined" || el.offsetParent === null) return;
    if (!state.inatMap) {
      state.inatMap = L.map(el, { scrollWheelZoom: false }).setView([-28.7, 137.4], 8);
      L.tileLayer("https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png", {
        maxZoom: 15,
        attribution: "&copy; OpenTopoMap (CC-BY-SA), &copy; OpenStreetMap contributors",
      }).addTo(state.inatMap);
    }
    if (!state.inat) return;
    if (!state.inatTiles && state.inat.filter) {
      state.inatTiles = L.tileLayer(
        `https://api.inaturalist.org/v1/points/{z}/{x}/{y}.png?${state.inat.filter}`, {
          maxZoom: 15, opacity: 0.9,
          attribution: 'observations &copy; <a href="https://www.inaturalist.org">iNaturalist</a> contributors',
        }).addTo(state.inatMap);
    }
    if (state.inatLayer) state.inatMap.removeLayer(state.inatLayer);
    const layer = L.layerGroup();
    INat.mappable(state.inat.recent).forEach((o) => {
      const nm = inatName(o);
      L.circleMarker(o.coords, {
        radius: 7, color: "#134450", weight: 2, fillColor: "#FFFFFF", fillOpacity: 0.6,
      }).bindPopup(`<b>${nm.first}</b>${nm.sci ? `<br>${nm.sci}` : ""}<br>`
        + `${esc(INat.formatDate(o.observed_on))}<br>`
        + `<a href="${esc(o.url)}" target="_blank" rel="noopener">Open on iNaturalist</a>`).addTo(layer);
    });
    layer.addTo(state.inatMap);
    state.inatLayer = layer;
  }

  // ── Plants and animals: live observations by group ───────
  //
  // Each group section of the page carries an empty .obs-block, filled here
  // from iNaturalist (every group) and eBird (birds). Called when the page
  // is first opened and again as each dataset arrives, in any order.

  const OBS_SHOWN = 12;

  function renderGroupBlocks() {
    const blocks = document.querySelectorAll("#tab-fauna-flora .obs-block");
    if (!blocks.length || typeof INat === "undefined") return;
    const inat = state.inat || {};
    const ebird = state.ebird || {};
    blocks.forEach((el) => {
      const groups = (el.dataset.groups || "").split(",").filter(Boolean);
      const useEbird = el.dataset.ebird === "true";
      const list = INat.groupSpecies(inat.species, ebird.species, groups, useEbird);
      const nInat = list.filter((x) => x.inat > 0).length;
      const nEbird = list.filter((x) => x.ebird).length;
      const explore = inat.links && inat.links.explore
        ? `${inat.links.explore}&iconic_taxa=${encodeURIComponent(groups.join(","))}` : null;

      let head;
      if (!state.inat && !(useEbird && state.ebird)) {
        head = "Observations shared around the lake will appear here.";
      } else if (!list.length) {
        head = `None has been shared on iNaturalist around the lake yet. `
          + `<a href="#inaturalist">Share the first observation</a>.`;
      } else {
        const days = esc(ebird.back_days || 30);
        const sp = (n) => `${n === 1 ? "species" : "species"}`;
        if (nInat && useEbird && nEbird) {
          head = `${spell(nInat)} ${sp(nInat)} ${nInat === 1 ? "has" : "have"} been observed around the lake `
            + `on iNaturalist, and ${spell(nEbird, true)} ${nEbird === 1 ? "was" : "were"} reported on eBird `
            + `in the last ${days} days.`;
        } else if (nInat) {
          head = `${spell(nInat)} ${sp(nInat)} ${nInat === 1 ? "has" : "have"} been observed around the lake `
            + "on iNaturalist.";
        } else {
          head = `${spell(nEbird)} ${sp(nEbird)} ${nEbird === 1 ? "was" : "were"} reported around the lake `
            + `on eBird in the last ${days} days; none has yet been shared on iNaturalist.`;
        }
      }

      const items = list.slice(0, OBS_SHOWN).map((x) => {
        const pic = x.photo
          ? `<img src="${esc(x.photo.square)}" alt="" loading="lazy" title="${esc(x.photo.attribution)}">`
          : '<span class="obs-thumb-empty"></span>';
        const nm = x.nameIsScientific ? `<i>${esc(x.name)}</i>` : esc(x.name);
        const name = x.url ? `<a href="${esc(x.url)}" target="_blank" rel="noopener">${nm}</a>` : nm;
        const meta = [];
        if (x.inat) meta.push(`${x.inat} iNaturalist observation${x.inat === 1 ? "" : "s"}`);
        if (x.ebird) meta.push(`on eBird ${esc(EBird.formatDate(x.ebird.date))}`);
        return `<li>${pic}<span><span class="obs-name">${name}</span>`
          + (x.scientific ? `<span class="obs-sci">${esc(x.scientific)}</span>` : "")
          + `<span class="obs-meta">${meta.join(", ")}</span></span></li>`;
      }).join("");

      const more = [];
      if (list.length > OBS_SHOWN) more.push(`${list.length - OBS_SHOWN} more species not shown.`);
      if (explore && nInat) {
        more.push(`<a href="${esc(explore)}" target="_blank" rel="noopener">All these observations on iNaturalist</a>`);
      }
      if (useEbird) more.push('<a href="#birds">Recent sightings and how to submit yours</a>');

      el.innerHTML = `<p class="obs-head">${head}</p>`
        + (items ? `<ul class="obs-list">${items}</ul>` : "")
        + (more.length ? `<p class="obs-more">${more.join(" ")}</p>` : "")
        + (list.some((x) => x.photo)
          ? '<p class="obs-credit">Thumbnails from iNaturalist under their observers&rsquo; licences; '
            + "hover a photo for its credit.</p>" : "");
    });
  }

  // ── Catchment: rain and rivers ───────────────────────────
  //
  // data/rainfall.json (SILO) and data/rivers.json (Water Data Online) are
  // written daily by the pipeline; nothing is fetched from the browser.

  async function loadJson(apiPath, file) {
    const sources = state.staticMode ? [`data/${file}`] : [apiPath, `data/${file}`];
    for (const url of sources) {
      try {
        const res = await fetch(url, { cache: "no-store" });
        if (res.ok) return await res.json();
      } catch (_) { /* next source */ }
    }
    return null;
  }

  function rainImageUrl(png) {
    return (state.staticMode ? "data/" : "/data/") + png;
  }

  function currentRain() {
    const r = state.rain;
    if (!r) return null;
    if (state.rrView === "daily") {
      const days = (r.days || []).slice().reverse();          // oldest first
      const i = Math.min(Math.max(0, Number($("rain-day").value) || 0), days.length - 1);
      const d = days[i];
      return d ? { png: d.png, text: `${fmtLongDate(d.date)}: ${Catchment.fmtNumber(d.mean_mm)} mm on average over the basin, up to ${Catchment.fmtNumber(d.max_mm)} mm` } : null;
    }
    const t = r[state.rrView];
    return t ? { png: t.png, text: `${fmtLongDate(t.from)} to ${fmtLongDate(t.to)}: ${Catchment.fmtNumber(t.mean_mm)} mm on average over the basin, up to ${Catchment.fmtNumber(t.max_mm)} mm` } : null;
  }

  function showRain() {
    const cur = currentRain();
    $("rain-period").textContent = cur ? cur.text : "";
    if (!state.rainMap || !state.rain || !cur) return;
    if (state.rainOverlay) state.rainMap.removeLayer(state.rainOverlay);
    state.rainOverlay = L.imageOverlay(rainImageUrl(cur.png), state.rain.bounds, {
      opacity: 0.85,
      attribution: 'Rainfall &copy; <a href="https://www.longpaddock.qld.gov.au/silo/">SILO</a> (CC BY 4.0)',
    }).addTo(state.rainMap);
  }

  function baseCatchmentMap(el) {
    const map = L.map(el, { scrollWheelZoom: false }).setView([-25.5, 139.0], 5);
    L.tileLayer("https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png", {
      maxZoom: 12,
      attribution: "&copy; OpenTopoMap (CC-BY-SA), &copy; OpenStreetMap contributors",
    }).addTo(map);
    return map;
  }

  // The basin outline comes with the rainfall data; both maps draw it
  function drawOutline(map) {
    const o = state.rain && state.rain.outline;
    if (!o || map._ktleOutline) return;
    map._ktleOutline = L.polygon(o.coords, {
      color: "#134450", weight: 1.2, fill: false, dashArray: o.kind === "official" ? null : "4 4",
    }).addTo(map);
  }

  function showHydrograph(st) {
    const q = st.discharge && st.discharge.values && st.discharge.values.length ? st.discharge : null;
    const series = q || st.level;
    const el = $("flow-hydro");
    if (!series || !series.values || !series.values.length) {
      el.innerHTML = `<p class="rr-note">${esc(st.name)}: no values in the past year.</p>`;
      return;
    }
    const unit = Catchment.unitLabel(series.unit);
    Plotly.newPlot(el, [{
      x: series.values.map((v) => v[0]), y: series.values.map((v) => v[1]),
      type: "scatter", mode: "lines", line: { color: "#1F6470", width: 1.8 },
      hovertemplate: `%{x}<br>%{y} ${unit}<extra></extra>`,
    }], {
      title: { text: `${esc(st.name)}: daily mean ${q ? "flow" : "level"}`, font: { size: 14 } },
      margin: { l: 56, r: 16, t: 40, b: 40 }, height: 300,
      yaxis: { title: unit, rangemode: "tozero" }, xaxis: { type: "date" },
      paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
    }, { displayModeBar: false, responsive: true });
  }

  function notesFor(d) {
    return (d && d.demo ? "<p>These are demonstration data.</p>" : "")
      + (d && d.stale ? "<p>These data could not be refreshed; the last valid set is shown.</p>" : "");
  }

  function renderRainfall() {
    const rain = state.rain;
    if (!$("rain-now")) return;
    $("rain-empty").hidden = Boolean(rain);
    $("rain-now").innerHTML = Catchment.summary(rain, null).map((l) => `<p>${esc(l)}</p>`).join("")
      + notesFor(rain);
    if (!rain) return;
    $("rain-legend").innerHTML = Catchment.legend(rain.scale).map((x) =>
      `<span><i style="background:${esc(x.colour)}"></i>${esc(x.label)}</span>`).join("");
    if (rain.outline && rain.outline.kind === "official") {
      $("rain-caption").textContent = $("rain-caption").textContent.replace(" The basin outline is approximate.", "");
    }
    const days = (rain.days || []).slice().reverse();
    $("rain-day").max = String(Math.max(0, days.length - 1));
    $("rain-day").value = String(Math.max(0, days.length - 1));
    Plotly.newPlot($("rain-chart"), [{
      x: days.map((d) => d.date), y: days.map((d) => d.mean_mm), type: "bar",
      marker: { color: "#2A73B8" }, hovertemplate: "%{x}<br>%{y:.1f} mm<extra></extra>",
    }], {
      margin: { l: 56, r: 16, t: 10, b: 40 }, height: 240,
      yaxis: { title: "mm, basin average", rangemode: "tozero" }, xaxis: { type: "date" },
      paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
    }, { displayModeBar: false, responsive: true });
    initRainMap();
  }

  function renderRiverFlow() {
    const rivers = state.rivers;
    if (!$("flow-now")) return;
    $("flow-empty").hidden = Boolean(rivers);
    $("flow-now").innerHTML = Catchment.summary(null, rivers).map((l) => `<p>${esc(l)}</p>`).join("")
      + notesFor(rivers);
    const st = (rivers && rivers.stations) || [];
    $("flow-stations").innerHTML = st.map((x, i) => {
      const q = Catchment.latest(x, "discharge"), h = Catchment.latest(x, "level");
      return `<tr data-i="${i}"><td><button type="button" class="rr-link" data-i="${i}">${esc(x.name)}</button></td>`
        + `<td><i class="rr-dot" style="background:${Catchment.statusColour(x.status)}"></i>${Catchment.statusLabel(x.status)}</td>`
        + `<td>${q ? `${Catchment.fmtNumber(q.value)} ${esc(q.unit)}<span class="rr-date">${esc(fmtLongDate(q.date))}</span>` : ""}</td>`
        + `<td>${h ? `${Catchment.fmtNumber(h.value)} ${esc(h.unit)}<span class="rr-date">${esc(fmtLongDate(h.date))}</span>` : ""}</td></tr>`;
    }).join("") || '<tr><td colspan="4">No gauges with recent data.</td></tr>';
    const first = st.find((x) => x.status === "flowing") || st[0];
    if (first) showHydrograph(first);
    initFlowMap();
  }

  function initRainMap() {
    const el = $("rain-map");
    if (!el || typeof L === "undefined" || el.offsetParent === null) return;
    if (!state.rainMap) state.rainMap = baseCatchmentMap(el);
    drawOutline(state.rainMap);
    showRain();
  }

  function initFlowMap() {
    const el = $("flow-map");
    if (!el || typeof L === "undefined" || el.offsetParent === null) return;
    if (!state.flowMap) state.flowMap = baseCatchmentMap(el);
    drawOutline(state.flowMap);
    if (state.rivers && !state.flowStations) {
      const layer = L.layerGroup();
      state.rivers.stations.forEach((st) => {
        const q = Catchment.latest(st, "discharge");
        L.circleMarker([st.lat, st.lon], {
          radius: 7, color: "#FFFFFF", weight: 2,
          fillColor: Catchment.statusColour(st.status), fillOpacity: 0.95,
        }).bindTooltip(`<b>${esc(st.name)}</b><br>${Catchment.statusLabel(st.status)}`
          + (q ? `<br>${Catchment.fmtNumber(q.value)} ${esc(q.unit)} on ${esc(fmtLongDate(q.date))}` : ""))
          .on("click", () => showHydrograph(st)).addTo(layer);
      });
      layer.addTo(state.flowMap);
      state.flowStations = layer;
    }
  }

  function wireRainRivers() {
    document.querySelectorAll("[data-rain]").forEach((b) => b.addEventListener("click", () => {
      state.rrView = b.dataset.rain;
      document.querySelectorAll("[data-rain]").forEach((x) => x.classList.toggle("active", x === b));
      $("rain-day").hidden = state.rrView !== "daily";
      showRain();
    }));
    const day = $("rain-day");
    if (day) day.addEventListener("input", showRain);
    const body = $("flow-stations");
    if (body) body.addEventListener("click", (e) => {
      const b = e.target.closest(".rr-link");
      if (b && state.rivers) showHydrograph(state.rivers.stations[Number(b.dataset.i)]);
    });
  }

  // Data that do not depend on SWOT: weather, birds, community observations,
  // rain and rivers. They load whether or not the lake data exist.
  function loadIndependentData(withScenario) {
    loadWeather().then(() => { if (withScenario) loadScenario(null); });
    loadEbird().then((d) => { state.ebird = d; renderBirds(d); renderHome(); renderGroupBlocks(); });
    loadInat().then((d) => { state.inat = d; renderInat(d); renderGroupBlocks(); });
    Promise.all([loadJson("/api/rainfall", "rainfall.json"), loadJson("/api/rivers", "rivers.json")])
      .then(([rain, rivers]) => {
        state.rain = rain; state.rivers = rivers;
        renderRainfall(); renderRiverFlow();
      });
  }

  async function init() {
    loadHeroImage();
    const { data, viaApi } = await loadData();

    if (!data || !data.sites) {
      $("empty-state").hidden = false;
      renderHome();
      loadIndependentData(false);
      return;
    }

    state.data = data;
    renderHome();
    refreshDownloadButtons();
    $("dashboard").hidden = false;
    $("generated-at").textContent = fmtDate(data.generated_at.replace("Z", ""));
    $("datum-label").textContent = data.datum_label || "WSE (m)";
    if (data.demo) $("demo-banner").hidden = false;

    // Refresh button: only when served by Flask
    if (viaApi) {
      const btn = $("refresh-btn");
      btn.hidden = false;
      btn.addEventListener("click", startRefresh);
      // Re-display the last update result (survives the reload) or
      // resume polling if an update is still running.
      try {
        const st = await (await fetch("/api/refresh/status", { cache: "no-store" })).json();
        if (st.allowed === false) { btn.hidden = true; return; }
        if (st.running) {
          btn.disabled = true;
          setRefreshStatus("Downloading and extracting…", false);
          pollRefresh();
        } else if (st.last) {
          setRefreshStatus(st.last.message, !st.last.ok);
        }
      } catch (_) { /* status unavailable: harmless */ }
    }

    // Local data freshness
    const src = data.source;
    if (src && src.last_granule_date) {
      $("last-granule-row").hidden = false;
      $("last-granule").textContent = fmtDateShort(src.last_granule_date);
    }

    const select = $("site-select");
    data.sites.forEach((s) => {
      const opt = document.createElement("option");
      opt.value = s.name;
      opt.textContent = s.name;
      select.appendChild(opt);
    });
    select.addEventListener("change", (e) => selectSite(e.target.value));

    // Sans API, le site tourne sur des fichiers pré-calculés.
    state.staticMode = !viaApi;
    if (state.staticMode) {
      state.manifest = await loadManifest();
      if (state.manifest) {
        try {
          state.staticIndex = await loadStaticIndex();
          state.paramGrid = paramGrid(state.staticIndex.scenarios);
        } catch (_) { state.manifest = null; }
      }
    }

    state.area = await loadArea();
    renderHome();
    state.extent = await loadExtent();
    refreshDownloadButtons();
    state.imagery = await loadImageryConfig();
    initMap(data.lake, data.sites);

    let stored = null;
    try { stored = sessionStorage.getItem("lke-site"); } catch (_) { /* ignore */ }
    const first = data.sites.find((s) => s.name === stored)
      || data.sites.find((s) => s.latest)
      || data.sites[0];
    selectSite(first.name);

    // Asynchronous: neither waits on BOM nor on the NetCDF read.
    // The scenario depends on the weather, so it follows.
    wireScenario();
    wireTimeline();
    state.areaIdx = Math.max(0, areaDates().length - 1);
    drawAreaChart();
    loadIndependentData(true);
  }

  document.addEventListener("DOMContentLoaded", () => {
    // Les onglets fonctionnent même si les données manquent
    wireTabs();
    wireDownloads();
    wireRainRivers();
    init();
  });
})();
