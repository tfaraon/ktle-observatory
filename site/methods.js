/* Methods tab — technical documentation.
 *
 * Kept as a separate file so the text can be revised without touching
 * the application logic. Injected into #tab-methods on first view.
 */

const METHODS_HTML = `
<article class="panel">
  <div class="panel-head">
    <p class="eyebrow">Documentation</p>
    <h2>Methods</h2>
  </div>
  <div class="prose-body">

    <p class="lede">This observatory places satellite altimetry, ground
    weather observations and a pre-computed hydrodynamic model side by
    side for Kati Thanda&nbsp;&ndash; Lake Eyre. Everything below
    describes what the site actually computes, including where the
    approximations lie.</p>

    <h3>Water surface elevation from SWOT</h3>

    <p>Levels come from the SWOT mission's <em>L2 HR Raster</em>
    product, distributed by NASA PO.DAAC. The KaRIn interferometer
    measures water surface elevation over a 120&nbsp;km swath, which
    means a lake the size of Kati Thanda is imaged in a single pass
    rather than along a one-dimensional ground track as with
    conventional nadir altimeters.</p>

    <p>Granules covering the lake are downloaded through
    <code>earthaccess</code> and processed with a purpose-built
    toolbox. At each extraction site, elevation is averaged over a
    13&nbsp;&times;&nbsp;13 pixel window (<code>buffer_size&nbsp;=&nbsp;6</code>)
    centred on the point, which suppresses speckle without smoothing
    across the shoreline. Only pixels flagged <code>wse_qual</code>
    0&ndash;2 are retained. Two further filters run per pass,
    resolution and tile: values outside [&minus;16,&nbsp;6]&nbsp;m are
    discarded, then an interquartile-range test removes residual
    outliers. Groups of fewer than four observations are left
    untouched, since a quartile estimate would be meaningless.</p>

    <p>Elevations are referenced to the <strong>EGM2008
    geoid</strong>. Two sites are extracted: <strong>Belt Bay</strong>
    (137.028&nbsp;&deg;E, 28.893&nbsp;&deg;S), which contains the
    lowest point of the lake and serves as the level reference, and
    <strong>Madigan Gulf</strong> (137.560&nbsp;&deg;E), about
    52&nbsp;km further east.</p>

    <p class="caveat">The series is irregular by construction: a point
    exists only where a SWOT pass covered the site and returned valid
    pixels. Gaps are not missing data but absence of observation, so
    the chart deliberately shows points rather than a joined line.
    Note also that a dry lake yields no valid elevation at all &mdash;
    early gaps reflect a dry basin, not a sensor failure.</p>

    <h3>Hydrodynamic model</h3>

    <p>Simulations use <strong>Delft3D-FLOW coupled with
    SWAN</strong>, on a curvilinear grid covering the lake. The flow
    model is three-dimensional, with ten vertical layers; the wave
    model supplies significant wave height, mean period, mean
    direction and wavelength.</p>

    <p>The scenario database is a <strong>Latin hypercube
    sample</strong> of 790 runs over four parameters: wind speed
    (1&ndash;35&nbsp;m/s), wind direction (eight compass points), water
    level (&minus;14 to &minus;6.5&nbsp;m) and salinity
    (0&ndash;250&nbsp;g/L). Each run is a <strong>steady
    state</strong>, not a time series: the model is driven to
    equilibrium under fixed forcing.</p>

    <h3>Matching observations to a scenario</h3>

    <p>Current conditions are converted into model parameters &mdash;
    wind speed from km/h to m/s, wind direction in the nautical
    convention, water level from the SWOT reference &mdash; and the
    nearest scenario is selected. Distance is normalised by the range
    of each parameter, and wind direction is treated as circular, so
    350&deg; matches 0&deg; rather than 315&deg;. Weights arbitrate
    which parameter to sacrifice: wind speed and direction drive wave
    generation, whereas salinity acts only through density.</p>

    <p class="caveat">A Latin hypercube of 790 runs covers roughly
    3&nbsp;% of the parameter space, so the nearest scenario is a
    compromise, not a match. The site reports the offset on every
    parameter, and marks in amber any condition falling outside the
    simulated range &mdash; a strong wind, or a level below the lowest
    modelled. Moving back through the timeline changes
    <em>which</em> scenario applies; it does not advance time inside a
    simulation.</p>

    <h3>Displaying the model fields</h3>

    <p>Model output is in projected metres (MGA zone&nbsp;53) whereas
    the map works in degrees, so each field is resampled onto a regular
    geographic grid before display. Velocity components are stored in
    the grid's own axes: they are rotated to map axes, and corrected
    for meridian convergence (about 1.2&deg; here) so that arrows point
    to true bearings. Wave arrows follow the SWAN convention, in which
    <code>dir</code> is the direction waves come <em>from</em>; the
    arrows drawn show propagation.</p>

    <p>The wet extent of the lake is taken from a field that vanishes
    only outside water &mdash; water level for flow, depth for waves
    &mdash; rather than from the displayed quantity itself. Without
    that distinction a calm lake, where currents are genuinely zero,
    would be indistinguishable from a dry one.</p>

    <h3>Weather observations</h3>

    <p>Wind, temperature, humidity, pressure and rainfall come from
    three Bureau of Meteorology stations surrounding the lake:
    <strong>Marree Airport</strong>, <strong>Oodnadatta</strong> and
    <strong>Moomba Airport</strong>. Wind speed is a ten-minute mean,
    reported roughly every half hour. A rolling 48-hour archive is
    maintained locally, which also drives the timeline.</p>

    <p class="caveat">All three stations sit on land, tens of
    kilometres from the modelled water. Over a smooth, unobstructed
    salt surface the wind is typically stronger than at an inland
    station, so matched scenarios likely understate the true forcing
    over the lake.</p>

    <h3>Satellite imagery</h3>

    <p>Background imagery is served by NASA GIBS. The default
    combination is MODIS bands&nbsp;7&ndash;2&ndash;1: shortwave
    infrared is strongly absorbed by water, which therefore appears
    very dark, while salt crust and bare ground stay bright. The
    shoreline reads far more clearly than in true colour, where
    shallow turbid water and salt are easily confused. Native
    resolution is 250&nbsp;m.</p>

    <h3>Reproducibility</h3>

    <p>Every figure on this site is regenerated from the raw data by a
    documented pipeline: SWOT download and extraction, weather
    retrieval, scenario indexing, and compaction of the model archive.
    Source code and full method notes accompany the project.</p>

  </div>
</article>
`;
