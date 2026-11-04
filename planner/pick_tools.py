"""T403: the two tools Muse Spark Open may call while it picks a place (llm.pick_place).

No Django import here, so scripts/muse_tools_probe.py can send the same schemas with no settings.
  find_places(area, kind, food) -> the top candidates from Mifgash's own list (id, name, tags, hours)
  check_hours(place_id, date, part) -> open | closed | unknown (planner/hours.py, the OSM opening_hours)
"""

TOOLS = [
    {"type": "function", "function": {
        "name": "find_places",
        "description": "List candidate places for the plan from the Mifgash directory "
                       "(OpenStreetMap data). Returns id, name, tags and opening hours.",
        "parameters": {"type": "object", "properties": {
            "area": {"type": "string", "description": "Neighborhood or city, for example 'Mission'"},
            "kind": {"type": "string", "description": "lunch, kids, evening, weekend or group_dinner"},
            "food": {"type": "string", "description": "A food type to filter on, or empty"},
        }, "required": ["area"]}}},
    {"type": "function", "function": {
        "name": "check_hours",
        "description": "Is the place open on that date in that part of the day? "
                       "Answers open, closed or unknown.",
        "parameters": {"type": "object", "properties": {
            "place_id": {"type": "integer", "description": "The candidate id"},
            "date": {"type": "string", "description": "YYYY-MM-DD"},
            "part": {"type": "string", "description": "morning, lunch, afternoon or evening"},
        }, "required": ["place_id"]}}},
]

# The JSON 'tool request' variant, for an endpoint with no native tool support.
JSON_TOOLS_PROMPT = """You may ask for ONE tool per answer before you pick. Tools:
 find_places(area, kind, food): candidate places with id, name, tags, hours
 check_hours(place_id, date, part): open, closed or unknown
To call a tool answer ONLY {"tool": "check_hours", "args": {"place_id": 12}}.
To pick answer ONLY {"id": <the candidate id>, "why": "<one sentence>"}. At most 3 answers in all."""
