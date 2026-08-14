#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Conversion des coordonnees projetees du modele vers WGS84.

Les sorties Delft3D sont en metres dans une projection transverse de
Mercator (MGA / UTM), tandis que Leaflet attend des degres. La
conversion inverse est implementee ici avec les series classiques
(Snyder), a la fois pour eviter une dependance a pyproj et pour rester
verifiable : l'erreur est millimetrique sur l'etendue d'un lac.

Ellipsoide GRS80 (GDA94 / GDA2020), identique a WGS84 pour cet usage.
"""

import math

A = 6378137.0                     # demi-grand axe GRS80
F = 1.0 / 298.257222101           # aplatissement GRS80
K0 = 0.9996                       # facteur d'echelle UTM
E0 = 500000.0                     # false easting
N0_SOUTH = 10000000.0             # false northing, hemisphere sud

E2 = F * (2 - F)                  # excentricite au carre
EP2 = E2 / (1 - E2)


def infer_zone(lon):
    """Fuseau UTM/MGA contenant cette longitude."""
    return int(math.floor((lon + 180.0) / 6.0)) + 1


def zone_central_meridian(zone):
    return (zone - 1) * 6.0 - 180.0 + 3.0


def utm_to_lonlat(x, y, zone, south=True):
    """(easting, northing) -> (lon, lat) en degres."""
    lon0 = math.radians(zone_central_meridian(zone))
    north = y - (N0_SOUTH if south else 0.0)
    east = x - E0

    m = north / K0
    e1 = (1 - math.sqrt(1 - E2)) / (1 + math.sqrt(1 - E2))
    mu = m / (A * (1 - E2 / 4 - 3 * E2 ** 2 / 64 - 5 * E2 ** 3 / 256))

    phi1 = (mu
            + (3 * e1 / 2 - 27 * e1 ** 3 / 32) * math.sin(2 * mu)
            + (21 * e1 ** 2 / 16 - 55 * e1 ** 4 / 32) * math.sin(4 * mu)
            + (151 * e1 ** 3 / 96) * math.sin(6 * mu)
            + (1097 * e1 ** 4 / 512) * math.sin(8 * mu))

    sin1, cos1, tan1 = math.sin(phi1), math.cos(phi1), math.tan(phi1)
    c1 = EP2 * cos1 ** 2
    t1 = tan1 ** 2
    n1 = A / math.sqrt(1 - E2 * sin1 ** 2)
    r1 = A * (1 - E2) / (1 - E2 * sin1 ** 2) ** 1.5
    d = east / (n1 * K0)

    lat = phi1 - (n1 * tan1 / r1) * (
        d ** 2 / 2
        - (5 + 3 * t1 + 10 * c1 - 4 * c1 ** 2 - 9 * EP2) * d ** 4 / 24
        + (61 + 90 * t1 + 298 * c1 + 45 * t1 ** 2 - 252 * EP2
           - 3 * c1 ** 2) * d ** 6 / 720)

    lon = lon0 + (
        d
        - (1 + 2 * t1 + c1) * d ** 3 / 6
        + (5 - 2 * c1 + 28 * t1 - 3 * c1 ** 2 + 8 * EP2
           + 24 * t1 ** 2) * d ** 5 / 120) / cos1

    return math.degrees(lon), math.degrees(lat)


def lonlat_to_utm(lon, lat, zone, south=True):
    """(lon, lat) en degres -> (easting, northing). Reciproque exacte
    de utm_to_lonlat, utilisee pour echantillonner le modele sur une
    grille geographique reguliere."""
    lon0 = math.radians(zone_central_meridian(zone))
    phi, lam = math.radians(lat), math.radians(lon)

    sinp, cosp, tanp = math.sin(phi), math.cos(phi), math.tan(phi)
    n = A / math.sqrt(1 - E2 * sinp ** 2)
    t = tanp ** 2
    c = EP2 * cosp ** 2
    a_ = (lam - lon0) * cosp

    m = A * ((1 - E2 / 4 - 3 * E2 ** 2 / 64 - 5 * E2 ** 3 / 256) * phi
             - (3 * E2 / 8 + 3 * E2 ** 2 / 32 + 45 * E2 ** 3 / 1024)
             * math.sin(2 * phi)
             + (15 * E2 ** 2 / 256 + 45 * E2 ** 3 / 1024) * math.sin(4 * phi)
             - (35 * E2 ** 3 / 3072) * math.sin(6 * phi))

    east = E0 + K0 * n * (
        a_
        + (1 - t + c) * a_ ** 3 / 6
        + (5 - 18 * t + t ** 2 + 72 * c - 58 * EP2) * a_ ** 5 / 120)

    north = K0 * (m + n * tanp * (
        a_ ** 2 / 2
        + (5 - t + 9 * c + 4 * c ** 2) * a_ ** 4 / 24
        + (61 - 58 * t + t ** 2 + 600 * c - 330 * EP2) * a_ ** 6 / 720))
    if south:
        north += N0_SOUTH
    return east, north


def grid_convergence(lon, lat, zone):
    """Angle entre le nord de la grille et le nord geographique (deg).

    Un azimut vrai vaut l'azimut de grille augmente de cette valeur ;
    l'ecart atteint environ 1,5 deg aux bords d'un fuseau, ce qui se
    voit sur l'orientation des fleches.
    """
    dlon = math.radians(lon - zone_central_meridian(zone))
    return math.degrees(math.atan(math.tan(dlon) * math.sin(math.radians(lat))))


def detect_zone(x, y, lon_hint, lat_hint=None, south=True, tol_deg=1.5):
    """Fuseau coherent avec la position connue du lac.

    On part du fuseau contenant lon_hint, puis on verifie que le point
    projete retombe bien pres du lac : une erreur de fuseau deplace le
    resultat de plusieurs degres, ce qui serait invisible autrement.
    Retourne (zone, ecart_en_degres) ou (None, ecart) si aucun fuseau
    voisin ne convient.
    """
    for zone in (infer_zone(lon_hint), infer_zone(lon_hint) - 1,
                 infer_zone(lon_hint) + 1):
        lon, lat = utm_to_lonlat(x, y, zone, south)
        err = abs(lon - lon_hint)
        if lat_hint is not None:
            err = math.hypot(err, abs(lat - lat_hint))
        if err <= tol_deg:
            return zone, err
    lon, lat = utm_to_lonlat(x, y, infer_zone(lon_hint), south)
    err = abs(lon - lon_hint)
    if lat_hint is not None:
        err = math.hypot(err, abs(lat - lat_hint))
    return None, err


def lonlat_to_utm_array(lon, lat, zone, south=True):
    """Version vectorisee de lonlat_to_utm (tableaux numpy, degres)."""
    import numpy as np

    lon0 = math.radians(zone_central_meridian(zone))
    phi = np.radians(lat)
    lam = np.radians(lon)

    sinp, cosp, tanp = np.sin(phi), np.cos(phi), np.tan(phi)
    n = A / np.sqrt(1 - E2 * sinp ** 2)
    t = tanp ** 2
    c = EP2 * cosp ** 2
    a_ = (lam - lon0) * cosp

    m = A * ((1 - E2 / 4 - 3 * E2 ** 2 / 64 - 5 * E2 ** 3 / 256) * phi
             - (3 * E2 / 8 + 3 * E2 ** 2 / 32 + 45 * E2 ** 3 / 1024)
             * np.sin(2 * phi)
             + (15 * E2 ** 2 / 256 + 45 * E2 ** 3 / 1024) * np.sin(4 * phi)
             - (35 * E2 ** 3 / 3072) * np.sin(6 * phi))

    east = E0 + K0 * n * (
        a_
        + (1 - t + c) * a_ ** 3 / 6
        + (5 - 18 * t + t ** 2 + 72 * c - 58 * EP2) * a_ ** 5 / 120)

    north = K0 * (m + n * tanp * (
        a_ ** 2 / 2
        + (5 - t + 9 * c + 4 * c ** 2) * a_ ** 4 / 24
        + (61 - 58 * t + t ** 2 + 600 * c - 330 * EP2) * a_ ** 6 / 720))
    if south:
        north = north + N0_SOUTH
    return east, north


def utm_to_lonlat_array(x, y, zone, south=True):
    """Version vectorisee de utm_to_lonlat (tableaux numpy, metres).

    Reprojeter maille par maille en Python coute ~9 us l'unite, soit une
    quinzaine de secondes pour un granule SWOT de 1,6 million de mailles.
    La meme formule appliquee a des tableaux tombe a quelques dizaines
    de millisecondes.
    """
    import numpy as np

    lon0 = math.radians(zone_central_meridian(zone))
    north = np.asarray(y, dtype="float64") - (N0_SOUTH if south else 0.0)
    east = np.asarray(x, dtype="float64") - E0

    m = north / K0
    e1 = (1 - math.sqrt(1 - E2)) / (1 + math.sqrt(1 - E2))
    mu = m / (A * (1 - E2 / 4 - 3 * E2 ** 2 / 64 - 5 * E2 ** 3 / 256))

    phi1 = (mu
            + (3 * e1 / 2 - 27 * e1 ** 3 / 32) * np.sin(2 * mu)
            + (21 * e1 ** 2 / 16 - 55 * e1 ** 4 / 32) * np.sin(4 * mu)
            + (151 * e1 ** 3 / 96) * np.sin(6 * mu)
            + (1097 * e1 ** 4 / 512) * np.sin(8 * mu))

    sin1, cos1, tan1 = np.sin(phi1), np.cos(phi1), np.tan(phi1)
    c1 = EP2 * cos1 ** 2
    t1 = tan1 ** 2
    n1 = A / np.sqrt(1 - E2 * sin1 ** 2)
    r1 = A * (1 - E2) / (1 - E2 * sin1 ** 2) ** 1.5
    d = east / (n1 * K0)

    lat = phi1 - (n1 * tan1 / r1) * (
        d ** 2 / 2
        - (5 + 3 * t1 + 10 * c1 - 4 * c1 ** 2 - 9 * EP2) * d ** 4 / 24
        + (61 + 90 * t1 + 298 * c1 + 45 * t1 ** 2 - 252 * EP2
           - 3 * c1 ** 2) * d ** 6 / 720)

    lon = lon0 + (
        d
        - (1 + 2 * t1 + c1) * d ** 3 / 6
        + (5 - 2 * c1 + 28 * t1 - 3 * c1 ** 2 + 8 * EP2
           + 24 * t1 ** 2) * d ** 5 / 120) / cos1

    return np.degrees(lon), np.degrees(lat)
