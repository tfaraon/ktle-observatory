/* Logique d'affichage des observations eBird, testable sous Node.
 *
 * Les donnees viennent de data/ebird.json, produit cote serveur par
 * pipeline/fetch_ebird.py : aucune cle ne transite par le navigateur.
 */

(function (root) {
  "use strict";

  const DAY = 86400000;

  function parseObsDate(s) {
    if (!s) return null;
    const m = /^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2}))?/.exec(s);
    if (!m) return null;
    return new Date(Date.UTC(+m[1], +m[2] - 1, +m[3], +(m[4] || 0), +(m[5] || 0)));
  }

  function daysAgo(obsDt, now) {
    const d = parseObsDate(obsDt);
    if (!d) return null;
    return Math.max(0, Math.floor(((now || new Date()) - d) / DAY));
  }

  /* eBird note « X » (espece presente, non comptee) ; l'API renvoie
   * alors un effectif absent. */
  function formatCount(n) {
    if (n === null || n === undefined || n === "" || n === "X") return "present";
    const v = Number(n);
    return Number.isFinite(v) && v > 0 ? v.toLocaleString("en-AU") : "present";
  }

  function formatDate(obsDt) {
    const d = parseObsDate(obsDt);
    if (!d) return "";
    return d.toLocaleDateString("en-AU", { day: "numeric", month: "short",
                                          year: "numeric", timeZone: "UTC" });
  }

  function speciesUrl(code) {
    return "https://ebird.org/species/" + encodeURIComponent(code || "");
  }

  /* Oiseaux d'eau indicateurs d'abord, puis especes notables, puis
   * les autres, chaque groupe du plus recent au plus ancien. */
  function sortSpecies(list) {
    const rank = (s) => (s.indicator ? 0 : s.notable ? 1 : 2);
    return (list || []).slice().sort((a, b) => {
      if (rank(a) !== rank(b)) return rank(a) - rank(b);
      return (b.obsDt || "").localeCompare(a.obsDt || "");
    });
  }

  /* Localites pour la carte. Les lieux prives n'ont plus de
   * coordonnees dans le fichier : ils n'apparaissent pas sur la carte,
   * mais leurs especes restent dans la liste. */
  function locationGroups(list) {
    const groups = new Map();
    (list || []).forEach((s) => {
      if (s.lat === null || s.lat === undefined
          || s.lng === null || s.lng === undefined) return;
      const key = s.locId || `${s.lat},${s.lng}`;
      if (!groups.has(key)) {
        groups.set(key, { key, name: s.locName || "Unnamed location",
                          lat: s.lat, lng: s.lng, species: [], last: "" });
      }
      const g = groups.get(key);
      g.species.push(s);
      if ((s.obsDt || "") > g.last) g.last = s.obsDt || "";
    });
    return [...groups.values()].sort((a, b) => b.species.length - a.species.length);
  }

  function summary(data, now) {
    const species = (data && data.species) || [];
    const indicators = (data && data.indicators) || [];
    const latest = species.reduce((m, s) => ((s.obsDt || "") > m ? s.obsDt : m), "");
    return {
      nSpecies: species.length,
      nIndicators: indicators.length,
      nIndicatorsPresent: indicators.filter((i) => i.present).length,
      nPrivate: species.filter((s) => s.locationPrivate).length,
      latest,
      latestAge: latest ? daysAgo(latest, now) : null,
    };
  }

  function hotspotUrl(locId) {
    return "https://ebird.org/hotspot/" + encodeURIComponent(locId || "");
  }

  /* Hotspots pour la carte et le tableau : les actifs (observations dans
   * la fenetre) d'abord, du plus recent au plus ancien, puis les autres. */
  function hotspotList(data) {
    return ((data && data.hotspots) || []).map((h) => ({
      locId: h.locId, name: h.name || "Unnamed hotspot", lat: h.lat, lng: h.lng,
      latest: h.latestObsDt || "", allTime: h.numSpeciesAllTime || 0,
      recent: h.recent || [], active: (h.recent || []).length > 0,
      waterbirds: (h.recent || []).filter((r) => r.indicator).length,
      url: hotspotUrl(h.locId),
    })).sort((a, b) => (a.active !== b.active ? (a.active ? -1 : 1)
      : String(b.latest).localeCompare(String(a.latest))));
  }

  /* Localites qui ne sont pas des hotspots : observations a un lieu
   * personnel public, deja dans la liste des especes. */
  function otherLocations(data) {
    const hs = new Set(((data && data.hotspots) || []).map((h) => h.locId));
    return locationGroups((data && data.species) || []).filter((g) => !hs.has(g.key));
  }

  const api = { parseObsDate, daysAgo, formatCount, formatDate, speciesUrl,
                sortSpecies, locationGroups, summary, hotspotUrl, hotspotList, otherLocations };

  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    root.EBird = api;
  }
})(typeof self !== "undefined" ? self : this);
