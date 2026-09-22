/* Test de la logique d'affichage eBird (frontend/ebird.js).
 *
 *   node tests/test_ebird.js
 *
 * Ce qui est verifie : l'ordre d'affichage (oiseaux d'eau indicateurs en
 * tete), la mise a l'ecart des lieux prives sur la carte, le traitement
 * des especes notees presentes sans effectif, et le calcul des ages.
 */

"use strict";

const assert = require("assert");
const path = require("path");
const E = require(path.join(__dirname, "..", "frontend", "ebird.js"));

// ── Dates et ages ────────────────────────────────────────────
const now = new Date(Date.UTC(2026, 8, 22, 12, 0));
assert.strictEqual(E.daysAgo("2026-09-22 08:15", now), 0);
assert.strictEqual(E.daysAgo("2026-09-19", now), 3);
assert.strictEqual(E.daysAgo("", now), null);
assert.strictEqual(E.daysAgo("pas une date", now), null);
// Une date future (horloges decalees) ne donne pas d'age negatif
assert.strictEqual(E.daysAgo("2026-09-25", now), 0);
assert(E.formatDate("2026-09-03 10:00").includes("2026"));

// ── Effectifs : « X » dans eBird = présent, non compté ───────
assert.strictEqual(E.formatCount(null), "present");
assert.strictEqual(E.formatCount("X"), "present");
assert.strictEqual(E.formatCount(0), "present");
assert.strictEqual(E.formatCount(1200), (1200).toLocaleString("en-AU"));

assert.strictEqual(E.speciesUrl("bansti1"), "https://ebird.org/species/bansti1");

// ── Ordre : indicateurs, notables, puis le reste ─────────────
const species = [
  { speciesCode: "a", obsDt: "2026-09-20", indicator: false, notable: false,
    locId: "L1", locName: "Halligan Bay", lat: -28.6, lng: 137.2 },
  { speciesCode: "b", obsDt: "2026-09-10", indicator: true, notable: false,
    locId: "L1", locName: "Halligan Bay", lat: -28.6, lng: 137.2 },
  { speciesCode: "c", obsDt: "2026-09-15", indicator: false, notable: true,
    locId: "L2", locName: "Level Post Bay", lat: -29.2, lng: 137.4 },
  { speciesCode: "d", obsDt: "2026-09-21", indicator: true, notable: false,
    locId: null, locName: null, lat: null, lng: null, locationPrivate: true },
];
const sorted = E.sortSpecies(species).map((s) => s.speciesCode);
assert.deepStrictEqual(sorted, ["d", "b", "c", "a"], sorted);
// La liste d'origine n'est pas modifiée
assert.strictEqual(species[0].speciesCode, "a");

// ── Carte : les lieux privés n'y figurent pas ────────────────
const groups = E.locationGroups(species);
assert.strictEqual(groups.length, 2, "deux localités publiques");
assert.strictEqual(groups[0].name, "Halligan Bay");
assert.strictEqual(groups[0].species.length, 2);
assert.strictEqual(groups[0].last, "2026-09-20");
assert(!groups.some((g) => g.species.some((s) => s.locationPrivate)),
  "aucune espèce d'un lieu privé sur la carte");

// ── Résumé ───────────────────────────────────────────────────
const sum = E.summary({
  species,
  indicators: [{ present: true }, { present: true }, { present: false }],
}, now);
assert.strictEqual(sum.nSpecies, 4);
assert.strictEqual(sum.nIndicators, 3);
assert.strictEqual(sum.nIndicatorsPresent, 2);
assert.strictEqual(sum.nPrivate, 1);
assert.strictEqual(sum.latest, "2026-09-21");
assert.strictEqual(sum.latestAge, 1);

const empty = E.summary({}, now);
assert.strictEqual(empty.nSpecies, 0);
assert.strictEqual(empty.latestAge, null);
assert.deepStrictEqual(E.locationGroups(undefined), []);

console.log("OK — ages, effectifs « présent », ordre indicateurs puis notables, "
  + "lieux privés absents de la carte, résumé.");
