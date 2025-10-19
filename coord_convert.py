#!/usr/bin/env python3
"""
coord_convert.py
Convert coordinates from DMS + elevation format (e.g. 41°02'38"N 111°56'45"W1,331 m)
to decimal degrees format compatible with astro_align.py.
"""

import re

def dms_to_decimal(d, m, s, hemi):
    dec = float(d) + float(m) / 60 + float(s) / 3600
    if hemi in ['S', 'W']:
        dec = -dec
    return dec

def parse_coord_string(s):
    # Example input: 41°02'38"N 111°56'45"W1,331 m
    pattern = r"(\d+)°(\d+)'(\d+)\"?([NS])\s+(\d+)°(\d+)'(\d+)\"?([EW])([\d,\.]*)\s*m"
    match = re.search(pattern, s.replace("’", "'").replace("”", '"').replace("″", '"'))
    if not match:
        raise ValueError("Invalid coordinate format.")
    lat_d, lat_m, lat_s, lat_h, lon_d, lon_m, lon_s, lon_h, elev = match.groups()
    lat = dms_to_decimal(lat_d, lat_m, lat_s, lat_h)
    lon = dms_to_decimal(lon_d, lon_m, lon_s, lon_h)
    elev = float(elev.replace(',', '')) if elev else 0.0
    return lat, lon, elev

def main():
    s = input("Enter coordinate (e.g. 41°02'38\"N 111°56'45\"W1,331 m): ").strip()
    lat, lon, elev = parse_coord_string(s)
    print(f"Decimal format: {lat:.6f},{lon:.6f},{elev:.1f}")

if __name__ == "__main__":
    main()
