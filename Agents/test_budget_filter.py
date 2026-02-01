#!/usr/bin/env python3
"""
Test script for Budget Filter Agent - demonstrates compatibility with Agentverse string inputs.

Shows how to send JSON strings to the agent and parse responses.
"""

import json
from budgetFilterAgent import parse_text_to_json, filter_from_dicts

# Test Case 1: Single EventScraperAgent output as string
print("=" * 60)
print("Test 1: EventScraperAgent output (string from Agentverse)")
print("=" * 60)

events_string = '''{
  "location": "Paris",
  "timeframe": "1 week",
  "budget": 2000.0,
  "interest_activities": ["sightseeing", "cultural", "dining"]
}'''

try:
    parsed = parse_text_to_json(events_string)
    print("✓ Parsed successfully")
    print(f"  Events data: {parsed['events']}")
    output = filter_from_dicts(parsed['events'], parsed['fund'])
    print(f"✓ Filtering complete - {len(output['matched_activities'])} activities matched")
except Exception as e:
    print(f"✗ Error: {e}")

# Test Case 2: Single FundAllocationAgent output as string
print("\n" + "=" * 60)
print("Test 2: FundAllocationAgent output (string from Agentverse)")
print("=" * 60)

fund_string = '''{
  "location": "Paris",
  "activities": [
    "Visit the Eiffel Tower",
    "Louvre Museum tour",
    "Dinner at bistro",
    "Arc de Triomphe visit",
    "Seine river cruise"
  ],
  "budget": 2000.0
}'''

try:
    parsed = parse_text_to_json(fund_string)
    print("✓ Parsed successfully")
    print(f"  Fund data: {list(parsed['fund'].keys())}")
    output = filter_from_dicts(parsed['events'], parsed['fund'])
    print(f"✓ Filtering complete - selected {len(output['filtered_selection']['selected_activities'])} activities")
except Exception as e:
    print(f"✗ Error: {e}")

# Test Case 3: Combined format as string
print("\n" + "=" * 60)
print("Test 3: Combined format (both events and fund)")
print("=" * 60)

combined_string = '''{
  "events": {
    "location": "Tokyo",
    "interest_activities": ["cultural", "adventure", "dining"],
    "budget": 1500.0
  },
  "fund": {
    "location": "Tokyo",
    "activities": [
      "Tokyo Tower visit",
      "Sumo wrestling tournament",
      "Traditional sushi meal",
      "Mount Fuji day trip",
      "Shibuya Crossing tour"
    ],
    "budget": 1500.0
  }
}'''

try:
    parsed = parse_text_to_json(combined_string)
    print("✓ Parsed successfully")
    print(f"  Both events and fund detected")
    output = filter_from_dicts(parsed['events'], parsed['fund'])
    print(f"✓ Filtering complete - {len(output['matched_activities'])} matched, "
          f"{len(output['filtered_selection']['selected_activities'])} selected")
except Exception as e:
    print(f"✗ Error: {e}")

# Test Case 4: Two JSONs in one string (agent will separate them)
print("\n" + "=" * 60)
print("Test 4: Two separate JSON objects in one string")
print("=" * 60)

two_json_string = '''{
  "location": "Barcelona",
  "interest_activities": ["entertainment", "outdoor"],
  "budget": 800.0
}

{
  "location": "Barcelona",
  "activities": [
    "Sagrada Familia tour",
    "Beach day at Barceloneta",
    "Park Güell visit",
    "Flamenco show",
    "Gothic Quarter walk"
  ],
  "budget": 800.0
}'''

try:
    parsed = parse_text_to_json(two_json_string)
    print("✓ Parsed successfully - separated both JSONs")
    output = filter_from_dicts(parsed['events'], parsed['fund'])
    print(f"✓ Filtering complete - {len(output['matched_activities'])} activities matched")
except Exception as e:
    print(f"✗ Error: {e}")

# Test Case 5: JSON with agent address mention (Agentverse format)
print("\n" + "=" * 60)
print("Test 5: JSON with agent address (typical Agentverse message)")
print("=" * 60)

agentverse_string = '''Send this to @agent1qtlpfshtlcxekgrfcpmv7m9zpajuwu7d5jfyachvpa4u3dkt6k0uwwp2lct:
{
  "location": "Boston",
  "interest_activities": ["sightseeing", "entertainment"],
  "budget": 600.0
}

{
  "location": "Boston",
  "activities": [
    "Freedom Trail walking tour",
    "Museum of Fine Arts",
    "Red Sox game at Fenway",
    "Boston Harbor Island cruise",
    "Theater show on Broadway"
  ],
  "budget": 600.0
}'''

try:
    parsed = parse_text_to_json(agentverse_string)
    print("✓ Parsed successfully - stripped agent addresses")
    output = filter_from_dicts(parsed['events'], parsed['fund'])
    print(f"✓ Filtering complete - {len(output['matched_activities'])} activities matched")
except Exception as e:
    print(f"✗ Error: {e}")

# Test Case 6: JSON in markdown code block (if formatted that way)
print("\n" + "=" * 60)
print("Test 6: JSON in markdown code fence")
print("=" * 60)

markdown_json_string = '''```json
{
  "location": "San Francisco",
  "interest_activities": ["outdoor", "adventure"],
  "budget": 1200.0,
  "activities": [
    "Golden Gate Bridge hike",
    "Rock climbing at Twin Peaks",
    "Kayaking in Bay",
    "Mountain biking trails",
    "Cable car sightseeing"
  ]
}
```'''

try:
    parsed = parse_text_to_json(markdown_json_string)
    print("✓ Parsed successfully - handled markdown code fence")
    output = filter_from_dicts(parsed['events'], parsed['fund'])
    print(f"✓ Filtering complete - {len(output['matched_activities'])} activities matched")
except Exception as e:
    print(f"✗ Error: {e}")

print("\n" + "=" * 60)
print("All tests completed!")
print("=" * 60)
