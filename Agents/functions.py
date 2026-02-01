from uagents import Model
from typing import Optional, List, Dict
import json
import os
import re
from dotenv import load_dotenv
from pymongo import MongoClient
from openai import OpenAI

load_dotenv()

# ------------------------------------------------------------
# Models
# ------------------------------------------------------------

class IntentRequest(Model):
    """Request model for intent dispatch"""
    user_request: str
    location: Optional[str] = None
    budget: Optional[float] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    preferences: Optional[List[str]] = None

class IntentResponse(Model):
    """Response model for intent dispatch"""
    activity_list: List[str]
    constraints: Dict
    agents_to_call: List[str]
    notes: str

# ------------------------------------------------------------
# OpenAI Client
# ------------------------------------------------------------

client = OpenAI(
    base_url="https://api.asi1.ai/v1",
    api_key=os.getenv("FETCH_API_KEY", ""),
)

# ------------------------------------------------------------
# MongoDB Connection
# ------------------------------------------------------------

def get_mongodb_client():
    """Get MongoDB client connection"""
    mongodb_connection_string = os.getenv("MONGODB_CONNECTION_STRING")
    
    if mongodb_connection_string:
        connection_string = mongodb_connection_string
        try:
            if "/" in connection_string and "?" in connection_string:
                db_part = connection_string.split("/")[-1].split("?")[0]
            elif "/" in connection_string:
                db_part = connection_string.split("/")[-1]
            else:
                db_part = os.getenv("MONGODB_DATABASE", "HackBrown")
        except:
            db_part = os.getenv("MONGODB_DATABASE", "HackBrown")
    else:
        mongodb_username = os.getenv("MONGODB_USERNAME")
        mongodb_password = os.getenv("MONGODB_PASSWORD")
        mongodb_cluster = os.getenv("MONGODB_CLUSTER")
        mongodb_database = os.getenv("MONGODB_DATABASE", "HackBrown")
        
        if not all([mongodb_username, mongodb_password, mongodb_cluster]):
            print("MongoDB connection error: Missing required environment variables")
            return None, None
        
        if ".mongodb.net" in mongodb_cluster:
            cluster_host = mongodb_cluster
        elif "." in mongodb_cluster and not mongodb_cluster.endswith(".net"):
            cluster_host = f"{mongodb_cluster}.mongodb.net"
        else:
            cluster_lower = mongodb_cluster.lower().replace(" ", "-")
            cluster_host = f"{cluster_lower}.mongodb.net"
        
        connection_string = f"mongodb+srv://{mongodb_username}:{mongodb_password}@{cluster_host}/{mongodb_database}?retryWrites=true&w=majority"
        db_part = mongodb_database
    
    try:
        client_mongo = MongoClient(connection_string, serverSelectionTimeoutMS=10000)
        client_mongo.admin.command('ping')
        print(f"Successfully connected to MongoDB: {db_part}")
        return client_mongo, db_part
    except Exception as e:
        print(f"MongoDB connection error: {e}")
        return None, None

mongodb_client, mongodb_db_name = get_mongodb_client()

# ------------------------------------------------------------
# System Prompts
# ------------------------------------------------------------

VAGUENESS_CHECK_PROMPT = """
Analyze the following user request and determine if it's too vague to create a specific activity plan.

A request is considered vague if:
- It only mentions a location without specific activities (e.g., "Plan me a day in New York", "I want to visit Paris")
- It lacks clear preferences or interests
- It's too general and doesn't specify what types of activities the user wants
- It asks for a "day plan" or "itinerary" without specifying activities

A request is NOT vague if:
- It mentions specific activities (e.g., "I want to visit the Eiffel Tower and eat at a French restaurant")
- It includes clear preferences (e.g., "I like museums and art galleries")
- It specifies activity types (e.g., "I want to go shopping and sightseeing")

IMPORTANT: If the request only mentions a location and asks for a plan/itinerary without specific activities, it IS vague.

Return ONLY valid JSON:
{
  "is_vague": true or false,
  "location": "extracted location or null",
  "reason": "brief explanation"
}
"""

RESEARCH_PROMPT = """
Research popular general things to do in {location}. 
Return a JSON object with general activity categories and popular examples:

{
  "general_categories": [
    {
      "category": "eat",
      "description": "Dining and food experiences",
      "examples": ["local cuisine", "fine dining", "street food", "cafes"]
    },
    {
      "category": "shop",
      "description": "Shopping and markets",
      "examples": ["local markets", "boutiques", "souvenirs", "malls"]
    },
    {
      "category": "sightsee",
      "description": "Sightseeing and landmarks",
      "examples": ["monuments", "museums", "parks", "historic sites"]
    }
  ]
}

Include 4-6 relevant categories based on what's popular in {location}.
"""

