"""
Fund Allocation Agent - Web scrapes activity costs based on location
This agent takes an activities list and budget from JSON, then uses AI to find
how much is spent on each activity based on location, returning JSON with activity and cost.
"""
from uagents import Agent, Context, Protocol, Model
from uagents_core.contrib.protocols.chat import (
    ChatMessage,
    TextContent,
    chat_protocol_spec,
    ChatAcknowledgement,
)
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import uuid4
import json
import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# ============================================================
# Models
# ============================================================

class FundAllocationRequest(Model):
    """Input model for fund allocation request"""
    activities: List[str]  # List of activity names
    location: str  # Location/city name
    budget: float  # Total budget in USD

class ActivityCost(Model):
    """Individual activity with cost"""
    activity: str
    cost: float
    currency: str = "USD"
    source: Optional[str] = None  # Where the cost info came from
    notes: Optional[str] = None  # Additional notes about the cost

class FundAllocationResponse(Model):
    """Response model with activity costs"""
    location: str
    total_budget: float
    activities: List[ActivityCost]
    total_estimated_cost: float
    remaining_budget: float
    budget_allocation_percentage: Dict[str, float]  # Percentage of budget per activity

# ============================================================
# AI Client
# ============================================================

client = OpenAI(
    base_url="https://api.asi1.ai/v1",
    api_key=os.getenv("FETCH_API_KEY", ""),
)

# ============================================================
# System Prompts
# ============================================================

COST_SCRAPER_PROMPT = """
You are an expert at researching and finding accurate cost information for activities in specific locations.
Your task is to find realistic, current pricing information for activities based on web research and knowledge.

For each activity in the given location, you need to:
1. Research typical costs for that activity in that location
2. Consider factors like:
   - Entry fees, admission prices
   - Activity-specific costs (rentals, tickets, etc.)
   - Average spending per person
   - Time-based costs (hourly rates)
3. Provide realistic cost estimates in USD
4. IMPORTANT: Also calculate transit/transportation costs for getting between activities in this location

Return ONLY valid JSON in this format:
{{
  "activities": [
    {{
      "activity": "Activity Name",
      "cost": 45.00,
      "currency": "USD",
      "source": "Typical pricing for [activity type] in [location]",
      "notes": "Average cost per person, may vary by season/time"
    }}
  ],
  "transit_cost": 25.00,
  "total_estimated_cost": 350.00,
  "research_notes": "Brief summary of pricing research"
}}

IMPORTANT:
- Provide realistic, research-based cost estimates
- Consider location-specific pricing (e.g., activities in NYC vs small towns)
- Include all relevant costs (entry fees, rentals, tickets, etc.)
- If an activity is typically free, set cost to 0
- All costs should be in USD
- Be accurate and realistic based on current market rates
- ALWAYS include a "transit_cost" field with estimated transportation costs for getting between activities (e.g., subway, taxi, rideshare, public transit day passes)
"""

# ============================================================
# Fund Allocation Functions
# ============================================================

def scrape_activity_costs(
    activities: List[str],
    location: str,
    budget: float
) -> Optional[Dict]:
    """
    Scrape/research costs for activities in a given location using AI
    Returns structured cost data for each activity, including transit costs
    """
    try:
        activities_str = ", ".join(activities)
        
        prompt = f"""
Location: {location}
Total Budget: ${budget}
Activities to research: {activities_str}

For each of these {len(activities)} activities in {location}, research and provide accurate cost estimates.
Consider:
- Entry fees and admission prices
- Activity-specific costs (equipment rentals, tickets, etc.)
- Average spending per person for this activity type
- Location-specific pricing variations
- Transit/transportation costs for getting between these {len(activities)} activities in {location}

IMPORTANT: Include transit_cost in your response - estimate transportation costs (subway, taxi, rideshare, or public transit) for traveling between these activities in {location}.
Return cost information for ALL {len(activities)} activities plus transit costs.
"""
        
        response = client.chat.completions.create(
            model="asi1-mini",
            messages=[
                {"role": "system", "content": COST_SCRAPER_PROMPT},
                {"role": "user", "content": prompt},
            ],
            max_tokens=2000,
            timeout=30
        )
        
        scraped_data = json.loads(response.choices[0].message.content)
        
        # Ensure transit_cost is included, calculate if missing
        if "transit_cost" not in scraped_data or scraped_data["transit_cost"] is None:
            # Estimate transit cost: roughly 10-15% of budget or $20-50 depending on location
            transit_estimate = min(budget * 0.12, 50.0)  # 12% of budget or max $50
            scraped_data["transit_cost"] = round(transit_estimate, 2)
        
        return scraped_data
        
    except json.JSONDecodeError as e:
        print(f"JSON parsing error: {e}")
        print(f"Response content: {response.choices[0].message.content[:500] if 'response' in locals() else 'No response'}")
        # Fallback to estimated costs
        return generate_fallback_costs(activities, location, budget)
    except Exception as e:
        print(f"Cost scraping error: {e}")
        print(f"Using fallback cost estimates for {location}")
        # Return fallback cost estimates
        return generate_fallback_costs(activities, location, budget)

