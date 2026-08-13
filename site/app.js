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
    modelData: null,
    arrowPx: 16,       // arrow length in screen pixels
    staticMode: false, // no server: pre-rendered layers
    manifest: null, staticIndex: null, paramGrid: null,
    staticArrows: null, staticArrowsKey: null,
    methodsLoaded: false,
    weather: null,
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
    return `${date} · ${time} UTC`;
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
        setRefreshStatus(st.last.message + " · reloading…", false);
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
      attribution: "© OpenTopoMap (CC-BY-SA) · © OpenStreetMap",
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
      attribution: `${spec.layer} — NASA EOSDIS GIBS / Worldview`,
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
        ? `${site.latest.wse.toFixed(2)} m · ${fmtDateShort(site.latest.date)}`
        : "no data";
      m.bindTooltip(`<strong>${site.name}</strong><br>${latest}`);
      m.on("click", () => selectSite(site.name));
      state.markers[site.name] = m;
    });

    wireMapBar();
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

    Plotly.newPlot(chart, [past, latest], {
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
      hovermode: "closest",
    }, { displayModeBar: false, responsive: true });
  }

  // ── Animated counter ─────────────────────────────────────

  function setValue(target) {
    const node = $("wse-value");
    if (reduceMotion) { node.textContent = target.toFixed(2); return; }
    const from = parseFloat(node.textContent) || target;
    const t0 = performance.now(), dur = 550;
    (function tick(t) {
      const p = Math.min(1, (t - t0) / dur);
      const eased = 1 - Math.pow(1 - p, 3);
      node.textContent = (from + (target - from) * eased).toFixed(2);
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
        `${site.stats.n} obs · ${site.stats.min.toFixed(2)} to ${site.stats.max.toFixed(2)} m`;
    } else {
      $("wse-value").textContent = "—";
      $("latest-date").textContent = "no data";
      $("latest-age").textContent = "—";
      $("series-span").textContent = "—";
    }
    $("site-coords").textContent =
      `${site.lat.toFixed(3)}, ${site.lon.toFixed(3)}`;
    $("chart-title").textContent = `SWOT water surface elevation — ${site.name}`;

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
           + `<p class="wx-error">Unavailable${st.error ? " — " + st.error : ""}</p></div>`;
    }
    const l = st.latest;
    const dir = l.wind_dir || "variable";
    const age = bomAge(l.utc) || "";
    const ageTxt = st.stale ? `${age} · last known reading` : age;
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
        ? `${l.wind_dir || "variable"} ${fmtNum(l.wind_spd_kmh, " km/h")} · `
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
          + " · gusts %{customdata[0]:.0f}"
          + " · %{customdata[1]}<extra>" + st.name + "</extra>",
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
      hovertemplate: "%{theta} · %{r:.1f} %<extra>"
        + rose.labels[k] + " km/h</extra>",
    })).filter((t) => t.r.some((v) => v > 0));
  }

  function drawRose(el, station, records) {
    const rose = WindRose.binRose(records);
    if (!rose.total) {
      el.innerHTML = `<div class="rose-empty">${station.name}<br>`
        + `no observations in this period</div>`;
      return 0;
    }
    Plotly.newPlot(el, roseTraces(rose), {
      title: { text: `${station.name} · ${rose.total} obs`,
               font: { size: 12, family: "Archivo, sans-serif" } },
      margin: { l: 30, r: 30, t: 34, b: 22 },
      height: 260,
      paper_bgcolor: "rgba(0,0,0,0)",
      font: { family: "Archivo, sans-serif", size: 10, color: "#241F1A" },
      polar: {
        bgcolor: "rgba(0,0,0,0)",
        radialaxis: { ticksuffix: "%", angle: 45, tickfont: { size: 9 },
                      gridcolor: "#E9E3D6" },
        angularaxis: { direction: "clockwise", rotation: 90,
                       tickfont: { size: 9 }, gridcolor: "#E9E3D6" },
      },
      barmode: "stack",
      showlegend: false,
    }, { displayModeBar: false, responsive: true });
    return rose.total;
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

    // L'archive se construit au fil des relevés : dire franchement
    // ce que la période couvre réellement évite de sur-interpréter
    // une rose bâtie sur quelques heures.
    const span = archiveSpanHours(stations);
    const spec = WindRose.PERIODS[state.rosePeriod] || {};
    const note = $("rose-note");
    const bits = [`direction the wind blows from · ${shown} observations`];
    if (span !== null) bits.push(`archive spans ${span.toFixed(0)} h`);
    const short = spec.hours && span !== null && span < spec.hours * 0.9;
    if (short) {
      bits.push(`this period needs ${spec.hours} h — it will fill in as `
        + `observations accumulate`);
    }
    note.textContent = bits.join(" · ");
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
    strip.innerHTML = wx.stations.map(stationCard).join("");

    const note = $("weather-updated");
    const parts = [];
    if (wx.demo) parts.push("demonstration data");
    if (wx.stale) parts.push("cached — BOM unreachable");
    parts.push("fetched " + fmtDate(wx.fetched_at.replace("Z", "")));
    note.textContent = parts.join(" · ");
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

  function matchStatic(scenarios, grid, target, weights) {
    const scales = paramScales(grid);
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

    let best = scenarios[0], bestD = Infinity;
    scenarios.forEach((s) => {
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
      envelope, warnings, alternatives: [],
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
    const cfg = state.manifest.matching || {};
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
      <span class="match-delta">${out ? "outside simulated range · " : ""}${dTxt}</span>
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
    return bits.join(" · ");
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

  function clearModelLayer() {
    state.modelData = null;
    ["modelRaster", "modelShafts", "modelHeads"].forEach((k) => {
      if (state[k]) { state.map.removeLayer(state[k]); state[k] = null; }
    });
    $("map-legend").hidden = true;
  }

  function showLegend(d, lo, hi) {
    $("legend-title").textContent = `${d.label}${d.units ? " (" + d.units + ")" : ""}`;
    $("legend-min").textContent = lo.toFixed(hi < 2 ? 2 : 0);
    $("legend-max").textContent = hi.toFixed(hi < 2 ? 2 : 0);
    $("map-legend").hidden = false;
  }

  async function drawModelLayer() {
    if (!state.map) return;
    if (state.modelLayer === "none" || !state.scenario) {
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
        + `unavailable — ${e.message}`);
      setModelNote("Layer unavailable — " + e.message, true);
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
    drawArrows(d, hi);
    showLegend(d, lo, hi);
    buildModelSelectors(d);
    if (!d.zmax) {
      showMapMessage(`${d.label} is zero everywhere in this scenario `
        + `(calm conditions) — the lake outline is still shown.`);
    }
    setModelNote(`${d.label} · ${d.n_arrows} arrows`
      + (d.warning ? " · " + d.warning : ""), Boolean(d.warning));
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
      + (state.fieldTime !== null ? "&time=" + state.fieldTime : "");
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

    const [vmin, vmax] = man.scales[fileId] || [0, 1];
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

  function buildModelButtons() {
    const seg = $("model-seg");
    const specs = [
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
      + `<br>Conditions: ${originNote(m.origin, m.demo, m.at)}${coverageNote(m)}`
      + `<br><span id="scenario-note"></span></p>`;


    $("scenario-reset").hidden = !Object.keys(m.overrides || {}).length;
    // The matched run drives whatever model layer is shown on the map.
    drawModelLayer();
  }


  function coverageNote(m) {
    const c = m.coverage;
    if (!c || !c.n_missing) return "";
    return ` · design: ${c.n_done}/${c.n_design_unique} runs present`;
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
    const match = matchStatic(idx.scenarios, state.paramGrid, target,
                              (state.manifest.matching || {}).weights);
    renderScenario(body, {
      target, origin, match, at: query && query.at ? query.at : null,
      overrides: {}, demo: false,
      units: idx.units || {}, labels: idx.labels || {},
    });
  }

  function wireScenario() {
    $("scenario-reset").addEventListener("click", () => loadScenario(null));
  }

  // ── Tabs ─────────────────────────────────────────────────

  function showTab(name) {
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

    // Leaflet et Plotly calculent leurs dimensions au moment du rendu :
    // masqués, ils mesurent zéro et restent figés au retour.
    if (name === "observatory") {
      requestAnimationFrame(() => {
        if (state.map) state.map.invalidateSize();
        ["chart", "weather-history"].forEach((id) => {
          const el = $(id);
          if (el && el.data) Plotly.Plots.resize(el);
        });
        document.querySelectorAll(".rose-cell").forEach((el) => {
          if (el.data) Plotly.Plots.resize(el);
        });
      });
    }

    try { history.replaceState(null, "", "#" + name); } catch (_) { /* ignore */ }
  }

  function wireTabs() {
    document.querySelectorAll(".tab").forEach((b) =>
      b.addEventListener("click", () => showTab(b.dataset.tab)));
    const initial = (location.hash || "").replace("#", "");
    if (["methods", "publications"].includes(initial)) showTab(initial);
  }

  // ── Initialisation ───────────────────────────────────────

  async function init() {
    const { data, viaApi } = await loadData();

    if (!data || !data.sites) {
      $("empty-state").hidden = false;
      return;
    }

    state.data = data;
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
    loadWeather().then(() => loadScenario(null));
  }

  document.addEventListener("DOMContentLoaded", () => {
    // Les onglets fonctionnent même si les données manquent
    wireTabs();
    init();
  });
})();
