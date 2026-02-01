#!/usr/bin/env python3
"""
Budget Filter Agent - Filters activities from EventScraperAgent to fit budget constraints

Processes outputs from FundAllocationAgent and EventScraperAgent to produce
a filtered, budget-aware activity plan.

AGENTVERSE INTEGRATION:
- This agent listens on Chat Protocol and accepts JSON string messages from Agentverse
- Simply send the JSON output from EventScraperAgent or FundAllocationAgent as a text message
- Agent will auto-detect the format and produce filtered activities

EXPECTED INPUT FORMATS:

1. EventScraperAgent output (sent as JSON string):
   {
     "location": "New York City",
     "interest_activities": ["sightseeing", "dining", "entertainment"],
     "timeframe": "weekend",
     "budget": 500.0
   }

2. FundAllocationAgent output (sent as JSON string):
   {
     "location": "New York City",
     "activities": ["Visit the Statue of Liberty", "Broadway show", "Central Park bike rental"],
     "budget": 500.0
   }

3. Both combined (sent as JSON string):
   {
     "events": {...EventScraperAgent output...},
     "fund": {...FundAllocationAgent output...}
   }

OUTPUT FORMAT:
{
  "location": string,
  "budget": float,
  "interest_activities": [string],
  "input_activities": [string],
  "matched_activities": [string matching interests],
  "filtered_selection": {
    "selected_activities": [{"activity": string, "cost": float}],
    "transit_cost": float,
    "total_estimated_cost": float,
    "remaining_budget": float
  },
  "summary": {
    "total_input_activities": int,
    "matched_to_interests": int,
    "selected_within_budget": int,
    "total_cost": float,
    "remaining_budget": float
  }
}

WORKFLOW:
1. Receives JSON string from EventScraperAgent (with interest_activities and budget)
2. Receives JSON string from FundAllocationAgent (with activities list and budget)
3. Maps activities to categories using KEYWORD_MAP heuristics
4. Filters activities matching user's interest categories
5. Estimates costs using fallback cost distribution
6. Selects activities that fit within total budget
7. Returns comprehensive filtered_output.json

LOCAL USAGE:
   python budgetFilterAgent.py
   (reads events_scraper_example.json and fund_allocation_example.json)

AGENTVERSE USAGE:
   Send Chat Protocol message to this agent with EventScraperAgent or FundAllocationAgent JSON
"""

import json
import os
from typing import List, Dict, Optional
import re
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# AI Client for transit research and scheduling
client = OpenAI(
    base_url="https://api.asi1.ai/v1",
    api_key=os.getenv("FETCH_API_KEY", ""),
)

try:
    from uagents import Agent, Context, Protocol, Model
    from uagents_core.contrib.protocols.chat import (
        ChatMessage,
        TextContent,
        chat_protocol_spec,
        ChatAcknowledgement,
    )
    UA_PRESENT = True
except Exception:
    UA_PRESENT = False

BASE_DIR = os.path.dirname(__file__)


def read_json_file_strip(path: str) -> Dict:
    """Read a JSON file and strip surrounding triple-backticks if present."""
    with open(path, "r", encoding="utf-8") as f:
        text = f.read().strip()

    # Remove code fence wrappers (```json ... ```)
    if text.startswith("```") and text.endswith("```"):
        # remove first and last fence lines
        parts = text.split("```")
        # find the first part that looks like JSON
        candidate = None
        for p in parts:
            p = p.strip()
            if p.startswith("{") or p.startswith("["):
                candidate = p
                break
        if candidate is None:
            candidate = text
        text = candidate

    return json.loads(text)


