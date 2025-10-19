#!/usr/bin/env python3
"""
astro_align.py

Find times when a celestial body lines up (azimuth + elevation) from an observer to a POI.

Usage example:
  python3 astro_align.py \
    --body Moon \
    --observer 41.113889,-111.951389,1486.0 \
    --poi 41.032778,-111.838889,2880.0 \
    --days 365 \
    --az-tol 0.5 \
    --el-tol 0.5 \
    --step 1 \
    --output alignments.csv
"""
from __future__ import annotations
import argparse
import csv
import math
from datetime import datetime, timedelta, timezone
import ephem

try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None

try:
    from timezonefinder import TimezoneFinder
    TF = TimezoneFinder()
except Exception:
    TF = None

UTC = timezone.utc


# ----------------------
# Utility functions
# ----------------------
def parse_triplet(s: str):
    parts = [p.strip() for p in s.split(',')]
    if len(parts) != 3:
        raise argparse.ArgumentTypeError("Expect 'lat,lon,elev' with three comma-separated values.")
    return float(parts[0]), float(parts[1]), float(parts[2])


def deg(x):
    return math.degrees(x)


def ang_diff_deg(a: float, b: float) -> float:
    """Smallest difference between two azimuth angles in degrees."""
    d = abs((a - b) % 360.0)
    return d if d <= 180.0 else 360.0 - d


def compute_bearing(lat1, lon1, lat2, lon2):
    φ1, φ2 = math.radians(lat1), math.radians(lat2)
    Δλ = math.radians(lon2 - lon1)
    x = math.sin(Δλ) * math.cos(φ2)
    y = math.cos(φ1) * math.sin(φ2) - math.sin(φ1) * math.cos(φ2) * math.cos(Δλ)
    brng = math.degrees(math.atan2(x, y))
    return (brng + 360.0) % 360.0


def compute_elevation_angle(lat1, lon1, elev1, lat2, lon2, elev2):
    R = 6371000.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    surface_dist = 2 * R * math.asin(math.sqrt(a))
    alt_diff = elev2 - elev1
    return math.degrees(math.atan2(alt_diff, surface_dist)), surface_dist  # elevation deg, distance meters


def tz_for_location(lat, lon):
    if TF is None or ZoneInfo is None:
        return UTC
    tzname = TF.timezone_at(lat=lat, lng=lon)
    if not tzname:
        return UTC
    try:
        return ZoneInfo(tzname)
    except Exception:
        return UTC


def set_ephem_observer(obs: ephem.Observer, dt_utc: datetime):
    # ephem expects naive datetime in UTC. We convert aware UTC -> naive UTC.
    obs.date = ephem.Date(dt_utc.replace(tzinfo=None))


def instantiate_body(body_name: str):
    # Accept names like "moon", "Moon", "mars", "Sun"
    try:
        cls = getattr(ephem, body_name.title())
        return cls()
    except AttributeError:
        # allow lowercase for "sun"->Sun, but getattr above handles that mostly
        raise ValueError(f"Unknown celestial body '{body_name}'. Use a name supported by pyephem.")


# ----------------------
# Core search logic
# ----------------------
def find_alignments(observer, poi, body_name, search_days, az_tol_deg, el_tol_deg, step_minutes):
    obs = ephem.Observer()
    obs.lat = str(observer['lat'])
    obs.lon = str(observer['lon'])
    obs.elev = observer['elev']

    poi_az = compute_bearing(observer['lat'], observer['lon'], poi['lat'], poi['lon'])
    poi_el, poi_dist_m = compute_elevation_angle(observer['lat'], observer['lon'], observer['elev'],
                                                 poi['lat'], poi['lon'], poi['elev'])

    start_utc = datetime.now(UTC)
    end_utc = start_utc + timedelta(days=search_days)
    step = timedelta(minutes=step_minutes)

    body_template = instantiate_body(body_name)

    coarse_matches = []

    t = start_utc
    while t <= end_utc:
        set_ephem_observer(obs, t)
        body = instantiate_body(body_name)
        body.compute(obs)
        az = deg(body.az)
        el = deg(body.alt)
        # require above horizon (el > -90 is redundant; main check el> -5? we require >-90 but also allow negative if user wants)
        if el > -90:
            if ang_diff_deg(az, poi_az) <= az_tol_deg and abs(el - poi_el) <= el_tol_deg:
                coarse_matches.append((t, az, el))
        t += step

    # refine each coarse match with a local fine search (±step window, 1-second steps)
    refined = []
    for coarse_t, coarse_az, coarse_el in coarse_matches:
        window_start = max(start_utc, coarse_t - step)
        window_end = min(end_utc, coarse_t + step)
        best = None
        best_metric = None
        s = window_start
        while s <= window_end:
            set_ephem_observer(obs, s)
            body = instantiate_body(body_name)
            body.compute(obs)
            az = deg(body.az)
            el = deg(body.alt)
            az_diff = ang_diff_deg(az, poi_az)
            el_diff = abs(el - poi_el)
            metric = az_diff + el_diff  # simple scalar for closeness
            if best is None or metric < best_metric:
                best = (s, az, el, az_diff, el_diff, getattr(body, 'phase', None))
                best_metric = metric
            s += timedelta(seconds=1)
        if best:
            refined.append(best)

    # Remove duplicates (close times) and sort
    refined_sorted = sorted(refined, key=lambda x: x[0])
    filtered = []
    last_time = None
    min_sep = timedelta(seconds=10)
    for entry in refined_sorted:
        if last_time is None or (entry[0] - last_time) >= min_sep:
            filtered.append(entry)
            last_time = entry[0]
    return {
        'poi_az': poi_az,
        'poi_el': poi_el,
        'poi_dist_m': poi_dist_m,
        'matches': filtered,
        'start_utc': start_utc,
        'end_utc': end_utc
    }


