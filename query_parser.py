# query_parser.py
import re

def parse_query(text):
    text = text.lower()

    # Try to find a route name
    route_match = re.search(r"(?:route|line)\s*[:#]?\s*([a-z0-9]+)", text)
    if not route_match:
        # Fallback: catch route number after "show", "map", or alone at end
        fallback = re.search(r"(?:show|map|visualize)?\s*([a-z0-9]+)$", text)
        route = fallback.group(1).upper() if fallback else None
    else:
        route = route_match.group(1).upper()

    if "how many stops" in text or "number of stops" in text:
        return {"type": "stops", "route": route}
    elif "how many trips" in text or "number of trips" in text:
        return {"type": "trips", "route": route}
    elif "run time" in text or "duration" in text:
        return {"type": "runtime", "route": route}
    elif "headway" in text or "frequency" in text:
        return {"type": "headway", "route": route}
    elif "length" in text or "distance" in text:
        return {"type": "length", "route": route}
    elif "weekday" in text and ("time" in text or "run time" in text):
        return {"type": "weekday_runtime", "route": route}
    elif "schedule" in text:
        return {"type": "schedule", "route": route}
    elif "calendar" in text or "service" in text:
        return {"type": "service", "route": None}
    elif "routes" in text:
        return {"type": "routes", "route": None}
    elif "stops" in text and route is None:
        return {"type": "stops_summary", "route": None}
    elif "map" in text or "show me" in text or "visualize" in text:
        return {"type": "map", "route": route}
    else:
        return {"type": "unknown", "route": route}
