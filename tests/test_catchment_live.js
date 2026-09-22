/* Test de frontend/catchment_live.js :  node tests/test_catchment_live.js */
"use strict";
const assert = require("assert");
const path = require("path");
const C = require(path.join(__dirname, "..", "frontend", "catchment_live.js"));

assert.strictEqual(C.unitLabel("cumec"), "m\u00b3/s");
assert.strictEqual(C.unitLabel("ML/d"), "ML/day");
assert.strictEqual(C.unitLabel("m"), "m");
assert.strictEqual(C.statusLabel("flowing"), "Flowing");
assert.strictEqual(C.statusLabel("inconnu"), "No recent data");
assert.notStrictEqual(C.statusColour("flowing"), C.statusColour("no flow"));

const lg = C.legend({ breaks_mm: [1, 5, 10], colours: ["#a", "#b", "#c"] });
assert.deepStrictEqual(lg.map((x) => x.label), ["1\u20135 mm", "5\u201310 mm", "10 mm and more"]);
assert.deepStrictEqual(C.legend(undefined), []);

assert.strictEqual(C.fmtNumber(1234.6), (1235).toLocaleString("en-AU"));
assert.strictEqual(C.fmtNumber(12.34), "12.3");
assert.strictEqual(C.fmtNumber(null), "");
assert.deepStrictEqual(C.lastN([1, 2, 3, 4], 2), [3, 4]);
assert.deepStrictEqual(C.lastN(undefined, 2), []);

const st = { name: "Cooper Ck at Nappa Merrie", status: "flowing",
             discharge: { unit: "cumec", last: { date: "2026-09-20", value: 14 } } };
assert.deepStrictEqual(C.latest(st, "discharge"), { value: 14, date: "2026-09-20", unit: "m\u00b3/s" });
assert.strictEqual(C.latest(st, "level"), null);

const s = C.summary(
  { sum7: { to: "2026-09-20", mean_mm: 3.2, max_mm: 41 } },
  { stations: [st, { name: "Dry", status: "no flow" }] });
assert.strictEqual(s.length, 2);
assert(s[0].includes("3.2 mm") && s[0].includes("41 mm") && s[0].includes("20 September"), s[0]);
assert(s[1].startsWith("One of the two gauges with recent data reports flow"), s[1]);
assert(s[1].includes("Nappa Merrie"));
assert.deepStrictEqual(C.summary(null, null), []);

console.log("OK — unités, états des stations, légende, nombres, synthèse.");
