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

    <h3>Surface water area</h3>

    <p>Water area follows the method of <strong>Rai, Cohen, Armon and
    Marx (2026)</strong>, <em>Volumetric analysis of a playa lake using
    SWOT data</em>, Journal of Hydrology 676, 135652 &mdash; the same
    lake, and the first study to estimate its storage from SWOT without
    a hypsometric curve. Cells are retained where the water fraction
    falls between 0.1 and 0.99 and the area quality flag is good or
    suspect; a 5&nbsp;&times;&nbsp;5 median filter then removes isolated
    detections, and the retained cell areas are summed.</p>

    <p>The median filter matters more than it might seem. Over a salt
    crust, speckle scatters false detections across the dry playa; on a
    synthetic test that seeded 1&nbsp;706 such cells, the filter removed
    1&nbsp;687 of them and brought the area error from
    +2.2&nbsp;% to nil.</p>

    <p class="caveat">One departure from the published method deserves
    stating. Rai and colleagues constrain SWOT with an optical water
    mask from Sentinel-3 OLCI, because wet salt crust and very shallow
    water return almost the same backscatter to KaRIn
    (roughly 0&ndash;15&nbsp;dB) and cannot be told apart from radar
    alone. That mask is not part of this pipeline; the Delft3D model
    domain is used instead, which excludes detections outside the lake
    but does not separate shallow water from saturated salt within it.
    The area reported here is therefore an upper bound, and less
    accurate than the ~15&nbsp;% error the paper achieves with the
    fusion. Adding Sentinel-3 would be the single most useful
    improvement.</p>

    <p class="caveat">A SWOT pass does not always cover the whole lake.
    Passes observing less than 15&nbsp;% of the domain are flagged and
    drawn as open circles: an incomplete pass would otherwise read as a
    drying lake, an artefact the authors report for October 2024.</p>

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

    <p>Water level is treated asymmetrically: only scenarios at or
    <em>below</em> the observed level are eligible. Selecting a higher
    one would simulate more water than there is, and on a shallow lake
    that error compounds &mdash; at &minus;12.9&nbsp;m over a bed near
    &minus;15.2&nbsp;m, moving up to &minus;12.0&nbsp;m adds nearly
    40&nbsp;% to the depth, which changes wave dissipation, current
    speeds and set-up. Rounding down keeps the error on the
    conservative side.</p>

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

    <p>The wind roses show the direction the wind blows
    <em>from</em>, in sixteen sectors, stacked by speed band. Day and
    night are separated using the <strong>actual solar elevation</strong>
    at the lake rather than clock hours, because the point of the split
    is physical: by day, convective mixing brings momentum down from
    aloft and the wind is stronger and gustier; at night the surface
    layer decouples, and the wind often falls away or veers.</p>

    <p class="caveat">The archive builds up over time. Only the most
    recent 72&nbsp;hours can be recovered from the Bureau in one call,
    so the seven-day roses fill in progressively as observations
    accumulate. The note under the selector states how much the archive
    currently spans.</p>

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

    <h3>Downloading the data</h3>

    <p>Each panel offers a CSV export: the full SWOT series for both
    sites, the local weather archive for all three stations, and the
    model field currently displayed. Files are written in the browser
    and carry a commented header giving the source, the datum and the
    processing applied, so a downloaded series remains interpretable
    on its own.</p>

    <p>For the model layer, the full grid is exported where the field
    values are available; on the static site only the pre-rendered
    image is held, so the arrows are exported instead &mdash; coarser,
    but they carry direction as well as magnitude.</p>

    <h3>Reproducibility</h3>

    <p>Every figure on this site is regenerated from the raw data by a
    documented pipeline: SWOT download and extraction, weather
    retrieval, scenario indexing, and compaction of the model archive.
    Source code and full method notes accompany the project.</p>

  </div>
</article>
`;
