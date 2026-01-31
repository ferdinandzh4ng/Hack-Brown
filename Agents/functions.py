from uagents import Model
from typing import Optional, List, Dict
import json
import os
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
- It only mentions a location without specific activities
- It lacks clear preferences or interests
- It's too general (e.g., "I want to visit Paris" without details)

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

{
  "activity_list": [
    "specific activity 1",
    "specific activity 2",
    ...
  ],
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

The activity_list should be specific, actionable activities based on the user's preferences.
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
  "activity_list": [ ... ],
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
        
        result = json.loads(response.choices[0].message.content)
        return result
        
    except Exception as e:
        print(f"Error analyzing transactions: {e}")
        return None

# ------------------------------------------------------------
# Intent Dispatch Functions
# ------------------------------------------------------------

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
        result = json.loads(response.choices[0].message.content)
        return result
    except Exception as e:
        print(f"Vagueness check error: {e}")
        return {"is_vague": False, "location": None, "reason": "Error checking"}

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
        result = json.loads(response.choices[0].message.content)
        return result
    except Exception as e:
        print(f"Research error: {e}")
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

def finalize_activity_list(original_request: str, user_preferences: str, location: str, budget: str, start_time: str, end_time: str, transaction_data: Optional[Dict] = None) -> dict:
    """Create finalized activity list based on user preferences and transaction history"""
    try:
        transaction_context = ""
        if transaction_data and transaction_data.get("has_sufficient_data"):
            inferred = transaction_data.get("inferred_preferences", [])
            categories = transaction_data.get("activity_categories", [])
            transaction_context = f"\nUser's past activity preferences (from transaction history): {', '.join(inferred)}\nPreferred activity categories: {', '.join(categories)}\nUse these preferences to personalize the activity list."
        
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
                {"role": "user", "content": "Create the finalized activity list"},
            ],
            max_tokens=800,
        )
        result = json.loads(response.choices[0].message.content)
        return result
    except Exception as e:
        print(f"Finalization error: {e}")
        return None

def dispatch_intent(user_request: str, sender: str, conversation_state: Optional[Dict] = None) -> Dict:
    """
    Main intent dispatch function that processes user requests.
    Returns a dictionary with either:
    - A dispatch plan (if complete)
    - A clarification prompt (if more info needed)
    - An error message
    """
    try:
        # Check if we're waiting for user clarification
        if conversation_state and conversation_state.get("waiting_for_clarification"):
            user_preferences = user_request
            original_request = conversation_state.get("original_request", "")
            location = conversation_state.get("location", "")
            budget = conversation_state.get("budget", "null")
            start_time = conversation_state.get("start_time", "null")
            end_time = conversation_state.get("end_time", "null")
            
            transaction_data = None
            if conversation_state.get("transaction_data"):
                transaction_data = conversation_state.get("transaction_data")
            
            dispatch_plan = finalize_activity_list(
                original_request, user_preferences, location, budget, start_time, end_time, transaction_data
            )
            
            if dispatch_plan:
                return {"type": "dispatch_plan", "data": dispatch_plan}
            else:
                return {"type": "error", "data": {"error": "Failed to finalize activity list"}}
        
        # New request - check if vague
        vagueness_result = check_vagueness(user_request)
        
        if vagueness_result.get("is_vague") and vagueness_result.get("location"):
            location = vagueness_result["location"]
            
            # Extract basic info
            try:
                initial_parse = client.chat.completions.create(
                    model="asi1-mini",
                    messages=[
                        {"role": "system", "content": "Extract budget, start_time, and end_time from: " + user_request + "\nReturn JSON: {\"budget\": number or null, \"start_time\": \"ISO 8601 datetime string or null\", \"end_time\": \"ISO 8601 datetime string or null\"}"},
                        {"role": "user", "content": user_request},
                    ],
                    max_tokens=150,
                )
                basic_info = json.loads(initial_parse.choices[0].message.content)
            except:
                basic_info = {"budget": None, "start_time": None, "end_time": None}
            
            # Check user transactions
            user_transactions = get_user_transactions(sender)
            transaction_analysis = analyze_transaction_preferences(user_transactions, location)
            
            # If we have sufficient transaction data, use it to create activity list
            if transaction_analysis and transaction_analysis.get("has_sufficient_data"):
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
                    return {"type": "dispatch_plan", "data": dispatch_plan}
                else:
                    # Fallback to prompting
                    research_result = research_location_activities(location)
                    categories = research_result.get("general_categories", [])
                    if categories:
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
                # Not enough transaction data - research and prompt user
                research_result = research_location_activities(location)
                categories = research_result.get("general_categories", [])
                
                if categories:
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
                    # Research failed, proceed with normal dispatch
                    response = client.chat.completions.create(
                        model="asi1-mini",
                        messages=[
                            {"role": "system", "content": DISPATCHER_SYSTEM_PROMPT},
                            {"role": "user", "content": user_request},
                        ],
                        max_tokens=600,
                    )
                    raw_json = response.choices[0].message.content
                    dispatch_plan = json.loads(raw_json)
                    return {"type": "dispatch_plan", "data": dispatch_plan}
        else:
            # Request is specific enough - proceed with normal dispatch
            response = client.chat.completions.create(
                model="asi1-mini",
                messages=[
                    {"role": "system", "content": DISPATCHER_SYSTEM_PROMPT},
                    {"role": "user", "content": user_request},
                ],
                max_tokens=600,
            )
            raw_json = response.choices[0].message.content
            dispatch_plan = json.loads(raw_json)
            return {"type": "dispatch_plan", "data": dispatch_plan}
            
    except Exception as e:
        print(f"Dispatch error: {e}")
        return {"type": "error", "data": {"error": "dispatch_failed", "message": str(e)}}

