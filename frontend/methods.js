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
  <figure class="fig" data-fig="model-grid"><figcaption>The Delft3D computational grid over the lake
    bathymetry, on which the hydrodynamic scenarios are run.</figcaption></figure>
  <div class="prose-body">

    <p class="lede">This observatory brings together three sources for
    Kati Thanda&nbsp;&ndash; Lake Eyre: satellite altimetry, weather
    observations from the stations surrounding the lake, and a
    pre-computed hydrodynamic model. We describe below the processing
    applied to each, the assumptions on which it rests, and the terms
    we have neglected.</p>

    <h3 id="me-swot">Water surface elevation from SWOT</h3>

    <p>Levels come from the SWOT mission's <em>L2 HR Raster</em>
    product, distributed by NASA PO.DAAC. The KaRIn interferometer
    measures water surface elevation over a swath 120&nbsp;km wide. A
    water-body the size of Kati Thanda is therefore imaged within a
    single pass, whereas a conventional nadir altimeter samples it
    along a one-dimensional ground track.</p>

    <p>We download the granules covering the lake through
    <code>earthaccess</code> and process them with a purpose-built
    toolbox. At each extraction site, elevation is averaged over a
    13&nbsp;&times;&nbsp;13 pixel window
    (<code>buffer_size&nbsp;=&nbsp;6</code>) centred on the point. This
    window is wide enough to suppress speckle and narrow enough not to
    smooth the signal across the shoreline. We retain only pixels
    flagged <code>wse_qual</code> 0&ndash;2. Two further filters are
    applied per pass, resolution and tile: values outside
    [&minus;16,&nbsp;6]&nbsp;m are discarded, then an
    interquartile-range test removes the residual outliers. Groups of
    fewer than four observations are left untouched, since a quartile
    estimate is meaningless at that size.</p>

    <p class="caveat">Elevations are referenced to the
    <strong>EGM2008 geoid</strong>, the model SWOT distributes.
    Australian bathymetries and the contours on which the hydrodynamic
    model is built use the <strong>Australian Height Datum</strong>,
    reached through AUSGeoid2020. The two datums are not
    interchangeable, and comparing a SWOT level with a model level
    without reconciling them introduces a systematic bias. The
    <code>wlvl_offset</code> setting exists for this reconciliation. It
    is currently set to zero, and we consider that it should be
    established before any published comparison. Rai and colleagues
    found their elevations 0.45&ndash;0.55&nbsp;m above field DGPS
    surveys and applied a uniform 0.5&nbsp;m correction. This value
    gives an order of magnitude for the bias at this lake; it is not a
    correction to adopt here.</p>

    <p> Two sites are extracted. <strong>Belt Bay</strong>
    (137.028&nbsp;&deg;E, 28.893&nbsp;&deg;S) contains the lowest point
    of the lake and serves as the level reference.
    <strong>Madigan Gulf</strong> (137.560&nbsp;&deg;E) lies
    <em>ca.</em> 52&nbsp;km further east.</p>

    <p class="caveat">The series is irregular by construction. A point
    exists only where a SWOT pass covered the site and returned valid
    pixels, so a gap records the absence of an observation and not a
    missing value. For this reason the chart shows points and not a
    joined line. A dry lake returns no valid elevation at all, which
    accounts for the early gaps in the record.</p>

    <h3 id="me-extent">Water extent</h3>

    <p>The quantity SWOT measures reliably is the
    <strong>elevation</strong> of the water surface. Its pixel-by-pixel
    water classification behaves differently over a playa, where wet
    salt crust and very shallow water return almost the same
    backscatter to KaRIn, <em>ca.</em> 0&ndash;15&nbsp;dB. Read
    directly, this classification carries speckle, layover and the
    geometry of the swath.</p>

    <p>We therefore <em>derive</em> the extent from the level rather
    than read it from the radar. The flooded domain is the set of cells
    of the model bathymetry lying below the observed water surface. In
    other words, the outline we display inherits the resolution of the
    bathymetry and not the noise of the instrument, and depth and
    volume follow from the same intersection.</p>

    <p>We keep only the pool <strong>hydraulically connected</strong>
    to the low point. A hollow lying below the same level but cut off
    by a sill is not flooded, and the lake does fragment into
    sub-basins as it dries. A simple threshold on elevation would not
    reproduce this behaviour.</p>

    <p class="caveat">The bathymetry is referenced to AHD and the SWOT
    levels to EGM2008, so the intersection is only as good as
    <code>scenarios.wlvl_offset</code>. We establish this offset from
    the data. Sentinel-2 SWIR imagery provides an optical shoreline,
    which by definition lies at the true water level; the model level
    that best reproduces this shoreline, compared with the SWOT reading
    for the same date, gives the offset. Where the shore slopes gently,
    several levels fit equally well and the estimate is correspondingly
    loose. The calibration reports this plateau rather than a single
    value.</p>

    <h3 id="me-area">Surface water area</h3>

    <p>Water area follows the method of <strong>Rai, Cohen, Armon and
    Marx (2026)</strong>, <em>Volumetric analysis of a playa lake using
    SWOT data: an improved understanding of the inflows to Kati
    Thanda&ndash;Lake Eyre</em>, Journal of Hydrology 676, 135652,
    <a href="https://doi.org/10.1016/j.jhydrol.2026.135652">doi:10.1016/j.jhydrol.2026.135652</a>.
    These authors work on the same lake, and theirs is the first study
    to estimate its storage from SWOT without a hypsometric curve.
    Cells are retained where the water fraction reaches 0.1 and the
    area quality flag is good or suspect. A
    5&nbsp;&times;&nbsp;5 median filter then removes the isolated
    detections, and the retained cell areas are summed.</p>

    <p class="caveat">Working on the pixel cloud, these authors keep
    water fractions between 0.1 and 0.99. We find that this upper bound
    does not transfer to the gridded Raster product, where the
    open-water distribution lies at a fraction of 1.0 give or take
    noise. The bound then cuts through the middle of that distribution
    and discards <em>ca.</em> 60&nbsp;% of it at random, leaving a
    dither of one cell in two or three, in bands following the swath.
    We apply no upper bound here.</p>

    <p>Over a salt crust, speckle scatters false detections across the
    dry playa. On a synthetic test seeded with 1&nbsp;706 such cells,
    the median filter removed 1&nbsp;687 of them and brought the area
    error from +2.2&nbsp;% to nil.</p>

    <p class="caveat">Rai and colleagues constrain SWOT with an optical
    water mask from Sentinel-3 OLCI, because wet salt crust and very
    shallow water return almost the same backscatter to KaRIn,
    <em>ca.</em> 0&ndash;15&nbsp;dB, and cannot be separated from radar
    alone. This mask is not part of the present pipeline. We use the
    Delft3D model domain in its place, which excludes the detections
    lying outside the lake but does not separate shallow water from
    saturated salt within it. The area we report is therefore an upper
    bound, and is less accurate than the ~15&nbsp;% error the paper
    achieves with the fusion. Introducing Sentinel-3 would be the
    single most useful improvement to this pipeline.</p>

    <p>The area series has its own panel, and the retained water mask
    is kept for each pass. The <em>SWOT water</em> layer draws this
    mask over the map, with a date selector. Opacity follows the water
    fraction of each cell, so that a half-flooded margin reads paler
    than open water. A binary mask would not convey this gradation.</p>

    <p class="caveat">Two SWOT passes cover the lake and can fall on
    the same day. Their footprints overlap, so the area is computed on
    a merged grid in which each cell takes the mean of the passes that
    saw it as water. Adding the scenes together would count the same
    water twice, and nothing on the chart would betray it.</p>

    <p class="caveat">A SWOT pass does not always cover the whole lake.
    Passes observing less than 15&nbsp;% of the domain are flagged and
    drawn as open circles. Left unmarked, an incomplete pass reads as a
    drying lake, an artefact the same authors report for October
    2024.</p>

    <h3 id="me-model">Hydrodynamic model</h3>

    <p>Simulations use <strong>Delft3D-FLOW coupled with
    SWAN</strong>, on a curvilinear grid covering the lake. The flow
    model is three-dimensional, with ten vertical layers. The wave
    model supplies significant wave height, mean period, mean
    direction and wavelength.</p>

    <p>The scenario database is a <strong>Latin hypercube
    sample</strong> of 790 runs over four parameters: wind speed
    (1&ndash;35&nbsp;m/s), wind direction (eight compass points), water
    level (&minus;14 to &minus;6.5&nbsp;m) and salinity
    (0&ndash;250&nbsp;g/L). Each run is a <strong>steady
    state</strong> and not a time series: the model is driven to
    equilibrium under a fixed forcing.</p>

    <h3 id="me-matching">Selecting a scenario from the observations</h3>

    <p>Current conditions are converted into model parameters (wind
    speed from km/h to m/s, wind direction in the nautical convention,
    water level from the SWOT reference), and the nearest scenario is
    selected. Distance is normalised by the range of each parameter,
    and wind direction is treated as circular, so that 350&deg; matches
    0&deg; and not 315&deg;. Weights arbitrate which parameter to
    sacrifice: wind speed and direction drive wave generation, whereas
    salinity acts only through density.</p>

    <p>We treat water level asymmetrically, in that only scenarios at
    or <em>below</em> the observed level are eligible. Selecting a
    higher one would simulate more water than is present, and on a
    shallow lake this error compounds. At &minus;12.9&nbsp;m over a bed
    near &minus;15.2&nbsp;m, moving up to &minus;12.0&nbsp;m adds
    nearly 40&nbsp;% to the depth, and with it the wave dissipation,
    the current speeds and the set-up. Rounding down keeps the error on
    the conservative side.</p>

    <p class="caveat">A Latin hypercube of 790 runs covers
    <em>ca.</em> 3&nbsp;% of the parameter space, so the selected
    scenario is a compromise and not a match. The site reports the
    offset on every parameter, and marks in amber any condition falling
    outside the simulated range, such as a strong wind or a level below
    the lowest modelled. Moving back through the timeline changes
    <em>which</em> scenario applies; it does not advance time within a
    simulation.</p>

    <h3 id="me-fields">Display of the model fields</h3>

    <p>Model output is expressed in projected metres (MGA
    zone&nbsp;53) whereas the map works in degrees, so each field is
    resampled onto a regular geographic grid before display. Velocity
    components are stored in the axes of the computational grid. They
    are rotated to map axes and corrected for meridian convergence,
    <em>ca.</em> 1.2&deg; here, so that the arrows point to true
    bearings. Wave arrows follow the SWAN convention, in which
    <code>dir</code> is the direction waves come <em>from</em>; the
    arrows we draw show propagation.</p>

    <p>Colour bounds are fitted to each scenario by default and taken
    at the 99th percentile. A few edge cells, often interpolation
    artefacts along the shore, would otherwise compress the whole
    palette and leave a calm lake uniformly dark. The <em>Fixed
    scale</em> button switches to bounds shared by every scenario, so
    that colours become comparable along the timeline, at the cost of
    legibility on quiet days. Hovering the map reads the value under
    the cursor.</p>

    <p>We take the wet extent of the lake from a field that vanishes
    only outside water, water level for flow and depth for waves, and
    not from the displayed quantity itself. Without this distinction a
    calm lake, where currents are genuinely zero, would be
    indistinguishable from a dry one.</p>

    <h3 id="me-weather">Weather observations</h3>

    <p>Wind, temperature, humidity, pressure and rainfall come from
    three Bureau of Meteorology stations surrounding the lake:
    <strong>Marree Airport</strong>, <strong>Oodnadatta</strong> and
    <strong>Moomba Airport</strong>. Wind speed is a ten-minute mean,
    reported <em>ca.</em> every half hour. A rolling 48-hour archive is
    maintained locally, and it also drives the timeline.</p>

    <p>The wind roses show the direction the wind blows
    <em>from</em>, in sixteen sectors, stacked by speed band. Day and
    night are separated on the <strong>actual solar elevation</strong>
    at the lake and not on clock hours, the split being a physical one.
    By day, convective mixing brings momentum down from aloft and the
    wind is stronger and gustier. At night the surface layer decouples,
    and the wind often falls away or veers.</p>

    <p class="caveat">The archive builds up over time. Only the most
    recent 72&nbsp;hours can be recovered from the Bureau in one call,
    so the seven-day roses fill in progressively as observations
    accumulate. The note under the selector states how much the archive
    currently spans.</p>

    <p class="caveat">All three stations stand on land, tens of
    kilometres from the modelled water. Over a smooth and unobstructed
    salt surface the wind is typically stronger than at an inland
    station, so the matched scenarios most likely understate the true
    forcing over the lake.</p>

    <h3 id="me-imagery">Satellite imagery</h3>

    <p>Background imagery is served by NASA GIBS. The default
    combination is MODIS bands&nbsp;7&ndash;2&ndash;1. Water absorbs
    shortwave infrared strongly and appears very dark, while salt crust
    and bare ground remain bright. The shoreline reads far more clearly
    than in true colour, where shallow turbid water and salt are easily
    confused. Native resolution is 250&nbsp;m.</p>

    <h3 id="me-download">Data download</h3>

    <p>Each panel offers a CSV export: the full SWOT series for both
    sites, the local weather archive for the three stations, and the
    model field currently displayed. Files are written in the browser
    and carry a commented header giving the source, the datum and the
    processing applied, so that a downloaded series remains
    interpretable on its own.</p>

    <p>For the model layer, the full grid is exported where the field
    values are available. On the static site only the pre-rendered
    image is held, so the arrows are exported instead. They are
    coarser, but they carry direction as well as magnitude.</p>

    <h3 id="me-repro">Reproducibility</h3>

    <p>Every figure on this site is regenerated from the raw data by a
    documented pipeline: SWOT download and extraction, weather
    retrieval, scenario indexing, and compaction of the model archive.
    Source code and full method notes accompany the project.</p>

  </div>
</article>
`;
