#!/usr/bin/env python3
"""
Gemini AI Fallback - Complete schedule generation using Google Gemini AI

This is a fallback mechanism that uses Gemini AI to generate a complete schedule
with events, transit, and activities when the agent system is unavailable.

It takes the same input format as the orchestrator and returns the same output format
as the budget filter agent, ensuring compatibility.
"""

import json
import os
import sys
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

# Add Agents directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from Login import LoginManager
    LOGIN_MANAGER_AVAILABLE = True
except ImportError:
    LOGIN_MANAGER_AVAILABLE = False
    print("Warning: LoginManager not available. User preferences will not be used.")

try:
    import pytz
    PYTZ_AVAILABLE = True
except ImportError:
    PYTZ_AVAILABLE = False
    print("Warning: pytz not installed. Install with: pip install pytz for better timezone support")

try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    print("Warning: google.generativeai not installed. Install with: pip install google-generativeai")

load_dotenv()

# Gemini API configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY and GEMINI_AVAILABLE:
    print("Warning: GEMINI_API_KEY not found in environment variables")

def is_vague_request(user_request: Optional[str]) -> bool:
    """
    Check if user request is vague (like "Plan me a day", "Plan a trip", etc.)
    """
    if not user_request:
        return False
    
    vague_phrases = [
        "plan me a day",
        "plan a day",
        "plan me a trip",
        "plan a trip",
        "plan something",
        "plan activities",
        "what should i do",
        "what to do",
        "suggest something",
        "give me ideas",
        "help me plan",
        "create a plan",
        "make a plan"
    ]
    
    user_request_lower = user_request.lower().strip()
    
    # Check if request is very short (less than 20 chars) or matches vague phrases
    if len(user_request_lower) < 20:
        return True
    
    for phrase in vague_phrases:
        if phrase in user_request_lower:
            return True
    
    return False

def get_user_preferences(user_id: Optional[str]) -> Optional[Dict]:
    """
    Get user preferences from database if user_id is provided
    """
    if not user_id or not LOGIN_MANAGER_AVAILABLE:
        return None
    
    try:
        login_manager = LoginManager()
        user_profile = login_manager.get_user_profile(user_id)
        
        if user_profile and user_profile.get("preferences"):
            return user_profile.get("preferences")
    except Exception as e:
        print(f"Error fetching user preferences: {e}")
    
    return None

# COMMENTED OUT: Gemini fallback disabled
def generate_schedule_with_gemini(
    location: str,
    budget: float,
    interest_activities: List[str],
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    user_request: Optional[str] = None,
    user_id: Optional[str] = None
) -> Dict[str, Any]:
    """Gemini fallback - DISABLED"""
    return {
        "error": "Gemini fallback is disabled.",
        "fallback_attempted": False
    }
    
