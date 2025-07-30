import pandas as pd
import numpy as np
import os
from math import radians, cos, sin, asin, sqrt


def to_minutes(hhmmss):
    try:
        parts = list(map(int, str(hhmmss).split(":")))
        return parts[0] * 60 + parts[1] + parts[2] / 60
    except:
        return None


def haversine(lat1, lon1, lat2, lon2):
    R = 3959  # Earth radius in miles
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * R * asin(sqrt(a))


def compute_polyline_length(shape_df):
    shape_df = shape_df.sort_values("shape_pt_sequence")
    coords = shape_df[['shape_pt_lat', 'shape_pt_lon']].values
    total_distance = 0
    for i in range(1, len(coords)):
        lat1, lon1 = coords[i - 1]
        lat2, lon2 = coords[i]
        total_distance += haversine(lat1, lon1, lat2, lon2)
    return total_distance


class GTFSDataV2:
    def __init__(self, folder):
        self.folder = folder
        self.routes = pd.read_csv(os.path.join(folder, "routes.txt"))
        self.trips = pd.read_csv(os.path.join(folder, "trips.txt"))
        self.stop_times = pd.read_csv(os.path.join(folder, "stop_times.txt"), low_memory=False)
        self.stops = pd.read_csv(os.path.join(folder, "stops.txt"))
        self.shapes = pd.read_csv(os.path.join(folder, "shapes.txt")) if os.path.exists(os.path.join(folder, "shapes.txt")) else pd.DataFrame()
        self.calendar = pd.read_csv(os.path.join(folder, "calendar.txt")) if os.path.exists(os.path.join(folder, "calendar.txt")) else pd.DataFrame()

    def get_route_id(self, route_name):
        match = self.routes[
            (self.routes['route_short_name'].astype(str).str.lower() == route_name.lower()) |
            (self.routes['route_long_name'].astype(str).str.lower().str.contains(route_name.lower()))
        ]
        return match.iloc[0]['route_id'] if not match.empty else None

    def get_all_shapes(self):
        df = self.shapes.sort_values(["shape_id", "shape_pt_sequence"]).copy()
        df = df.rename(columns={"shape_pt_lat": "lat", "shape_pt_lon": "lon"})

        segments = []
        for shape_id, group in df.groupby("shape_id"):
            coords = group[["lat", "lon"]].values
            for i in range(1, len(coords)):
                segments.append({
                    "shape_id": shape_id,
                    "lat1": coords[i - 1][0],
                    "lon1": coords[i - 1][1],
                    "lat2": coords[i][0],
                    "lon2": coords[i][1]
                })
        return pd.DataFrame(segments)

    def get_route_metrics_summary(self):
        results = []
        if not self.calendar.empty and "monday" in self.calendar.columns:
            weekday_service_ids = set(self.calendar[self.calendar['monday'] == 1]['service_id'])
        else:
            weekday_service_ids = set(self.trips['service_id'].unique())  # fallback

        for _, route in self.routes.iterrows():
            route_id = route['route_id']
            short_name = str(route.get('route_short_name', ''))
            long_name = str(route.get('route_long_name', ''))

            weekday_trips = self.trips[
                (self.trips['route_id'] == route_id) &
                (self.trips['service_id'].isin(weekday_service_ids))
            ]
            trip_ids = weekday_trips['trip_id'].unique()

            # --- Length ---
            length_miles = None
            shape_ids = weekday_trips['shape_id'].dropna().unique()
            if len(shape_ids) > 0 and not self.shapes.empty:
                shape_df = self.shapes[self.shapes['shape_id'] == shape_ids[0]]
                if not shape_df.empty:
                    length_miles = compute_polyline_length(shape_df)

            # --- Runtime ---
            durations = []
            for trip_id in trip_ids[:10]:
                trip_stops = self.stop_times[self.stop_times['trip_id'] == trip_id].sort_values('stop_sequence')
                if not trip_stops.empty:
                    t0 = to_minutes(trip_stops.iloc[0].get("departure_time"))
                    t1 = to_minutes(trip_stops.iloc[-1].get("arrival_time"))
                    if t0 is not None and t1 is not None and t1 > t0:
                        durations.append(t1 - t0)
            avg_runtime = np.mean(durations) if durations else None

            # --- Headway ---
            departures = []
            for trip_id in trip_ids[:20]:
                trip_stops = self.stop_times[self.stop_times['trip_id'] == trip_id].sort_values('stop_sequence')
                t0 = to_minutes(trip_stops.iloc[0].get("departure_time"))
                if t0 is not None:
                    departures.append(t0)
            headways = np.diff(sorted(departures))
            avg_headway = np.mean(headways) if len(headways) > 1 else None

            results.append({
                "route_id": route_id,
                "short_name": short_name,
                "long_name": long_name,
                "length_miles": round(length_miles, 2) if length_miles else None,
                "weekday_runtime_min": round(avg_runtime, 1) if avg_runtime else None,
                "weekday_trips_per_day": len(trip_ids),
                "avg_headway_min": round(avg_headway, 1) if avg_headway else None,
            })

        return pd.DataFrame(results)

    def answer_query(self, intent):
        route_name = intent.get("route")
        if not route_name:
            return {"type": "text", "answer": "Please specify a route name or number."}
        route_id = self.get_route_id(route_name)
        if not route_id:
            return {"type": "text", "answer": f"Route '{route_name}' not found."}

        if intent['type'] in ("show_map", "map"):
            return self.get_route_map(route_id)
        else:
            return {"type": "text", "answer": "Sorry, I didn't understand that question."}

    def get_route_map(self, route_id):
        trips = self.trips[self.trips['route_id'] == route_id]
        if trips.empty:
            return {"type": "map", "shape": None, "stops": None}

        shape_id = trips.iloc[0].get("shape_id")
        shape_df = self.shapes[self.shapes["shape_id"] == shape_id].sort_values("shape_pt_sequence") if shape_id in self.shapes["shape_id"].values else pd.DataFrame()
        shape_df = shape_df.rename(columns={"shape_pt_lat": "lat", "shape_pt_lon": "lon"})

        trip_id = trips.iloc[0]['trip_id']
        stop_times = self.stop_times[self.stop_times['trip_id'] == trip_id].sort_values('stop_sequence')
        stops_df = pd.merge(stop_times, self.stops, on="stop_id", how="left")
        stops_df = stops_df.rename(columns={"stop_lat": "lat", "stop_lon": "lon"})

        return {
            "type": "map",
            "shape": shape_df[["lat", "lon"]] if not shape_df.empty else None,
            "stops": stops_df[["lat", "lon", "stop_name"]] if not stops_df.empty else None,
        }
