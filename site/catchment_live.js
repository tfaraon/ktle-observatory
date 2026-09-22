/* Logique d'affichage de l'onglet Rain and rivers, testable sous Node.
 *
 * Donnees : data/rainfall.json (pipeline/fetch_rainfall.py, SILO) et
 * data/rivers.json (pipeline/fetch_rivers.py, Water Data Online).
 */

(function (root) {
  "use strict";

  const STATUS = {
    flowing: { label: "Flowing", colour: "#1F6470" },
    "no flow": { label: "No flow", colour: "#C9A66B" },
    "level only": { label: "Level only", colour: "#7C8B8E" },
    "no recent data": { label: "No recent data", colour: "#B8C2C4" },
  };

  function statusLabel(s) { return (STATUS[s] || STATUS["no recent data"]).label; }
  function statusColour(s) { return (STATUS[s] || STATUS["no recent data"]).colour; }

  /* Unites de Water Data Online, en notation lisible */
  function unitLabel(u) {
    const k = String(u || "").trim().toLowerCase();
    if (k === "cumec" || k === "m3/s" || k === "m^3/s") return "m\u00b3/s";
    if (k === "ml/d" || k === "ml/day") return "ML/day";
    return u || "";
  }

  function fmtNumber(v) {
    if (v === null || v === undefined || !Number.isFinite(Number(v))) return "";
    const x = Number(v);
    const digits = Math.abs(x) >= 100 ? 0 : Math.abs(x) >= 10 ? 1 : 2;
    return x.toLocaleString("en-AU", { maximumFractionDigits: digits, minimumFractionDigits: 0 });
  }

  /* Legende : une entree par classe de pluie */
  function legend(scale) {
    const b = (scale && scale.breaks_mm) || [];
    const c = (scale && scale.colours) || [];
    return b.map((lo, i) => ({
      label: i + 1 < b.length ? `${lo}\u2013${b[i + 1]} mm` : `${lo} mm and more`,
      colour: c[i] || "#999999",
    }));
  }

  function latest(st, kind) {
    const s = st && st[kind];
    return s && s.last ? { value: s.last.value, date: s.last.date, unit: unitLabel(s.unit) } : null;
  }

  function lastN(values, n) {
    return (values || []).slice(Math.max(0, (values || []).length - n));
  }

  const WORDS = ["No", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten"];
  function spell(n, lower) {
    const w = n >= 0 && n < WORDS.length ? WORDS[n] : String(n);
    return lower ? w.toLowerCase() : w;
  }

  function formatDate(iso) {
    const d = new Date(String(iso).slice(0, 10) + "T00:00:00Z");
    if (Number.isNaN(d.getTime())) return String(iso || "");
    return d.toLocaleDateString("en-AU", { day: "numeric", month: "long", timeZone: "UTC" });
  }

  /* Phrases de synthese, seulement pour ce que les donnees permettent */
  function summary(rain, rivers) {
    const out = [];
    if (rain && rain.sum7 && rain.sum7.mean_mm !== null) {
      out.push(`Over the seven days to ${formatDate(rain.sum7.to)}, an average of `
        + `${fmtNumber(rain.sum7.mean_mm)} mm fell over the basin, and up to `
        + `${fmtNumber(rain.sum7.max_mm)} mm at the wettest point.`);
    }
    const st = (rivers && rivers.stations) || [];
    if (st.length) {
      const flowing = st.filter((s) => s.status === "flowing");
      let s = `${spell(flowing.length)} of the ${spell(st.length, true)} gauges with recent data `
        + `${flowing.length === 1 ? "reports" : "report"} flow`;
      const top = flowing.map((x) => ({ x, q: latest(x, "discharge") }))
        .filter((o) => o.q).sort((a, b) => b.q.value - a.q.value)[0];
      if (top) s += `; the largest is ${fmtNumber(top.q.value)} ${top.q.unit} at ${top.x.name}`;
      out.push(s + ".");
    }
    return out;
  }

  const api = { statusLabel, statusColour, unitLabel, fmtNumber, legend, latest, lastN, summary, formatDate };
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.Catchment = api;
})(typeof self !== "undefined" ? self : this);