def parse_text_to_json(text: str) -> Dict:
    """
    Parse string input (JSON from Agentverse) into a dict with 'events' and 'fund' keys.
    
    Accepts multiple formats:
    1. EventScraperAgent output (has interest_activities, timeframe, budget)
    2. FundAllocationAgent output (has activities, budget, location)
    3. Pre-wrapped format with 'events' and 'fund' keys
    4. Two JSON objects in sequence (auto-detected and classified)
    5. Single JSON object (auto-classified by key detection)
    
    Returns:
        Dictionary with keys: {'events': {...}, 'fund': {...}}
    
    Raises ValueError if parsing fails.
    """
    if not text or not isinstance(text, str):
        raise ValueError("Input must be a non-empty string")

    # Remove common agent mentions and excessive whitespace
    cleaned = re.sub(r'@agent[a-zA-Z0-9]+', '', text)
    cleaned = re.sub(r'\bagent1q[a-zA-Z0-9]+\b', '', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()

    # Try direct JSON parse first
    try:
        obj = json.loads(cleaned)
    except Exception:
        obj = None

    candidates = []
    if isinstance(obj, dict):
        # If it already looks like the wrapped format, return as-is
        if 'events' in obj or 'fund' in obj:
            # Ensure both keys exist with defaults
            result = {
                'events': obj.get('events', {}),
                'fund': obj.get('fund', {})
            }
            return result

        # Detect what type of agent output this is
        has_events_keys = 'interest_activities' in obj or 'timeframe' in obj or 'interests' in obj
        has_fund_keys = 'activities' in obj or 'activities_found' in obj
        has_basic_keys = 'location' in obj or 'budget' in obj
        
        # Classification logic
        if has_events_keys and has_fund_keys and has_basic_keys:
            # Could be either or both - treat it as events since it has interest_activities
            return {'events': obj, 'fund': obj}
        elif has_events_keys:
            # This is EventScraperAgent output
            return {'events': obj, 'fund': {}}
        elif has_fund_keys:
            # This is FundAllocationAgent output
            return {'events': {}, 'fund': obj}
        elif has_basic_keys:
            # Has location/budget but unclear - treat as fund (activities list)
            return {'events': {}, 'fund': obj}

    # If direct parse failed or ambiguous, extract JSON-like substrings
    matches = re.findall(r'\{.*?\}', cleaned, re.S)
    for m in matches:
        try:
            parsed = json.loads(m)
            if isinstance(parsed, dict):
                candidates.append(parsed)
        except Exception:
            continue

    # Classify candidate JSONs
    def classify_json(d):
        """Determine if JSON is from EventScraperAgent, FundAllocationAgent, or unknown."""
        has_events_keys = 'interest_activities' in d or 'timeframe' in d or 'interests' in d
        has_fund_keys = 'activities' in d or 'activities_found' in d
        
        if has_events_keys:
            return 'events'
        elif has_fund_keys:
            return 'fund'
        elif 'location' in d and 'budget' in d:
            # Ambiguous - could be either, default to fund
            return 'fund'
        return None

    # Process candidates
    if len(candidates) >= 2:
        # Two or more JSON objects found
        classified = {}
        for cand in candidates:
            ctype = classify_json(cand)
            if ctype:
                # Store the first occurrence of each type
                if ctype not in classified:
                    classified[ctype] = cand

        if 'events' in classified and 'fund' in classified:
            return {'events': classified['events'], 'fund': classified['fund']}
        elif 'events' in classified:
            return {'events': classified['events'], 'fund': classified.get('fund', {})}
        elif 'fund' in classified:
            return {'events': classified.get('events', {}), 'fund': classified['fund']}

    # If we found exactly one JSON dict, use heuristics to classify
    if len(candidates) == 1:
        d = candidates[0]
        ctype = classify_json(d)
        if ctype == 'events':
            return {'events': d, 'fund': {}}
        elif ctype == 'fund':
            return {'events': {}, 'fund': d}
        else:
            # Try as fund by default
            return {'events': {}, 'fund': d}

    # Last resort: try to extract JSON from text without balance checking
    # Look for arrays of activities specifically
    activities_match = re.search(r'"activities"\s*:\s*(\[[^\]]*(?:\{[^\}]*\}[^\]]*)*\])', cleaned, re.I)
    if activities_match:
        try:
            activities = json.loads(activities_match.group(1))
            return {'events': {}, 'fund': {'activities': activities, 'location': '', 'budget': 0}}
        except Exception:
            pass

    raise ValueError(
        'Unable to parse input string into valid JSON.\n'
        'Expected formats:\n'
        '  1. EventScraperAgent: {"location": "...", "interest_activities": [...], "budget": 500}\n'
        '  2. FundAllocationAgent: {"location": "...", "activities": [...], "budget": 500}\n'
        '  3. Both wrapped: {"events": {...}, "fund": {...}}'
    )


KEYWORD_MAP = {
    "sightseeing": ["statue", "times square", "sightseeing", "tour", "landmark", "monument"],
    "dining": ["dinner", "restaurant", "dining", "food", "brunch", "lunch", "meal"],
    "entertainment": ["broadway", "show", "concert", "performance", "theater", "theatre"],
    "adventure": ["ski", "rafting", "adventure", "climb"],
    "cultural": ["museum", "gallery", "metropolitan", "art", "history"],
    "relaxation": ["spa", "relax", "retreat"],
    "outdoor": ["park", "bike", "biking", "hike", "trail"],
    "shopping": ["shop", "shopping", "mall", "boutique"],
    "skiing": ["ski", "skiing"]
}


def map_activity_to_category(activity: str) -> Optional[str]:
    a = activity.lower()
    for cat, keywords in KEYWORD_MAP.items():
        for kw in keywords:
            if kw in a:
                return cat
    return None


def generate_fallback_costs(activities: List[str], location: str, budget: float) -> Dict:
    """Fallback cost estimator mirroring the FundAllocationAgent logic."""
    num_activities = len(activities)
    if num_activities == 0:
        return {"activities": [], "transit_cost": 0, "total_estimated_cost": 0, "research_notes": "No activities provided"}

    transit_cost = min(budget * 0.12, 50.0)
    remaining_budget = max(budget - transit_cost, 0)
    cost_per_activity = remaining_budget / num_activities if num_activities > 0 else 0

    activities_list = []
    for activity in activities:
        activities_list.append({
            "activity": activity,
            "cost": round(cost_per_activity, 2),
            "currency": "USD",
            "source": "Estimated by budget distribution",
            "notes": f"Fallback estimate for {location}"
        })

    total_cost = round(cost_per_activity * num_activities + transit_cost, 2)

    return {
        "activities": activities_list,
        "transit_cost": round(transit_cost, 2),
        "total_estimated_cost": total_cost,
        "research_notes": f"Fallback distribution across {num_activities} activities plus transit"
    }


def filter_activities_by_interest(fund_activities: List[str], interests: List[str]) -> List[str]:
    matched = []
    for act in fund_activities:
        cat = map_activity_to_category(act)
        if cat and cat in interests:
            matched.append(act)
    return matched


def select_activities_within_budget(cost_data: Dict, budget: float) -> Dict:
    transit = cost_data.get("transit_cost", 0)
    activities = cost_data.get("activities", [])

    selected = []
    total = transit

    for a in activities:
        c = float(a.get("cost", 0))
        # include activity if it keeps total <= budget
        if total + c <= budget:
            selected.append({"activity": a.get("activity"), "cost": c})
            total += c

    remaining = round(budget - total, 2)

    return {
        "selected_activities": selected,
        "transit_cost": transit,
        "total_estimated_cost": round(total, 2),
        "remaining_budget": remaining
    }


def main():
    """
    Run the filter agent on example files.
    
    Expected files:
    - events_scraper_example.json: Output from EventScraperAgent with interest_activities
    - fund_allocation_example.json: Output from FundAllocationAgent with activities list
    
    Produces:
    - filtered_output.json: Filtered activities matching interests and budget
    """
    events_path = os.path.join(BASE_DIR, "events_scraper_example.json")
    fund_path = os.path.join(BASE_DIR, "fund_allocation_example.json")

    try:
        events = read_json_file_strip(events_path)
        print(f"Loaded EventScraperAgent output from {events_path}")
    except FileNotFoundError:
        print(f"Warning: {events_path} not found, using empty dict")
        events = {}
    except Exception as e:
        print(f"Error reading EventScraperAgent output: {e}")
        events = {}

    try:
        fund = read_json_file_strip(fund_path)
        print(f"Loaded FundAllocationAgent output from {fund_path}")
    except FileNotFoundError:
        print(f"Warning: {fund_path} not found, using empty dict")
        fund = {}
    except Exception as e:
        print(f"Error reading FundAllocationAgent output: {e}")
        fund = {}

    output = filter_from_dicts(events, fund)

    out_path = os.path.join(BASE_DIR, "filtered_output.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)
    
    print(f"\nFiltered output written to {out_path}")
    print("\nResult:")
    print(json.dumps(output, indent=2))


def parse_duration(duration_str: str) -> int:
    """Parse duration string (e.g., '2 hours', '30 minutes') to minutes"""
    if not duration_str:
        return 60  # Default 1 hour
    
    duration_str = duration_str.lower()
    minutes = 0
    
    # Extract hours
    hour_match = re.search(r'(\d+)\s*h(?:our)?s?', duration_str)
    if hour_match:
        minutes += int(hour_match.group(1)) * 60
    
    # Extract minutes
    min_match = re.search(r'(\d+)\s*m(?:inute)?s?', duration_str)
    if min_match:
        minutes += int(min_match.group(1))
    
    # Extract "half day" or "full day"
    if 'half day' in duration_str:
        minutes = 240  # 4 hours
    elif 'full day' in duration_str:
        minutes = 480  # 8 hours
    
    return minutes if minutes > 0 else 60  # Default to 1 hour


def estimate_transit_time_quick(from_address: str, to_address: str, location: str) -> int:
    """Quickly estimate transit time between two addresses (in minutes) without full API call"""
    if not from_address or not to_address or from_address == to_address:
        return 0
    
    # Quick heuristic: if addresses are very similar (same street, nearby numbers), assume walking
    from_parts = from_address.lower().split()
    to_parts = to_address.lower().split()
    
    # Check if they're on the same street
    common_words = set(from_parts) & set(to_parts)
    if len(common_words) >= 2:  # Same street name and city
        return 10  # Assume 10 min walk
    
    # Otherwise, use AI to estimate (but cache results)
    return None  # Signal to use full research_transit


def research_transit(from_address: str, to_address: str, location: str) -> Dict:
    """Research best transit method between two addresses using AI"""
    if not from_address or not to_address or from_address == to_address:
        return {
            "method": "walking",
            "duration_minutes": 0,
            "cost_usd": 0.0,
            "description": "Same location"
        }
    
    try:
        prompt = f"""Research the best transportation method between these two locations in {location}:

From: {from_address}
To: {to_address}

Return ONLY valid JSON:
{{
  "method": "walking|driving|public_transit|taxi|rideshare",
  "duration_minutes": number,
  "cost_usd": number,
  "description": "brief description of the route"
}}

Consider:
- Walking if under 1 mile (15-20 min walk)
- Public transit (bus, subway, train) if available and efficient
- Driving/taxi/rideshare for longer distances or when public transit is inconvenient
- Cost should be realistic for the location and method
- If locations are very far apart (more than 30 miles), transit should be at least 45-60 minutes"""
        
        response = client.chat.completions.create(
            model="asi1-mini",
            messages=[
                {"role": "system", "content": "You are a transportation research assistant. Research the best transit methods between locations."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=200,
        )
        
        result = json.loads(response.choices[0].message.content)
        
        # Cap transit time at reasonable maximum (2 hours)
        if result.get("duration_minutes", 0) > 120:
            result["duration_minutes"] = 120
            result["method"] = "driving"
            result["description"] = "Long distance travel"
        
        return result
    except Exception as e:
        print(f"Error researching transit: {e}")
        # Fallback: estimate based on distance
        return {
            "method": "walking",
            "duration_minutes": 15,
            "cost_usd": 0.0,
            "description": "Estimated walking route"
        }


def schedule_activities(venues: List[Dict], all_available_venues: Dict[str, List[Dict]], location: str, budget: float, total_cost: float, start_time: Optional[str] = None, end_time: Optional[str] = None) -> List[Dict]:
    """Schedule activities with timing, transit, and pack multiple activities efficiently to fill time constraint"""
    if not venues:
        return []
    
    # Parse start and end times
    if start_time:
        try:
            start_datetime = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
        except:
            start_datetime = datetime.now().replace(hour=9, minute=0, second=0, microsecond=0)
    else:
        start_datetime = datetime.now().replace(hour=9, minute=0, second=0, microsecond=0)
    
    if end_time:
        try:
            end_datetime = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
        except:
            end_datetime = start_datetime + timedelta(hours=12)  # Default 12 hours
    else:
        end_datetime = start_datetime + timedelta(hours=12)
    
    # Separate meals from other activities
    meal_categories = {"breakfast", "brunch", "lunch", "dinner", "eat", "dining", "food"}
    meals = []
    other_activities = []
    
    for venue in venues:
        venue_category = venue.get("category", "").lower()
        if venue_category in meal_categories:
            meals.append(venue)
        else:
            other_activities.append(venue)
    
    # Determine meal times based on time window
    total_hours = (end_datetime - start_datetime).total_seconds() / 3600
    start_hour = start_datetime.hour + start_datetime.minute / 60
    
    # Plan meal times (spaced out appropriately)
    meal_times = []
    if meals:
        if total_hours >= 8:  # Full day - can fit 3 meals
            if start_hour < 10:  # Early start
                meal_times = [11.0, 14.0, 19.0]  # Brunch, Lunch, Dinner
            elif start_hour < 12:  # Mid-morning start
                meal_times = [12.0, 15.0, 19.0]  # Lunch, Late lunch, Dinner
            else:  # Afternoon start
                meal_times = [13.0, 18.0]  # Lunch, Dinner
        elif total_hours >= 5:  # Half day - can fit 2 meals
            if start_hour < 11:
                meal_times = [11.5, 15.0]  # Brunch, Late lunch
            else:
                meal_times = [13.0, 18.0]  # Lunch, Dinner
        else:  # Short window - 1 meal
            meal_times = [start_hour + total_hours / 2]  # Middle of window
    
    # Sort meals by type (breakfast/brunch first, then lunch, then dinner)
    meal_order = {"breakfast": 1, "brunch": 1, "lunch": 2, "dinner": 3, "eat": 2}
    meals.sort(key=lambda v: meal_order.get(v.get("category", "").lower(), 99))
    
    scheduled = []
    current_time = start_datetime
    scheduled_venue_names = set()
    
    # Helper function to add transit
    def add_transit_if_needed(prev_address: str, next_address: str, next_venue_name: str) -> bool:
        nonlocal current_time, total_cost
        if prev_address and next_address and prev_address != next_address:
            transit_info = research_transit(prev_address, next_address, location)
            transit_duration = transit_info.get("duration_minutes", 15)
            transit_cost = transit_info.get("cost_usd", 0.0)
            transit_method = transit_info.get("method", "walking")
            
            # Cap transit duration at reasonable maximum
            if transit_duration > 120:  # More than 2 hours is unreasonable
                transit_duration = 120
                transit_method = "driving"
            
            if (current_time + timedelta(minutes=transit_duration)) <= end_datetime:
                transit_activity = {
                    "type": "transit",
                    "venue": f"Travel via {transit_method}",
                    "category": "transit",
                    "start_time": current_time.isoformat(),
                    "end_time": (current_time + timedelta(minutes=transit_duration)).isoformat(),
                    "duration_minutes": transit_duration,
                    "cost": transit_cost,
                    "description": transit_info.get("description", f"Travel to {next_venue_name}"),
                    "method": transit_method,
                    "address": next_address
                }
                scheduled.append(transit_activity)
                current_time += timedelta(minutes=transit_duration)
                total_cost += transit_cost
                return True
        return False
    
    # Schedule meals at appropriate times
    meal_index = 0
    for meal_time in meal_times:
        if meal_index >= len(meals):
            break
        
        # Calculate target time for this meal
        target_time = start_datetime.replace(hour=int(meal_time), minute=int((meal_time % 1) * 60), second=0, microsecond=0)
        if target_time < current_time:
            target_time = current_time
        if target_time >= end_datetime:
            break
        
        meal = meals[meal_index]
        meal_name = meal.get("name", "")
        meal_category = meal.get("category", "").lower()
        meal_cost = meal.get("cost", 0)
        meal_address = meal.get("address", "")
        meal_duration = parse_duration(meal.get("duration", "1 hour"))
        
        # If we're before the target time, fill with other activities
        # Reserve budget for this meal and remaining meals
        remaining_meals_cost = sum(m.get("cost", 0) for m in meals[meal_index:])
        available_budget = budget - total_cost - remaining_meals_cost
        
        # Also try to pull from all_available_venues to fill gaps before meals
        all_activities_pool = list(other_activities)
        for cat, venue_list in all_available_venues.items():
            for venue in venue_list:
                if venue.get("name") not in scheduled_venue_names:
                    # Only add non-meal activities
                    venue_category = venue.get("category", "").lower()
                    if venue_category not in meal_categories:
                        all_activities_pool.append(venue)
        
        while current_time < target_time and all_activities_pool and available_budget > 0:
            # Try to pack multiple activities before the meal
            time_until_meal = (target_time - current_time).total_seconds() / 60
            
            # Find activities that fit in this gap
            # First, calculate transit times for all candidates and sort by transit time
            candidates_with_transit = []
            prev_addr = scheduled[-1].get("address", "") if scheduled else ""
            
            for activity in all_activities_pool[:]:  # Copy list to iterate safely
                if activity.get("name") in scheduled_venue_names:
                    continue
                
                act_name = activity.get("name", "")
                act_address = activity.get("address", "")
                act_duration = parse_duration(activity.get("duration", "1 hour"))
                act_cost = activity.get("cost", 0)
                
                # Check transit time - reject if too far (more than 30 minutes to keep transit times short)
                transit_time = 0
                if prev_addr and act_address and prev_addr != act_address:
                    # Quick estimate first
                    quick_estimate = estimate_transit_time_quick(prev_addr, act_address, location)
                    if quick_estimate is not None:
                        transit_time = quick_estimate
                    else:
                        # Need to check actual transit time
                        transit_info = research_transit(prev_addr, act_address, location)
                        transit_time = transit_info.get("duration_minutes", 15)
                    
                    # Reject activities that are too far away (reduced from 45 to 30 minutes)
                    if transit_time > 30:  # More than 30 minutes transit is too far
                        continue
                
                total_needed = transit_time + act_duration
                
                # Check budget including reserved meal costs
                if (current_time + timedelta(minutes=total_needed)) <= target_time and (total_cost + act_cost) <= (budget - remaining_meals_cost):
                    candidates_with_transit.append((activity, transit_time, act_duration, act_cost))
            
            # Sort candidates by transit time (shortest first) to minimize transit times
            candidates_with_transit.sort(key=lambda x: x[1])  # Sort by transit_time
            
            # Select activities in order of shortest transit time
            activities_to_add = []
            temp_time = current_time
            temp_cost = total_cost
            temp_prev_addr = prev_addr
            
            for activity, transit_time, act_duration, act_cost in candidates_with_transit:
                total_needed = transit_time + act_duration
                
                # Check budget including reserved meal costs
                if (temp_time + timedelta(minutes=total_needed)) <= target_time and (temp_cost + act_cost) <= (budget - remaining_meals_cost):
                    activities_to_add.append((activity, transit_time))
                    temp_time += timedelta(minutes=total_needed)
                    temp_cost += act_cost
                    temp_prev_addr = activity.get("address", "")
                elif len(activities_to_add) > 0:
                    break  # Can't fit more, but we have some
            
            if not activities_to_add:
                break  # Can't fit any activities before this meal
            
            # Add the activities we found
            for activity, transit_time in activities_to_add:
                act_name = activity.get("name", "")
                act_address = activity.get("address", "")
                act_duration = parse_duration(activity.get("duration", "1 hour"))
                act_cost = activity.get("cost", 0)
                
                # Add transit
                if scheduled:
                    prev_venue = scheduled[-1]
                    prev_addr = prev_venue.get("address", "")
                    add_transit_if_needed(prev_addr, act_address, act_name)
                
                # Add activity
                activity_end = current_time + timedelta(minutes=act_duration)
                if activity_end <= end_datetime:
                    activity_obj = {
                        "type": "venue",
                        "venue": act_name,
                        "category": activity.get("category", "").lower(),
                        "start_time": current_time.isoformat(),
                        "end_time": activity_end.isoformat(),
                        "duration_minutes": act_duration,
                        "cost": act_cost,
                        "description": activity.get("description", ""),
                        "address": act_address,
                        "phone": activity.get("phone"),
                        "url": activity.get("url")
                    }
                    scheduled.append(activity_obj)
                    current_time = activity_end
                    total_cost += act_cost
                    scheduled_venue_names.add(act_name)
                    # Remove from both lists if present
                    if activity in other_activities:
                        other_activities.remove(activity)
                    if activity in all_activities_pool:
                        all_activities_pool.remove(activity)
            
            # Update available budget after adding activities
            remaining_meals_cost = sum(m.get("cost", 0) for m in meals[meal_index:])
            available_budget = budget - total_cost - remaining_meals_cost
        
        # Now schedule the meal
        if current_time < target_time:
            current_time = target_time
        
        # Add transit to meal if needed
        if scheduled:
            prev_venue = scheduled[-1]
            prev_addr = prev_venue.get("address", "")
            add_transit_if_needed(prev_addr, meal_address, meal_name)
        
        # Schedule meal
        meal_end = current_time + timedelta(minutes=meal_duration)
        if meal_end <= end_datetime and (total_cost + meal_cost) <= budget:
            meal_activity = {
                "type": "venue",
                "venue": meal_name,
                "category": meal_category,
                "start_time": current_time.isoformat(),
                "end_time": meal_end.isoformat(),
                "duration_minutes": meal_duration,
                "cost": meal_cost,
                "description": meal.get("description", ""),
                "address": meal_address,
                "phone": meal.get("phone"),
                "url": meal.get("url")
            }
            scheduled.append(meal_activity)
            current_time = meal_end
            total_cost += meal_cost
            scheduled_venue_names.add(meal_name)
            meal_index += 1
    
    # Fill remaining time with other activities (pack multiple when possible)
    # Be very aggressive about filling the time window - continue until we're within 30 minutes of end time
    # This ensures the itinerary doesn't end more than 30 minutes before the specified end time
    remaining_time = (end_datetime - current_time).total_seconds() / 60
    remaining_budget = budget - total_cost
    
    # Sort other activities by transit time first (shortest transit = highest priority), then duration, then cost
    # This ensures we minimize transit times throughout the itinerary
    if scheduled:
        current_location = scheduled[-1].get("address", "")
        if current_location:
            # Pre-calculate transit times for all activities to sort by transit time
            def calculate_transit_for_sorting(activity):
                act_address = activity.get("address", "")
                if act_address and current_location and act_address != current_location:
                    quick_estimate = estimate_transit_time_quick(current_location, act_address, location)
                    if quick_estimate is not None:
                        return quick_estimate
                    # For sorting, use a conservative estimate - will be recalculated when actually scheduling
                    return 20  # Default estimate for sorting
                return 0  # Same location or no address
            
            # Sort by: 1) transit time (shortest first), 2) duration (shorter first to pack more), 3) cost
            def sort_key(activity):
                transit_time = calculate_transit_for_sorting(activity)
                duration = parse_duration(activity.get("duration", "1 hour"))
                cost = activity.get("cost", 0)
                return (transit_time, duration, cost)
            
            other_activities.sort(key=sort_key)
        else:
            other_activities.sort(key=lambda v: parse_duration(v.get("duration", "1 hour")))
    else:
        other_activities.sort(key=lambda v: parse_duration(v.get("duration", "1 hour")))
    
    # First, use up all activities from the original list
    # Continue until we're within 30 minutes of end time to ensure we fill the time constraint
    # Even if other_activities is exhausted, we'll continue with all_available_venues below
    while remaining_time > 30 and remaining_budget > 5 and other_activities:
        # Try to pack multiple activities in remaining time
        activities_to_add = []
        temp_time = current_time
        temp_cost = total_cost
        prev_addr = scheduled[-1].get("address", "") if scheduled else ""
        
        # Calculate transit times for all candidates first, then sort by transit time
        # This ensures we prioritize activities with shorter transit times
        candidates_with_transit = []
        for activity in other_activities[:]:
            if activity.get("name") in scheduled_venue_names:
                continue
            
            act_name = activity.get("name", "")
            act_address = activity.get("address", "")
            act_duration = parse_duration(activity.get("duration", "1 hour"))
            act_cost = activity.get("cost", 0)
            
            # Check transit time - reject if too far (more than 30 minutes to keep transit times short)
            transit_time = 0
            if prev_addr and act_address and prev_addr != act_address:
                quick_estimate = estimate_transit_time_quick(prev_addr, act_address, location)
                if quick_estimate is not None:
                    transit_time = quick_estimate
                else:
                    transit_info = research_transit(prev_addr, act_address, location)
                    transit_time = transit_info.get("duration_minutes", 15)
                
                # Reject activities that are too far away (reduced from 45 to 30 minutes)
                if transit_time > 30:
                    continue
            
            total_needed = transit_time + act_duration
            
            if (temp_time + timedelta(minutes=total_needed)) <= end_datetime and (temp_cost + act_cost) <= budget:
                candidates_with_transit.append((activity, transit_time, act_duration, act_cost))
        
        # Sort candidates by transit time (shortest first) to minimize transit times
        candidates_with_transit.sort(key=lambda x: x[1])  # Sort by transit_time
        
        # Select activities in order of shortest transit time
        for activity, transit_time, act_duration, act_cost in candidates_with_transit:
            total_needed = transit_time + act_duration
            if (temp_time + timedelta(minutes=total_needed)) <= end_datetime and (temp_cost + act_cost) <= budget:
                activities_to_add.append((activity, transit_time))
                temp_time += timedelta(minutes=total_needed)
                temp_cost += act_cost
                prev_addr = activity.get("address", "")
            else:
                break  # Can't fit more
        
        if not activities_to_add:
            # Can't fit any more activities from other_activities list
            # Remove activities that are too expensive or don't fit time-wise to avoid infinite loop
            # But continue to all_available_venues section which will keep trying until < 30 mins
            break  # Move to all_available_venues section
        
        # Add the activities
        for activity, transit_time in activities_to_add:
            act_name = activity.get("name", "")
            act_address = activity.get("address", "")
            act_duration = parse_duration(activity.get("duration", "1 hour"))
            act_cost = activity.get("cost", 0)
            
            # Add transit
            if scheduled:
                prev_venue = scheduled[-1]
                prev_addr = prev_venue.get("address", "")
                add_transit_if_needed(prev_addr, act_address, act_name)
            
            # Add activity
            activity_end = current_time + timedelta(minutes=act_duration)
            if activity_end <= end_datetime:
                activity_obj = {
                    "type": "venue",
                    "venue": act_name,
                    "category": activity.get("category", "").lower(),
                    "start_time": current_time.isoformat(),
                    "end_time": activity_end.isoformat(),
                    "duration_minutes": act_duration,
                    "cost": act_cost,
                    "description": activity.get("description", ""),
                    "address": act_address,
                    "phone": activity.get("phone"),
                    "url": activity.get("url")
                }
                scheduled.append(activity_obj)
                current_time = activity_end
                total_cost += act_cost
                scheduled_venue_names.add(act_name)
                other_activities.remove(activity)
        
        remaining_time = (end_datetime - current_time).total_seconds() / 60
        remaining_budget = budget - total_cost
    
    # Aggressively fill remaining time from all_available_venues
    # Keep looping through categories until we can't fit any more activities
    # Continue until we're within 30 minutes of end time to ensure we fill the time constraint
    # Increase max_iterations to allow more attempts to fill the time window
    max_iterations = 30  # Increased from 10 to allow more attempts to fill time
    iteration = 0
    added_any = True
    
    # Continue scheduling until less than 30 minutes remain, regardless of whether we added anything in previous iteration
    # This ensures we keep trying to fill the time window
    while remaining_time > 30 and remaining_budget > 5 and iteration < max_iterations:
        iteration += 1
        added_any = False
        # Recalculate remaining time and budget at start of each iteration
        # Get current time from last scheduled activity
        if scheduled:
            last_activity_end = scheduled[-1].get("end_time", "")
            if isinstance(last_activity_end, str):
                try:
                    current_time = datetime.fromisoformat(last_activity_end.replace('Z', '+00:00'))
                except:
                    current_time = datetime.now()
            else:
                current_time = last_activity_end
        else:
            current_time = start_datetime
        
        remaining_time = (end_datetime - current_time).total_seconds() / 60
        remaining_budget = budget - total_cost
        
        # If we're already within 30 minutes, break
        if remaining_time <= 30:
            break
        
        additional_categories = ["entertainment", "sightsee", "sightseeing", "cultural", "shop", "outdoor", "relax", "museum", "park", "gallery"]
        
        # Try to pack multiple activities from available venues
        for category in additional_categories:
            if remaining_time <= 30:
                break
            
            available_for_category = []
            for cat, venue_list in all_available_venues.items():
                if match_venue_to_category(cat, category):
                    available_for_category.extend(venue_list)
            
            # Calculate transit times for all venues first, then sort by transit time (shortest first)
            # This ensures we prioritize venues with shorter transit times
            candidates_with_transit = []
            prev_addr = scheduled[-1].get("address", "") if scheduled else ""
            
            for venue in available_for_category:
                if venue.get("name") in scheduled_venue_names:
                    continue
                
                venue_name = venue.get("name", "")
                venue_cost = venue.get("cost", 0)
                venue_address = venue.get("address", "")
                venue_duration = parse_duration(venue.get("duration", "1 hour"))
                
                # Check transit time - reject if too far (more than 30 minutes to keep transit times short)
                transit_time = 0
                if prev_addr and venue_address and prev_addr != venue_address:
                    quick_estimate = estimate_transit_time_quick(prev_addr, venue_address, location)
                    if quick_estimate is not None:
                        transit_time = quick_estimate
                    else:
                        transit_info = research_transit(prev_addr, venue_address, location)
                        transit_time = transit_info.get("duration_minutes", 15)
                    
                    # Reject venues that are too far away (reduced from 45 to 30 minutes)
                    if transit_time > 30:
                        continue
                
                total_needed = transit_time + venue_duration
                
                if (current_time + timedelta(minutes=total_needed)) <= end_datetime and (total_cost + venue_cost) <= budget:
                    candidates_with_transit.append((venue, transit_time, venue_duration, venue_cost))
            
            # Sort by transit time (shortest first) to minimize transit times
            candidates_with_transit.sort(key=lambda x: x[1])  # Sort by transit_time
            
            # Try to pack multiple activities from this category, selecting shortest transit times first
            activities_to_add = []
            temp_time = current_time
            temp_cost = total_cost
            temp_prev_addr = prev_addr
            
            for venue, transit_time, venue_duration, venue_cost in candidates_with_transit:
                total_needed = transit_time + venue_duration
                
                if (temp_time + timedelta(minutes=total_needed)) <= end_datetime and (temp_cost + venue_cost) <= budget:
                    activities_to_add.append((venue, transit_time))
                    temp_time += timedelta(minutes=total_needed)
                    temp_cost += venue_cost
                    temp_prev_addr = venue.get("address", "")
                else:
                    break  # Can't fit more from this category
            
            # Add all activities we found for this category
            for venue, transit_time in activities_to_add:
                venue_name = venue.get("name", "")
                venue_cost = venue.get("cost", 0)
                venue_address = venue.get("address", "")
                venue_duration = parse_duration(venue.get("duration", "1 hour"))
                
                # Add transit
                if scheduled:
                    prev_venue = scheduled[-1]
                    prev_addr = prev_venue.get("address", "")
                    add_transit_if_needed(prev_addr, venue_address, venue_name)
                
                # Add activity
                activity_end = current_time + timedelta(minutes=venue_duration)
                if activity_end <= end_datetime:
                    activity_obj = {
                        "type": "venue",
                        "venue": venue_name,
                        "category": venue.get("category", "").lower(),
                        "start_time": current_time.isoformat(),
                        "end_time": activity_end.isoformat(),
                        "duration_minutes": venue_duration,
                        "cost": venue_cost,
                        "description": venue.get("description", ""),
                        "address": venue_address,
                        "phone": venue.get("phone"),
                        "url": venue.get("url")
                    }
                    scheduled.append(activity_obj)
                    current_time = activity_end
                    total_cost += venue_cost
                    scheduled_venue_names.add(venue_name)
                    added_any = True
                    remaining_time = (end_datetime - current_time).total_seconds() / 60
                    remaining_budget = budget - total_cost
    
    # Final aggressive check: Keep adding activities until we're within 30 minutes of end time
    # This ensures the itinerary doesn't end too early (e.g., ending at 2pm when end time is 6:50pm)
    remaining_time = (end_datetime - current_time).total_seconds() / 60
    remaining_budget = budget - total_cost
    
    # Keep looping until we're within 30 minutes of end time or can't add more
    # Increased iterations to allow more attempts to fill large time gaps
    max_final_iterations = 50  # Increased from 20 to allow filling large time gaps
    final_iteration = 0
    
    while remaining_time > 30 and remaining_budget > 5 and final_iteration < max_final_iterations:
        final_iteration += 1
        # Try to find a short activity that fits in the remaining time
        # Prioritize activities with very short transit times
        current_location = scheduled[-1].get("address", "") if scheduled else ""
        all_candidates = []
        
        # Collect all available venues that haven't been scheduled
        for cat, venue_list in all_available_venues.items():
            for venue in venue_list:
                if venue.get("name") not in scheduled_venue_names:
                    venue_address = venue.get("address", "")
                    venue_duration = parse_duration(venue.get("duration", "1 hour"))
                    venue_cost = venue.get("cost", 0)
                    
                    # Calculate transit time
                    transit_time = 0
                    if current_location and venue_address and current_location != venue_address:
                        quick_estimate = estimate_transit_time_quick(current_location, venue_address, location)
                        if quick_estimate is not None:
                            transit_time = quick_estimate
                        else:
                            transit_info = research_transit(current_location, venue_address, location)
                            transit_time = transit_info.get("duration_minutes", 15)
                    
                    total_needed = transit_time + venue_duration
                    
                    # Accept activities with transit up to 30 minutes (increased from 20 for more flexibility)
                    if total_needed <= remaining_time and venue_cost <= remaining_budget and transit_time <= 30:
                        all_candidates.append((venue, transit_time, venue_duration, venue_cost))
        
        # Sort by transit time (shortest first), then duration
        all_candidates.sort(key=lambda x: (x[1], x[2]))
        
        if not all_candidates:
            # No more candidates, break
            break
        
        # Try to add the best candidate
        venue, transit_time, venue_duration, venue_cost = all_candidates[0]
        venue_name = venue.get("name", "")
        venue_address = venue.get("address", "")
        
        # Get current time from last scheduled activity
        if scheduled:
            last_activity_end = scheduled[-1].get("end_time", "")
            if isinstance(last_activity_end, str):
                try:
                    current_time = datetime.fromisoformat(last_activity_end.replace('Z', '+00:00'))
                except:
                    current_time = datetime.now()
            else:
                current_time = last_activity_end
        else:
            current_time = start_datetime
        
        # Add transit if needed
        if scheduled and current_location and venue_address and current_location != venue_address:
            transit_info = research_transit(current_location, venue_address, location)
            transit_duration = transit_info.get("duration_minutes", 15)
            transit_cost = transit_info.get("cost_usd", 0.0)
            transit_method = transit_info.get("method", "walking")
            
            # Cap transit at 30 minutes (increased from 20 to allow more flexibility)
            if transit_duration > 30:
                transit_duration = 30
                transit_method = "driving"
            
            if transit_duration <= 30 and (current_time + timedelta(minutes=transit_duration)) <= end_datetime:
                transit_activity = {
                    "type": "transit",
                    "venue": f"Travel via {transit_method}",
                    "category": "transit",
                    "start_time": current_time.isoformat(),
                    "end_time": (current_time + timedelta(minutes=transit_duration)).isoformat(),
                    "duration_minutes": transit_duration,
                    "cost": transit_cost,
                    "description": transit_info.get("description", f"Travel to {venue_name}"),
                    "method": transit_method,
                    "address": venue_address
                }
                scheduled.append(transit_activity)
                current_time += timedelta(minutes=transit_duration)
                total_cost += transit_cost
        
        # Update current_time after transit
        if scheduled:
            last_activity_end = scheduled[-1].get("end_time", "")
            if isinstance(last_activity_end, str):
                try:
                    current_time = datetime.fromisoformat(last_activity_end.replace('Z', '+00:00'))
                except:
                    current_time = datetime.now()
            else:
                current_time = last_activity_end
        
        # Add activity
        activity_end = current_time + timedelta(minutes=venue_duration)
        if activity_end <= end_datetime and (total_cost + venue_cost) <= budget:
            activity_obj = {
                "type": "venue",
                "venue": venue_name,
                "category": venue.get("category", "").lower(),
                "start_time": current_time.isoformat(),
                "end_time": activity_end.isoformat(),
                "duration_minutes": venue_duration,
                "cost": venue_cost,
                "description": venue.get("description", ""),
                "address": venue_address,
                "phone": venue.get("phone"),
                "url": venue.get("url")
            }
            scheduled.append(activity_obj)
            scheduled_venue_names.add(venue_name)
            current_time = activity_end
            total_cost += venue_cost
        
        # Update remaining time and budget for next iteration
        remaining_time = (end_datetime - current_time).total_seconds() / 60
        remaining_budget = budget - total_cost
    
    return scheduled


def match_venue_to_category(venue_category: str, interest_category: str) -> bool:
    """Check if a venue category matches an interest category"""
    venue_cat_lower = venue_category.lower()
    interest_cat_lower = interest_category.lower()
    
    # Direct match
    if venue_cat_lower == interest_cat_lower:
        return True
    
    # Keyword matching
    category_keywords = {
        "eat": ["dining", "food", "restaurant", "meal", "cafe"],
        "sightsee": ["sightseeing", "sights", "landmark", "monument", "museum", "attraction"],
        "entertainment": ["entertainment", "show", "concert", "theater", "nightlife", "bar", "club"],
        "shop": ["shopping", "shop", "mall", "market", "boutique"],
        "adventure": ["adventure", "outdoor", "hiking", "sports"],
        "cultural": ["cultural", "art", "gallery", "history", "museum"]
    }
    
    # Check if venue category matches any keywords for the interest
    keywords = category_keywords.get(interest_cat_lower, [])
    return any(kw in venue_cat_lower for kw in keywords) or any(kw in venue_cat_lower for kw in [interest_cat_lower])


def filter_from_dicts(events: Dict, fund: Dict) -> Dict:
    """
    Run the filtering pipeline given parsed JSON dicts and return output dict.
    Matches specific venues from EventsScraperAgent to budget categories from FundAllocationAgent.
    
    Args:
        events: EventScraperAgent output (contains activities list with name/category/cost, interest_activities, location, budget)
        fund: FundAllocationAgent output (contains activities list with activity/cost, location, budget, leftover_budget)
    
    Returns:
        Dictionary with specific venues that match interests and fit budget.
    """
    location = fund.get("location") or events.get("location") or ""
    budget = float(fund.get("budget") or events.get("budget") or 0)

    interest_activities = events.get("interest_activities", [])
    
    # Extract venues from EventsScraperAgent output
    # EventsScraperAgent returns: {"activities": [{"name": "Venue Name", "category": "eat", "estimated_cost": 45.0, ...}, ...]}
    events_activities_list = events.get("activities", [])
    venues_by_category = {}  # Map category -> list of venues
    
    for venue in events_activities_list:
        if isinstance(venue, dict):
            venue_category = venue.get("category", "").lower()
            venue_name = venue.get("name", "")
            venue_cost = float(venue.get("estimated_cost", 0))
            
            if venue_name and venue_category:
                if venue_category not in venues_by_category:
                    venues_by_category[venue_category] = []
                venues_by_category[venue_category].append({
                    "name": venue_name,
                    "category": venue_category,
                    "cost": venue_cost,
                    "description": venue.get("description", ""),
                    "address": venue.get("address"),
                    "phone": venue.get("phone"),
                    "url": venue.get("url"),
                    "duration": venue.get("duration", "1 hour"),
                    "best_time": venue.get("best_time", "flexible")
                })
    
    # Extract activities and costs from FundAllocationAgent output
    # FundAllocationAgent returns: {"activities": [{"activity": "eat", "cost": 123.45}, ...], "leftover_budget": ...}
    fund_activities_list = fund.get("activities", [])
    fund_activity_costs = {}  # Map category -> allocated cost
    
    for act in fund_activities_list:
        if isinstance(act, dict):
            activity_category = act.get("activity", "").lower()
            cost = float(act.get("cost", 0))
            if activity_category and activity_category != "transit":
                fund_activity_costs[activity_category] = cost
    
    # Get transit cost from fund allocation
    transit_cost = 0.0
    for act in fund_activities_list:
        if isinstance(act, dict) and act.get("activity", "").lower() == "transit":
            transit_cost = float(act.get("cost", 0))
            break
    
    if transit_cost == 0:
        transit_cost = min(budget * 0.12, 50.0)
    
    # Log filtering operation
    print(f"\nFiltering for {location} (Budget: ${budget:.2f})")
    print(f"Interests: {interest_activities}")
    print(f"Available venues by category: {list(venues_by_category.keys())}")
    print(f"Budget categories with costs: {list(fund_activity_costs.keys())}")

    # Match venues to interest categories and select ones that fit budget
    selected_venues = []
    total_cost = transit_cost
    
    # For each interest category, find matching venues and select the first one that fits
    for interest_cat in interest_activities:
        interest_cat_lower = interest_cat.lower()
        
        # Find allocated budget for this category
        allocated_cost = fund_activity_costs.get(interest_cat_lower, 0)
        
        # If no direct match, try to find a matching category in fund_activity_costs
        if allocated_cost == 0:
            for fund_cat, cost in fund_activity_costs.items():
                if match_venue_to_category(fund_cat, interest_cat_lower):
                    allocated_cost = cost
                    break
        
        # Find venues that match this interest category
        matching_venues = []
        for venue_cat, venues in venues_by_category.items():
            if match_venue_to_category(venue_cat, interest_cat_lower):
                matching_venues.extend(venues)
        
        # Select the first venue that fits within the allocated budget (or total remaining budget)
        selected_venue = None
        for venue in matching_venues:
            venue_cost = venue.get("cost", 0)
            # Check if venue fits within allocated cost for this category AND total budget
            if venue_cost > 0 and (allocated_cost == 0 or venue_cost <= allocated_cost) and (total_cost + venue_cost) <= budget:
                selected_venue = venue
                break
        
        # If no venue fits allocated cost, try to find any venue that fits total budget
        if not selected_venue:
            for venue in matching_venues:
                venue_cost = venue.get("cost", 0)
                if venue_cost > 0 and (total_cost + venue_cost) <= budget:
                    selected_venue = venue
                    break
        
        if selected_venue:
            selected_venues.append(selected_venue)
            total_cost += selected_venue.get("cost", 0)
            print(f"Selected venue for {interest_cat}: {selected_venue.get('name')} (${selected_venue.get('cost', 0):.2f})")
    
    # Get start_time and end_time from events or fund data
    start_time = events.get("start_time") or fund.get("start_time")
    end_time = events.get("end_time") or fund.get("end_time")
    
    # Schedule activities with timing and transit, passing all available venues for adding more
    scheduled_activities = schedule_activities(selected_venues, venues_by_category, location, budget, total_cost, start_time, end_time)
    
    # Format output with scheduled activities
    activities_output = {}
    total_scheduled_cost = 0.0
    
    for i, activity in enumerate(scheduled_activities, 1):
        activities_output[f"Activity {i}"] = {
            "venue": activity.get("venue", ""),
            "type": activity.get("type", "venue"),
            "category": activity.get("category", ""),
            "start_time": activity.get("start_time", ""),
            "end_time": activity.get("end_time", ""),
            "duration_minutes": activity.get("duration_minutes", 0),
            "cost": round(activity.get("cost", 0), 2),
            "description": activity.get("description", ""),
            "address": activity.get("address"),
            "phone": activity.get("phone"),
            "url": activity.get("url")
        }
        if activity.get("type") == "transit":
            activities_output[f"Activity {i}"]["method"] = activity.get("method", "walking")
        
        total_scheduled_cost += activity.get("cost", 0)
    
    remaining_budget = budget - total_scheduled_cost
    
    output = {
        "location": location,
        "budget": budget,
        "interest_activities": interest_activities,
        "activities": activities_output,
        "total_cost": round(total_scheduled_cost, 2),
        "remaining_budget": round(remaining_budget, 2),
        "summary": {
            "total_activities": len(scheduled_activities),
            "total_cost": round(total_scheduled_cost, 2),
            "remaining_budget": round(remaining_budget, 2)
        }
    }

    print(f"Scheduled: {len(scheduled_activities)} activities")
    print(f"Total cost: ${total_scheduled_cost:.2f}")
    print(f"Remaining: ${remaining_budget:.2f}")

    return output


# --- Optional uagents chat handler ------------------------------------------------
if UA_PRESENT:
    agent = Agent(
        name="BudgetFilter",
        seed=os.getenv("BUDGET_FILTER_AGENT_SEED", "budget-filter-seed"),
        port=int(os.getenv("BUDGET_FILTER_AGENT_PORT", "8006")),
        mailbox=True,
        publish_agent_details=True,
        network=os.getenv("AGENT_NETWORK", "testnet"),
    )

    chat_proto = Protocol(spec=chat_protocol_spec)


    @chat_proto.on_message(ChatMessage)
    async def handle_filter_request(ctx: Context, sender: str, msg: ChatMessage):
        """
        Handle filtering requests from EventScraperAgent and FundAllocationAgent via Agentverse.
        
        Accepted message formats (as JSON string):
        1. EventScraperAgent output: {"location": "...", "interest_activities": [...], "budget": 500}
        2. FundAllocationAgent output: {"location": "...", "activities": [...], "budget": 500}
        3. Both combined: {"events": {...EventScraperAgent...}, "fund": {...FundAllocationAgent...}}
        4. Two JSON objects in one message (auto-classified)
        
        Returns filtered_output with activities matching interests and budget constraints.
        """
        # Check if message is stale (older than 5 minutes)
        try:
            now = datetime.now(timezone.utc)
            msg_time = msg.timestamp
            
            # If timestamp is naive, assume it's UTC
            if msg_time.tzinfo is None:
                msg_time = msg_time.replace(tzinfo=timezone.utc)
            
            message_age = (now - msg_time).total_seconds()
            if message_age > 300:  # 5 minutes
                ctx.logger.warning(f"Ignoring stale message (age: {message_age:.0f}s, ID: {msg.msg_id})")
                return
        except Exception as e:
            ctx.logger.warning(f"Error checking message age: {e}, proceeding with message")
        
        # NOTE: Not sending ChatAcknowledgement to avoid interfering with ctx.send_and_receive
        # The orchestrator uses send_and_receive which can match acknowledgements instead of actual responses

        try:
            for item in msg.content:
                if isinstance(item, TextContent):
                    # Check for error messages in the text before parsing
                    text_preview = item.text[:200] if len(item.text) > 200 else item.text
                    error_indicators = [
                        "parse input string into valid JSON",
                        "Unable to parse input string",
                        '"type": "error"',
                        '"error":',
                        "Expected formats:",
                        "EventScraperAgent:",
                        "FundAllocationAgent:"
                    ]
                    if any(indicator in item.text for indicator in error_indicators):
                        ctx.logger.warning(f"Ignoring error message: {text_preview}")
                        return
                    
                    # Expect JSON string from Agentverse
                    try:
                        parsed = parse_text_to_json(item.text)
                    except ValueError as ve:
                        err = {
                            "type": "error", 
                            "message": str(ve),
                            "received_text": item.text[:200] if len(item.text) > 200 else item.text,
                            "hint": "Send JSON from EventScraperAgent or FundAllocationAgent"
                        }
                        response_msg = ChatMessage(
                            timestamp=datetime.now(timezone.utc), 
                            msg_id=uuid4(), 
                            content=[TextContent(type="text", text=json.dumps(err))]
                        )
                        await ctx.send(sender, response_msg)
                        ctx.logger.error(f"Parse error: {ve}")
                        return

                    # Check if parsed data contains error messages
                    if parsed.get("type") == "error" or parsed.get("error"):
                        error_msg = parsed.get("message") or parsed.get("error", "")
                        ctx.logger.warning(f"Ignoring error response: {error_msg[:100]}")
                        return
                    
                    events = parsed.get("events") or parsed.get("events_scraper") or {}
                    fund = parsed.get("fund") or parsed.get("fund_allocation") or {}
                    
                    # Validate location - reject invalid locations like error messages
                    location = None
                    if events:
                        location = events.get("location", "")
                    elif fund:
                        location = fund.get("location", "")
                    
                    if location and ("parse input string" in str(location).lower() or "error" in str(location).lower() or len(str(location)) < 2):
                        ctx.logger.warning(f"Rejecting message with invalid location: {location}")
                        return

                    if not events and not fund:
                        err = {
                            "type": "error", 
                            "message": "No valid data found in input",
                            "expected": [
                                "EventScraperAgent with 'interest_activities' field",
                                "FundAllocationAgent with 'activities' field",
                                "Both combined with 'events' and 'fund' keys"
                            ]
                        }
                        response_msg = ChatMessage(
                            timestamp=datetime.now(timezone.utc), 
                            msg_id=uuid4(), 
                            content=[TextContent(type="text", text=json.dumps(err))]
                        )
                        await ctx.send(sender, response_msg)
                        ctx.logger.warning("No events or fund data in parsed input")
                        return

                    output = filter_from_dicts(events, fund)
                    
                    ctx.logger.info(
                        f"Filter processed: {len(output.get('matched_activities', []))} matched, "
                        f"{len(output.get('filtered_selection', {}).get('selected_activities', []))} selected"
                    )

                    response_msg = ChatMessage(
                        timestamp=datetime.utcnow(), 
                        msg_id=uuid4(), 
                        content=[TextContent(type="text", text=json.dumps(output))]
                    )
                    await ctx.send(sender, response_msg)

        except Exception as e:
            err = {
                "type": "error", 
                "message": f"Filter processing failed: {str(e)}",
                "error_type": type(e).__name__
            }
            try:
                response_msg = ChatMessage(
                    timestamp=datetime.utcnow(), 
                    msg_id=uuid4(), 
                    content=[TextContent(type="text", text=json.dumps(err))]
                )
                await ctx.send(sender, response_msg)
            except Exception as send_err:
                ctx.logger.error(f"Failed to send error response: {send_err}")
            ctx.logger.error(f"Exception in filter handler: {e}", exc_info=True)

    @chat_proto.on_message(ChatAcknowledgement)
    async def handle_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
        ctx.logger.info(f"BudgetFilter received ack from {sender}")

    agent.include(chat_proto)

    if os.getenv("RUN_BUDGET_FILTER_AGENT", "false").lower() in ("1", "true", "yes"):
        agent.run()


if __name__ == "__main__":
    import sys
    # If run with --agent flag or RUN_BUDGET_FILTER_AGENT env var, start the agent
    if "--agent" in sys.argv or os.getenv("RUN_BUDGET_FILTER_AGENT", "false").lower() in ("1", "true", "yes"):
        if UA_PRESENT:
            print(f"Budget Filter Agent address: {agent.address}")
            print(f"Port: {os.getenv('BUDGET_FILTER_AGENT_PORT', '8006')}")
            print(f"Network: {os.getenv('AGENT_NETWORK', 'testnet')}")
            print("\nStarting budget filter agent...")
            agent.run()
        else:
            print("Error: uagents library not available. Cannot run agent.")
            sys.exit(1)
    else:
        # Otherwise, run the test/main function with example files
        main()