FINALIZE_PROMPT = """
Based on the user's original request and their selected activity preferences, create a finalized activity list.

Original request: {original_request}
User selected preferences: {user_preferences}
Location: {location}
Budget: {budget}
Start time: {start_time}
End time: {end_time}
{transaction_context}

Return ONLY valid JSON in this format:

{{
  "activity_list": [
    "eat",
    "sightsee",
    "shop",
    ...
  ],
  "constraints": {{
    "budget": number or null,
    "start_time": "ISO 8601 datetime string or null",
    "end_time": "ISO 8601 datetime string or null",
    "location": "...",
    "preferences": [ ... ]
  }},
  "agents_to_call": [ ... ],
  "notes": "short explanation"
}}

CRITICAL REQUIREMENTS:
1. The activity_list MUST contain at least one activity category. It CANNOT be empty.
2. The activity_list should contain GENERAL activity categories (like "eat", "sightsee", "shop", "entertainment", "relax", "outdoor", "cultural", etc.) 
3. NOT specific activities. Use simple, one-word category names based on the user's preferences.
4. If user preferences mention "eat" or "dining" or "food", include "eat" in activity_list.
5. If user preferences mention "sightsee" or "sightseeing" or "landmarks", include "sightsee" in activity_list.
6. If user preferences mention "shop" or "shopping" or "markets", include "shop" in activity_list.
7. Extract ALL relevant categories from the user preferences - do not leave the activity_list empty.

{transaction_context}
"""

DISPATCHER_SYSTEM_PROMPT = """
You are the Intent Dispatcher Agent for AgentCity.

Your job:
- Parse the user's request into a structured mission.
- Extract constraints: budget, time, location, preferences.
- Decide which specialist agents should be called.

Available specialist agents:
- budget_agent
- venue_agent
- activity_agent
- transit_agent
- safety_agent
- schedule_agent
- booking_agent
- validation_agent

Return ONLY valid JSON in this format:

{
  "activity_list": [ "eat", "sightsee", "shop", ... ],
  "constraints": {
    "budget": number or null,
    "start_time": "ISO 8601 datetime string or null",
    "end_time": "ISO 8601 datetime string or null",
    "location": "...",
    "preferences": [ ... ]
  },
  "agents_to_call": [ ... ],
  "notes": "short explanation"
}

IMPORTANT: The activity_list should contain GENERAL activity categories (like "eat", "sightsee", "shop", "entertainment", "relax", "outdoor", "cultural", etc.) 
NOT specific activities. Use simple, one-word category names.

Do NOT include any extra text outside JSON.
"""

# ------------------------------------------------------------
# MongoDB Helper Functions
# ------------------------------------------------------------

def get_user_transactions(user_id: str, limit: int = 50) -> List[Dict]:
    """Get user's past transactions from MongoDB"""
    if not mongodb_client or not mongodb_db_name:
        return []
    
    try:
        db = mongodb_client[mongodb_db_name]
        collection = db.get_collection("transactions")
        
        transactions = list(collection.find(
            {"user_id": user_id},
            sort=[("timestamp", -1)],
            limit=limit
        ))
        
        return transactions
    except Exception as e:
        print(f"Error fetching transactions: {e}")
        return []

def analyze_transaction_preferences(transactions: List[Dict], location: str) -> Optional[Dict]:
    """Analyze user transactions to infer activity preferences"""
    if not transactions or len(transactions) < 3:
        return None
    
    try:
        transaction_summary = []
        for txn in transactions[:20]:
            txn_data = {
                "activity": txn.get("activity", txn.get("name", "")),
                "category": txn.get("category", txn.get("type", "")),
                "amount": txn.get("amount", 0),
                "location": txn.get("location", ""),
            }
            transaction_summary.append(txn_data)
        
        analysis_prompt = f"""
Analyze the following user transaction history and infer their activity preferences for a trip to {location}.

Transactions:
{json.dumps(transaction_summary, indent=2)}

Return ONLY valid JSON:
{{
  "has_sufficient_data": true or false,
  "inferred_preferences": ["preference1", "preference2", ...],
  "activity_categories": ["category1", "category2", ...],
  "confidence": "high/medium/low",
  "notes": "brief explanation"
}}

Consider has_sufficient_data true if you can identify clear patterns (at least 3 similar activities/categories).
"""
        
        response = client.chat.completions.create(
            model="asi1-mini",
            messages=[
                {"role": "system", "content": "You are an expert at analyzing user behavior patterns from transaction data."},
                {"role": "user", "content": analysis_prompt},
            ],
            max_tokens=400,
        )
        
        result = safe_json_parse(response.choices[0].message.content)
        return result
        
    except Exception as e:
        print(f"Error analyzing transactions: {e}")
        return None

