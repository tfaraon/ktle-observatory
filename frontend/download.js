/* CSV export — kept separate so it can be unit-tested under Node.
 *
 * Files are built in the browser from data already loaded, so the
 * buttons work behind Flask and on the static site alike.
 *
 * Each file carries a commented header describing the source, the
 * datum and the processing, so a downloaded series stays interpretable
 * once it has left the site.
 */

(function (root) {
  "use strict";

  function escapeCell(value) {
    if (value === null || value === undefined) return "";
    const text = String(value);
    return /[",\n]/.test(text) ? '"' + text.replace(/"/g, '""') + '"' : text;
  }

  /* Header lines (prefixed with #), column names, then rows. */
  function toCSV(columns, rows, meta) {
    const lines = (meta || []).map((line) => "# " + line);
    lines.push(columns.join(","));
    rows.forEach((row) => lines.push(row.map(escapeCell).join(",")));
    return lines.join("\n") + "\n";
  }

  function stamp(date) {
    return (date || new Date()).toISOString().slice(0, 10);
  }

  function slug(text) {
    return String(text).toLowerCase().replace(/[^a-z0-9]+/g, "-")
      .replace(/^-|-$/g, "");
  }

  // ── SWOT water levels ────────────────────────────────────

  function wseRows(data) {
    const rows = [];
    (data.sites || []).forEach((site) => {
      (site.series || []).forEach((r) => {
        rows.push([site.name, site.lon, site.lat, r.date, r.wse]);
      });
    });
    return rows;
  }

  function wseCSV(data) {
    const meta = [
      "Kati Thanda-Lake Eyre observatory - water surface elevation",
      "Source: SWOT L2 HR Raster (NASA/CNES), " + (data.datum_label || "WSE (m)"),
      "Extraction: mean over a 13x13 pixel window, wse_qual 0-2, "
        + "IQR outlier filter",
      "Dates are UTC; no observation means no valid SWOT pass, not a gap",
      "Generated: " + new Date().toISOString(),
    ];
    if (data.demo) meta.push("WARNING: synthetic demonstration data");
    return {
      name: `ktle_water_levels_${stamp()}.csv`,
      text: toCSV(["site", "longitude", "latitude", "date_utc", "wse_m"],
                  wseRows(data), meta),
    };
  }

  // ── BOM weather ──────────────────────────────────────────

  const WEATHER_COLUMNS = ["station", "latitude", "longitude", "date_utc",
                           "wind_dir", "wind_dir_deg", "wind_speed_kmh",
                           "gust_kmh", "air_temp_c", "relative_humidity_pct",
                           "pressure_hpa", "rain_since_9am_mm"];

  function weatherRows(wx) {
    const rows = [];
    (wx.stations || []).forEach((st) => {
      (st.history || []).forEach((r) => {
        rows.push([st.name, st.lat, st.lon, r.utc, r.wind_dir, r.wind_dir_deg,
                   r.wind_spd_kmh, r.gust_kmh, r.air_temp, r.rel_hum,
                   r.press_hpa, r.rain_since_9am]);
      });
    });
    return rows;
  }

  function weatherCSV(wx) {
    const meta = [
      "Kati Thanda-Lake Eyre observatory - weather observations",
      "Source: Australian Bureau of Meteorology",
      "Wind speed is a ten-minute mean; dates are UTC (YYYYMMDDhhmmss)",
      "Generated: " + new Date().toISOString(),
    ];
    if (wx.demo) meta.push("WARNING: synthetic demonstration data");
    if (wx.stale) meta.push("WARNING: some stations were unreachable; "
      + "their last known reading is included");
    return {
      name: `ktle_weather_${stamp()}.csv`,
      text: toCSV(WEATHER_COLUMNS, weatherRows(wx), meta),
    };
  }

  // ── Lake surface area ────────────────────────────────────

  const AREA_CITATION =
    "Method: Rai, A.K., Cohen, T.J., Armon, M. & Marx, S.K. (2026). "
    + "Volumetric analysis of a playa lake using SWOT data: an improved "
    + "understanding of the inflows to Kati Thanda-Lake Eyre. "
    + "Journal of Hydrology 676, 135652. "
    + "https://doi.org/10.1016/j.jhydrol.2026.135652";

  function areaRows(area) {
    return (area.series || []).map((r) => [
      r.date, r.area_km2, r.uncert_km2, r.coverage,
      r.partial ? "partial" : "full", r.n_scenes]);
  }

  function areaCSV(area) {
    const meta = [
      "Kati Thanda-Lake Eyre observatory - surface water area",
      "Source: SWOT L2 HR Raster (NASA/CNES)",
      AREA_CITATION,
    ];
    if (area.note) meta.push("Note: " + area.note);
    meta.push("Rows flagged 'partial' come from a pass covering only part "
      + "of the lake and understate the area");
    meta.push("Generated: " + new Date().toISOString());
    return {
      name: `ktle_water_area_${stamp()}.csv`,
      text: toCSV(["date", "area_km2", "uncertainty_km2", "coverage_fraction",
                   "pass_coverage", "n_scenes"], areaRows(area), meta),
    };
  }

  // ── Model layer ──────────────────────────────────────────

  function layerMeta(d, scenario) {
    const meta = [
      "Kati Thanda-Lake Eyre observatory - Delft3D model output",
      `Field: ${d.label}${d.units ? " (" + d.units + ")" : ""}`,
      "Model: Delft3D-FLOW / SWAN, steady state",
      "Coordinates are WGS84 decimal degrees",
    ];
    if (scenario) {
      meta.push("Scenario: " + scenario.key);
      const p = scenario.params || {};
      meta.push(`Parameters: wind ${p.wind_speed} m/s from ${p.wind_dir} deg, `
        + `water level ${p.wlvl} m, salinity ${p.salinity} g/L`);
    }
    meta.push("Generated: " + new Date().toISOString());
    return meta;
  }

  /* The grid is exported when the field values are available; the
   * static site only holds a pre-rendered image, so the arrows — which
   * also carry direction — are exported instead. */
  function layerCSV(d, scenario) {
    const base = `ktle_${slug(d.layer || d.label)}`
      + (scenario ? "_" + slug(scenario.key) : "");

    if (d.z && d.lat && d.lon) {
      const rows = [];
      d.z.forEach((row, iy) => row.forEach((value, ix) => {
        if (value === null || value === undefined) return;
        rows.push([d.lon[ix], d.lat[iy], value]);
      }));
      return {
        name: `${base}_grid.csv`,
        text: toCSV(["longitude", "latitude", "value"], rows,
                    layerMeta(d, scenario).concat(
                      "Rows are grid points where the lake is wet")),
      };
    }

    const a = (d.arrows || {});
    const rows = (a.lat || []).map((lat, i) =>
      [a.lon[i], lat, a.bearing[i], a.value[i]]);
    return {
      name: `${base}_arrows.csv`,
      text: toCSV(["longitude", "latitude", "bearing_deg", "value"], rows,
                  layerMeta(d, scenario).concat(
                    "Bearing is the true direction the vector points towards")),
    };
  }

  // ── Trigger a download from a string ─────────────────────

  function save(file) {
    // The BOM keeps Excel from mangling non-ASCII characters.
    const blob = new Blob(["\ufeff" + file.text],
                          { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = file.name;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  const api = { toCSV, escapeCell, wseCSV, weatherCSV, areaCSV, layerCSV,
                wseRows, weatherRows, areaRows, WEATHER_COLUMNS,
                AREA_CITATION, slug, save };

  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    root.Download = api;
  }
})(typeof self !== "undefined" ? self : this);
