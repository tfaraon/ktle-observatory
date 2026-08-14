# Kati Thanda–Lake Eyre Dashboard

Web dashboard for tracking recent conditions at Kati Thanda–Lake Eyre and
comparing them with pre-computed Delft3D simulations.

The dashboard currently brings together:

- water levels derived from SWOT;
- weather observations from the Bureau of Meteorology (BOM);
- MODIS and VIIRS imagery from NASA GIBS;
- wave and current fields from Delft3D-FLOW/SWAN.

The data processing is handled in Python. The frontend only reads the files
generated in `data/`, so observations can be updated without changing the
interface itself.

The interface is organised in three tabs: **Observatory** for the data views,
**Methods** for the technical documentation shown on the site, and
**Publications**.

## Installation

The project was developed with Python 3.10 or later. Using a virtual environment
is recommended.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

On Windows, activate the environment with:

```
.venv\Scripts\activate
```

## First run

```bash
python startup.py
```

This checks `config.yaml`, updates the SWOT and BOM data, indexes the
simulations, creates the compact dataset when needed, and starts the server.
Steps are skipped when their outputs already exist.

The first run can take several hours, mainly because of the SWOT download and
the compaction of the Delft3D outputs. Later runs are much quicker.

Available options:

| Option | Description |
|---|---|
| `--skip-download` | use only the SWOT granules already on disk |
| `--skip-swot` | skip the SWOT step entirely |
| `--skip-weather` | skip the BOM step |
| `--skip-compact` | do not create the compact NetCDF file |
| `--layers 0,9` | retain the selected layers during compaction |
| `--force` | rebuild outputs even when they already exist |
| `--no-serve` | prepare the data without starting the server |

To start the website without running the full setup:

```bash
python run.py
```

The dashboard will be available at http://127.0.0.1:8000.

## Configuration

Paths, weather stations, extraction sites, and model settings are defined in
`config.yaml`. The main entries to check before the first run are:

- `paths.swot_data`: directory containing the SWOT granules;
- `sites`: coordinates of the extraction points;
- `weather.stations`: BOM stations shown on the dashboard;
- `scenarios.directory`: directory containing the Delft3D outputs;
- `scenarios.design_csv`: experimental design, when available;
- `scenarios.wlvl_site`: SWOT site used to match water levels to scenarios.

Two sites are included by default: Belt Bay and Madigan Gulf. A vertical offset
can be applied to the WSE at each site with `datum_offset`.

## Updating the data

### SWOT

```bash
# Download new granules and update the time series
python pipeline/update_swot.py --download

# Rebuild the time series from files already on disk
python pipeline/update_swot.py

# Generate synthetic data for testing the interface
python pipeline/update_swot.py --demo
```

The workflow is incremental. Granules that have already been processed are
recorded in `data/extraction_cache.json` and are not read again on every run.
The cache for a site is invalidated automatically if the main extraction
settings change; renaming a site does not invalidate it, since the cache key is
based on coordinates.

Two options are available for checking or bypassing the cache:

```bash
python pipeline/update_swot.py --rebuild-cache
python pipeline/update_swot.py --no-cache
```

Downloads are handled with `earthaccess`. On the first run, Earthdata
credentials are requested in the terminal and stored in `~/.netrc`. Credentials
should never be added to this repository.

The default collection is `SWOT_L2_HR_Raster_D`. Version C granules may still
be kept as an archive, but a single processing version should be used for data
intended for publication.

### Surface water area

```bash
python pipeline/lake_area.py
python pipeline/lake_area.py --limit 5      # quick check
python pipeline/lake_area.py --workers 1    # sequential, for debugging
```

Granules are processed in parallel across cores. Two shortcuts do most of the
work before that: the reprojection is vectorised, and each granule is rejected
up front if its UTM zone or its bounding box does not meet the lake, so scenes
from other regions cost almost nothing. Both are covered by tests, since a
rejection that is slightly too aggressive would silently drop water.

Water area is computed from the SWOT granules already on disk, following:

> Rai, A.K., Cohen, T.J., Armon, M. & Marx, S.K. (2026). Volumetric analysis of
> a playa lake using SWOT data: an improved understanding of the inflows to
> Kati Thanda–Lake Eyre. *Journal of Hydrology* **676**, 135652.
> https://doi.org/10.1016/j.jhydrol.2026.135652 Cells are kept where the water fraction lies between
0.1 and 0.99 and the quality flag is good or suspect; a 5×5 median filter
removes isolated detections; retained cell areas are summed and uncertainties
combined in quadrature. The series is written to `data/lake_area.json` and
shown in its own panel and downloadable as CSV with the reference in its
header. The retained water mask is also rasterised to `data/area_maps/`, one
PNG per pass, and can be viewed on the map through the **SWOT water** layer,
with a date selector. Opacity follows the water fraction, so partially flooded
margins read paler than open water.

> Rai, A.K., Cohen, T.J., Armon, M. & Marx, S.K. (2026). Volumetric analysis of
> a playa lake using SWOT data: an improved understanding of the inflows to
> Kati Thanda–Lake Eyre. *Journal of Hydrology* **676**, 135652.
> <https://doi.org/10.1016/j.jhydrol.2026.135652> — open access, CC BY.

Two departures from the published method are worth knowing. The paper works on
the PIXC point cloud, whereas this uses the Raster product already downloaded.
More importantly, the paper constrains SWOT with a Sentinel-3 OLCI water mask,
because wet salt crust and very shallow water are nearly indistinguishable to
KaRIn; that mask is absent here, replaced by the Delft3D model domain. The
constraint is spatial rather than spectral, so **the area is an upper bound**.
Passes covering less than `area.min_coverage` of the domain are flagged and
drawn as open circles, so that an incomplete pass is not read as a drying lake.
Granules that do not intersect the lake — the download directory may hold
scenes from other regions — are counted and reported separately.

The `uncertainty_km2` column is the quadrature sum of the per-cell
uncertainties reported by the product. It is a **formal precision, not a
validated accuracy**: it will look implausibly small, because it says nothing
about how well SWOT separates shallow water from wet salt. The source paper
reports around 15 % error against optical water masks, which is the figure to
quote.

### BOM observations

```bash
python pipeline/fetch_weather.py
```

Observations are written to `data/weather.json`. They are fetched through Flask
because the BOM endpoints cannot be queried directly from the browser. The
server uses a 15-minute cache by default.

A rolling local archive is retained, covering `weather.history_hours`
(168 h by default). The Bureau only publishes the most recent 72 hours, so the
archive builds up over successive runs. If a station becomes unavailable, its
latest valid observation remains visible rather than being removed. Synthetic
data produced by `--demo` is never merged with real observations.

The weather panel shows a wind rose for each station, with a period selector:
*All*, *7 days*, *7 nights*, *24 h*, *Last day*, *Last night*. Day and night are
separated using the solar elevation at the lake rather than clock hours, so the
split follows the boundary layer rather than the timezone. The seven-day roses
remain partial until the archive has filled.

### MODIS and VIIRS imagery

Satellite basemaps are served by NASA GIBS. The available layers are listed in
`imagery.layers` in `config.yaml`. The default configuration includes:

| Name | GIBS layer |
|---|---|
| MODIS 7-2-1 | `MODIS_Terra_CorrectedReflectance_Bands721` |
| MODIS true colour | `MODIS_Terra_CorrectedReflectance_TrueColor` |
| VIIRS 7-2-1 | `VIIRS_SNPP_CorrectedReflectance_BandsM11-I2-I1` |

The 7-2-1 composite is used by default because it separates shallow water from
the surrounding salt surface more clearly. MODIS imagery has a maximum native
resolution of 250 m, so zooming in further does not reveal additional detail.

## Delft3D scenarios

The dashboard selects the pre-computed scenario closest to the observed wind
speed, wind direction, water level, and salinity.

### Building the index

```bash
python pipeline/scenario_index.py
python pipeline/scenario_index.py --list
python pipeline/scenario_index.py --demo
```

Scenario parameters are read from the filenames. For example:

```
wind-sp12_5_wind-dir270_0_wlvl-11_0_sal250_0.nc
```

represents a wind speed of 12.5 m/s, a wind direction of 270°, a water level of
-11.0 m, and a salinity of 250 g/L. WAVE outputs use the `wave_` prefix; FLOW
outputs are identified from their directory.

If `scenarios.design_csv` is set, the index compares the available files with
the experimental design and reports missing runs. AppleDouble files (`._*.nc`),
hidden directories, and incomplete NetCDF files are ignored.