# ------------------------------------------------------------
# Intent Dispatch Functions
# ------------------------------------------------------------

def safe_json_parse(text: str) -> dict:
    """Safely parse JSON from AI response, handling markdown code blocks and extra whitespace"""
    if not text:
        return {}
    
    # Remove markdown code blocks if present
    text = text.strip()
    if text.startswith("```"):
        # Remove opening ```json or ```
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        # Remove closing ```
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    
    # Try to find JSON object in the text
    text = text.strip()
    
    # Check if text is just a fragment (starts with a key name but no opening brace)
    # This handles cases like '\n  "activity_list"' where response was cut off
    if not text.startswith("{") and not text.startswith("["):
        # Check if it looks like a partial JSON key
        if text.strip().startswith('"') and ':' not in text[:50]:
            print(f"Warning: Received incomplete JSON response (likely truncated): {text[:100]}...")
            # If it mentions activity_list, return a minimal structure
            if '"activity_list"' in text:
                return {
                    "activity_list": [],
                    "constraints": {},
                    "agents_to_call": [],
                    "notes": "Incomplete response - please try again"
                }
            return {}
    
    # Find the first { and last }
    start_idx = text.find("{")
    end_idx = text.rfind("}")
    
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        text = text[start_idx:end_idx + 1]
    elif start_idx == -1:
        # No opening brace found - might be a fragment
        # Check if it's just a partial JSON structure
        if '"general_categories"' in text:
            # Try to extract the array
            array_match = re.search(r'(\[[^\]]*(?:\{[^\}]*\}[^\]]*)*\])', text, re.DOTALL)
            if array_match:
                try:
                    return {"general_categories": json.loads(array_match.group(1))}
                except:
                    pass
            return {"general_categories": []}
        # Check for activity_list fragment
        if '"activity_list"' in text:
            # Try to extract activity_list array
            array_match = re.search(r'"activity_list"\s*:\s*(\[[^\]]*\])', text, re.DOTALL)
            if array_match:
                try:
                    activities = json.loads(array_match.group(1))
                    return {
                        "activity_list": activities,
                        "constraints": {},
                        "agents_to_call": [],
                        "notes": "Partial response - some fields may be missing"
                    }
                except:
                    pass
        return {}
    
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError) as e:
        # If parsing fails, try to extract just the JSON part
        # Use a more robust approach: find balanced braces
        def find_balanced_json(text, start_pos=0):
            """Find a complete JSON object starting from start_pos"""
            if start_pos >= len(text) or text[start_pos] != '{':
                return None
            
            depth = 0
            in_string = False
            escape_next = False
            start = start_pos
            
            for i in range(start_pos, len(text)):
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
                            return text[start:i+1]
            
            return None
        
        # Try to find a complete JSON object
        json_text = find_balanced_json(text)
        if json_text:
            try:
                return json.loads(json_text)
            except:
                pass
        
        # Fallback: try simpler regex pattern
        json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group())
            except:
                pass
        
        # Try to fix common issues: incomplete JSON, trailing commas, etc.
        # If we see a partial JSON structure, try to extract what we can
        
        # Handle activity_list responses (for finalize_activity_list)
        if '"activity_list"' in text:
            result = {}
            # Extract activity_list array
            activity_match = re.search(r'"activity_list"\s*:\s*(\[[^\]]*(?:\{[^\}]*\}[^\]]*)*\])', text, re.DOTALL)
            if activity_match:
                try:
                    result["activity_list"] = json.loads(activity_match.group(1))
                except:
                    result["activity_list"] = []
            else:
                result["activity_list"] = []
            
            # Extract constraints object
            constraints_match = re.search(r'"constraints"\s*:\s*(\{[^\}]*\})', text, re.DOTALL)
            if constraints_match:
                try:
                    result["constraints"] = json.loads(constraints_match.group(1))
                except:
                    result["constraints"] = {}
            else:
                result["constraints"] = {}
            
            # Extract agents_to_call array
            agents_match = re.search(r'"agents_to_call"\s*:\s*(\[[^\]]*\])', text, re.DOTALL)
            if agents_match:
                try:
                    result["agents_to_call"] = json.loads(agents_match.group(1))
                except:
                    result["agents_to_call"] = []
            else:
                result["agents_to_call"] = []
            
            # Extract notes
            notes_match = re.search(r'"notes"\s*:\s*"([^"]*)"', text)
            if notes_match:
                result["notes"] = notes_match.group(1)
            else:
                result["notes"] = "Partial response - some fields may be missing"
            
            if result.get("activity_list"):
                return result
        
        if '"general_categories"' in text:
            # Try to find the array or object containing general_categories
            # More flexible pattern to match nested structures
            match = re.search(r'"general_categories"\s*:\s*(\[[^\]]*(?:\{[^\}]*\}[^\]]*)*\])', text, re.DOTALL)
            if match:
                try:
                    return {"general_categories": json.loads(match.group(1))}
                except:
                    pass
            # If that fails, return empty structure
            return {"general_categories": []}
        
        if '"is_vague"' in text:
            # Try to extract is_vague boolean
            bool_match = re.search(r'"is_vague"\s*:\s*(true|false)', text, re.IGNORECASE)
            location_match = re.search(r'"location"\s*:\s*"([^"]*)"', text)
            reason_match = re.search(r'"reason"\s*:\s*"([^"]*)"', text)
            result = {
                "is_vague": bool_match.group(1).lower() == "true" if bool_match else False,
                "location": location_match.group(1) if location_match else None,
                "reason": reason_match.group(1) if reason_match else "Unable to parse"
            }
            return result
        
        # If all else fails, log the problematic text for debugging
        print(f"Warning: Could not parse JSON from text: {text[:200]}...")
        return {}