# ORIGINAL FUNCTION COMMENTED OUT:
"""
def generate_schedule_with_gemini_ORIGINAL(
    location: str,
    budget: float,
    interest_activities: List[str],
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    user_request: Optional[str] = None,
    user_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Generate a complete schedule using Gemini AI.
    
    Args:
        location: City/location name
        budget: Total budget in dollars
        interest_activities: List of activity interests (e.g., ["sightseeing", "dining", "entertainment"])
        start_time: ISO 8601 datetime string for start (optional)
        end_time: ISO 8601 datetime string for end (optional)
        user_request: Original user request text (optional)
    
    Returns:
        Dict in the same format as budget filter agent output
    """
    if not GEMINI_AVAILABLE:
        return {
            "error": "Gemini AI library not available. Install with: pip install google-generativeai"
        }
    
    if not GEMINI_API_KEY:
        return {
            "error": "GEMINI_API_KEY not configured. Set it in your .env file."
        }
    
    try:
        # Configure Gemini using the standard API
        genai.configure(api_key=GEMINI_API_KEY)
        
        # List available models first to see what's actually available
        available_models = []
        try:
            for m in genai.list_models():
                # Only include models that support generateContent
                if 'generateContent' in m.supported_generation_methods:
                    available_models.append(m.name)
            if available_models:
                print(f"Found {len(available_models)} available models. First few: {available_models[:3]}")
        except Exception as e:
            print(f"Could not list models: {e}")
        
        # Try to find a working model - prioritize models that support generateContent
        model = None
        model_name = None
        
        # First, try models from the available list - prioritize Gemini Flash models (better free tier limits)
        if available_models:
            # Filter and prioritize Gemini models (not Gemma)
            gemini_models = [m for m in available_models if 'gemini' in m.lower() and 'gemma' not in m.lower()]
            other_models = [m for m in available_models if m not in gemini_models]
            
            # Prioritize Flash models first (better free tier quotas), then Pro models
            flash_models = [m for m in gemini_models if 'flash' in m.lower()]
            pro_models = [m for m in gemini_models if 'pro' in m.lower() and m not in flash_models]
            other_gemini = [m for m in gemini_models if m not in flash_models and m not in pro_models]
            
            # Sort each group by name length (shorter = usually better/newer)
            prioritized_models = (
                sorted(flash_models, key=lambda x: len(x)) +
                sorted(pro_models, key=lambda x: len(x)) +
                sorted(other_gemini, key=lambda x: len(x)) +
                sorted(other_models, key=lambda x: len(x))
            )
            
            for avail_model in prioritized_models:
                try:
                    # Use just the model name part (after last /)
                    model_short = avail_model.split('/')[-1]
                    model = genai.GenerativeModel(model_short)
                    model_name = model_short
                    print(f"Successfully initialized model: {model_short} (from {avail_model})")
                    break
                except Exception as e:
                    # Try with full path
                    try:
                        model = genai.GenerativeModel(avail_model)
                        model_name = avail_model
                        print(f"Successfully initialized model: {avail_model}")
                        break
                    except Exception as e2:
                        print(f"Failed to initialize {avail_model}: {str(e2)[:100]}")
                        continue
        
        # Fallback: try the most common model name
        if model is None:
            try:
                model = genai.GenerativeModel('gemini-pro')
                model_name = 'gemini-pro'
                print("Successfully initialized model: gemini-pro (fallback)")
            except Exception as e:
                return {
                    "error": f"Could not initialize any Gemini model. Available models: {', '.join(available_models[:10]) if available_models else 'unknown (could not list)'}. Error: {str(e)}"
                }
        
        # Parse times if provided - keep everything in UTC to avoid timezone issues
        start_dt = None
        end_dt = None
        
        if start_time:
            try:
                start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                # Ensure UTC timezone
                if start_dt.tzinfo is None:
                    start_dt = start_dt.replace(tzinfo=timezone.utc)
                else:
                    # Convert to UTC if not already
                    start_dt = start_dt.astimezone(timezone.utc)
            except Exception as e:
                print(f"Warning: Could not parse start_time: {e}")
                pass
        if end_time:
            try:
                end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
                # Ensure UTC timezone
                if end_dt.tzinfo is None:
                    end_dt = end_dt.replace(tzinfo=timezone.utc)
                else:
                    # Convert to UTC if not already
                    end_dt = end_dt.astimezone(timezone.utc)
            except Exception as e:
                print(f"Warning: Could not parse end_time: {e}")
                pass
        
        # Calculate duration
        duration_hours = None
        if start_dt and end_dt:
            duration_hours = (end_dt - start_dt).total_seconds() / 3600
        elif start_dt:
            # Default to 8 hours if only start time provided
            duration_hours = 8
        else:
            # Default to full day
            duration_hours = 12
        
        # Check if request is vague and fetch user preferences if needed
        preferences_context = ""
        if is_vague_request(user_request) and user_id:
            user_prefs = get_user_preferences(user_id)
            if user_prefs:
                # Extract activity categories and favorite stores
                activity_categories = user_prefs.get("activity_categories", [])
                favorite_stores = user_prefs.get("favorite_stores", [])
                
                if activity_categories or favorite_stores:
                    prefs_list = []
                    if activity_categories:
                        prefs_list.append(f"Activity interests: {', '.join(activity_categories)}")
                    if favorite_stores:
                        prefs_list.append(f"Favorite stores/brands: {', '.join(favorite_stores)}")
                    
                    preferences_context = f"\n\nIMPORTANT - User Preferences (use these to create specific activities):\n" + "\n".join(prefs_list) + "\n\nWhen creating the schedule, be SPECIFIC and use these preferences to generate concrete activities. For example:\n"
                    if activity_categories:
                        preferences_context += "- If user likes 'dining', include specific restaurants in " + location + "\n"
                        preferences_context += "- If user likes 'sightseeing', include specific landmarks, museums, or attractions in " + location + "\n"
                        preferences_context += "- If user likes 'entertainment', include specific shows, events, or venues in " + location + "\n"
                    if favorite_stores:
                        preferences_context += "- Include visits to: " + ", ".join(favorite_stores) + " if available in " + location + "\n"
                    preferences_context += "\nDo NOT use generic activity names. Use specific venue names, restaurant names, attraction names, etc. based on the user's preferences.\n"
        
        # Build prompt for Gemini - all times in UTC
        activities_str = ", ".join(interest_activities)
        time_info = ""
        
        if start_dt and end_dt:
            # Format times in UTC
            start_str = start_dt.strftime('%Y-%m-%d %H:%M UTC')
            end_str = end_dt.strftime('%Y-%m-%d %H:%M UTC')
            time_info = f" from {start_str} to {end_str}"
        elif start_dt:
            start_str = start_dt.strftime('%Y-%m-%d %H:%M UTC')
            time_info = f" starting at {start_str}"
        
        prompt = f"""You are a travel planning assistant. Create a detailed schedule for a trip to {location} with a budget of ${budget:.2f}.

RULE: When the user's prompt says a location (e.g. Providence, Providence RI, Rhode Island, Toronto), all results MUST be based on that location only. Use ONLY "{location}" here. All venues and addresses MUST be in this location. Never substitute a different city.

User interests: {activities_str}
Duration: approximately {duration_hours:.1f} hours{time_info}{preferences_context}

Generate a complete schedule with:
1. Multiple activities/venues that match the user's interests
2. Transit between locations (walking, public transit, taxi/ride-share)
3. Realistic costs for each activity
4. Realistic transit costs
5. Start and end times for each activity
6. Addresses, descriptions, and other details

Return ONLY a valid JSON object in this exact format:
{{
  "location": "{location}",
  "budget": {budget},
  "interest_activities": {json.dumps(interest_activities)},
  "activities": {{
    "Activity 1": {{
      "venue": "Name of venue/activity",
      "type": "venue" or "transit",
      "category": "sightseeing" or "dining" or "entertainment" etc,
      "start_time": "ISO 8601 datetime string",
      "end_time": "ISO 8601 datetime string",
      "duration_minutes": 60,
      "cost": 25.50,
      "description": "Brief description",
      "address": "Full address",
      "phone": "Phone number if available",
      "url": "Website URL if available",
      "method": "walking" or "transit" or "taxi" (only for transit type)
    }},
    "Activity 2": {{...}},
    ...
  }},
  "total_cost": 0.00,
  "remaining_budget": 0.00,
  "summary": {{
    "total_activities": 0,
    "total_cost": 0.00,
    "remaining_budget": 0.00
  }}
}}

Requirements:
- CRITICAL: Include transit activities between venues (type: "transit") - these are separate activities
- Total cost must be under the budget
- Activities should be scheduled in chronological order
- Include realistic addresses and details for {location}
- Mix of activities matching: {activities_str}
- CRITICAL: Ensure start_time and end_time are valid ISO 8601 format in UTC (e.g., "2026-02-01T10:00:00.000Z")
- CRITICAL: All times must be in UTC timezone (Z suffix)
- For transit activities, include "method" field (walking, transit, taxi, etc.)
- For venue activities, type should be "venue", not the category name
- Make costs realistic for {location}
- Transit activities should have realistic costs (walking: $0, transit: $2-5, taxi: $10-30)
- Each venue activity should be followed by a transit activity to the next venue (except the last one)

Generate the schedule now:"""

        # Call Gemini API with retry logic for quota errors
        max_retries = 3
        retry_delay = 1  # Start with 1 second
        
        for attempt in range(max_retries):
            try:
                response = model.generate_content(prompt)
                break  # Success, exit retry loop
            except Exception as e:
                error_str = str(e)
                # Check if it's a quota error (429)
                if "429" in error_str or "quota" in error_str.lower() or "rate limit" in error_str.lower():
                    if attempt < max_retries - 1:
                        # Extract retry delay from error if available
                        if "retry in" in error_str.lower():
                            try:
                                import re
                                delay_match = re.search(r'retry in ([\d.]+)s', error_str.lower())
                                if delay_match:
                                    retry_delay = float(delay_match.group(1)) + 1  # Add 1 second buffer
                            except:
                                pass
                        
                        print(f"Quota/rate limit hit. Waiting {retry_delay:.1f}s before retry {attempt + 1}/{max_retries}...")
                        import time
                        time.sleep(retry_delay)
                        retry_delay *= 2  # Exponential backoff
                        continue
                    else:
                        # Last attempt failed
                        raise Exception(f"Quota exceeded after {max_retries} retries. Error: {error_str}")
                else:
                    # Not a quota error, raise immediately
                    raise
        
        # Extract text from response
        if hasattr(response, 'text'):
            response_text = response.text.strip()
        elif hasattr(response, 'candidates') and response.candidates:
            # Fallback extraction method
            response_text = response.candidates[0].content.parts[0].text.strip()
        else:
            response_text = str(response).strip()
        
        # Try to extract JSON if it's wrapped in markdown code blocks
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0].strip()
        
        # Parse JSON
        try:
            schedule_data = json.loads(response_text)
        except json.JSONDecodeError as e:
            # Try to find JSON object in the response
            import re
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                schedule_data = json.loads(json_match.group())
            else:
                return {
                    "error": f"Failed to parse Gemini response as JSON: {str(e)}",
                    "raw_response": response_text[:500]
                }
        
        # Validate and fix the structure
        if "activities" not in schedule_data:
            return {
                "error": "Gemini response missing 'activities' field",
                "raw_response": response_text[:500]
            }
        
        # Fix and validate activities
        activities = schedule_data.get("activities", {})
        fixed_activities = {}
        total_cost = 0.0
        activity_count = 0
        
        for key, activity in activities.items():
            if isinstance(activity, dict):
                activity_count += 1
                
                # Fix type field - should be "venue" or "transit", not category
                if activity.get("type") not in ["venue", "transit"]:
                    # If it's a category name, change to "venue"
                    if activity.get("type") in ["sightseeing", "dining", "entertainment", "eat", "transit"]:
                        if activity.get("type") == "transit":
                            activity["type"] = "transit"
                        else:
                            activity["type"] = "venue"
                    else:
                        activity["type"] = "venue"
                
                # Fix timestamp format to ISO 8601 and ensure UTC
                for time_field in ["start_time", "end_time"]:
                    if time_field in activity and activity[time_field]:
                        time_str = str(activity[time_field])
                        # If it's not already ISO 8601 format, try to convert it
                        if "T" not in time_str or "Z" not in time_str:
                            try:
                                dt = None
                                # Try parsing common formats
                                if " " in time_str and "T" not in time_str:
                                    # Format like "2026-02-01 10:00" or "2026-02-01 10:00 EST"
                                    time_str_clean = time_str.split()[0] + " " + time_str.split()[1] if len(time_str.split()) >= 2 else time_str
                                    try:
                                        dt = datetime.strptime(time_str_clean, "%Y-%m-%d %H:%M")
                                    except:
                                        dt = datetime.strptime(time_str_clean, "%Y-%m-%d %H:%M:%S")
                                    
                                    # Keep everything in UTC - no timezone conversion
                                    if dt and dt.tzinfo is None:
                                        # Naive datetime - assume UTC
                                        dt = dt.replace(tzinfo=timezone.utc)
                                    elif dt and dt.tzinfo:
                                        # Already has timezone - convert to UTC
                                        dt = dt.astimezone(timezone.utc)
                                else:
                                    # Try ISO format
                                    dt = datetime.fromisoformat(time_str.replace('Z', '+00:00'))
                                
                                # Ensure UTC and convert to ISO 8601 format
                                if dt:
                                    if dt.tzinfo is None:
                                        dt_utc = dt.replace(tzinfo=timezone.utc)
                                    else:
                                        dt_utc = dt.astimezone(timezone.utc)
                                    # Convert to ISO 8601 with Z
                                    activity[time_field] = dt_utc.strftime("%Y-%m-%dT%H:%M:%S.000Z")
                                else:
                                    continue
                            except Exception as e:
                                # If parsing fails, keep original
                                print(f"Warning: Could not parse time {time_str}: {e}")
                                pass
                
                # Ensure transit activities have method field
                if activity.get("type") == "transit" and "method" not in activity:
                    activity["method"] = "walking"  # Default
                
                # Calculate cost
                cost = activity.get("cost", 0)
                if isinstance(cost, (int, float)):
                    total_cost += float(cost)
                
                fixed_activities[key] = activity
        
        schedule_data["activities"] = fixed_activities
        
        # Update totals
        schedule_data["total_cost"] = round(total_cost, 2)
        schedule_data["remaining_budget"] = round(budget - total_cost, 2)
        
        if "summary" not in schedule_data:
            schedule_data["summary"] = {}
        schedule_data["summary"]["total_activities"] = activity_count
        schedule_data["summary"]["total_cost"] = round(total_cost, 2)
        schedule_data["summary"]["remaining_budget"] = round(budget - total_cost, 2)
        
        # Ensure location and budget are set
        schedule_data["location"] = location
        schedule_data["budget"] = budget
        if "interest_activities" not in schedule_data:
            schedule_data["interest_activities"] = interest_activities
        
        return schedule_data
        
    except Exception as e:
        import traceback
        return {
            "error": f"Error generating schedule with Gemini: {str(e)}",
            "traceback": traceback.format_exc()
        }


