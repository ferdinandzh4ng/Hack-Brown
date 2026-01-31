"""
Events Scraper Agent - Scrapes and aggregates activities/events
This agent takes user preferences and returns a curated list of activities
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

class ActivityPreferences(Model):
    """Input model for activity scraping request"""
    location: str  # City name
    timeframe: str  # e.g., "weekend", "3 days", "1 week"
    budget: float  # Total budget in USD
    interest_activities: List[str]  # List of activity types (e.g., ["skiing", "hiking", "sightseeing"])

class ScrapedActivity(Model):
    """Individual activity/event"""
    name: str
    category: str
    description: str
    estimated_cost: float
    duration: str
    best_time: str  # e.g., "morning", "afternoon", "evening"
    difficulty: str  # "easy", "moderate", "challenging"
    url: Optional[str] = None

class ScraperResponse(Model):
    """Response model with scraped activities"""
    location: str
    activities: List[ScrapedActivity]
    total_activities_found: int
    budget_analysis: Dict[str, Any]
    recommendations: List[str]
    raw_json: Dict[str, Any]

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

ACTIVITY_SCRAPER_PROMPT = """
You are an expert travel activity scraper and curator. Given a location, timeframe, budget, and user interests, 
generate a comprehensive list of activities and experiences available in that location.