def check_vagueness(user_text: str) -> dict:
    """Check if the user request is too vague"""
    try:
        response = client.chat.completions.create(
            model="asi1-mini",
            messages=[
                {"role": "system", "content": VAGUENESS_CHECK_PROMPT},
                {"role": "user", "content": user_text},
            ],
            max_tokens=200,
        )
        result = safe_json_parse(response.choices[0].message.content)
        # Ensure boolean is properly set
        if "is_vague" in result:
            result["is_vague"] = bool(result["is_vague"])
        print(f"Vagueness check parsed result: {result}")  # Debug logging
        return result
    except Exception as e:
        print(f"Vagueness check error: {e}")
        # Default to vague if we can't check, so we prompt the user
        # Try to extract location from text as fallback
        import re
        # Ensure user_text is a string before using regex
        if not isinstance(user_text, str):
            user_text = str(user_text)
        location_match = re.search(r'\b(?:in|at|to|visit|visit|going to|trip to)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)', user_text, re.IGNORECASE)
        location = location_match.group(1) if location_match else None
        return {"is_vague": True, "location": location, "reason": "Error checking - defaulting to vague"}

def research_location_activities(location: str) -> dict:
    """Research popular activities in a location"""
    try:
        response = client.chat.completions.create(
            model="asi1-mini",
            messages=[
                {"role": "system", "content": RESEARCH_PROMPT.format(location=location)},
                {"role": "user", "content": f"Research activities for {location}"},
            ],
            max_tokens=800,
        )
        content = response.choices[0].message.content
        if not content:
            return {"general_categories": []}
        result = safe_json_parse(content)
        # Ensure we always return a dict with general_categories
        if not isinstance(result, dict) or "general_categories" not in result:
            return {"general_categories": []}
        return result
    except Exception as e:
        # Log the actual error and response content for debugging
        error_msg = str(e)
        if hasattr(e, '__cause__') and e.__cause__:
            error_msg = f"{error_msg} (caused by: {e.__cause__})"
        print(f"Research error: {error_msg}")
        if 'response' in locals() and hasattr(response, 'choices'):
            print(f"Response content: {response.choices[0].message.content[:200] if response.choices else 'No response'}")
        return {"general_categories": []}

def create_preference_prompt(categories: list) -> str:
    """Create a user-friendly prompt asking for preferences"""
    prompt = "To help plan your trip, please select which types of activities interest you:\n\n"
    for i, cat in enumerate(categories, 1):
        prompt += f"{i}. {cat['category'].upper()}: {cat['description']}\n"
        if cat.get('examples'):
            prompt += f"   Examples: {', '.join(cat['examples'][:3])}\n"
    prompt += "\nPlease reply with the numbers or names of categories you're interested in (e.g., '1, 3, 5' or 'eat, sightsee')."
    return prompt