def generate_fallback_costs(
    activities: List[str],
    location: str,
    budget: float
) -> Dict:
    """
    Generate fallback cost estimates when API fails
    Uses budget distribution logic, including transit costs
    """
    num_activities = len(activities)
    if num_activities == 0:
        return {
            "activities": [],
            "transit_cost": 0,
            "total_estimated_cost": 0,
            "research_notes": "No activities provided"
        }
    
    # Reserve 10-15% of budget for transit
    transit_cost = min(budget * 0.12, 50.0)  # 12% of budget or max $50
    remaining_budget = budget - transit_cost
    
    # Distribute remaining budget evenly across activities
    cost_per_activity = remaining_budget / num_activities if num_activities > 0 else 0
    
    activities_list = []
    for activity in activities:
        activities_list.append({
            "activity": activity,
            "cost": round(cost_per_activity, 2),
            "currency": "USD",
            "source": "Estimated based on budget distribution",
            "notes": f"Fallback estimate - actual costs may vary in {location}"
        })
    
    total_cost = (cost_per_activity * num_activities) + transit_cost
    
    return {
        "activities": activities_list,
        "transit_cost": round(transit_cost, 2),
        "total_estimated_cost": round(total_cost, 2),
        "research_notes": f"Fallback estimates: budget distributed across {num_activities} activities plus transit"
    }

def format_allocation_response(
    location: str,
    budget: float,
    scraped_data: Dict
) -> FundAllocationResponse:
    """
    Format scraped cost data into standardized FundAllocationResponse model
    Includes transit costs as an activity
    """
    activities_list = []
    total_cost = 0.0
    
    # Add regular activities
    for activity_data in scraped_data.get("activities", []):
        cost = float(activity_data.get("cost", 0))
        total_cost += cost
        
        activity = ActivityCost(
            activity=activity_data.get("activity", ""),
            cost=cost,
            currency=activity_data.get("currency", "USD"),
            source=activity_data.get("source"),
            notes=activity_data.get("notes")
        )
        activities_list.append(activity)
    
    # Add transit as an activity
    transit_cost = float(scraped_data.get("transit_cost", 0))
    if transit_cost > 0:
        transit_activity = ActivityCost(
            activity="Transit",
            cost=transit_cost,
            currency="USD",
            source="Estimated transportation costs",
            notes=f"Transportation between activities in {location}"
        )
        activities_list.append(transit_activity)
        total_cost += transit_cost
    
    # Calculate budget allocation percentages
    budget_allocation = {}
    if total_cost > 0:
        for activity in activities_list:
            percentage = (activity.cost / total_cost) * 100
            budget_allocation[activity.activity] = round(percentage, 2)
    else:
        # If no costs, distribute evenly
        if len(activities_list) > 0:
            percentage = 100.0 / len(activities_list)
            for activity in activities_list:
                budget_allocation[activity.activity] = round(percentage, 2)
    
    remaining_budget = budget - total_cost
    
    return FundAllocationResponse(
        location=location,
        total_budget=budget,
        activities=activities_list,
        total_estimated_cost=round(total_cost, 2),
        remaining_budget=round(remaining_budget, 2),
        budget_allocation_percentage=budget_allocation
    )

# ============================================================
# Agent Setup
# ============================================================