For each activity, provide:
1. Name of the activity/event
2. Category (must match or relate to one of the user's interests)
3. Description (2-3 sentences)
4. Estimated cost in USD
5. Duration (e.g., "2 hours", "half day", "full day")
6. Best time to do it (morning/afternoon/evening/flexible)
7. Difficulty level (easy/moderate/challenging)

Return ONLY valid JSON in this format:
{{
  "activities": [
    {{
      "name": "Activity Name",
      "category": "activity_type",
      "description": "Description of the activity",
      "estimated_cost": 45.00,
      "duration": "2 hours",
      "best_time": "morning",
      "difficulty": "moderate"
    }}
  ],
  "total_budget_analysis": {{
    "total_available": 500,
    "total_estimated": 350,
    "remaining_budget": 150,
    "budget_per_day": 125
  }},
  "recommendations": [
    "Recommended combination 1",
    "Recommended combination 2"
  ]
}}

IMPORTANT: Generate exactly 4-5 activities/events/venues for EACH interest category provided by the user.
Mix price ranges and difficulty levels across each category. Ensure variety within each interest type.
"""

BUDGET_ANALYSIS_PROMPT = """
Analyze if these activities fit within the user's budget and timeframe.

User budget: {budget}
Timeframe: {timeframe}
Selected activities: {activities}

Return JSON analysis:
{{
  "feasible": true/false,
  "total_cost": number,
  "days_available": number,
  "activities_per_day": number,
  "suggestions": ["suggestion1", "suggestion2"]
}}
"""

# ============================================================
# Fallback Mock Data
# ============================================================

def generate_mock_activities(
    location: str,
    timeframe: str,
    budget: float,
    interest_activities: List[str]
) -> Dict:
    """
    Generate realistic mock activity data as fallback when API fails
    """
    mock_activities = {
        "skiing": [
            {"name": "Mountain Peak Ski Resort", "category": "skiing", "description": "Full-service ski resort with varied terrain for all levels.", "estimated_cost": 75, "duration": "full day", "best_time": "morning", "difficulty": "moderate"},
            {"name": "Beginner Ski Lessons", "category": "skiing", "description": "Professional instruction for first-time skiers in a safe environment.", "estimated_cost": 95, "duration": "3 hours", "best_time": "morning", "difficulty": "easy"},
            {"name": "Night Skiing Experience", "category": "skiing", "description": "Skiing under lights on groomed runs with a festive atmosphere.", "estimated_cost": 60, "duration": "4 hours", "best_time": "evening", "difficulty": "moderate"},
            {"name": "Backcountry Ski Tour", "category": "skiing", "description": "Off-piste skiing adventure with experienced guides in remote terrain.", "estimated_cost": 150, "duration": "full day", "best_time": "morning", "difficulty": "challenging"},
            {"name": "Ski Equipment Rental", "category": "skiing", "description": "Premium ski and snowboard rental packages for all skill levels.", "estimated_cost": 45, "duration": "flexible", "best_time": "flexible", "difficulty": "easy"},
        ],
        "hiking": [
            {"name": "Mountain Trail Loop", "category": "hiking", "description": "Scenic 8-mile loop with breathtaking views and moderate elevation gain.", "estimated_cost": 0, "duration": "4 hours", "best_time": "morning", "difficulty": "moderate"},
            {"name": "Waterfall Hike Adventure", "category": "hiking", "description": "Trek to cascading waterfalls through diverse forest ecosystems.", "estimated_cost": 25, "duration": "5 hours", "best_time": "morning", "difficulty": "moderate"},
            {"name": "Summit Challenge Hike", "category": "hiking", "description": "Demanding ascent to high altitude peaks with panoramic views.", "estimated_cost": 0, "duration": "6 hours", "best_time": "early morning", "difficulty": "challenging"},
            {"name": "Guided Nature Walk", "category": "hiking", "description": "Educational walk with naturalist guide learning about local flora and fauna.", "estimated_cost": 35, "duration": "2 hours", "best_time": "afternoon", "difficulty": "easy"},
            {"name": "Rock Climbing Trail", "category": "hiking", "description": "Hiking combined with scrambling and light climbing sections.", "estimated_cost": 40, "duration": "5 hours", "best_time": "morning", "difficulty": "challenging"},
        ],
        "sightseeing": [
            {"name": "Historic Downtown Tour", "category": "sightseeing", "description": "Guided walking tour of historic architecture and cultural landmarks.", "estimated_cost": 20, "duration": "2 hours", "best_time": "afternoon", "difficulty": "easy"},
            {"name": "Museum of Art & Culture", "category": "sightseeing", "description": "Extensive collections of regional and international artwork and artifacts.", "estimated_cost": 15, "duration": "3 hours", "best_time": "afternoon", "difficulty": "easy"},
            {"name": "Panoramic Viewpoint", "category": "sightseeing", "description": "Stunning observation platform overlooking the city and surrounding landscape.", "estimated_cost": 10, "duration": "1 hour", "best_time": "sunset", "difficulty": "easy"},
            {"name": "Scenic Drive Route", "category": "sightseeing", "description": "Self-guided driving tour through picturesque landscapes and scenic overlooks.", "estimated_cost": 0, "duration": "3 hours", "best_time": "flexible", "difficulty": "easy"},
            {"name": "Local Food & Craft Market", "category": "sightseeing", "description": "Vibrant marketplace showcasing regional crafts, food, and local vendors.", "estimated_cost": 30, "duration": "2 hours", "best_time": "morning", "difficulty": "easy"},
        ],
        "dining": [
            {"name": "Fine Dining Restaurant", "category": "dining", "description": "Upscale culinary experience with locally-sourced ingredients and creative cuisine.", "estimated_cost": 85, "duration": "2.5 hours", "best_time": "evening", "difficulty": "easy"},
            {"name": "Street Food Tour", "category": "dining", "description": "Guided tasting of authentic street food and local specialties.", "estimated_cost": 40, "duration": "3 hours", "best_time": "afternoon", "difficulty": "easy"},
            {"name": "Brewery Tour & Tasting", "category": "dining", "description": "Behind-the-scenes tour of a local craft brewery with beer tastings.", "estimated_cost": 25, "duration": "2 hours", "best_time": "afternoon", "difficulty": "easy"},
            {"name": "Farm-to-Table Dining", "category": "dining", "description": "Seasonal menu featuring fresh produce from local farms and producers.", "estimated_cost": 65, "duration": "2 hours", "best_time": "evening", "difficulty": "easy"},
            {"name": "Cooking Class Experience", "category": "dining", "description": "Learn to prepare regional dishes from a professional chef.", "estimated_cost": 55, "duration": "3 hours", "best_time": "afternoon", "difficulty": "easy"},
        ],
        "adventure": [
            {"name": "Zip Lining Course", "category": "adventure", "description": "Exhilarating zip line experience through forest canopy.", "estimated_cost": 80, "duration": "2 hours", "best_time": "morning", "difficulty": "moderate"},
            {"name": "Whitewater Rafting", "category": "adventure", "description": "Thrilling river rafting adventure with experienced guides.", "estimated_cost": 70, "duration": "4 hours", "best_time": "morning", "difficulty": "moderate"},
            {"name": "Paragliding Experience", "category": "adventure", "description": "Tandem paragliding with certified instructors over scenic terrain.", "estimated_cost": 120, "duration": "2 hours", "best_time": "early morning", "difficulty": "moderate"},
            {"name": "Rock Climbing Gym", "category": "adventure", "description": "Indoor climbing facility with routes for all skill levels.", "estimated_cost": 20, "duration": "2 hours", "best_time": "flexible", "difficulty": "moderate"},
            {"name": "Canyoneering Adventure", "category": "adventure", "description": "Explore narrow canyons via hiking, scrambling, and rappelling.", "estimated_cost": 95, "duration": "full day", "best_time": "morning", "difficulty": "challenging"},
        ],
    }
    
    # Build activities list based on user interests
    activities = []
    for interest in interest_activities:
        interest_lower = interest.lower()
        if interest_lower in mock_activities:
            activities.extend(mock_activities[interest_lower])
        else:
            # Generic fallback for unknown interests
            activities.append({
                "name": f"Popular {interest.title()} Activity",
                "category": interest_lower,
                "description": f"Experience authentic {interest.lower()} activities in {location}.",
                "estimated_cost": 50,
                "duration": "3 hours",
                "best_time": "afternoon",
                "difficulty": "moderate"
            })
    
    # Calculate budget analysis
    total_estimated = sum(a.get("estimated_cost", 0) for a in activities)
    remaining = budget - total_estimated
    
    return {
        "activities": activities,
        "total_budget_analysis": {
            "total_available": budget,
            "total_estimated": total_estimated,
            "remaining_budget": max(0, remaining),
            "budget_per_day": budget / (int(timeframe.split()[0]) if timeframe.split()[0].isdigit() else 1)
        },
        "recommendations": [
            f"Combine {activities[0]['name']} with {activities[1]['name']} for a full day",
            f"Book {activities[2]['name']} in advance for better rates",
            f"Save budget for meals at local restaurants"
        ]
    }

# ============================================================
# Events Scraper Functions
# ============================================================

def scrape_activities(
    location: str,
    timeframe: str,
    budget: float,
    interest_activities: List[str]
) -> Optional[Dict]:
    """
    Scrape activities for a given location and preferences
    Returns structured activity list with budget analysis
    Generates 4-5 activities per interest category
    Falls back to mock data if API fails
    """
    try:
        interests_str = ", ".join(interest_activities)
        num_interests = len(interest_activities)
        
        prompt = f"""
Location: {location}
Timeframe: {timeframe}
Total Budget: ${budget}
User Interests: {interests_str} ({num_interests} categories)

Generate 4-5 activities/events/venues for EACH of these {num_interests} interest categories in {location}.
This should total approximately {num_interests * 4}-{num_interests * 5} activities (about 4-5 per category).
Mix price ranges within each category and ensure variety and quality in recommendations.
"""
        
        response = client.chat.completions.create(
            model="asi1-mini",
            messages=[
                {"role": "system", "content": ACTIVITY_SCRAPER_PROMPT},
                {"role": "user", "content": prompt},
            ],
            max_tokens=2000,
            timeout=30
        )
        
        scraped_data = json.loads(response.choices[0].message.content)
        return scraped_data
        
    except Exception as e:
        print(f"Activity scraping error: {e}")
        print(f"Using fallback mock data for {location}")
        # Return mock data as fallback
        return generate_mock_activities(location, timeframe, budget, interest_activities)

def analyze_budget_feasibility(
    budget: float,
    timeframe: str,
    activities: List[Dict]
) -> Optional[Dict]:
    """
    Analyze if activities fit within budget and timeframe constraints
    """
    try:
        activities_str = json.dumps(activities, indent=2)
        prompt = BUDGET_ANALYSIS_PROMPT.format(
            budget=budget,
            timeframe=timeframe,
            activities=activities_str
        )
        
        response = client.chat.completions.create(
            model="asi1-mini",
            messages=[
                {"role": "system", "content": "You are a budget analyst for travel activities."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=400,
        )
        
        analysis = json.loads(response.choices[0].message.content)
        return analysis
        
    except Exception as e:
        print(f"Budget analysis error: {e}")
        return None

def format_scraper_response(
    location: str,
    scraped_data: Dict,
    budget: float,
    budget_analysis: Optional[Dict] = None
) -> ScraperResponse:
    """
    Format scraper response into standardized ScraperResponse model
    """
    activities_list = []
    for activity_data in scraped_data.get("activities", []):
        activity = ScrapedActivity(
            name=activity_data.get("name", ""),
            category=activity_data.get("category", ""),
            description=activity_data.get("description", ""),
            estimated_cost=float(activity_data.get("estimated_cost", 0)),
            duration=activity_data.get("duration", ""),
            best_time=activity_data.get("best_time", ""),
            difficulty=activity_data.get("difficulty", ""),
            url=activity_data.get("url")
        )
        activities_list.append(activity)
    
    budget_info = scraped_data.get("total_budget_analysis", {})
    if budget_analysis:
        budget_info.update(budget_analysis)
    
    return ScraperResponse(
        location=location,
        activities=activities_list,
        total_activities_found=len(activities_list),
        budget_analysis=budget_info,
        recommendations=scraped_data.get("recommendations", []),
        raw_json=scraped_data
    )

# ============================================================
# Agent Setup
# ============================================================

agent = Agent(
    name="EventsScraper",
    seed=os.getenv("SCRAPER_AGENT_SEED", "events-scraper-seed"),
    port=8002,
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
    Try to parse text as JSON, or convert plain text to JSON format
    Also removes @agent mentions
    """
    # Remove @agent mentions
    import re
    cleaned_text = re.sub(r'@agent[a-zA-Z0-9]+', '', text).strip()
    
    # Try to parse as JSON first
    try:
        return json.loads(cleaned_text)
    except json.JSONDecodeError:
        pass
    
    # If not JSON, use AI to parse natural language into JSON
    try:
        response = client.chat.completions.create(
            model="asi1-mini",
            messages=[
                {"role": "system", "content": """You are a JSON converter. Convert the user's natural language request into a JSON object with these fields:
- location: (string, required - city name)
- timeframe: (string, optional - e.g., "weekend", "3 days")
- budget: (number, optional - in USD)
- interest_activities: (array of strings, optional - activity types like ["skiing", "hiking"])

If any field is missing, use reasonable defaults. Return ONLY valid JSON."""},
                {"role": "user", "content": cleaned_text},
            ],
            max_tokens=300,
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        # Fallback: return a basic structure
        return {
            "location": "Unknown",
            "timeframe": "weekend",
            "budget": 500,
            "interest_activities": ["sightseeing"]
        }

# ============================================================
# Message Handlers
# ============================================================

@chat_proto.on_message(ChatMessage)
async def handle_scraper_request(ctx: Context, sender: str, msg: ChatMessage):
    """
    Handle incoming activity scraping requests
    Accepts both JSON and natural language input
    """
    ctx.logger.info(f"Scraper received message from {sender}")
    
    # Send acknowledgement
    await ctx.send(
        sender,
        ChatAcknowledgement(timestamp=datetime.utcnow(), acknowledged_msg_id=msg.msg_id),
    )
    
    try:
        for item in msg.content:
            if isinstance(item, TextContent):
                ctx.logger.info(f"Processing scraper request: {item.text}")
                
                try:
                    # Parse text to JSON (handles both JSON and natural language)
                    request_data = parse_text_to_json(item.text)
                    prefs = ActivityPreferences(
                        location=request_data.get("location", ""),
                        timeframe=request_data.get("timeframe", ""),
                        budget=float(request_data.get("budget", 0)),
                        interest_activities=request_data.get("interest_activities", [])
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
                if not prefs.location or not prefs.interest_activities or prefs.budget <= 0:
                    error_response = {
                        "type": "error",
                        "message": "Missing required fields: location, interest_activities, budget (must be > 0)"
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
                
                ctx.logger.info(f"Valid request for {prefs.location} with interests: {prefs.interest_activities}")
                
                # Scrape activities (with fallback to mock data)
                scraped_data = scrape_activities(
                    prefs.location,
                    prefs.timeframe,
                    prefs.budget,
                    prefs.interest_activities
                )
                
                ctx.logger.info(f"Successfully scraped {len(scraped_data.get('activities', []))} activities")
                
                # Analyze budget feasibility
                activities_for_analysis = scraped_data.get("activities", [])
                budget_analysis = analyze_budget_feasibility(
                    prefs.budget,
                    prefs.timeframe,
                    activities_for_analysis
                )
                
                # Format response
                response = format_scraper_response(
                    prefs.location,
                    scraped_data,
                    prefs.budget,
                    budget_analysis
                )
                
                # Convert to JSON-serializable format
                response_json = {
                    "type": "scraper_response",
                    "location": response.location,
                    "total_activities_found": response.total_activities_found,
                    "activities": [
                        {
                            "name": a.name,
                            "category": a.category,
                            "description": a.description,
                            "estimated_cost": a.estimated_cost,
                            "duration": a.duration,
                            "best_time": a.best_time,
                            "difficulty": a.difficulty,
                            "url": a.url
                        }
                        for a in response.activities
                    ],
                    "budget_analysis": response.budget_analysis,
                    "recommendations": response.recommendations
                }
                
                ctx.logger.info(f"Sending response to {sender}")
                
                # Send response
                await ctx.send(
                    sender,
                    ChatMessage(
                        timestamp=datetime.utcnow(),
                        msg_id=uuid4(),
                        content=[TextContent(type="text", text=json.dumps(response_json, indent=2))],
                    ),
                )
                
    except Exception as e:
        ctx.logger.error(f"Scraper error: {e}")
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
    ctx.logger.info(f"Scraper received acknowledgement from {sender}")

# Include chat protocol
agent.include(chat_proto)

if __name__ == "__main__":
    agent.run()
