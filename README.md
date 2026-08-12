Web dashboard for tracking recent conditions at Kati Thanda–Lake Eyre andcomparing them with pre-computed Delft3D simulations.

The dashboard currently brings together:

water levels derived from SWOT;

weather observations from the Bureau of Meteorology (BOM);

MODIS and VIIRS imagery from NASA GIBS;

wave and current fields from Delft3D-FLOW/SWAN.

The data processing is handled in Python. The frontend only reads the filesgenerated in data/, so observations can be updated without changing theinterface itself.

Installation

The project was developed with Python 3.10 or later. Using a virtual environmentis recommended.

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

On Windows, activate the environment with:

.venv\Scripts\activate

First run

python startup.py

This checks config.yaml, updates the SWOT and BOM data, indexes thesimulations, creates the compact dataset when needed, and starts the server.Steps are skipped when their outputs already exist.

The first run can take several hours, mainly because of the SWOT download andthe compaction of the Delft3D outputs. Later runs are much quicker.

Available options:

Option

Description

--skip-download

use only the SWOT granules already on disk

--skip-compact

do not create the compact NetCDF file

--layers 0,9

retain the selected layers during compaction

--force

rebuild outputs even when they already exist

--no-serve

prepare the data without starting the server

To start the website without running the full setup:

python run.py

The dashboard will be available at http://127.0.0.1:8000.

Configuration

Paths, weather stations, extraction sites, and model settings are defined inconfig.yaml. The main entries to check before the first run are:

paths.swot_data: directory containing the SWOT granules;

sites: coordinates of the extraction points;

weather.stations: BOM stations shown on the dashboard;

scenarios.directory: directory containing the Delft3D outputs;

scenarios.design_csv: experimental design, when available;

scenarios.wlvl_site: SWOT site used to match water levels to scenarios.

Two sites are included by default: Belt Bay and Madigan Gulf. A vertical offsetcan be applied to the WSE at each site with datum_offset.

Updating the data

SWOT

# Download new granules and update the time series
python pipeline/update_swot.py --download

# Rebuild the time series from files already on disk
python pipeline/update_swot.py

# Generate synthetic data for testing the interface
python pipeline/update_swot.py --demo

The workflow is incremental. Granules that have already been processed arerecorded in data/extraction_cache.json and are not read again on every run.The cache for a site is invalidated automatically if the main extractionsettings change.

Two options are available for checking or bypassing the cache:

python pipeline/update_swot.py --rebuild-cache
python pipeline/update_swot.py --no-cache

Downloads are handled with earthaccess. On the first run, Earthdatacredentials are requested in the terminal and stored in ~/.netrc. Credentialsshould never be added to this repository.

The default collection is SWOT_L2_HR_Raster_D. Version C granules may stillbe kept as an archive, but a single processing version should be used for dataintended for publication.

BOM observations

python pipeline/fetch_weather.py

Observations are written to data/weather.json. They are fetched through Flaskbecause the BOM endpoints cannot be queried directly from the browser. Theserver uses a 15-minute cache by default.

A rolling local archive is retained. If a station becomes unavailable, itslatest valid observation remains visible rather than being removed.

MODIS and VIIRS imagery

Satellite basemaps are served by NASA GIBS. The available layers are listed inimagery.layers in config.yaml. The default configuration includes:

Name

GIBS layer

MODIS 7-2-1

MODIS_Terra_CorrectedReflectance_Bands721

MODIS true colour

MODIS_Terra_CorrectedReflectance_TrueColor

VIIRS 7-2-1

VIIRS_SNPP_CorrectedReflectance_BandsM11-I2-I1

The 7-2-1 composite is used by default because it separates shallow water fromthe surrounding salt surface more clearly. MODIS imagery has a maximum nativeresolution of 250 m, so zooming in further does not reveal additional detail.

Delft3D scenarios

The dashboard selects the pre-computed scenario closest to the observed windspeed, wind direction, water level, and salinity.

Building the index

python pipeline/scenario_index.py
python pipeline/scenario_index.py --list
python pipeline/scenario_index.py --demo

Scenario parameters are read from the filenames. For example:

wind-sp12_5_wind-dir270_0_wlvl-11_0_sal250_0.nc

represents a wind speed of 12.5 m/s, a wind direction of 270°, a water level of-11.0 m, and a salinity of 250 g/L. WAVE outputs use the wave_ prefix; FLOWoutputs are identified from their directory.

If scenarios.design_csv is set, the index compares the available files withthe experimental design and reports missing runs. AppleDouble files (._*.nc),hidden directories, and incomplete NetCDF files are ignored.

The full simulation archive can be checked with:

python pipeline/check_runs.py
python pipeline/check_runs.py --csv bad_runs.csv

Matching observations to scenarios

The match is based on a normalised distance between the observations and thesimulated parameters. Wind direction is treated as a circular variable. Therelative weights can be changed in config.yaml.