agent = Agent(
    name="FundAllocation",
    seed=os.getenv("FUND_ALLOCATION_AGENT_SEED", "fund-allocation-seed"),
    port=8003,
    mailbox=True,
    publish_agent_details=True,
    network="testnet"
)

chat_proto = Protocol(spec=chat_protocol_spec)

# ============================================================
# Helper Functions
# ============================================================

def parse_text_to_json(text: str) -> Dict:
    """
    Parse text into JSON format, removing agent IDs and cleaning up the input.
    Handles both direct JSON input and natural language input.
    Validates required parameters strictly.
    
    Args:
        text: Input text that may contain agent IDs, JSON, or natural language
        
    Returns:
        Dict: Parsed and validated JSON data
        
    Raises:
        ValueError: If required fields are missing or invalid
    """
    import re
    
    if not text or not isinstance(text, str):
        raise ValueError("Input text must be a non-empty string")
    
    # Remove agent IDs in various formats:
    # - @agent1q... (standard format)
    # - agent1q... (without @)
    # - @agent... (any agent mention)
    cleaned_text = text.strip()
    
    # Remove @agent mentions with alphanumeric IDs
    cleaned_text = re.sub(r'@agent[a-zA-Z0-9]+', '', cleaned_text)
    
    # Remove standalone agent addresses (agent1q followed by alphanumeric)
    cleaned_text = re.sub(r'\bagent1q[a-zA-Z0-9]+\b', '', cleaned_text)
    
    # Remove any remaining agent mentions
    cleaned_text = re.sub(r'\bagent\s*\d+[a-zA-Z0-9]*\b', '', cleaned_text, flags=re.IGNORECASE)
    
    # Clean up extra whitespace and newlines
    cleaned_text = re.sub(r'\s+', ' ', cleaned_text).strip()
    
    # Remove leading/trailing punctuation that might be left after agent ID removal
    cleaned_text = re.sub(r'^[,\s]+|[,\s]+$', '', cleaned_text)
    
    if not cleaned_text:
        raise ValueError("No valid content found after removing agent IDs")
    
    # Try to parse as JSON first
    try:
        data = json.loads(cleaned_text)
        # Validate required fields
        if not data.get("location"):
            raise ValueError("Missing required field: location")
        if not data.get("activities"):
            raise ValueError("Missing required field: activities (must be non-empty list)")
        if not isinstance(data.get("activities"), list) or len(data.get("activities")) == 0:
            raise ValueError("activities must be a non-empty list")
        if "budget" not in data or data["budget"] is None or data["budget"] <= 0:
            raise ValueError("budget must be provided and greater than 0")
        return data
    except json.JSONDecodeError:
        pass
    except ValueError as ve:
        raise ve
    
    # If not valid JSON, use AI to parse natural language into JSON with strict validation
    try:
        response = client.chat.completions.create(
            model="asi1-mini",
            messages=[
                {"role": "system", "content": """You are a strict JSON converter. Convert the user's natural language request into a JSON object with these REQUIRED fields:
- location: (string, REQUIRED - city name only, must be a real place)
- activities: (array of strings, REQUIRED - must have at least 1 activity)
- budget: (number, REQUIRED - in USD, must be > 0)

STRICT RULES:
1. Location MUST be provided and must be a valid city/place name
2. activities MUST be a non-empty array
3. Budget MUST be positive
4. Return ONLY valid JSON with no other text"""},
                {"role": "user", "content": cleaned_text},
            ],
            max_tokens=300,
        )
        data = json.loads(response.choices[0].message.content)
        
        # Validate the parsed data
        if not data.get("location"):
            raise ValueError("Location not provided or invalid")
        if not data.get("activities") or not isinstance(data.get("activities"), list) or len(data["activities"]) == 0:
            raise ValueError("At least one activity is required")
        if "budget" not in data or data["budget"] is None or data["budget"] <= 0:
            raise ValueError("Budget must be greater than 0")
            
        return data
    except (json.JSONDecodeError, ValueError) as e:
        raise ValueError(f"Failed to parse request. Required fields: location, activities (list), budget. Error: {str(e)}")

# ============================================================
# Message Handlers
# ============================================================

