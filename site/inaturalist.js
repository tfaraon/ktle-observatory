/* Logique d'affichage des observations iNaturalist, testable sous Node.
 *
 * Les donnees viennent de data/inaturalist.json (pipeline/fetch_inaturalist.py).
 * Les photos y sont deja filtrees : seules celles placees sous licence par
 * leur auteur y figurent, avec leur attribution.
 */

(function (root) {
  "use strict";

  const GROUPS = {
    Aves: "Birds", Plantae: "Plants", Reptilia: "Reptiles", Mammalia: "Mammals",
    Amphibia: "Amphibians", Actinopterygii: "Fish", Insecta: "Insects",
    Arachnida: "Spiders and allies", Mollusca: "Molluscs", Fungi: "Fungi",
    Animalia: "Other animals", Protozoa: "Protozoa", Chromista: "Algae and allies",
  };

  const QUALITY = { research: "Research grade", needs_id: "Needs ID", casual: "Casual" };

  function groupLabel(g) { return GROUPS[g] || "Other"; }
  function qualityLabel(q) { return QUALITY[q] || ""; }

  /* Nom commun s'il existe, sinon nom scientifique, sinon la proposition
   * de l'observateur. Le nom scientifique est renvoye a part pour l'italique. */
  function names(o) {
    const t = (o && o.taxon) || {};
    const common = t.common || null;
    const sci = t.name || null;
    return {
      primary: common || sci || (o && o.guess) || "Unidentified",
      scientific: common && sci ? sci : null,
      primaryIsScientific: !common && Boolean(sci),
    };
  }

  function formatDate(iso) {
    if (!iso) return "";
    const d = new Date(String(iso).slice(0, 10) + "T00:00:00Z");
    if (Number.isNaN(d.getTime())) return String(iso);
    return d.toLocaleDateString("en-AU", { day: "numeric", month: "short", year: "numeric",
                                          timeZone: "UTC" });
  }

  /* Points pour la carte : jamais d'observation a localisation masquee. */
  function mappable(list) {
    return (list || []).filter((o) => !o.obscured && Array.isArray(o.coords)
      && o.coords.length === 2 && o.coords.every((v) => typeof v === "number"));
  }

  function summary(data) {
    const t = (data && data.totals) || {};
    const recent = (data && data.recent) || [];
    return {
      observations: t.observations || 0,
      species: t.species || 0,
      observers: t.observers || 0,
      withPhoto: recent.filter((o) => o.photo).length,
      hidden: recent.filter((o) => o.obscured).length,
    };
  }

  /* Especes d'un groupe, iNaturalist et eBird reunis par nom scientifique.
   * Une espece vue sur les deux plateformes n'apparait qu'une fois. Ordre :
   * les especes signalees recemment sur eBird d'abord, de la plus recente a
   * la plus ancienne, puis les autres par nombre d'observations iNaturalist. */
  function groupSpecies(inatSpecies, ebirdSpecies, groups, useEbird) {
    const wanted = new Set(groups || []);
    const bySci = new Map();
    (inatSpecies || []).forEach((sp) => {
      const t = sp.taxon || {};
      if (!wanted.has(t.group) || !t.name) return;
      bySci.set(t.name, {
        name: t.common || t.name, scientific: t.common ? t.name : null,
        nameIsScientific: !t.common, inat: sp.count || 0, url: sp.url || null,
        photo: sp.photo || null, ebird: null,
      });
    });
    if (useEbird) {
      (ebirdSpecies || []).forEach((e) => {
        if (!e.sciName) return;
        const seen = { date: e.obsDt || "", count: e.howMany || null,
                       url: "https://ebird.org/species/" + encodeURIComponent(e.speciesCode || "") };
        const cur = bySci.get(e.sciName);
        if (cur) { cur.ebird = seen; return; }
        bySci.set(e.sciName, {
          name: e.comName || e.sciName, scientific: e.comName ? e.sciName : null,
          nameIsScientific: !e.comName, inat: 0, url: seen.url, photo: null, ebird: seen,
        });
      });
    }
    return [...bySci.values()].sort((a, b) => {
      if (Boolean(a.ebird) !== Boolean(b.ebird)) return a.ebird ? -1 : 1;
      if (a.ebird && b.ebird && a.ebird.date !== b.ebird.date) return b.ebird.date.localeCompare(a.ebird.date);
      return b.inat - a.inat;
    });
  }

  const api = { groupLabel, qualityLabel, names, formatDate, mappable, summary, groupSpecies };
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.INat = api;
})(typeof self !== "undefined" ? self : this);