For each parameter, the dashboard shows the observed value, the value from theselected scenario, and the difference between them. It also warns when anobservation falls outside the simulated range.

The main conversion settings are:

Setting

Purpose

wind_station

BOM station used for the wind conditions

wind_dir_convention

wind direction expressed as from or to

wlvl_offset

offset between the SWOT and model vertical datums

The timeline uses the recent weather archive. Moving along it selects adifferent steady-state scenario; it does not move through time within a singlesimulation.

Displayed fields

The map can display:

current speed and direction;

significant wave height;

wavelength;

wave period.

To inspect the structure of a file before adding it to the index:

python pipeline/scenario_field.py --inspect path/to/file.nc

The reader supports the FLOW and WAVE grids, vertical layers, and model timesteps. Fields are reprojected from the MGA model grid to WGS84 before they aredisplayed in Leaflet.

Dry cells are masked with S1 for FLOW and depth for WAVE. This mattersbecause a zero velocity may describe calm water and should not be mistaken fora dry cell.

Compact dataset

The complete Delft3D outputs occupy about 200 GB, although the dashboard usesonly a small part of them. pipeline/compact.py collects the required fields ina single NetCDF file:

python pipeline/scenario_index.py
python pipeline/compact.py --dry-run
python pipeline/compact.py --limit 5
python pipeline/compact.py --layers 0,9 --time -1

Layer indices start at zero. In the example above, layers 1 and 10 are retained.If the process is interrupted, it can be resumed with:

python pipeline/compact.py --layers 0,9 --resume

The output is saved as data/compact.nc. It contains one time step perscenario, shared coordinates, and only the variables used by the dashboard.Values are encoded as 16-bit integers and compressed with zlib. The firstscenario is read back immediately to check the encoding.

The server uses the compact file automatically when it exists and falls back tothe original NetCDF files otherwise.

API

The main routes are:

Route

Content

/api/wse

complete SWOT time series

/api/wse/latest

latest observation for each site

/api/weather

BOM observations

/api/scenarios

simulation index

/api/scenario/match

closest scenario

/api/scenario/field

scalar field from a scenario

/api/scenario/currents

current field and vectors

/api/health

server status

POST /api/refresh

run the SWOT update in the background

/api/refresh/status

update status

Examples:

/api/scenario/match?wind_speed=25&wind_dir=270&wlvl=-11
/api/scenario/match?at=2026-08-10T03:00:00Z

Tests

The main tests do not require local SWOT granules:

python tests/test_pipeline_wiring.py
python tests/test_incremental.py
python tests/test_weather.py

They cover the connection with SWOT_toolbox, incremental processing, timeseries filtering, and the retrieval of weather observations.

Static export

A static version can be generated for GitHub Pages:

python pipeline/export_static.py
python pipeline/export_static.py --limit 20

The result is written to site/. Rasters and arrows are generated in advancebecause GitHub Pages cannot run Flask or read NetCDF files directly.

The static version retains the data views, satellite imagery, weather, andscenario matching. The SWOT update button is disabled, so the data must beregenerated locally before publishing.

The .github/workflows/pages.yml workflow publishes site/. Theweather.yml workflow can update the BOM observations, provided that the BOMservers accept requests from GitHub-hosted runners.

Deploying with Flask

To retain the complete functionality, including live updates and dynamic accessto the simulations, run Gunicorn behind Nginx:

pip install gunicorn
gunicorn -c deploy/gunicorn.conf.py deploy.wsgi:app

The deploy/ directory contains:

wsgi.py, the application entry point;

gunicorn.conf.py, the Gunicorn configuration;

lake-eyre.service, an example systemd service;

nginx.conf, an example HTTPS reverse-proxy configuration.

Before making the dashboard public, disable updates triggered from theinterface:

export LKE_ALLOW_REFRESH=0

The same setting can be applied with allow_refresh: false in config.yaml.

Repository structure

lake-eyre-dashboard/
├── SWOT_toolbox/          # SWOT extraction tools
├── pipeline/              # data download and preparation
├── backend/               # Flask application and API
├── frontend/              # HTML, CSS, and JavaScript interface
├── data/                  # files generated by the pipeline
├── deploy/                # Gunicorn, Nginx, and systemd configuration
├── tests/                 # pipeline and API tests
├── config.yaml
├── requirements.txt
├── run.py
└── startup.py

NetCDF outputs, generated JSON files, .netrc, and AppleDouble files areexcluded through .gitignore.

Notes

The point previously labelled “Belt Bay” at 137.560° E is in Madigan Gulf.Belt Bay and Madigan Gulf are now stored as separate sites.

SWOT_toolbox is used almost unchanged. The import of SWOT_plot is madeoptional so that the server does not require the mapping dependencies.

A reprocessed SWOT granule may have a different filename and be downloadedalongside the older version. Removing the old file prevents two observationsfrom being retained for the same date.

Never commit Earthdata credentials or other secrets. Removing a secret aftera commit does not remove it from the Git history.