The full simulation archive can be checked with:

```bash
python pipeline/check_runs.py
python pipeline/check_runs.py --csv bad_runs.csv
```

### Matching observations to scenarios

The match is based on a normalised distance between the observations and the
simulated parameters. Wind direction is treated as a circular variable. The
relative weights can be changed in `config.yaml`.

For each parameter, the dashboard shows the observed value, the value from the
selected scenario, and the difference between them. It also warns when an
observation falls outside the simulated range.

The main conversion settings are:

| Setting | Purpose |
|---|---|
| `wind_station` | BOM station used for the wind conditions |
| `wind_dir_convention` | wind direction expressed as `from` or `to` |
| `wlvl_offset` | offset between the SWOT and model vertical datums |
| `colour_scale` | `auto` fits the palette to each scenario; `fixed` uses `layer_scales` |
| `wlvl_rounding` | `down` restricts the match to levels at or below the observed one; `nearest` allows either side |

`wlvl_rounding` defaults to `down`. Selecting a scenario above the observed
level would simulate more water than there is, which on a shallow lake changes
wave dissipation and current speeds appreciably.

The timeline uses the recent weather archive. Moving along it selects a
different steady-state scenario; it does not move through time within a single
simulation.

### Displayed fields

The colour scale defaults to `auto`: bounds are fitted to each scenario using
the 99th percentile, so a calm regime stays legible and a handful of edge
artefacts cannot flatten the palette. The map has an **Auto scale / Fixed
scale** button; fixed bounds make colours comparable between scenarios but
often leave quiet scenarios almost uniform. Hovering the map reads out the
value under the cursor.

The map can display:

- current speed and direction;
- significant wave height;
- wavelength;
- wave period.

To inspect the structure of a file before adding it to the index:

```bash
python pipeline/scenario_field.py --inspect path/to/file.nc
```

The reader supports the FLOW and WAVE grids, vertical layers, and model time
steps. Fields are reprojected from the MGA model grid to WGS84 before they are
displayed in Leaflet. Current vectors are rotated from the grid axes to map
axes and corrected for meridian convergence; wave arrows follow the SWAN
convention, in which `dir` is the direction waves come from.

Dry cells are masked with `S1` for FLOW and `depth` for WAVE. This matters
because a zero velocity may describe calm water and should not be mistaken for
a dry cell.

## Compact dataset

The complete Delft3D outputs occupy about 200 GB, although the dashboard uses
only a small part of them. `pipeline/compact.py` collects the required fields in
a single NetCDF file:

```bash
python pipeline/scenario_index.py
python pipeline/compact.py --dry-run
python pipeline/compact.py --limit 5
python pipeline/compact.py --layers 0,9 --time -1
```

Layer indices start at zero. In the example above, layers 1 and 10 are retained.
If the process is interrupted, it can be resumed with:

```bash
python pipeline/compact.py --layers 0,9 --resume
```

The output is saved as `data/compact.nc`. It contains one time step per
scenario, shared coordinates, and only the variables used by the dashboard.
Values are encoded as 16-bit integers and compressed with zlib. The first
scenario is read back immediately to check the encoding.

The server uses the compact file automatically when it exists and falls back to
the original NetCDF files otherwise.

## API

The main routes are:

| Route | Content |
|---|---|
| `/api/wse` | complete SWOT time series |
| `/api/wse/latest` | latest observation for each site |
| `/api/weather` | BOM observations |
| `/api/area` | water area time series |
| `/api/config` | imagery layers used by the frontend |
| `/api/scenarios` | simulation index |
| `/api/scenario/match` | closest scenario |
| `/api/scenario/maplayer` | map layer, resampled to WGS84 |
| `/api/scenario/field` | scalar field from a scenario |
| `/api/scenario/currents` | current field and vectors |
| `/api/health` | server status |
| `POST /api/refresh` | run the SWOT update in the background |
| `/api/refresh/status` | update status |

Examples:

```
/api/scenario/match?wind_speed=25&wind_dir=270&wlvl=-11
/api/scenario/match?at=2026-08-10T03:00:00Z
```

## Tests

None of the tests require local SWOT granules or Delft3D outputs; synthetic
files are created as needed.