def parse_user_preferences(user_input: str, categories: Optional[List[Dict]] = None) -> str:
    """
    Parse user preference input (could be "1, 3, 5" or "eat, sightsee" or category names)
    and convert to a comma-separated string of category names.
    
    Args:
        user_input: User's response (e.g., "1, 3, 5" or "eat, sightsee")
        categories: List of category dictionaries from conversation_state (optional)
    
    Returns:
        Comma-separated string of category names (e.g., "eat, sightsee, shop")
    """
    if not user_input:
        return ""
    
    # Clean the input
    user_input = user_input.strip().lower()
    
    # If categories are provided, try to map numbers to category names
    if categories and isinstance(categories, list):
        # Check if input contains numbers
        import re
        numbers = re.findall(r'\d+', user_input)
        if numbers:
            # Map numbers to category names
            selected_categories = []
            for num_str in numbers:
                try:
                    idx = int(num_str) - 1  # Convert to 0-based index
                    if 0 <= idx < len(categories):
                        selected_categories.append(categories[idx].get('category', ''))
                except ValueError:
                    pass
            
            if selected_categories:
                return ", ".join(selected_categories)
    
    # If input contains category names directly, extract them
    # Common category names to look for
    common_categories = ["eat", "sightsee", "shop", "entertainment", "relax", "outdoor", "cultural", "dining", "hiking", "skiing", "adventure"]
    
    found_categories = []
    for cat in common_categories:
        if cat in user_input:
            found_categories.append(cat)
    
    if found_categories:
        return ", ".join(found_categories)
    
    # If we can't parse it, return the original input (AI will try to interpret it)
    return user_input

def finalize_activity_list(original_request: str, user_preferences: str, location: str, budget: str, start_time: str, end_time: str, transaction_data: Optional[Dict] = None) -> dict:
    """Create finalized activity list based on user preferences and transaction history"""
    try:
        transaction_context = ""
        if transaction_data and transaction_data.get("has_sufficient_data"):
            inferred = transaction_data.get("inferred_preferences", [])
            categories = transaction_data.get("activity_categories", [])
            transaction_context = f"\nUser's past activity preferences (from transaction history): {', '.join(inferred)}\nPreferred activity categories: {', '.join(categories)}\nUse these preferences to personalize the activity list."
        
        try:
            response = client.chat.completions.create(
                model="asi1-mini",
                messages=[
                    {"role": "system", "content": FINALIZE_PROMPT.format(
                        original_request=original_request,
                        user_preferences=user_preferences,
                        location=location,
                        budget=budget,
                        start_time=start_time,
                        end_time=end_time,
                        transaction_context=transaction_context
                    )},
                    {"role": "user", "content": "Create the finalized activity list. Return ONLY valid JSON with no additional text."},
                ],
                max_tokens=1200,  # Increased to prevent truncation
                temperature=0.3,  # Lower temperature for more consistent JSON output
            )
            content = response.choices[0].message.content
            finish_reason = response.choices[0].finish_reason
            
            # Check if response was truncated
            if finish_reason == "length":
                print(f"Warning: AI response was truncated (finish_reason=length). Content: {content[:200]}...")
            
            if not content:
                print("Finalization error: Empty response from AI")
                # Fall through to fallback logic below
                result = None
            else:
                # Log the raw content for debugging (first 500 chars)
                print(f"Finalization response (first 500 chars): {content[:500]}")
                
                result = safe_json_parse(content)
                
                # Validate that we got the required fields
                if not result or not isinstance(result, dict):
                    print(f"Finalization error: Invalid response structure. Full content: {content}")
                    print(f"Parsed result: {result}")
                    result = None
        except Exception as api_error:
            print(f"API call error: {api_error}")
            import traceback
            print(traceback.format_exc())
            result = None
        
        # If API call failed or returned invalid result, use fallback
        if result is None:
            print("Using fallback: Creating activity_list directly from user preferences")
            # Extract categories from user preferences
            import re
            category_keywords = {
                "eat": ["eat", "dining", "food", "restaurant", "cafe", "meal"],
                "sightsee": ["sightsee", "sightseeing", "landmark", "monument", "museum", "view", "attraction"],
                "shop": ["shop", "shopping", "market", "boutique", "store", "mall"],
                "entertainment": ["entertainment", "show", "concert", "nightlife", "bar", "club", "theater"],
                "outdoor": ["outdoor", "hiking", "park", "nature", "walk"],
                "cultural": ["cultural", "culture", "art", "gallery", "history", "historic"]
            }
            
            user_pref_lower = user_preferences.lower()
            extracted_categories = []
            for category, keywords in category_keywords.items():
                if any(keyword in user_pref_lower for keyword in keywords):
                    extracted_categories.append(category)
            
            # If we couldn't extract, use defaults
            if not extracted_categories:
                extracted_categories = ["eat", "sightsee"]
            
            result = {
                "activity_list": extracted_categories,
                "constraints": {
                    "budget": float(budget) if budget and budget != "null" and budget.lower() != "none" else None,
                    "start_time": start_time if start_time and start_time != "null" else None,
                    "end_time": end_time if end_time and end_time != "null" else None,
                    "location": location,
                    "preferences": user_preferences.split(", ") if user_preferences else []
                },
                "agents_to_call": [],
                "notes": f"Activity list created from user preferences: {', '.join(extracted_categories)}"
            }
            print(f"Fallback result: {result}")
        
        # Ensure required fields exist
        if "activity_list" not in result:
            print(f"Finalization error: Missing activity_list in response.")
            # Try to create a minimal valid response
            result["activity_list"] = []
        
        # Validate that activity_list is not empty
        if not result.get("activity_list") or len(result.get("activity_list", [])) == 0:
            print(f"Warning: activity_list is empty. Attempting to extract from user preferences: {user_preferences}")
            # Try to extract categories from user preferences as fallback
            import re
            # Look for common category names in user_preferences
            category_keywords = {
                "eat": ["eat", "dining", "food", "restaurant", "cafe"],
                "sightsee": ["sightsee", "sightseeing", "landmark", "monument", "museum"],
                "shop": ["shop", "shopping", "market", "boutique"],
                "entertainment": ["entertainment", "show", "concert", "nightlife"],
                "outdoor": ["outdoor", "hiking", "park", "nature"],
                "cultural": ["cultural", "culture", "art", "gallery"]
            }
            
            user_pref_lower = user_preferences.lower()
            extracted_categories = []
            for category, keywords in category_keywords.items():
                if any(keyword in user_pref_lower for keyword in keywords):
                    extracted_categories.append(category)
            
            if extracted_categories:
                result["activity_list"] = extracted_categories
                print(f"Extracted activity_list from preferences: {extracted_categories}")
            else:
                # Last resort: use default categories based on common preferences
                result["activity_list"] = ["eat", "sightsee"]
                print(f"Using default activity_list: {result['activity_list']}")
        
        if "constraints" not in result:
            result["constraints"] = {}
        
        if "agents_to_call" not in result:
            result["agents_to_call"] = []
        
        if "notes" not in result:
            result["notes"] = "Activity list finalized"
        
        # Final validation: ensure activity_list is not empty
        if not result.get("activity_list") or len(result.get("activity_list", [])) == 0:
            print("ERROR: activity_list is still empty after all attempts. Setting default.")
            result["activity_list"] = ["eat", "sightsee"]
        
        print(f"Final activity_list: {result.get('activity_list')}")
        return result
    except Exception as e:
        print(f"Finalization error: {e}")
        import traceback
        print(traceback.format_exc())
        return None

