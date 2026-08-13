/* Wind rose logic — kept separate so it can be unit-tested under Node.
 *
 * Day and night are decided from the actual solar elevation at the
 * lake rather than from fixed clock hours: the point of splitting them
 * is the boundary layer, which follows the sun, not the timezone.
 */

(function (root) {
  "use strict";

  const DEG = Math.PI / 180;

  // ── Solar position (NOAA low-precision, ~0.01° — ample here) ──

  function julianCenturies(date) {
    // Days since J2000.0 (2000-01-01 12:00 UTC)
    return (date.getTime() / 86400000) + 2440587.5 - 2451545.0;
  }

  function solarElevation(date, lat, lon) {
    const n = julianCenturies(date);
    const L = (280.460 + 0.9856474 * n) % 360;
    const g = ((357.528 + 0.9856003 * n) % 360) * DEG;
    const lambda = (L + 1.915 * Math.sin(g) + 0.020 * Math.sin(2 * g)) * DEG;
    const eps = (23.439 - 0.0000004 * n) * DEG;

    const dec = Math.asin(Math.sin(eps) * Math.sin(lambda));
    const ra = Math.atan2(Math.cos(eps) * Math.sin(lambda), Math.cos(lambda));

    // Greenwich mean sidereal time, in hours
    let gmst = (18.697374558 + 24.06570982441908 * n) % 24;
    if (gmst < 0) gmst += 24;
    const lmst = gmst * 15 + lon;                  // degrees
    const H = (lmst - ra / DEG) * DEG;             // hour angle

    const phi = lat * DEG;
    return Math.asin(Math.sin(phi) * Math.sin(dec)
      + Math.cos(phi) * Math.cos(dec) * Math.cos(H)) / DEG;
  }

  function isDaytime(date, lat, lon) {
    return solarElevation(date, lat, lon) > 0;
  }

  // ── Period selection ─────────────────────────────────────

  function obsDate(rec) {
    const u = rec && rec.utc;
    if (!u || u.length < 14) return null;
    return new Date(Date.UTC(+u.slice(0, 4), +u.slice(4, 6) - 1,
      +u.slice(6, 8), +u.slice(8, 10), +u.slice(10, 12)));
  }

  const PERIODS = {
    all: { label: "All" },
    d7: { label: "7 days", hours: 168, phase: "day" },
    n7: { label: "7 nights", hours: 168, phase: "night" },
    h24: { label: "24 h", hours: 24 },
    lastday: { label: "Last day", phase: "day", contiguous: true },
    lastnight: { label: "Last night", phase: "night", contiguous: true },
  };

  /* Observations belonging to the requested period.
   *
   * "Last day" and "Last night" walk back from the most recent
   * observation and keep the last unbroken run of the requested phase,
   * so they describe one real daylight or night period rather than a
   * fixed window.
   */
  function selectPeriod(history, period, lat, lon, now) {
    const spec = PERIODS[period] || PERIODS.all;
    const withDate = (history || [])
      .map((r) => ({ rec: r, at: obsDate(r) }))
      .filter((o) => o.at)
      .sort((a, b) => a.at - b.at);
    if (!withDate.length) return [];

    const reference = now || withDate[withDate.length - 1].at;

    let pool = withDate;
    if (spec.hours) {
      const cutoff = reference.getTime() - spec.hours * 3600000;
      pool = pool.filter((o) => o.at.getTime() >= cutoff);
    }

    if (!spec.phase) return pool.map((o) => o.rec);

    const wantDay = spec.phase === "day";
    const tagged = pool.map((o) =>
      Object.assign({ day: isDaytime(o.at, lat, lon) }, o));

    if (!spec.contiguous) {
      return tagged.filter((o) => o.day === wantDay).map((o) => o.rec);
    }

    let end = -1;
    for (let i = tagged.length - 1; i >= 0; i--) {
      if (tagged[i].day === wantDay) { end = i; break; }
    }
    if (end < 0) return [];
    let start = end;
    while (start > 0 && tagged[start - 1].day === wantDay) start -= 1;
    return tagged.slice(start, end + 1).map((o) => o.rec);
  }

  // ── Directional binning ──────────────────────────────────

  const SECTORS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
                   "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"];
  // Upper bounds in km/h; the last bin is open-ended
  const SPEED_BINS = [10, 20, 30, 40, Infinity];
  const SPEED_LABELS = ["< 10", "10–20", "20–30", "30–40", "≥ 40"];

  /* Counts per direction sector and speed bin, as percentages.
   *
   * Following meteorological convention, sectors give the direction
   * the wind blows FROM — the same convention the Bureau reports.
   * Calm readings have no meaningful direction and are counted apart.
   */
  function binRose(records) {
    const counts = SPEED_BINS.map(() => SECTORS.map(() => 0));
    let calm = 0, total = 0;

    (records || []).forEach((r) => {
      const spd = r.wind_spd_kmh;
      if (spd === null || spd === undefined) return;
      total += 1;
      const deg = r.wind_dir_deg;
      if (spd <= 0 || deg === null || deg === undefined) { calm += 1; return; }
      const sector = Math.round(((deg % 360) + 360) % 360 / 22.5) % 16;
      let bin = SPEED_BINS.findIndex((hi) => spd < hi);
      if (bin < 0) bin = SPEED_BINS.length - 1;
      counts[bin][sector] += 1;
    });

    const scale = total ? 100 / total : 0;
    return {
      sectors: SECTORS,
      labels: SPEED_LABELS,
      series: counts.map((row) => row.map((c) => c * scale)),
      total, calm,
      calmPercent: total ? (calm * 100) / total : 0,
      max: Math.max(0, ...SECTORS.map((_, s) =>
        counts.reduce((sum, row) => sum + row[s], 0) * scale)),
    };
  }

  const api = { solarElevation, isDaytime, selectPeriod, binRose,
                obsDate, PERIODS, SECTORS, SPEED_BINS, SPEED_LABELS };

  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    root.WindRose = api;
  }
})(typeof self !== "undefined" ? self : this);
