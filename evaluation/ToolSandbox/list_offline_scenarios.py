"""Print the first N (argv[1]) ToolSandbox scenarios that need no RapidAPI tool."""
import sys
from itertools import islice

from tool_sandbox.common.tool_discovery import ToolBackend
from tool_sandbox.scenarios import named_scenarios

RAPID_API_TOOLS = {
    "convert_currency",
    "search_lat_lon",
    "search_location_around_lat_lon",
    "search_stock",
    "search_weather_around_lat_lon",
}

offline = (
    name
    for name, scenario in named_scenarios(ToolBackend.DEFAULT).items()
    if not set(scenario.starting_context.tool_allow_list or []) & RAPID_API_TOOLS
)
for name in islice(offline, int(sys.argv[1]) if len(sys.argv) > 1 else None):
    print(name)
