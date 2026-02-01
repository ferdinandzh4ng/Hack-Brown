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
import re
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
    address: Optional[str] = None
    phone: Optional[str] = None
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
You are an expert travel researcher and activity curator. Your job is to RESEARCH and find REAL, SPECIFIC venues and activities in the given location.

RULE: When the user's prompt says a location (e.g. Providence, Providence RI, Rhode Island, Toronto, New York), all results MUST be based on that location only. Never return venues from a different city.

CRITICAL REQUIREMENTS:
1. You MUST research the actual location and find REAL venues that exist there. Do NOT make up or guess venues.
2. Return SPECIFIC, REAL venues - not generic activities. Examples:
   - For "eat" or "dining": Research actual restaurants in the location like "The Cheesecake Factory", "Olive Garden", local popular restaurants, etc.
   - For "shop": Research actual malls like "Westfield Mall", "The Galleria", specific stores like "Nike Store", "Apple Store", etc.
   - For "sightsee": Research actual landmarks like "Empire State Building", "Golden Gate Bridge", "Times Square", etc.
   - For "adventure": Research actual venues like "Sky Zone Trampoline Park", "Rock Climbing Gym", etc.

3. ALL addresses MUST be REAL, VERIFIABLE addresses in the specified location. Research actual street addresses.
   Format: "Street Number Street Name, City, State ZIP" or "Street Number Street Name, City, Country"
   Example: "350 5th Ave, New York, NY 10118" or "100 Atwells Ave, Providence, RI 02903"
   CRITICAL: Use ONLY the location given in the request. Never substitute a different city (e.g. if the user asks for Providence RI or Rhode Island, do NOT return venues in Toronto or any other city).

4. Descriptions should be 2-3 sentences describing what makes this specific venue unique, what you can do there, and why it's worth visiting.

5. Research popular, well-known venues that are actually in the specified location. Use your knowledge of real places.

