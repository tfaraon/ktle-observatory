/* De la pluie au lac : decalages entre series, testable sous Node.
 *
 * Les trois maillons du bassin sont mesures separement : la pluie sur le
 * bassin (SILO), le debit aux stations (Water Data Online) et le niveau du
 * lac (SWOT). Ce module les aligne sur les memes dates et cherche le
 * decalage qui maximise leur correlation, c'est a dire le temps que l'eau
 * met a parcourir le bassin.
 *
 * Ce calcul est de premier ordre : il decrit une coincidence dans le temps,
 * pas une relation de cause a effet, et la page le dit.
 */

(function (root) {
  "use strict";

  const MIN_OVERLAP = 90;        // jours communs sous lesquels on ne conclut pas

  function toMap(pairs) {
    const m = new Map();
    (pairs || []).forEach((p) => {
      if (p && p[0] && Number.isFinite(Number(p[1]))) m.set(String(p[0]).slice(0, 10), Number(p[1]));
    });
    return m;
  }

  function addDays(iso, n) {
    const d = new Date(iso + "T00:00:00Z");
    d.setUTCDate(d.getUTCDate() + n);
    return d.toISOString().slice(0, 10);
  }

  /* Valeurs de b decalees de `lag` jours par rapport a a, sur leurs dates communes */
  function align(a, b, lag) {
    const A = toMap(a), B = toMap(b);
    const x = [], y = [], dates = [];
    [...A.keys()].sort().forEach((d) => {
      const shifted = B.get(addDays(d, lag));
      if (shifted !== undefined) { x.push(A.get(d)); y.push(shifted); dates.push(d); }
    });
    return { x, y, dates };
  }

  function pearson(x, y) {
    const n = x.length;
    if (n < 3) return null;
    const mx = x.reduce((s, v) => s + v, 0) / n;
    const my = y.reduce((s, v) => s + v, 0) / n;
    let sxy = 0, sxx = 0, syy = 0;
    for (let i = 0; i < n; i += 1) {
      const dx = x[i] - mx, dy = y[i] - my;
      sxy += dx * dy; sxx += dx * dx; syy += dy * dy;
    }
    if (sxx <= 0 || syy <= 0) return null;
    return sxy / Math.sqrt(sxx * syy);
  }

  /* Correlation pour chaque decalage de 0 a maxLag jours */
  function correlogram(a, b, maxLag) {
    const out = [];
    for (let lag = 0; lag <= maxLag; lag += 1) {
      const { x, y } = align(a, b, lag);
      const r = x.length >= MIN_OVERLAP ? pearson(x, y) : null;
      if (r !== null) out.push({ lag, r, n: x.length });
    }
    return out;
  }

  /* Decalage le plus correle, seulement s'il est net et positif */
  function bestLag(a, b, maxLag, minR) {
    const curve = correlogram(a, b, maxLag || 120);
    if (!curve.length) return null;
    const best = curve.reduce((m, p) => (p.r > m.r ? p : m), curve[0]);
    if (best.r < (minR === undefined ? 0.3 : minR)) return null;
    return { lag: best.lag, r: Math.round(best.r * 100) / 100, n: best.n, curve };
  }

  /* Somme glissante : une pluie ne fait une crue qu'accumulee sur plusieurs jours.
   * Centree par defaut : une fenetre cumulee vers l'arriere decalerait le
   * maximum d'une demi-fenetre et fausserait le temps de parcours mesure. */
  function rolling(pairs, window, trailing) {
    const rows = (pairs || []).slice().sort((p, q) => String(p[0]).localeCompare(String(q[0])));
    const half = Math.floor(window / 2);
    const out = [];
    for (let i = 0; i < rows.length; i += 1) {
      const from = trailing ? i - window + 1 : i - half;
      const to = trailing ? i : from + window - 1;
      if (from < 0 || to >= rows.length) continue;
      let sum = 0;
      for (let j = from; j <= to; j += 1) sum += Number(rows[j][1]) || 0;
      out.push([rows[i][0], Math.round(sum * 100) / 100]);
    }
    return out;
  }

  /* Variation quotidienne d'une serie de niveaux, pour la comparer a un debit */
  function dailyChange(pairs) {
    const rows = (pairs || []).slice().sort((p, q) => String(p[0]).localeCompare(String(q[0])));
    const out = [];
    for (let i = 1; i < rows.length; i += 1) {
      const gap = (new Date(rows[i][0]) - new Date(rows[i - 1][0])) / 86400000;
      if (gap > 0 && gap <= 15) {
        out.push([String(rows[i][0]).slice(0, 10), (rows[i][1] - rows[i - 1][1]) / gap]);
      }
    }
    return out;
  }

  function sentence(what, lag) {
    if (!lag) return `Not enough overlapping data yet to time ${what}.`;
    const weeks = lag.lag / 7;
    const about = weeks >= 2 ? `about ${Math.round(weeks)} weeks` : `about ${lag.lag} days`;
    return `Over the ${lag.n} days compared, ${what} line up best with a delay of ${about} `
      + `(${lag.lag} days, correlation ${lag.r.toFixed(2)}).`;
  }

  const api = { align, pearson, correlogram, bestLag, rolling, dailyChange, sentence, MIN_OVERLAP };
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.Travel = api;
})(typeof self !== "undefined" ? self : this);
