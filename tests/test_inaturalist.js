/* Test de frontend/inaturalist.js :  node tests/test_inaturalist.js */
"use strict";
const assert = require("assert");
const path = require("path");
const I = require(path.join(__dirname, "..", "frontend", "inaturalist.js"));

assert.strictEqual(I.groupLabel("Aves"), "Birds");
assert.strictEqual(I.groupLabel("Plantae"), "Plants");
assert.strictEqual(I.groupLabel("Inconnu"), "Other");
assert.strictEqual(I.qualityLabel("research"), "Research grade");
assert.strictEqual(I.qualityLabel(undefined), "");

// Noms : commun d'abord, scientifique à part pour l'italique
let n = I.names({ taxon: { common: "Banded Stilt", name: "Cladorhynchus leucocephalus" } });
assert.deepStrictEqual(n, { primary: "Banded Stilt", scientific: "Cladorhynchus leucocephalus",
                            primaryIsScientific: false });
n = I.names({ taxon: { name: "Tecticornia" } });
assert.strictEqual(n.primary, "Tecticornia");
assert.strictEqual(n.primaryIsScientific, true);
assert.strictEqual(I.names({ guess: "a lizard" }).primary, "a lizard");
assert.strictEqual(I.names({}).primary, "Unidentified");

assert(I.formatDate("2026-09-18").includes("2026"));
assert.strictEqual(I.formatDate(""), "");

// Carte : aucune localisation masquée, aucune coordonnée incomplète
const list = [
  { id: 1, coords: [-28.9, 137.0], obscured: false },
  { id: 2, coords: null, obscured: true },
  { id: 3, coords: [-28.9, 137.0], obscured: true },
  { id: 4, coords: [-28.9], obscured: false },
];
assert.deepStrictEqual(I.mappable(list).map((o) => o.id), [1]);
assert.deepStrictEqual(I.mappable(undefined), []);

const s = I.summary({ totals: { observations: 57, species: 21, observers: 11 },
                      recent: [{ photo: {} }, { photo: null, obscured: true }] });
assert.deepStrictEqual(s, { observations: 57, species: 21, observers: 11, withPhoto: 1, hidden: 1 });
assert.strictEqual(I.summary({}).observations, 0);

// ── Groupes : iNaturalist et eBird réunis par nom scientifique ──
const inat = [
  { count: 9, url: "u1", taxon: { name: "Pelecanus conspicillatus", common: "Australian Pelican", group: "Aves" } },
  { count: 30, url: "u2", taxon: { name: "Cladorhynchus leucocephalus", common: "Banded Stilt", group: "Aves" } },
  { count: 4, url: "u3", taxon: { name: "Ctenophorus maculosus", common: "Lake Eyre Dragon", group: "Reptilia" } },
  { count: 50, url: "u4", taxon: { name: "Corvus bennetti", group: "Aves" } },
];
const eb = [
  { sciName: "Pelecanus conspicillatus", comName: "Australian Pelican", speciesCode: "auspel1", obsDt: "2026-09-20" },
  { sciName: "Recurvirostra novaehollandiae", comName: "Red-necked Avocet", speciesCode: "renavo1", obsDt: "2026-09-18" },
];
const birds = I.groupSpecies(inat, eb, ["Aves"], true);
assert.deepStrictEqual(birds.map((b) => b.name),
  ["Australian Pelican", "Red-necked Avocet", "Corvus bennetti", "Banded Stilt"]);
assert.strictEqual(birds.filter((b) => b.name === "Australian Pelican").length, 1, "pas de doublon");
assert.strictEqual(birds[0].inat, 9);
assert.strictEqual(birds[0].ebird.date, "2026-09-20");
assert.strictEqual(birds[1].inat, 0);
assert.strictEqual(birds[1].url, "https://ebird.org/species/renavo1");
assert.strictEqual(birds[2].nameIsScientific, true);
// eBird n'entre que dans le groupe des oiseaux
const reptiles = I.groupSpecies(inat, eb, ["Reptilia"], false);
assert.deepStrictEqual(reptiles.map((r) => r.name), ["Lake Eyre Dragon"]);
assert.deepStrictEqual(I.groupSpecies(undefined, undefined, ["Aves"], true), []);

console.log("OK — groupes, qualité, noms, dates, carte sans localisation masquée, résumé, "
  + "espèces par groupe réunissant iNaturalist et eBird sans doublon.");
