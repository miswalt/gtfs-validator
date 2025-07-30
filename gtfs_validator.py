# gtfs_validator.py
import os
import pandas as pd

REQUIRED_FILES = ["agency.txt", "routes.txt", "trips.txt", "stop_times.txt", "stops.txt", "calendar.txt"]

def check_required_files(folder):
    missing = [f for f in REQUIRED_FILES if not os.path.exists(os.path.join(folder, f))]
    if missing:
        return f"Missing required GTFS files: {', '.join(missing)}"

def check_stop_coordinates(stops_df):
    missing_coords = stops_df[stops_df["stop_lat"].isna() | stops_df["stop_lon"].isna()]
    if not missing_coords.empty:
        return f"{len(missing_coords)} stops have missing coordinates"

def check_trips_with_no_stop_times(trips_df, stop_times_df):
    trips_with_stops = stop_times_df["trip_id"].unique()
    orphaned = ~trips_df["trip_id"].isin(trips_with_stops)
    count = orphaned.sum()
    if count > 0:
        return f"{count} trips have no stop_times"

def check_routes_with_no_trips(routes_df, trips_df):
    routes_with_trips = trips_df["route_id"].unique()
    orphaned = ~routes_df["route_id"].isin(routes_with_trips)
    count = orphaned.sum()
    if count > 0:
        return f"{count} routes have no trips"

def check_missing_shapes(trips_df, shapes_df):
    known_shapes = shapes_df["shape_id"].unique()
    missing = ~trips_df["shape_id"].isin(known_shapes)
    count = missing.sum()
    if count > 0:
        return f"{count} trips reference missing shape_ids"

def check_invalid_times(stop_times_df):
    invalid = stop_times_df[~stop_times_df["arrival_time"].str.match(r"^\d{1,2}:\d{2}:\d{2}$", na=False)]
    if not invalid.empty:
        return f"{len(invalid)} stop_times have invalid arrival_time format"

def validate_gtfs(folder):
    issues = []

    missing_files = check_required_files(folder)
    if missing_files:
        issues.append(missing_files)
        return issues  # Can't proceed further if core files are missing

    # Load core files
    stops = pd.read_csv(os.path.join(folder, "stops.txt"))
    routes = pd.read_csv(os.path.join(folder, "routes.txt"))
    trips = pd.read_csv(os.path.join(folder, "trips.txt"))
    stop_times = pd.read_csv(
        os.path.join(folder, "stop_times.txt"),
        dtype={"arrival_time": "object", "departure_time": "object"},
        low_memory=False
    )
    shapes = pd.read_csv(os.path.join(folder, "shapes.txt"))

    # Run each check
    for check_fn in [
        lambda: check_stop_coordinates(stops),
        lambda: check_trips_with_no_stop_times(trips, stop_times),
        lambda: check_routes_with_no_trips(routes, trips),
        lambda: check_missing_shapes(trips, shapes),
        lambda: check_invalid_times(stop_times)
    ]:
        result = check_fn()
        if result:
            issues.append(result)

    return issues
