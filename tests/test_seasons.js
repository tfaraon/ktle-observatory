/* Mise en forme du graphique saisonnier (frontend/seasons.js), sans
 * navigateur ni Plotly.
 *
 * Ce qui peut se tromper ici n'est pas le dessin mais les nombres qu'on
 * donne a dessiner :
 *   - un ecart a la moyenne calcule sur une annee tronquee serait
 *     negatif par construction et ferait croire a une secheresse ;
 *   - une moyenne glissante qui enjambe un trou ou un bord lisse une
 *     fenetre plus courte sans le dire ;
 *   - une saison incomplete empilee comme un total se lit comme une
 *     annee seche ;
 *   - le rang d'une annee seche compte depuis l'autre bout.
 *
 * Execution :  node tests/test_seasons.js
 */

"use strict";
const assert = require("assert");
const S = require("../frontend/seasons.js");

function year(y, warm, cool, complete) {
  return {
    year: y, warm_mm: warm, cool_mm: cool,
    total_mm: warm === null || cool === null ? null : Math.round((warm + cool) * 10) / 10,
    warm_months: warm === null ? 0 : 6, cool_months: cool === null ? 0 : 6,
    complete: complete !== false,
  };
}

// ── Empilement ──────────────────────────────────────────────

const sea = {
  period: { first: 1990, last: 1994 },
  norms: { from: 1990, to: 1993, warm_mm: 100, cool_mm: 40, total_mm: 140,
           warm_share: 71 },
  latest: year(1993, 60, 30),
  latest_rank: { rank: 4, of: 4 },
  sparse_before: 1950,
  series: [year(1990, 100, 40), year(1991, 200, 50), year(1992, 40, 30),
           year(1993, 60, 30), year(1994, null, 20, false)],
};

const st = S.traces(sea, "stack");
assert.strictEqual(st.length, 2, "deux saisons empilees");
// La fraiche d'abord, pour qu'elle soit au bas de la pile
assert(st[0].name.includes("Cool"), st[0].name);
assert(st[1].name.includes("Warm"), st[1].name);
assert.deepStrictEqual(st[1].y, [100, 200, 40, 60, null]);
assert.deepStrictEqual(st[0].x, [1990, 1991, 1992, 1993, 1994]);
assert.strictEqual(S.layout(sea, "stack").barmode, "stack");

// L'annee incomplete doit etre hachuree, et elle seule
const shapes = st[1].marker.pattern.shape;
assert.deepStrictEqual(shapes, ["", "", "", "", "/"], shapes);

// La moyenne de longue periode doit apparaitre comme repere
const lay = S.layout(sea, "stack");
assert.strictEqual(lay.shapes[0].y0, 140);
assert(lay.annotations[0].text.includes("140"), lay.annotations[0].text);
// Sans moyenne connue, pas de repere fantome a zero
const noNorm = S.layout({ series: sea.series, norms: {} }, "stack");
assert(!noNorm.shapes, "repere trace sans moyenne");

// ── Ecart a la moyenne ──────────────────────────────────────

const an = S.traces(sea, "anomaly");
assert.strictEqual(an.length, 1);
assert.deepStrictEqual(an[0].y, [0, 110, -70, -50, null], an[0].y);
// Une annee tronquee ne doit pas apparaitre comme un deficit
assert.strictEqual(an[0].y[4], null, "annee incomplete comptee comme sèche");
// Les annees seches dans la couleur seche, les humides dans l'eau
const cols = an[0].marker.color;
assert.strictEqual(cols[1], S.COLOURS.warm, "annee humide mal coloree");
assert.strictEqual(cols[2], S.COLOURS.dry, "annee seche mal coloree");
assert.strictEqual(cols[4], S.COLOURS.warm, "null doit rester neutre");
assert.strictEqual(S.layout(sea, "anomaly").showlegend, false,
  "une seule serie : pas de legende");
assert(S.layout(sea, "anomaly").yaxis.title.includes("from the long-term mean"));
// Sans moyenne, rien a tracer plutot qu'un graphique faux
assert.deepStrictEqual(S.traces({ series: sea.series, norms: {} }, "anomaly"), []);

// ── Moyenne glissante ───────────────────────────────────────