@chat_proto.on_message(ChatMessage)
async def handle_allocation_request(ctx: Context, sender: str, msg: ChatMessage):
    """
    Handle incoming fund allocation requests
    Accepts both JSON and natural language input
    """
    ctx.logger.info(f"Fund Allocation agent received message from {sender}")
    
    # NOTE: Not sending ChatAcknowledgement to avoid interfering with ctx.send_and_receive
    # The orchestrator uses send_and_receive which can match acknowledgements instead of actual responses
    
    try:
        for item in msg.content:
            if isinstance(item, TextContent):
                ctx.logger.info(f"Processing allocation request: {item.text}")
                
                try:
                    # Parse text to JSON (handles both JSON and natural language)
                    request_data = parse_text_to_json(item.text)
                    allocation_request = FundAllocationRequest(
                        activities=request_data.get("activities", []),
                        location=request_data.get("location", ""),
                        budget=float(request_data.get("budget", 0))
                    )
                except (json.JSONDecodeError, ValueError, TypeError) as e:
                    error_response = {
                        "type": "error",
                        "message": f"Invalid request format: {str(e)}"
                    }
                    await ctx.send(
                        sender,
                        ChatMessage(
                            timestamp=datetime.utcnow(),
                            msg_id=uuid4(),
                            content=[TextContent(type="text", text=json.dumps(error_response))],
                        ),
                    )
                    return
                
                # Validate input
                if not allocation_request.location or not allocation_request.activities or allocation_request.budget <= 0:
                    error_response = {
                        "type": "error",
                        "message": "Missing required fields: location, activities (non-empty list), budget (must be > 0)"
                    }
                    await ctx.send(
                        sender,
                        ChatMessage(
                            timestamp=datetime.utcnow(),
                            msg_id=uuid4(),
                            content=[TextContent(type="text", text=json.dumps(error_response))],
                        ),
                    )
                    return
                
                ctx.logger.info(f"Valid request for {allocation_request.location} with {len(allocation_request.activities)} activities, budget: ${allocation_request.budget}")
                
                # Scrape activity costs (with fallback to estimated costs)
                scraped_data = scrape_activity_costs(
                    allocation_request.activities,
                    allocation_request.location,
                    allocation_request.budget
                )
                
                ctx.logger.info(f"Successfully scraped costs for {len(scraped_data.get('activities', []))} activities")
                
                # Format response
                response = format_allocation_response(
                    allocation_request.location,
                    allocation_request.budget,
                    scraped_data
                )
                
                # Convert to JSON-serializable format - activity, cost, and leftover budget
                # Include location and budget for budget filter agent compatibility
                response_json = {
                    "location": allocation_request.location,
                    "budget": allocation_request.budget,
                    "activities": [
                        {
                            "activity": a.activity,
                            "cost": a.cost
                        }
                        for a in response.activities
                    ],
                    "leftover_budget": response.remaining_budget
                }
                
                response_text = json.dumps(response_json, indent=2)
                ctx.logger.info(f"Sending response to {sender} ({len(response_text)} chars)")
                ctx.logger.info(f"Response preview: {response_text[:200]}...")
                
                # Send response
                response_message = ChatMessage(
                    timestamp=datetime.utcnow(),
                    msg_id=uuid4(),
                    content=[TextContent(type="text", text=response_text)],
                )
                
                await ctx.send(sender, response_message)
                ctx.logger.info(f"Response sent successfully to {sender}")
                
    except Exception as e:
        ctx.logger.error(f"Fund Allocation error: {e}")
        error_response = {
            "type": "error",
            "message": f"Processing error: {str(e)}"
        }
        try:
            await ctx.send(
                sender,
                ChatMessage(
                    timestamp=datetime.utcnow(),
                    msg_id=uuid4(),
                    content=[TextContent(type="text", text=json.dumps(error_response))],
                ),
            )
        except Exception as send_err:
            ctx.logger.error(f"Failed to send error response: {send_err}")

@chat_proto.on_message(ChatAcknowledgement)
async def handle_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
    """Handle acknowledgement messages"""
    ctx.logger.info(f"Fund Allocation agent received acknowledgement from {sender}")

# Include chat protocol
agent.include(chat_proto)

if __name__ == "__main__":
    agent.run()

