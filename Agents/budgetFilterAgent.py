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
from datetime import datetime
from uuid import uuid4

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


def filter_from_dicts(events: Dict, fund: Dict) -> Dict:
    """
    Run the filtering pipeline given parsed JSON dicts and return output dict.
    
    Args:
        events: EventScraperAgent output (contains interest_activities, location, budget, timeframe)
        fund: FundAllocationAgent output (contains activities list, location, budget)
    
    Returns:
        Dictionary with filtered activities that match interests and fit budget.
    """
    location = fund.get("location") or events.get("location") or ""
    budget = float(fund.get("budget", events.get("budget", 0)))

    interest_activities = events.get("interest_activities", [])
    fund_activities = fund.get("activities", [])
    
    # Log filtering operation
    print(f"\nFiltering for {location} (Budget: ${budget:.2f})")
    print(f"Interests: {interest_activities}")
    print(f"Available activities: {len(fund_activities)}")

    # Filter activities that match user interests
    matched = filter_activities_by_interest(fund_activities, interest_activities)
    
    print(f"Matched to interests: {len(matched)}")

    # If nothing matched by keyword mapping, try direct interest matching
    if not matched:
        # try any keyword presence
        for act in fund_activities:
            for interest in interest_activities:
                if interest.lower() in act.lower():
                    matched.append(act)
                    break

    # If still nothing, use all activities (best-effort)
    activities_to_estimate = matched if matched else fund_activities

    # Estimate costs for selected activities
    cost_data = generate_fallback_costs(activities_to_estimate, location, budget)

    # Ensure selection fits budget (includes transit)
    selection = select_activities_within_budget(cost_data, budget)

    output = {
        "location": location,
        "budget": budget,
        "interest_activities": interest_activities,
        "input_activities": fund_activities,
        "matched_activities": activities_to_estimate,
        "filtered_selection": selection,
        "summary": {
            "total_input_activities": len(fund_activities),
            "matched_to_interests": len(activities_to_estimate),
            "selected_within_budget": len(selection.get("selected_activities", [])),
            "total_cost": selection.get("total_estimated_cost", 0),
            "remaining_budget": selection.get("remaining_budget", 0)
        }
    }

    print(f"Selected: {len(selection.get('selected_activities', []))} activities")
    print(f"Total cost: ${selection.get('total_estimated_cost', 0):.2f}")
    print(f"Remaining: ${selection.get('remaining_budget', 0):.2f}")

    return output


if __name__ == "__main__":
    main()

# --- Optional uagents chat handler ------------------------------------------------
if UA_PRESENT:
    agent = Agent(
        name="BudgetFilter",
        seed=os.getenv("BUDGET_FILTER_AGENT_SEED", "budget-filter-seed"),
        port=int(os.getenv("BUDGET_FILTER_AGENT_PORT", "8004")),
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
        await ctx.send(
            sender,
            ChatAcknowledgement(timestamp=datetime.utcnow(), acknowledged_msg_id=msg.msg_id),
        )

        try:
            for item in msg.content:
                if isinstance(item, TextContent):
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
                            timestamp=datetime.utcnow(), 
                            msg_id=uuid4(), 
                            content=[TextContent(type="text", text=json.dumps(err))]
                        )
                        await ctx.send(sender, response_msg)
                        ctx.logger.error(f"Parse error: {ve}")
                        return

                    events = parsed.get("events") or parsed.get("events_scraper") or {}
                    fund = parsed.get("fund") or parsed.get("fund_allocation") or {}

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
                            timestamp=datetime.utcnow(), 
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
    main()