# ----------------------
# CLI / I/O
# ----------------------
def main():
    p = argparse.ArgumentParser(description="Find times when a celestial body aligns with an observer-POI line of sight.")
    p.add_argument('--body', required=True, help='Celestial body name supported by pyephem (e.g. Moon, Sun, Mars)')
    p.add_argument('--observer', required=True, type=parse_triplet,
                   help="Observer as 'lat,lon,elev' (decimal degrees, meters). Example: 41.035,-111.938,1300")
    p.add_argument('--poi', required=True, type=parse_triplet,
                   help="POI as 'lat,lon,elev' (decimal degrees, meters). Example: 41.0328,-111.8386,2866")
    p.add_argument('--days', type=int, default=30, help='Search window in days (default 30)')
    p.add_argument('--az-tol', type=float, default=0.5, help='Azimuth tolerance in degrees (default 0.5)')
    p.add_argument('--el-tol', type=float, default=0.5, help='Elevation tolerance in degrees (default 0.5)')
    p.add_argument('--step', type=int, default=5, help='Coarse search time step in minutes (default 5)')
    p.add_argument('--output', type=str, default=None, help='Optional CSV output filename. If omitted, no CSV is written.')
    p.add_argument('--local-time', action='store_true', help='Also print local times (auto-detected from observer coords).')
    args = p.parse_args()

    obs_lat, obs_lon, obs_elev = args.observer
    poi_lat, poi_lon, poi_elev = args.poi

    observer = {'lat': obs_lat, 'lon': obs_lon, 'elev': obs_elev}
    poi = {'lat': poi_lat, 'lon': poi_lon, 'elev': poi_elev}

    tz = tz_for_location(obs_lat, obs_lon) if args.local_time else UTC

    result = find_alignments(observer, poi, args.body, args.days, args.az_tol, args.el_tol, args.step)

    print(f"POI azimuth: {result['poi_az']:.4f}°")
    print(f"POI elevation angle: {result['poi_el']:.4f}°")
    print(f"POI surface distance: {result['poi_dist_m']/1000.0:.3f} km")
    print(f"Search window: {result['start_utc'].isoformat()} to {result['end_utc'].isoformat()} (UTC)")
    if args.local_time and tz is not UTC:
        print(f"Observer timezone (detected): {tz}")

    matches = result['matches']
    if not matches:
        print(f"No alignments found within {args.days} days.")
    else:
        print(f"Found {len(matches)} alignment(s):")
        for idx, (t_utc, az, el, az_diff, el_diff, phase) in enumerate(matches, start=1):
            t_utc = t_utc.replace(tzinfo=UTC)
            local_str = ''
            if args.local_time:
                try:
                    local = t_utc.astimezone(tz)
                    local_str = f" | Local: {local.isoformat()}"
                except Exception:
                    local_str = ''
            phase_str = f"{phase:.2f}%" if (phase is not None) else "N/A"
            print(f"{idx:2d}: UTC {t_utc.isoformat()} {local_str} | az={az:.3f}° (Δ={az_diff:.3f}°) | el={el:.3f}° (Δ={el_diff:.3f}°) | illum={phase_str}")

    # CSV output
    if args.output and matches:
        with open(args.output, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['utc_iso', 'local_iso', 'az_deg', 'el_deg', 'az_diff_deg', 'el_diff_deg', 'illum_pct'])
            for (t_utc, az, el, az_diff, el_diff, phase) in matches:
                t_utc = t_utc.replace(tzinfo=UTC)
                local_iso = ''
                if args.local_time:
                    try:
                        local_iso = t_utc.astimezone(tz).isoformat()
                    except Exception:
                        local_iso = ''
                illum = f"{phase:.6f}" if phase is not None else ''
                writer.writerow([t_utc.isoformat(), local_iso, f"{az:.6f}", f"{el:.6f}", f"{az_diff:.6f}", f"{el_diff:.6f}", illum])
        print(f"CSV written to: {args.output}")

if __name__ == '__main__':
    main()
