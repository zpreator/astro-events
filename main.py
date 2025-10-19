import ephem
import math
from datetime import datetime, timedelta
from datetime import UTC
import zoneinfo

# ---- Inputs ----
# Observer (Kaysville, UT)
observer_lat = 41.035
observer_lon = -111.938
observer_elev = 1300  # meters

# Point of interest (mountain peak)
peak_lat = 41.0328
peak_lon = -111.8386
peak_elev = 2866  # meters

tolerance_deg = 5  # azimuth/altitude alignment tolerance

# ---- Setup observer ----
obs = ephem.Observer()
obs.lat = str(observer_lat)
obs.lon = str(observer_lon)
obs.elev = observer_elev

# ---- Bearing (observer → mountain) ----
def bearing(lat1, lon1, lat2, lon2):
    φ1, φ2 = math.radians(lat1), math.radians(lat2)
    Δλ = math.radians(lon2 - lon1)
    x = math.sin(Δλ) * math.cos(φ2)
    y = math.cos(φ1)*math.sin(φ2) - math.sin(φ1)*math.cos(φ2)*math.cos(Δλ)
    brng = math.degrees(math.atan2(x, y))
    return (brng + 360) % 360

# ---- Elevation angle (observer → mountain top) ----
def elevation_angle(lat1, lon1, elev1, lat2, lon2, elev2):
    R = 6371000  # Earth radius in meters
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    surface_dist = 2 * R * math.asin(math.sqrt(a))
    alt_diff = elev2 - elev1
    return math.degrees(math.atan2(alt_diff, surface_dist))

mountain_azimuth = bearing(observer_lat, observer_lon, peak_lat, peak_lon)
mountain_elev_angle = elevation_angle(observer_lat, observer_lon, observer_elev,
                                       peak_lat, peak_lon, peak_elev)

print(f"Azimuth to mountain: {mountain_azimuth:.2f}°")
print(f"Elevation angle to mountain: {mountain_elev_angle:.2f}°")

# ---- Search for alignment ----
num_days = 365
moon = ephem.Moon()
t = datetime.now(UTC)
end_time = t + timedelta(days=num_days)
found = None
step = timedelta(minutes=1)

while t < end_time:
    obs.date = t
    moon.compute(obs)
    moon_az = math.degrees(moon.az)
    moon_alt = math.degrees(moon.alt)
    if (moon_alt > 0 and
        abs(moon_az - mountain_azimuth) < tolerance_deg and
        abs(moon_alt - mountain_elev_angle) < tolerance_deg):
        found = t
        break
    t += step

# ---- Report results ----
if found:
    mt = found.astimezone(zoneinfo.ZoneInfo("America/Denver"))
    obs.date = found
    moon.compute(obs)
    #print(f"\nNext alignment: {found} UTC")
    print(f"Next alignment (local): {mt}")
    print(f"Moon phase at alignment: {moon.phase:.1f}%")
else:
    print(f"No alignment found within {num_days} days.")