def dispatch_intent(user_request: str, sender: str, conversation_state: Optional[Dict] = None) -> Dict:
    """
    Main intent dispatch function that processes user requests.
    
    PROMPTING FLOW WHEN REQUEST IS VAGUE OR INSUFFICIENT DATA:
    1. User sends vague request (e.g., "Plan me a day in New York City")
    2. check_vagueness() determines if request is vague and extracts location
    3. If vague:
       a. Extract basic info (budget, start_time, end_time) from request
       b. Check user's transaction history for preferences
       c. If sufficient transaction data (3+ similar activities):
          - Use inferred preferences to create activity list directly
          - Return dispatch plan with general categories (eat, sightsee, etc.)
       d. If insufficient transaction data:
          - research_location_activities() gets popular categories for location
          - create_preference_prompt() generates user-friendly prompt
          - Return clarification_needed with prompt asking user to select categories
    4. User responds with selected categories (e.g., "1, 3, 5" or "eat, sightsee")
    5. finalize_activity_list() creates activity list with general categories based on selections
    6. Return dispatch plan with general activity categories
    
    Returns a dictionary with either:
    - A dispatch plan (if complete) - contains general activity categories like ["eat", "sightsee", "shop"]
    - A clarification prompt (if more info needed) - asks user to select from categories
    - An error message
    """
    try:
        # STEP 1: Check if we're waiting for user clarification from a previous vague request
        if conversation_state and conversation_state.get("waiting_for_clarification"):
            # STEP 2: User has responded with their preference selections
            # Parse their response (could be "1, 3, 5" or "eat, sightsee" or category names)
            categories = conversation_state.get("categories", [])
            parsed_preferences = parse_user_preferences(user_request, categories)
            
            # Use parsed preferences, or fall back to original if parsing didn't work
            user_preferences = parsed_preferences if parsed_preferences else user_request
            
            original_request = conversation_state.get("original_request", "")
            location = conversation_state.get("location", "")
            budget = conversation_state.get("budget", "null")
            start_time = conversation_state.get("start_time", "null")
            end_time = conversation_state.get("end_time", "null")
            
            transaction_data = None
            if conversation_state.get("transaction_data"):
                transaction_data = conversation_state.get("transaction_data")
            
            print(f"Parsed user preferences: {user_preferences} (from input: {user_request})")
            
            # STEP 3: Create final activity list with GENERAL categories (eat, sightsee, etc.)
            dispatch_plan = finalize_activity_list(
                original_request, user_preferences, location, budget, start_time, end_time, transaction_data
            )
            
            if dispatch_plan:
                return {"type": "dispatch_plan", "data": dispatch_plan}
            else:
                return {"type": "error", "data": {"error": "Failed to finalize activity list"}}
        
        # STEP 1: New request - check if vague
        vagueness_result = check_vagueness(user_request)
        print(f"Vagueness check result: {vagueness_result}")  # Debug logging
        
        # Check if request is vague
        is_vague = vagueness_result.get("is_vague", False)
        location = vagueness_result.get("location")
        
        # Ensure user_request is a string before string operations
        if not isinstance(user_request, str):
            user_request = str(user_request)
        
        # Also check if this looks like a general planning request (contains words like "plan", "itinerary", "day in")
        is_planning_request = any(word in user_request.lower() for word in ["plan", "itinerary", "day in", "visit", "trip to"])
        
        # Treat as vague if: explicitly marked vague OR (has location AND looks like general planning request)
        if is_vague or (location and is_planning_request):
            # REQUEST IS VAGUE - Need to gather more information
            # If location wasn't extracted, try to extract it from text
            if not location:
                import re
                # Ensure user_request is a string before using regex
                if isinstance(user_request, dict):
                    user_request = str(user_request)
                elif not isinstance(user_request, str):
                    user_request = str(user_request)
                # Try to find location patterns like "in New York", "visit Paris", "trip to Tokyo"
                location_match = re.search(r'\b(?:in|at|to|visit|trip to|going to)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)', user_request, re.IGNORECASE)
                if location_match:
                    location = location_match.group(1)
                    print(f"Extracted location from text: {location}")
            
            # If still no location, we can't proceed with vague request handling
            if not location:
                print("Warning: Vague request but no location found, proceeding with normal dispatch")
                # Fall through to normal dispatch below
            else:
                # STEP 2a: Extract basic info (budget, times) from the vague request
                try:
                    initial_parse = client.chat.completions.create(
                        model="asi1-mini",
                        messages=[
                            {"role": "system", "content": "Extract budget, start_time, and end_time from: " + user_request + "\nReturn JSON: {\"budget\": number or null, \"start_time\": \"ISO 8601 datetime string or null\", \"end_time\": \"ISO 8601 datetime string or null\"}"},
                            {"role": "user", "content": user_request},
                        ],
                        max_tokens=150,
                    )
                    basic_info = safe_json_parse(initial_parse.choices[0].message.content)
                except:
                    basic_info = {"budget": None, "start_time": None, "end_time": None}
                
                # STEP 2b: Check user's transaction history to infer preferences
                user_transactions = get_user_transactions(sender)
                transaction_analysis = analyze_transaction_preferences(user_transactions, location)
                
                # STEP 2c: If we have sufficient transaction data (3+ similar activities), use it directly
                if transaction_analysis and transaction_analysis.get("has_sufficient_data"):
                    # SUFFICIENT TRANSACTION DATA: Create activity list directly using inferred preferences
                    inferred_preferences = ", ".join(transaction_analysis.get("inferred_preferences", []))
                    
                    dispatch_plan = finalize_activity_list(
                        original_request=user_request,
                        user_preferences=inferred_preferences,
                        location=location,
                        budget=str(basic_info.get("budget", "null")),
                        start_time=basic_info.get("start_time", "null") or "null",
                        end_time=basic_info.get("end_time", "null") or "null",
                        transaction_data=transaction_analysis
                    )
                    
                    if dispatch_plan:
                        # Return dispatch plan with GENERAL categories (eat, sightsee, etc.)
                        return {"type": "dispatch_plan", "data": dispatch_plan}
                    else:
                        # Fallback: If finalization fails, prompt user for preferences
                        research_result = research_location_activities(location)
                        categories = research_result.get("general_categories", [])
                        if not categories:
                            # If research failed, use default categories
                            print(f"Research failed for {location}, using default categories")
                            categories = [
                                {"category": "eat", "description": "Dining and food experiences", "examples": ["local cuisine", "restaurants", "cafes"]},
                                {"category": "sightsee", "description": "Sightseeing and landmarks", "examples": ["monuments", "museums", "parks"]},
                                {"category": "shop", "description": "Shopping and markets", "examples": ["local markets", "boutiques", "souvenirs"]},
                                {"category": "entertainment", "description": "Entertainment and nightlife", "examples": ["shows", "concerts", "bars"]},
                                {"category": "outdoor", "description": "Outdoor activities", "examples": ["parks", "hiking", "beaches"]},
                                {"category": "cultural", "description": "Cultural experiences", "examples": ["museums", "galleries", "historic sites"]}
                            ]
                        return {
                            "type": "clarification_needed",
                            "data": {
                                "prompt": create_preference_prompt(categories),
                                "conversation_state": {
                                    "waiting_for_clarification": True,
                                    "original_request": user_request,
                                    "location": location,
                                    "budget": str(basic_info.get("budget", "null")),
                                    "start_time": basic_info.get("start_time", "null") or "null",
                                    "end_time": basic_info.get("end_time", "null") or "null",
                                    "categories": categories
                                }
                            }
                        }
                else:
                    # INSUFFICIENT TRANSACTION DATA: Research location and prompt user for preferences
                    # STEP 2d: Research popular activity categories for the location
                    research_result = research_location_activities(location)
                    categories = research_result.get("general_categories", [])
                    
                    if categories:
                        # STEP 2e: Generate user-friendly prompt asking them to select categories
                        # Returns clarification_needed which will prompt user to select from:
                        # 1. EAT: Dining and food experiences
                        # 2. SHOP: Shopping and markets
                        # 3. SIGHTSEE: Sightseeing and landmarks
                        # etc.
                        return {
                            "type": "clarification_needed",
                            "data": {
                                "prompt": create_preference_prompt(categories),
                                "conversation_state": {
                                    "waiting_for_clarification": True,
                                    "original_request": user_request,
                                    "location": location,
                                    "budget": str(basic_info.get("budget", "null")),
                                    "start_time": basic_info.get("start_time", "null") or "null",
                                    "end_time": basic_info.get("end_time", "null") or "null",
                                    "categories": categories
                                }
                            }
                        }
                    else:
                        # Research failed - use default categories and still prompt user
                        print(f"Research failed for {location}, using default categories")
                        default_categories = [
                            {"category": "eat", "description": "Dining and food experiences", "examples": ["local cuisine", "restaurants", "cafes"]},
                            {"category": "sightsee", "description": "Sightseeing and landmarks", "examples": ["monuments", "museums", "parks"]},
                            {"category": "shop", "description": "Shopping and markets", "examples": ["local markets", "boutiques", "souvenirs"]},
                            {"category": "entertainment", "description": "Entertainment and nightlife", "examples": ["shows", "concerts", "bars"]},
                            {"category": "outdoor", "description": "Outdoor activities", "examples": ["parks", "hiking", "beaches"]},
                            {"category": "cultural", "description": "Cultural experiences", "examples": ["museums", "galleries", "historic sites"]}
                        ]
                        return {
                            "type": "clarification_needed",
                            "data": {
                                "prompt": create_preference_prompt(default_categories),
                                "conversation_state": {
                                    "waiting_for_clarification": True,
                                    "original_request": user_request,
                                    "location": location,
                                    "budget": str(basic_info.get("budget", "null")),
                                    "start_time": basic_info.get("start_time", "null") or "null",
                                    "end_time": basic_info.get("end_time", "null") or "null",
                                    "categories": default_categories
                                }
                            }
                        }
        else:
            # REQUEST IS NOT VAGUE: User provided enough detail, proceed with normal dispatch
            # This creates activity list with GENERAL categories (eat, sightsee, etc.) directly
            response = client.chat.completions.create(
                model="asi1-mini",
                messages=[
                    {"role": "system", "content": DISPATCHER_SYSTEM_PROMPT},
                    {"role": "user", "content": user_request},
                ],
                max_tokens=600,
            )
            raw_json = response.choices[0].message.content
            dispatch_plan = safe_json_parse(raw_json)
            # Return dispatch plan with GENERAL categories (eat, sightsee, shop, etc.)
            return {"type": "dispatch_plan", "data": dispatch_plan}
            
    except Exception as e:
        print(f"Dispatch error: {e}")
        return {"type": "error", "data": {"error": "dispatch_failed", "message": str(e)}}

