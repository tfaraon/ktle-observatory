/* Pluie saisonniere sur le bassin : mise en forme du graphique.
 *
 * Separe de app.js pour pouvoir etre verifie sous Node, sans Plotly ni
 * navigateur : ce qui peut se tromper ici n'est pas le dessin mais les
 * nombres qu'on lui donne — le sens d'un ecart a la moyenne, une
 * moyenne glissante qui enjambe un trou, une saison incomplete qui se
 * lit comme un total.
 *
 * La saison chaude va d'octobre a mars et porte l'annee de son octobre ;
 * les annees du bord sont donc incompletes. Elles restent affichees,
 * hachurees, parce qu'une barre absente se lit comme une annee seche.
 */

(function (root) {
  "use strict";

  const COLOURS = { warm: "#2A73B8", cool: "#8CC8E0",
                    dry: "#A8702D", mean: "#134450" };
  const COLUMNS = ["year", "warm_mm", "cool_mm", "total_mm"];

  /* Moyenne glissante centree, en annees. null des qu'un trou ou un bord
     entame la fenetre : mieux vaut une ligne coupee qu'une moyenne
     calculee sur moins d'annees sans le dire. */
  function running(rows, key, width) {
    const half = Math.floor(width / 2);
    return rows.map((_, i) => {
      if (i < half || i + half >= rows.length) return null;
      const win = rows.slice(i - half, i + half + 1);
      if (win.some((r) => !r.complete || r[key] === null || r[key] === undefined)) {
        return null;
      }
      return Math.round(win.reduce((a, r) => a + r[key], 0) / width * 10) / 10;
    });
  }

  function hatch(rows) {
    return rows.map((r) => (r.complete ? "" : "/"));
  }

  function bar(rows, key, name, colour) {
    return {
      x: rows.map((r) => r.year), y: rows.map((r) => r[key]),
      name: name, type: "bar",
      marker: { color: colour,
                pattern: { shape: hatch(rows), size: 3, solidity: 0.35 } },
      hovertemplate: "%{y:.0f} mm<extra>" + name + "</extra>",
    };
  }

  /* Ecart au total moyen, pour les seules annees completes. Un ecart
     calcule sur une annee tronquee serait negatif par construction. */
  function anomalies(rows, mean) {
    return rows.map((r) => (r.complete && r.total_mm !== null
      ? Math.round((r.total_mm - mean) * 10) / 10 : null));
  }

  function traces(sea, view) {
    const rows = (sea && sea.series) || [];
    if (!rows.length) return [];
    if (view === "warm") {
      return [
        bar(rows, "warm_mm", "Warm season (Oct–Mar)", COLOURS.warm),
        { x: rows.map((r) => r.year), y: running(rows, "warm_mm", 11),
          name: "11-year mean", type: "scatter", mode: "lines",
          line: { color: COLOURS.mean, width: 2 }, connectgaps: false,
          hovertemplate: "%{y:.0f} mm<extra>11-year mean</extra>" },
      ];
    }
    if (view === "anomaly") {
      const mean = (sea.norms || {}).total_mm;
      if (!mean) return [];
      const dev = anomalies(rows, mean);
      return [{
        x: rows.map((r) => r.year), y: dev, name: "Departure from the mean",
        type: "bar",
        marker: { color: dev.map((v) => (v === null || v >= 0 ? COLOURS.warm : COLOURS.dry)) },
        hovertemplate: "%{y:+.0f} mm<extra>vs mean</extra>",
      }];
    }
    // Empile la saison fraiche sous la chaude : le total se lit d'un coup
    return [bar(rows, "cool_mm", "Cool season (Apr–Sep)", COLOURS.cool),
            bar(rows, "warm_mm", "Warm season (Oct–Mar)", COLOURS.warm)];
  }

  function layout(sea, view) {
    const mean = ((sea && sea.norms) || {}).total_mm;
    const out = {
      margin: { l: 62, r: 16, t: 10, b: 44 }, height: 330,
      yaxis: { title: view === "anomaly" ? "mm from the long-term mean"
                                        : "mm, basin average",
               zeroline: true, zerolinecolor: "#B9B1A0" },
      xaxis: { title: "Year", dtick: 20 },
      paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
      showlegend: view !== "anomaly",
      legend: { orientation: "h", y: 1.12, x: 0 },
      hovermode: "x unified",
    };
    if (view === "stack") {
      out.barmode = "stack";
      if (mean) {
        out.shapes = [{ type: "line", xref: "paper", x0: 0, x1: 1,
                        y0: mean, y1: mean,
                        line: { color: COLOURS.mean, width: 1.5, dash: "dash" } }];
        out.annotations = [{ xref: "paper", x: 1, y: mean, xanchor: "right",
                             yanchor: "bottom", text: "mean " + mean + " mm",
                             showarrow: false,
                             font: { size: 11, color: COLOURS.mean } }];
      }
    }
    return out;
  }

  function ordinal(n) {
    const s = ["th", "st", "nd", "rd"], v = n % 100;
    return n + (s[(v - 20) % 10] || s[v] || s[0]);
  }

  /* Ou tombe une annee dans le classement. Un rang au milieu ne veut
     rien dire : annoncer « la 61e plus seche sur 126 » donne un air de
     fait notable a une annee ordinaire. On ne nomme donc un extreme que
     dans le tiers superieur ou inferieur. */
  function standing(r) {
    if (!r || !r.of) return "";
    if (r.rank <= r.of / 3) return `the ${ordinal(r.rank)} wettest of ${r.of}`;
    if (r.rank > 2 * r.of / 3) {
      return `the ${ordinal(r.of - r.rank + 1)} driest of ${r.of}`;
    }
    return `close to the middle of the ${r.of} years on record`;
  }

  /* Une ou deux phrases qui situent la serie : la moyenne du siecle, puis
     ou tombe la derniere annee complete. */
  function summary(sea) {
    if (!sea) return "";
    const n = sea.norms || {}, lt = sea.latest;
    const out = [];
    if (n.total_mm) {
      // Les bornes sont celles de la moyenne, non celles de la serie : la
      // moyenne ne porte que sur les annees completes, et annoncer une
      // periode plus large qu'elle serait faux.
      out.push(`Over ${n.from}–${n.to} the basin received ${n.total_mm} mm `
        + `of rain a year on average, ${n.warm_share}% of it between October `
        + "and March.");
    }
    if (lt && sea.latest_rank && sea.latest_rank.of > 1) {
      out.push(`The last full year, ${lt.year}, brought ${lt.total_mm} mm — `
        + standing(sea.latest_rank) + ".");
    }
    return out.join(" ");
  }

  /* Les reserves, qui doivent rester sous le graphique et non dans une
     note de bas de page qu'on ne lit pas. */
  function notes(sea) {
    if (!sea) return "";
    const p = sea.period || {}, out = [];
    out.push("A warm season is labelled by the year of its October, so the "
      + "1974 warm season runs from October 1974 to March 1975. Hatched bars "
      + "are seasons still missing months.");
    if (sea.sparse_before && p.first < sea.sparse_before) {
      out.push(`Before ${sea.sparse_before}, rain gauges in the basin were very `
        + "few and these grids are interpolated over long distances: read the "
        + "early decades as an order of magnitude, not a measurement.");
    }
    if (sea.demo) out.push("These are demonstration data.");
    (sea.warnings || []).forEach((w) => out.push(String(w)));
    return out.join(" ");
  }

  const api = { traces, layout, summary, notes, running, anomalies,
                standing, ordinal, COLOURS, COLUMNS };
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.Seasons = api;
})(typeof self !== "undefined" ? self : this);