For each activity, provide:
1. Name of the SPECIFIC venue/restaurant/mall/landmark (must be a real, specific place that exists in the location)
2. Category (must match or relate to one of the user's interests)
3. Description (2-3 sentences about this specific place - what it offers, atmosphere, specialties)
4. Estimated cost in USD (per person or per activity) - research typical costs
5. Duration (e.g., "2 hours", "half day", "full day")
6. Best time to do it (morning/afternoon/evening/flexible)
7. Difficulty level (easy/moderate/challenging)
8. Address (REQUIRED - must be a real, verifiable address in the location)
9. Phone number (if known - use real format)
10. Website URL (if known - use real URLs)

Return ONLY valid JSON in this format:
{{
  "activities": [
    {{
      "name": "Specific Venue Name (e.g., 'The Cheesecake Factory', 'Westfield Century City', 'Central Park')",
      "category": "activity_type",
      "description": "2-3 sentences describing this specific place - what makes it special, what you can do there, atmosphere, specialties",
      "estimated_cost": 45.00,
      "duration": "2 hours",
      "best_time": "morning",
      "difficulty": "moderate",
      "address": "REAL street address in the REQUESTED location only (e.g., '350 5th Ave, New York, NY 10118' or '100 Atwells Ave, Providence, RI 02903')",
      "phone": "+1-555-123-4567",
      "url": "https://real-website.com"
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

IMPORTANT: 
- RESEARCH the location and find REAL venues that actually exist there
- Generate exactly 4-5 SPECIFIC, REAL venues for EACH interest category provided by the user
- ALL addresses MUST be real, verifiable addresses in the specified location
- Focus on specific restaurants, malls, stores, landmarks, and venues - not generic activity types
- Mix price ranges and difficulty levels across each category
- Ensure variety within each interest type
- If you don't know specific venues in the location, research common/popular venues for that city
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
    Uses AI to research real venues in the location
    """
    interests_str = ", ".join(interest_activities)
    num_interests = len(interest_activities)
    
    prompt = f"""
Location: {location}
Timeframe: {timeframe}
Total Budget: ${budget}
User Interests: {interests_str} ({num_interests} categories)

RESEARCH and find 4-5 SPECIFIC, REAL venues for EACH of these {num_interests} interest categories in {location}.
This should total approximately {num_interests * 4}-{num_interests * 5} activities (about 4-5 per category).

CRITICAL: Use ONLY the location specified above: "{location}". Do NOT use a different city (e.g. do NOT return Toronto venues when the user asked for Providence RI, Rhode Island, or any other location).

CRITICAL REQUIREMENTS:
- RESEARCH the location {location} and find REAL venues that actually exist THERE (in {location} only)
- Return SPECIFIC venues: actual restaurant names, mall names, store names, landmark names - NOT generic activity types
- For "eat" or "dining": Research and return specific restaurants in {location} like popular chains, local favorites, etc.
- For "shop": Research and return specific malls, shopping centers, or stores in {location}
- For "sightsee": Research and return specific landmarks, attractions, parks, museums in {location}
- For "adventure": Research and return specific adventure venues, parks, activities in {location}
- ALL addresses MUST be real, verifiable street addresses in {location}
- Descriptions should be 2-3 sentences about what makes each specific place unique and worth visiting
- Mix price ranges within each category and ensure variety and quality in recommendations
- Use your knowledge to find well-known, popular venues that are actually in {location}
"""
    
    # Retry logic for API calls
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model="asi1-mini",
                messages=[
                    {"role": "system", "content": ACTIVITY_SCRAPER_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=4000,  # Increased to reduce truncation issues
                timeout=60  # Increased timeout for research
            )
            
            response_text = response.choices[0].message.content.strip()
            finish_reason = response.choices[0].finish_reason
            
            # Check if response was truncated
            if finish_reason == "length":
                print(f"Warning: AI response was truncated (finish_reason=length). Attempting to parse partial JSON...")
            
            # Remove markdown code blocks if present
            if response_text.startswith("```"):
                lines = response_text.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                response_text = "\n".join(lines).strip()
            
            # Helper function to extract activities from partial/incomplete JSON
            def extract_activities_from_text(text: str) -> List[Dict]:
                """Extract activity objects from text, even if JSON is incomplete"""
                activities = []
                
                # Try to find all complete activity objects using balanced braces
                start_pos = 0
                while True:
                    # Find next opening brace
                    start_idx = text.find("{", start_pos)
                    if start_idx == -1:
                        break
                    
                    # Find matching closing brace
                    depth = 0
                    in_string = False
                    escape_next = False
                    end_idx = -1
                    
                    for i in range(start_idx, len(text)):
                        char = text[i]
                        
                        if escape_next:
                            escape_next = False
                            continue
                        
                        if char == '\\':
                            escape_next = True
                            continue
                        
                        if char == '"' and not escape_next:
                            in_string = not in_string
                            continue
                        
                        if not in_string:
                            if char == '{':
                                depth += 1
                            elif char == '}':
                                depth -= 1
                                if depth == 0:
                                    end_idx = i
                                    break
                    
                    if end_idx > start_idx:
                        # Found a complete object, try to parse it
                        obj_text = text[start_idx:end_idx + 1]
                        try:
                            obj = json.loads(obj_text)
                            # Check if it looks like an activity (has name, category, etc.)
                            if isinstance(obj, dict) and ("name" in obj or "category" in obj or "estimated_cost" in obj):
                                activities.append(obj)
                        except:
                            pass
                        start_pos = end_idx + 1
                    else:
                        break
                
                return activities
            
            # Try to parse complete JSON first
            scraped_data = None
            try:
                # Find balanced JSON object
                start_idx = response_text.find("{")
                if start_idx != -1:
                    depth = 0
                    in_string = False
                    escape_next = False
                    end_idx = -1
                    
                    for i in range(start_idx, len(response_text)):
                        char = response_text[i]
                        
                        if escape_next:
                            escape_next = False
                            continue
                        
                        if char == '\\':
                            escape_next = True
                            continue
                        
                        if char == '"' and not escape_next:
                            in_string = not in_string
                            continue
                        
                        if not in_string:
                            if char == '{':
                                depth += 1
                            elif char == '}':
                                depth -= 1
                                if depth == 0:
                                    end_idx = i
                                    break
                    
                    if end_idx > start_idx:
                        json_text = response_text[start_idx:end_idx + 1]
                        scraped_data = json.loads(json_text)
            except json.JSONDecodeError:
                pass
            
            # If complete JSON parsing failed, try to extract activities from partial JSON
            if not scraped_data or not scraped_data.get("activities"):
                print("Attempting to extract activities from partial/incomplete JSON...")
                activities = extract_activities_from_text(response_text)
                
                if activities:
                    # Calculate totals
                    total_estimated = sum(a.get("estimated_cost", 0) for a in activities)
                    scraped_data = {
                        "activities": activities,
                        "total_budget_analysis": {
                            "total_available": budget,
                            "total_estimated": total_estimated,
                            "remaining_budget": max(0, budget - total_estimated),
                            "budget_per_day": budget
                        },
                        "recommendations": ["Some activities recovered from truncated response."] if finish_reason == "length" else []
                    }
                else:
                    # Last resort: try regex extraction
                    activities_match = re.search(r'"activities"\s*:\s*(\[[^\]]*(?:\{[^\}]*\}[^\]]*)*\])', response_text, re.DOTALL)
                    if activities_match:
                        try:
                            activities = json.loads(activities_match.group(1))
                            total_estimated = sum(a.get("estimated_cost", 0) for a in activities)
                            scraped_data = {
                                "activities": activities,
                                "total_budget_analysis": {
                                    "total_available": budget,
                                    "total_estimated": total_estimated,
                                    "remaining_budget": max(0, budget - total_estimated),
                                    "budget_per_day": budget
                                },
                                "recommendations": []
                            }
                        except:
                            raise json.JSONDecodeError("Could not parse activities from response", response_text, 0)
                    else:
                        raise json.JSONDecodeError("No valid JSON or activities found", response_text, 0)
            
            # Validate that we got activities
            if not scraped_data.get("activities") or len(scraped_data.get("activities", [])) == 0:
                print(f"Warning: No activities returned from AI, retrying... (attempt {attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    continue
                else:
                    # Last attempt failed, return minimal structure
                    return {
                        "activities": [],
                        "total_budget_analysis": {
                            "total_available": budget,
                            "total_estimated": 0,
                            "remaining_budget": budget,
                            "budget_per_day": budget
                        },
                        "recommendations": ["Unable to find activities. Please try again or provide more specific interests."]
                    }
            
            return scraped_data
            
        except json.JSONDecodeError as e:
            print(f"JSON decode error (attempt {attempt + 1}/{max_retries}): {e}")
            print(f"Response text: {response_text[:500]}...")
            if attempt < max_retries - 1:
                # Add instruction to return only JSON
                prompt += "\n\nIMPORTANT: Return ONLY valid JSON, no additional text or explanations."
                continue
            else:
                # Last attempt failed
                print(f"Failed to parse JSON after {max_retries} attempts")
                return {
                    "activities": [],
                    "total_budget_analysis": {
                        "total_available": budget,
                        "total_estimated": 0,
                        "remaining_budget": budget,
                        "budget_per_day": budget
                    },
                    "recommendations": ["Error parsing activity data. Please try again."]
                }
        
        except Exception as e:
            print(f"Activity scraping error (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                continue
            else:
                # Last attempt failed - return error structure instead of mock data
                print(f"Failed to scrape activities after {max_retries} attempts")
                return {
                    "activities": [],
                    "total_budget_analysis": {
                        "total_available": budget,
                        "total_estimated": 0,
                        "remaining_budget": budget,
                        "budget_per_day": budget
                    },
                    "recommendations": [f"Unable to research activities for {location}. Please try again or check the location name."]
                }
    
    # Should not reach here, but just in case
    return {
        "activities": [],
        "total_budget_analysis": {
            "total_available": budget,
            "total_estimated": 0,
            "remaining_budget": budget,
            "budget_per_day": budget
        },
        "recommendations": ["Unable to retrieve activities. Please try again."]
    }

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
            address=activity_data.get("address"),
            phone=activity_data.get("phone"),
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
    Validates required parameters strictly
    """
    import re
    
    # Remove @agent mentions
    cleaned_text = re.sub(r'@agent[a-zA-Z0-9]+', '', text).strip()
    
    # Try to parse as JSON first
    try:
        data = json.loads(cleaned_text)
        # Validate required fields
        if not data.get("location"):
            raise ValueError("Missing required field: location")
        if not data.get("interest_activities"):
            raise ValueError("Missing required field: interest_activities (must be non-empty list)")
        if not isinstance(data.get("interest_activities"), list) or len(data.get("interest_activities")) == 0:
            raise ValueError("interest_activities must be a non-empty list")
        # Budget should be positive if provided
        if "budget" in data and data["budget"] is not None and data["budget"] <= 0:
            raise ValueError("Budget must be greater than 0")
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
- location: (string, REQUIRED - use the EXACT location from the user's request only, e.g. "Providence, RI" or "Rhode Island" - do NOT substitute a different city like Toronto)
- interest_activities: (array of strings, REQUIRED - must have at least 1 activity like skiing, hiking, dining, sightseeing, adventure)
- budget: (number, optional - in USD, must be > 0 if provided)
- timeframe: (string, optional - e.g., "weekend", "3 days")

STRICT RULES:
1. Location MUST be provided and must be a valid city/place name
2. interest_activities MUST be a non-empty array
3. Budget MUST be positive if provided
4. Return ONLY valid JSON with no other text"""},
                {"role": "user", "content": cleaned_text},
            ],
            max_tokens=300,
        )
        data = json.loads(response.choices[0].message.content)
        
        # Validate the parsed data
        if not data.get("location"):
            raise ValueError("Location not provided or invalid")
        if not data.get("interest_activities") or not isinstance(data.get("interest_activities"), list) or len(data["interest_activities"]) == 0:
            raise ValueError("At least one activity interest is required")
        if "budget" in data and data["budget"] is not None and data["budget"] <= 0:
            raise ValueError("Budget must be greater than 0")
            
        return data
    except (json.JSONDecodeError, ValueError) as e:
        raise ValueError(f"Failed to parse request. Required fields: location, interest_activities. Error: {str(e)}")

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
    
    # NOTE: Not sending ChatAcknowledgement to avoid interfering with ctx.send_and_receive
    # The orchestrator uses send_and_receive which can match acknowledgements instead of actual responses
    
    try:
        for item in msg.content:
            if isinstance(item, TextContent):
                ctx.logger.info(f"Processing scraper request: {item.text}")
                
                try:
                    # Parse text to JSON (handles both JSON and natural language)
                    request_data = parse_text_to_json(item.text)
                    # Limit interests to maximum of 3
                    interest_activities = request_data.get("interest_activities", [])
                    if len(interest_activities) > 3:
                        interest_activities = interest_activities[:3]
                        ctx.logger.info(f"Limited interests to first 3: {interest_activities}")
                    prefs = ActivityPreferences(
                        location=request_data.get("location", ""),
                        timeframe=request_data.get("timeframe", ""),
                        budget=float(request_data.get("budget", 0)),
                        interest_activities=interest_activities
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
                
                # Scrape activities using AI
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
                
                # Convert to JSON-serializable format - include description as requested
                response_json = {
                    "activities": [
                        {
                            "name": a.name,
                            "description": a.description,
                            "address": a.address,
                            "phone": a.phone,
                            "url": a.url,
                            "category": a.category,
                            "estimated_cost": a.estimated_cost
                        }
                        for a in response.activities
                    ]
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