def get_timezone_for_location(location: str):
    """
    Get timezone for a given location.
    Returns pytz timezone object or None if not available.
    """
    if not PYTZ_AVAILABLE:
        return None
    
    # Common city to timezone mappings
    location_lower = location.lower()
    timezone_map = {
        # US Cities
        "new york": "America/New_York",
        "nyc": "America/New_York",
        "los angeles": "America/Los_Angeles",
        "la": "America/Los_Angeles",
        "chicago": "America/Chicago",
        "san francisco": "America/Los_Angeles",
        "boston": "America/New_York",
        "providence": "America/New_York",
        "rhode island": "America/New_York",
        "miami": "America/New_York",
        "seattle": "America/Los_Angeles",
        "denver": "America/Denver",
        "houston": "America/Chicago",
        "philadelphia": "America/New_York",
        "phoenix": "America/Phoenix",
        "atlanta": "America/New_York",
        "dallas": "America/Chicago",
        "detroit": "America/New_York",
        "minneapolis": "America/Chicago",
        "portland": "America/Los_Angeles",
        "san diego": "America/Los_Angeles",
        "washington": "America/New_York",
        "dc": "America/New_York",
        
        # International Cities
        "london": "Europe/London",
        "paris": "Europe/Paris",
        "tokyo": "Asia/Tokyo",
        "sydney": "Australia/Sydney",
        "toronto": "America/Toronto",
        "vancouver": "America/Vancouver",
        "mexico city": "America/Mexico_City",
        "rio de janeiro": "America/Sao_Paulo",
        "buenos aires": "America/Argentina/Buenos_Aires",
        "berlin": "Europe/Berlin",
        "rome": "Europe/Rome",
        "madrid": "Europe/Madrid",
        "amsterdam": "Europe/Amsterdam",
        "dublin": "Europe/Dublin",
        "moscow": "Europe/Moscow",
        "dubai": "Asia/Dubai",
        "singapore": "Asia/Singapore",
        "hong kong": "Asia/Hong_Kong",
        "beijing": "Asia/Shanghai",
        "shanghai": "Asia/Shanghai",
        "seoul": "Asia/Seoul",
        "bangkok": "Asia/Bangkok",
        "mumbai": "Asia/Kolkata",
        "delhi": "Asia/Kolkata",
        "cairo": "Africa/Cairo",
        "johannesburg": "Africa/Johannesburg",
    }
    
    # Check for exact matches or partial matches
    for city, tz_name in timezone_map.items():
        if city in location_lower:
            try:
                return pytz.timezone(tz_name)
            except:
                pass
    
    # Default to UTC if no match found
    return pytz.UTC

def generate_schedule_simple(
    location: str,
    budget: float,
    interest_activities: List[str],
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    user_request: Optional[str] = None,
    user_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Simplified version that can be used as a direct replacement.
    Same interface as generate_schedule_with_gemini.
    """
    return generate_schedule_with_gemini(
        location=location,
        budget=budget,
        interest_activities=interest_activities,
        start_time=start_time,
        end_time=end_time,
        user_request=user_request,
        user_id=user_id
    )


# Example usage
if __name__ == "__main__":
    # Test the fallback
    result = generate_schedule_with_gemini(
        location="New York City",
        budget=500.0,
        interest_activities=["sightseeing", "dining", "entertainment"],
        start_time="2026-02-01T09:00:00.000Z",
        end_time="2026-02-01T20:00:00.000Z"
    )
    
    if "error" in result:
        print(f"Error: {result['error']}")
    else:
        print(json.dumps(result, indent=2))
        print(f"\nGenerated {result['summary']['total_activities']} activities")
        print(f"Total cost: ${result['total_cost']:.2f}")
        print(f"Remaining budget: ${result['remaining_budget']:.2f}")

