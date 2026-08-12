#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue May 13 20:16:18 2025

@author: tfaraon
"""

from . import SWOT_tools as stools
import os
import matplotlib.pyplot as plt
import geopandas as gpd
from shapely.geometry import Point
import contextily as ctx
import folium
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def plot_points_on_opentopo_map(coords_list, output_path=None, zoom=10):
    """
    Affiche une carte avec les points donnés et leur nom sur fond OpenTopoMap.

    Args:
        coords_list (list): Liste de dictionnaires avec 'name', 'lon', 'lat'.
        output_path (str): Chemin pour sauvegarder la figure en PNG (facultatif).
        zoom (int): Niveau de zoom pour le fond de carte.
    """
    # Création du GeoDataFrame
    geometry = [Point(pt["lon"], pt["lat"]) for pt in coords_list]
    gdf = gpd.GeoDataFrame(coords_list, geometry=geometry, crs="EPSG:4326")
    
    # Reprojection en Web Mercator (pour contexte OpenStreetMap / OpenTopo)
    gdf_web = gdf.to_crs(epsg=3857)

    # Tracé
    fig, ax = plt.subplots(figsize=(10, 10))
    gdf_web.plot(ax=ax, color='red', markersize=50)

    # Afficher les noms
    for x, y, label in zip(gdf_web.geometry.x, gdf_web.geometry.y, gdf_web['name']):
        ax.text(x + 1000, y + 1000, label, fontsize=9, color='black')
        ax.set_aspect('equal')
    # Ajouter le fond de carte OpenTopoMap
    ctx.add_basemap(ax, source=ctx.providers.OpenTopoMap, zoom=zoom)

    ax.set_axis_off()
    plt.tight_layout()
    
    if output_path:
        plt.savefig(output_path, dpi=300)
    plt.show()
    

def plot_multipoint_WSE_timseries(swot_path, output_folder, coords_list, mnt_path = None,                 
                                  buffer_size=1,
                                  filter_resolution=None,
                                  filter_outliers=True,
                                  filter_bound=True,
                                  wse_qual_filter=[0, 1]):
    os.makedirs(output_folder, exist_ok=True)

    n = len(coords_list)
    fig, axs = plt.subplots(n, 1, figsize=(10, 2 * n), sharex=True)

    # Convert axs to array if there's only one subplot
    if n == 1:
        axs = [axs]

    if mnt_path is not None:
        # Chargement du MNT une seule fois
        mnt = stools.load_mnt(mnt_path)

        for i, point in enumerate(coords_list):
            name = point["name"]
            lon = point["lon"]
            lat = point["lat"]

            mnt_z = stools.get_mnt_value(mnt, lon, lat)

            # Extraction de la série temporelle
            wse_data = stools.extract_wse_timeseries_parallel(
                directory_path=swot_path,
                lon=lon,
                lat=lat,
                buffer_size=buffer_size,
                filter_resolution=filter_resolution,
                filter_outliers=filter_outliers,
                filter_bound=filter_bound,
                wse_qual_filter=wse_qual_filter,
                mnt_corr=mnt_z
            )

            # Vérifie que les données sont valides
            if wse_data is not None:
                axs[i].plot(wse_data["date"], wse_data["wse"], marker='o')
                axs[i].set_ylabel("WSE (m)")
                axs[i].set_title(f"{name} ({lon:.3f}, {lat:.3f})")

                output_path = os.path.join(output_folder, f"{lon}_{lat}_wse.csv")
                wse_data.to_csv(output_path, index=False)
            else:
                axs[i].text(0.5, 0.5, "No data", transform=axs[i].transAxes, ha="center", va="center")
                axs[i].set_title(f"{name} (no data)")
    else:
        for i, point in enumerate(coords_list):
            name = point["name"]
            lon = point["lon"]
            lat = point["lat"]

            # Extraction de la série temporelle
            wse_data = stools.extract_wse_timeseries_parallel(
                directory_path=swot_path,
                lon=lon,
                lat=lat,
                buffer_size=buffer_size,
                filter_resolution=filter_resolution,
                filter_outliers=filter_outliers,
                filter_bound=filter_bound,
                wse_qual_filter=wse_qual_filter
            )

            # Vérifie que les données sont valides
            if wse_data is not None:
                axs[i].plot(wse_data["date"], wse_data["wse"], marker='o')
                axs[i].set_ylabel("WSE (m)")
                axs[i].set_title(f"{name} ({lon:.3f}, {lat:.3f})")

                output_path = os.path.join(output_folder, f"{lon}_{lat}_wse.csv")
                wse_data.to_csv(output_path, index=False)
            else:
                axs[i].text(0.5, 0.5, "No data", transform=axs[i].transAxes, ha="center", va="center")
                axs[i].set_title(f"{name} (no data)")

    ymins = []
    ymaxs = []

    for ax in axs:
        lines = ax.get_lines()
        if lines:
            ydata = lines[0].get_ydata()
            ymins.append(min(ydata))
            ymaxs.append(max(ydata))

    if ymins and ymaxs:
        y_min = min(ymins)
        y_max = max(ymaxs)

        # Appliquer les mêmes limites à tous les subplots
        for ax in axs:
            ax.set_ylim(y_min, y_max)

            # Mise en forme finale
    plt.xlabel("date")
    plt.tight_layout()
    plt.show()


def plot_point_on_map(lon, lat, zoom=12):
    '''only for notebooks'''
    
    # Créer une carte centrée sur le point
    m = folium.Map(location=[lat, lon], zoom_start=zoom, 
                   tiles=None)  # tiles=None pour pouvoir choisir OpenTopoMap ensuite

    # Ajouter le fond OpenTopoMap
    folium.TileLayer(
        tiles='https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png',
        attr='© OpenTopoMap (CC-BY-SA)',
        name='OpenTopoMap'
    ).add_to(m)

    # Ajouter un marqueur
    folium.Marker(
        location=[lat, lon],
        popup=f"lon: {lon}, lat: {lat}",
        icon=folium.Icon(color='red', icon='info-sign')
    ).add_to(m)

    # Afficher la carte
    return m


def plot_timeseries_multiple(data_dict, lon=None, lat=None, title=None, var_name='wse', save_path=None):
    """
    Affiche plusieurs séries temporelles sur une figure interactive Plotly.

    Parameters:
    - data_dict (dict): dictionnaire de {nom_de_tuile: dataframe avec colonnes 'date' et 'wse'}
    - lon, lat (float, optional): coordonnées du point (utilisées pour le titre)
    - title (str, optional): titre personnalisé

    Exemple :
    plot_timeseries_multiple({
        "52F": wse_timeseries_52F,
        "53F": wse_timeseries_53F,
        "102F": wse_timeseries_102F,
        "103F": wse_timeseries_103F
    }, lon=138.2, lat=-29.8)
    """
    colors = ['blue', 'orange', 'green', 'red', 'purple', 'brown', 'cyan', 'magenta']
    fig = make_subplots()
    
    for i, (label, df) in enumerate(data_dict.items()):
        if df is None or df.empty or 'date' not in df.columns:
            print(f"Skipping tile {label}: no valid data.")
            continue
        fig.add_trace(go.Scatter(
            x=df['date'],
            y=df[var_name],
            mode='lines+markers',
            name=f'Tile {label}',
            line=dict(color=colors[i % len(colors)]),
            hovertemplate=f'<b>Date:</b> %{{x}}<br><b>{var_name}:</b> %{{y:.2f}} m<br><b>Tile:</b> {label}<extra></extra>'
        ))

    final_title = title or f'Série temporelle {var_name} à lon={lon}, lat={lat}' if lon and lat else f'Série temporelle {var_name}'
    fig.update_layout(
        title=final_title,
        xaxis_title='Date',
        yaxis_title=f'{var_name.upper()} (m)',
        legend_title='Tuiles SWOT',
        width=1200,
        height=600,
        hovermode='closest',
        xaxis=dict(tickangle=45)
    )

    fig.show()

    if save_path:
        fig.write_image(save_path)


def plot_timeseries_multiple_mpl(data_dict, lon=None, lat=None, title=None, var_name='wse', save_path=None):
    """
    Affiche plusieurs séries temporelles avec matplotlib.

    Parameters:
    - data_dict (dict): dictionnaire de {nom_de_tuile: dataframe avec colonnes 'date' et 'wse'}
    - lon, lat (float, optional): coordonnées du point (utilisées pour le titre)
    - title (str, optional): titre personnalisé

    Exemple :
    plot_timeseries_multiple({
        "52F": wse_timeseries_52F,
        "53F": wse_timeseries_53F,
        "102F": wse_timeseries_102F,
        "103F": wse_timeseries_103F
    }, lon=138.2, lat=-29.8)
    """
    colors = ['blue', 'orange', 'green', 'red', 'purple', 'brown', 'cyan', 'magenta']
    fig, ax = plt.subplots(figsize=(14, 4))

    for i, (label, df) in enumerate(data_dict.items()):
        if df is None or df.empty or 'date' not in df.columns:
            print(f"Skipping tile {label}: no valid data.")
            continue
        ax.plot(df['date'], df[var_name],
                color=colors[i % len(colors)],
                marker='o',
                linestyle='',
                label=f'Tile {label}')

    final_title = title or f'Série temporelle {var_name} à lon={lon}, lat={lat}' if lon and lat else f'Série temporelle {var_name}'

    ax.set_title(final_title)
    ax.set_xlabel('Date')
    ax.set_ylabel(f'{var_name.upper()} (m)')
    plt.xticks()
    plt.grid(True, color='black', linestyle='-', alpha=0.2)
    plt.box(True)
    if save_path:
        plt.savefig(save_path)

    plt.show()


def plot_wse_map(df, date, ax=None, cmap='viridis', vmin=None, vmax=None, title=None):
    """
    Plot WSE map for a specific date.

    Parameters
    ----------
    df : pandas.DataFrame
        DataFrame containing dates, coordinates and WSE values
    date : datetime or str
        Date to plot the WSE map for
    ax : matplotlib.axes.Axes, optional
        Axes to plot on. If None, creates new figure
    cmap : str, optional
        Colormap to use for plotting
    vmin, vmax : float, optional
        Min/max values for colorbar scaling
    title : str, optional
        Plot title. If None, uses date

    Returns
    -------
    matplotlib.axes.Axes
        The axes containing the plot
    """
    import matplotlib.pyplot as plt
    import numpy as np

    if ax is None:
        fig, ax = plt.subplots(figsize=(10, 8))

    # Convert date to datetime if string
    if isinstance(date, str):
        date = pd.to_datetime(date)

    # Filter data for given date
    date_data = df[df['date'].dt.date == date.date()]

    if date_data.empty:
        raise ValueError(f"No data found for date {date}")

    # Create scatter plot
    scatter = ax.scatter(date_data['lon'], date_data['lat'],
                         c=date_data['wse'],
                         cmap=cmap,
                         vmin=vmin, vmax=vmax)

    # Add colorbar
    plt.colorbar(scatter, ax=ax, label='WSE (m)')

    # Set labels and title
    ax.set_xlabel('Longitude')
    ax.set_ylabel('Latitude')
    if title is None:
        title = f'WSE Map for {date.strftime("%Y-%m-%d")}'
    ax.set_title(title)

    return ax