const flat = [];
for (let y = 1900; y <= 1920; y += 1) flat.push(year(y, 100, 40));
const run = S.running(flat, "warm_mm", 11);
// Les cinq premieres et dernieres annees n'ont pas de fenetre complete
assert.deepStrictEqual(run.slice(0, 5), [null, null, null, null, null]);
assert.strictEqual(run[5], 100, run[5]);
assert.deepStrictEqual(run.slice(-5), [null, null, null, null, null]);

// Un trou doit couper la ligne, pas la lisser sur moins d'annees
const holed = flat.map((r, i) => (i === 10 ? year(r.year, null, 40, false) : r));
const runHoled = S.running(holed, "warm_mm", 11);
assert.strictEqual(runHoled[10], null, "fenetre trouee lissee quand meme");
assert.strictEqual(runHoled[5], null, "le trou doit couper toute fenetre le contenant");

const warmT = S.traces(sea, "warm");
assert.strictEqual(warmT.length, 2);
assert.strictEqual(warmT[1].connectgaps, false,
  "une ligne qui relie les trous invente des annees");

// ── Phrases et reserves ─────────────────────────────────────

const sum = S.summary(sea);
assert(sum.includes("1990–1993"), sum);
assert(sum.includes("140 mm"), sum);
assert(sum.includes("71%"), sum);
// Rang 4 sur 4 : c'est l'annee la plus seche, et elle doit se dire ainsi
assert(sum.includes("1st driest of 4"), sum);

const wetYear = Object.assign({}, sea, { latest_rank: { rank: 1, of: 4 } });
assert(S.summary(wetYear).includes("1st wettest of 4"), S.summary(wetYear));

// Un rang au milieu ne doit pas se maquiller en fait remarquable :
// « la 61e plus seche sur 126 » est vrai et ne dit rien
assert.strictEqual(S.standing({ rank: 66, of: 126 }),
  "close to the middle of the 126 years on record");
assert.strictEqual(S.standing({ rank: 3, of: 126 }), "the 3rd wettest of 126");
assert.strictEqual(S.standing({ rank: 126, of: 126 }), "the 1st driest of 126");
assert.strictEqual(S.standing({ rank: 120, of: 126 }), "the 7th driest of 126");
assert.strictEqual(S.standing(null), "");
assert(S.summary(Object.assign({}, sea, { latest_rank: { rank: 63, of: 126 } }))
  .includes("close to the middle"));

const notes = S.notes(sea);
assert(notes.includes("October 1974 to March 1975"), "convention absente");
assert(notes.includes("Hatched"), "les barres hachurees doivent etre expliquees");
assert(!notes.includes("demonstration"), "faux avertissement de demo");
// La serie d'essai commence en 1990 : la reserve sur les pluviometres
// rares ne doit pas s'afficher pour une periode qui ne la concerne pas
assert(!notes.includes("1950"), notes);

// Serie qui remonte avant 1950 : la reserve devient obligatoire
const old = Object.assign({}, sea, { period: { first: 1900, last: 1994 } });
assert(S.notes(old).includes("1950"), "reserve sur les pluviometres rares absente");
assert(S.notes(old).includes("order of magnitude"), S.notes(old));

const demo = S.notes(Object.assign({ demo: true, warnings: ["1974-03: HTTP 500"] }, sea));
assert(demo.includes("demonstration data"), demo);
assert(demo.includes("HTTP 500"), "avertissement du pipeline non repris");

// ── Cas vides ───────────────────────────────────────────────

assert.deepStrictEqual(S.traces({ series: [] }, "stack"), []);
assert.deepStrictEqual(S.traces(null, "stack"), []);
assert.strictEqual(S.summary(null), "");
assert.strictEqual(S.notes(null), "");
assert.strictEqual(S.summary({ series: [], norms: {}, period: {} }), "");

// ── Ordinaux ────────────────────────────────────────────────

const ord = [1, 2, 3, 4, 11, 12, 13, 21, 22, 23, 101, 111, 112].map(S.ordinal);
assert.deepStrictEqual(ord, ["1st", "2nd", "3rd", "4th", "11th", "12th",
  "13th", "21st", "22nd", "23rd", "101st", "111th", "112th"], ord);

console.log("OK — graphique saisonnier : empilement et hachures des saisons "
  + "tronquées, écarts à la moyenne et leurs couleurs, moyenne glissante "
  + "coupée aux trous, rang d'une année sèche, réserves et cas vides.");