```bash
python tests/test_pipeline_wiring.py     # connection with SWOT_toolbox
python tests/test_incremental.py         # incremental extraction and cache
python tests/test_weather.py             # BOM parsing and rolling archive
python tests/test_scenarios.py           # filename parsing and matching
python tests/test_scenario_field.py      # NetCDF fields and map layers
python tests/test_geo.py                 # MGA to WGS84 reprojection
python tests/test_compact.py             # compact dataset encoding
python tests/test_export_static.py       # static export
python tests/test_startup.py             # first-run sequence
python tests/test_lake_area.py           # water area from SWOT
python tests/test_language.py            # interface strings stay in English
node tests/test_windrose.js              # solar elevation and wind roses
node tests/test_download.js              # CSV export
```

The interface is in English. Labels and warnings shown on the site come partly
from Python and partly from JavaScript, so `test_language.py` inspects the
payloads actually served as well as the frontend strings. Code comments,
docstrings, and terminal output from the pipeline scripts remain in French.

## Downloading data from the interface

Each panel has a CSV export button: the SWOT series for all sites, the local
weather archive, and the model field currently displayed. Files are built in
the browser, so the buttons work behind Flask and on the static site alike.

Every file starts with commented metadata lines giving the source, the datum
and the processing, so a downloaded series stays interpretable once separated
from the site. Where the field values are available the full grid is exported;
the static site holds only the pre-rendered image, so the arrows are exported
instead.

## Static export

A static version can be generated for GitHub Pages:

```bash
python pipeline/export_static.py
python pipeline/export_static.py --limit 20
```

The result is written to `site/`. Rasters and arrows are generated in advance
because GitHub Pages cannot run Flask or read NetCDF files directly. Scenario
matching is repeated in JavaScript, using the same metric as the server.

The static version retains the data views, satellite imagery, weather, and
scenario matching. The SWOT update button is disabled, so the data must be
regenerated locally before publishing.

A full export is only needed when the simulations change. After a new SWOT pass,
copying `data/swot_wse.json` into `site/data/` is enough.

The `.github/workflows/pages.yml` workflow publishes `site/`. The
`weather.yml` workflow can update the BOM observations, provided that the BOM
servers accept requests from GitHub-hosted runners.

## Deploying with Flask

To retain the complete functionality, including live updates and dynamic access
to the simulations, run Gunicorn behind Nginx:

```bash
pip install gunicorn
gunicorn -c deploy/gunicorn.conf.py deploy.wsgi:app
```

The `deploy/` directory contains:

- `wsgi.py`, the application entry point;
- `gunicorn.conf.py`, the Gunicorn configuration;
- `lake-eyre.service`, an example systemd service;
- `nginx.conf`, an example HTTPS reverse-proxy configuration.

Before making the dashboard public, disable updates triggered from the
interface:

```bash
export LKE_ALLOW_REFRESH=0
```

The same setting can be applied with `allow_refresh: false` in `config.yaml`.

## Repository structure

```
lake-eyre-dashboard/
├── SWOT_toolbox/          # SWOT extraction tools
├── pipeline/              # data download and preparation
├── backend/               # Flask application and API
├── frontend/              # HTML, CSS, and JavaScript interface
├── data/                  # files generated by the pipeline
├── site/                  # static export, published by GitHub Pages
├── deploy/                # Gunicorn, Nginx, and systemd configuration
├── tests/                 # pipeline and API tests
├── .github/workflows/     # deployment and weather refresh
├── config.yaml
├── requirements.txt
├── run.py
└── startup.py
```

NetCDF outputs, generated JSON files, `.netrc`, and AppleDouble files are
excluded through `.gitignore`.

## Notes

The point previously labelled "Belt Bay" at 137.560° E is in Madigan Gulf.
Belt Bay and Madigan Gulf are now stored as separate sites.

`SWOT_toolbox` is used almost unchanged. The import of `SWOT_plot` is made
optional so that the server does not require the mapping dependencies.

A reprocessed SWOT granule may have a different filename and be downloaded
alongside the older version. Removing the old file prevents two observations
from being retained for the same date.

The scenario database is a Latin hypercube of 790 runs, covering roughly 3 % of
the parameter space. The closest scenario is therefore a compromise rather than
a match, and the reported differences should be read alongside the fields.

Never commit Earthdata credentials or other secrets. Removing a secret after
a commit does not remove it from the Git history.
