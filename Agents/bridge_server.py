#!/usr/bin/env python3
"""
HTTP Bridge Server for Orchestrator Agent
Provides REST API endpoint to communicate with the LangGraph Orchestrator agent
"""
import asyncio
import json
import os
import threading
import signal
import sys
from datetime import datetime, timezone, timedelta
from uuid import uuid4
from typing import Optional, Tuple, List
from dotenv import load_dotenv

from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
from Login import LoginManager

from uagents import Agent, Context, Protocol
from uagents_core.contrib.protocols.chat import (
    ChatMessage,
    TextContent,
    ChatAcknowledgement,
    chat_protocol_spec,
)

load_dotenv()

# Orchestrator agent address
ORCHESTRATOR_AGENT_ADDRESS = os.getenv(
    "ORCHESTRATOR_AGENT_ADDRESS",
    "agent1qg2akmff6ke58spye465yje4e5fvdk6faku59h2akjjtu5hmkf8rqy346qj"
)

# Booking agent address
BOOKING_AGENT_ADDRESS = os.getenv(
    "BOOKING_AGENT_ADDRESS",
    ""  # Will be set when agent is registered
)

# Shared state for bridge communication
class BridgeState:
    def __init__(self):
        self.response_queue: Optional[asyncio.Queue] = None
        self.send_queue: Optional[asyncio.Queue] = None
        self.agent_running = False
        self.agent_context: Optional[Context] = None
        self.agent_thread: Optional[threading.Thread] = None
        self.last_request_time: Optional[datetime] = None
        self.pending_request_id: Optional[str] = None
    
    def reset(self):
        """Reset state and clear queues"""
        # Clear queues
        if self.response_queue:
            while not self.response_queue.empty():
                try:
                    self.response_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
        
        if self.send_queue:
            while not self.send_queue.empty():
                try:
                    self.send_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
        
        self.last_request_time = None
        self.pending_request_id = None

# Global state instance
bridge_state = BridgeState()

# Create bridge agent to communicate with orchestrator
bridge_agent = Agent(
    name="BridgeAgent",
    seed="bridge-server-seed",
    port=8009,
    mailbox=True,
    publish_agent_details=True,
    network="testnet"
)

# Include chat protocol (needed for send_and_receive to work)
chat_proto = Protocol(spec=chat_protocol_spec)

# Handler to receive responses from orchestrator
@chat_proto.on_message(ChatMessage)
async def handle_message(ctx: Context, sender: str, msg: ChatMessage):
    """Handle response from orchestrator - filter out stale messages"""
    ctx.logger.info(f"Bridge received message from {sender[:20]}... (orchestrator: {ORCHESTRATOR_AGENT_ADDRESS[:20]}...)")
    
    # Check if this is a response from orchestrator
    if sender == ORCHESTRATOR_AGENT_ADDRESS:
        ctx.logger.info(f"Message is from orchestrator, processing...")
        
        # Check if message is stale (older than 5 minutes)
        # Handle both timezone-aware and timezone-naive timestamps
        try:
            now = datetime.now(timezone.utc)
            msg_time = msg.timestamp
            
            # If timestamp is naive, assume it's UTC
            if msg_time.tzinfo is None:
                msg_time = msg_time.replace(tzinfo=timezone.utc)
            
            message_age = (now - msg_time).total_seconds()
            if message_age > 300:  # 5 minutes
                ctx.logger.warning(f"Ignoring stale message (age: {message_age:.0f}s)")
                return
        except Exception as e:
            ctx.logger.warning(f"Error checking message age: {e}, proceeding with message")
        
        # Check if we have a pending request (within last 2 minutes)
        # But don't block if we don't have last_request_time - might be a legitimate response
        if bridge_state.last_request_time:
            time_since_request = (datetime.now(timezone.utc) - bridge_state.last_request_time).total_seconds()
            if time_since_request > 120:  # 2 minutes
                ctx.logger.warning(f"Message received but last request was {time_since_request:.0f}s ago - might be stale, but processing anyway")
            else:
                ctx.logger.info(f"Message received within request window ({time_since_request:.0f}s since request)")
        else:
            ctx.logger.warning(f"Received message but no last_request_time set - processing anyway (might be from previous session)")
        
        # Extract text content
        response_text = ""
        for item in msg.content:
            if isinstance(item, TextContent):
                response_text = item.text
                break
        
        ctx.logger.info(f"Extracted response text: {len(response_text)} chars")
        
        # Put response in queue
        if response_text and bridge_state.response_queue is not None:
            try:
                await bridge_state.response_queue.put(response_text)
                ctx.logger.info(f"Successfully queued response from orchestrator: {len(response_text)} chars")
            except Exception as e:
                ctx.logger.error(f"Error putting response in queue: {e}")
                import traceback
                ctx.logger.error(traceback.format_exc())
        else:
            if not response_text:
                ctx.logger.error("No text content in response message")
            if bridge_state.response_queue is None:
                ctx.logger.error("Response queue is None - cannot queue response")
    else:
        ctx.logger.debug(f"Ignoring message from non-orchestrator sender: {sender[:20]}...")

# Interval handler to process send queue
@bridge_agent.on_interval(period=0.5)
async def process_send_queue(ctx: Context):
    """Periodically check send queue and send messages - clear stale messages"""
    bridge_state.agent_context = ctx  # Store context for use in send_to_orchestrator
    
    if bridge_state.send_queue is not None:
        queue_size = bridge_state.send_queue.qsize()
        if queue_size > 0:
            ctx.logger.info(f"Send queue has {queue_size} message(s) - processing...")
        try:
            # Process messages in queue, but limit to prevent infinite loops
            processed = 0
            max_per_interval = 10  # Max 10 messages per interval
            
            while not bridge_state.send_queue.empty() and processed < max_per_interval:
                try:
                    target_address, message_to_send = bridge_state.send_queue.get_nowait()
                    
                    # Check if message is stale (older than 5 minutes)
                    # Handle both timezone-aware and timezone-naive timestamps
                    try:
                        now = datetime.now(timezone.utc)
                        msg_time = message_to_send.timestamp
                        
                        # If timestamp is naive, assume it's UTC
                        if msg_time.tzinfo is None:
                            msg_time = msg_time.replace(tzinfo=timezone.utc)
                        
                        message_age = (now - msg_time).total_seconds()
                        if message_age > 300:  # 5 minutes
                            ctx.logger.warning(f"Skipping stale queued message (age: {message_age:.0f}s)")
                            processed += 1
                            continue
                    except Exception as e:
                        ctx.logger.warning(f"Error checking queued message age: {e}, sending message anyway")
                    
                    ctx.logger.info(f"Attempting to send message to {target_address}")
                    ctx.logger.info(f"Message ID: {message_to_send.msg_id}")
                    ctx.logger.info(f"Message timestamp: {message_to_send.timestamp}")
                    ctx.logger.info(f"Message content preview: {str(message_to_send.content)[:200]}")
                    await ctx.send(target_address, message_to_send)
                    ctx.logger.info(f"✓ Successfully sent message to {target_address}")
                    processed += 1
                except asyncio.QueueEmpty:
                    break
                except Exception as e:
                    ctx.logger.error(f"Error sending queued message: {e}")
                    import traceback
                    ctx.logger.error(traceback.format_exc())
                    processed += 1  # Count errors to prevent infinite loops
        except Exception as e:
            ctx.logger.error(f"Error processing send queue: {e}")
            import traceback
            ctx.logger.error(traceback.format_exc())

@chat_proto.on_message(ChatAcknowledgement)
async def handle_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
    """Handle acknowledgement messages - required for protocol verification"""
    # Just ignore acknowledgements - they're handled by send_and_receive
    pass

bridge_agent.include(chat_proto, publish_manifest=False)

# FastAPI app
app = FastAPI(title="Orchestrator Bridge Server")

# Initialize LoginManager for MongoDB operations
login_manager = LoginManager()

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],  # Next.js default
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ScheduleRequest(BaseModel):
    user_request: str
    location: str
    start_time: str  # ISO 8601 format
    end_time: str    # ISO 8601 format
    budget: Optional[float] = None  # Optional budget in dollars
    user_id: Optional[str] = None  # Optional user ID for preference-based planning

class ScheduleResponse(BaseModel):
    success: bool
    data: Optional[dict] = None
    error: Optional[str] = None

class BookingRequest(BaseModel):
    items: List[dict]  # List of itinerary items
    location: str
    user_id: Optional[str] = None  # Optional user ID for payment processing

class BookingResponse(BaseModel):
    success: bool
    data: Optional[dict] = None
    error: Optional[str] = None

class SaveTripRequest(BaseModel):
    location: str
    start_time: str
    end_time: str
    budget: Optional[float] = None
    user_request: str
    activities: List[dict] = []
    itinerary: List[dict] = []

class SaveTripResponse(BaseModel):
    success: bool
    trip_id: Optional[str] = None
    message: str

def extract_activities_and_budget(user_request: str) -> Tuple[list, float]:
    """Extract activities and budget from user request"""
    # Extract activities from user_request (simple keyword matching)
    activities = []
    user_lower = user_request.lower()
    if any(word in user_lower for word in ["eat", "dining", "food", "restaurant"]):
        activities.append("dining")
    if any(word in user_lower for word in ["sightsee", "sight", "tour", "visit", "see"]):
        activities.append("sightseeing")
    if any(word in user_lower for word in ["entertainment", "show", "movie", "concert", "theater"]):
        activities.append("entertainment")
    if any(word in user_lower for word in ["transit", "transport", "travel"]):
        activities.append("transit")
    
    # Default activities if none found
    if not activities:
        activities = ["sightseeing", "dining", "entertainment"]
    
    # Estimate budget from user request or use default
    budget = 200.0  # Default budget
    if "$" in user_request:
        import re
        budget_matches = re.findall(r'\$(\d+)', user_request)
        if budget_matches:
            budget = float(budget_matches[0])
    
    return activities, budget

def generate_simple_fallback_schedule(
    location: str,
    budget: float,
    activities: list,
    start_time: str,
    end_time: str
) -> dict:
    """
    Generate a simple fallback schedule when agents are unavailable.
    Creates a basic schedule structure without calling any external APIs.
    """
    from datetime import datetime, timedelta
    
    try:
        # Parse times
        start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
        end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
        duration_hours = (end_dt - start_dt).total_seconds() / 3600
    except:
        start_dt = datetime.now(timezone.utc)
        end_dt = start_dt + timedelta(hours=8)
        duration_hours = 8
    
    # Generate simple activities based on interests
    activities_list = {}
    current_time = start_dt
    activity_num = 1
    total_cost = 0.0
    
    # Activity templates based on interests
    activity_templates = {
        "sightseeing": [
            {"name": "City Tour", "duration": 120, "cost": 30.0},
            {"name": "Museum Visit", "duration": 90, "cost": 25.0},
            {"name": "Historic Site", "duration": 60, "cost": 15.0},
        ],
        "dining": [
            {"name": "Lunch", "duration": 60, "cost": 25.0},
            {"name": "Dinner", "duration": 90, "cost": 50.0},
            {"name": "Cafe Break", "duration": 30, "cost": 10.0},
        ],
        "entertainment": [
            {"name": "Show/Event", "duration": 120, "cost": 75.0},
            {"name": "Entertainment Venue", "duration": 90, "cost": 40.0},
        ],
    }
    
    # Generate activities
    for activity_type in activities[:3]:  # Limit to 3 activity types
        if activity_type in activity_templates:
            template = activity_templates[activity_type][0]  # Use first template
            
            # Add transit if not first activity
            if activity_num > 1:
                transit_end = current_time + timedelta(minutes=30)
                activities_list[f"Activity {activity_num}"] = {
                    "venue": f"Transit to {template['name']}",
                    "type": "transit",
                    "category": "transit",
                    "start_time": current_time.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                    "end_time": transit_end.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                    "duration_minutes": 30,
                    "cost": 5.0,
                    "description": f"Travel to {template['name']}",
                    "address": location,
                    "method": "transit"
                }
                total_cost += 5.0
                activity_num += 1
                current_time = transit_end
            
            # Add venue activity
            activity_end = current_time + timedelta(minutes=template['duration'])
            if total_cost + template['cost'] <= budget * 0.9:  # Use 90% of budget
                activities_list[f"Activity {activity_num}"] = {
                    "venue": template['name'],
                    "type": "venue",
                    "category": activity_type,
                    "start_time": current_time.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                    "end_time": activity_end.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                    "duration_minutes": template['duration'],
                    "cost": template['cost'],
                    "description": f"{template['name']} in {location}",
                    "address": location,
                }
                total_cost += template['cost']
                activity_num += 1
                current_time = activity_end
    
    return {
        "location": location,
        "budget": budget,
        "interest_activities": activities,
        "activities": activities_list,
        "total_cost": round(total_cost, 2),
        "remaining_budget": round(budget - total_cost, 2),
        "summary": {
            "total_activities": len(activities_list),
            "total_cost": round(total_cost, 2),
            "remaining_budget": round(budget - total_cost, 2)
        },
        "fallback": True,
        "fallback_reason": "Agents unavailable"
    }

async def send_to_orchestrator(user_request: str, location: str, start_time: str, end_time: str, budget: Optional[float] = None, user_id: Optional[str] = None) -> dict:
    """Send request to orchestrator and wait for response"""
    # Clear any stale messages from previous requests
    bridge_state.reset()
    
    # Initialize queues if needed
    if bridge_state.response_queue is None:
        bridge_state.response_queue = asyncio.Queue()
    if bridge_state.send_queue is None:
        bridge_state.send_queue = asyncio.Queue()
    
    # Mark this request time
    bridge_state.last_request_time = datetime.now(timezone.utc)
    request_id = str(uuid4())
    bridge_state.pending_request_id = request_id
    
    # Start agent in background if not running
    if not bridge_state.agent_running:
        bridge_state.agent_running = True
        # Run agent in background thread
        def run_agent():
            try:
                bridge_agent.run()
            except Exception as e:
                pass
            finally:
                bridge_state.agent_running = False
        
        bridge_state.agent_thread = threading.Thread(target=run_agent, daemon=True)
        bridge_state.agent_thread.start()
        # Give agent time to start
        await asyncio.sleep(3)
    
    # Create request JSON. Location from the user's prompt must be used as-is downstream; never substitute a different city.
    request_data = {
        "user_request": user_request,
        "location": location,
        "start_time": start_time,
        "end_time": end_time
    }
    if budget is not None:
        request_data["budget"] = budget
    if user_id is not None:
        request_data["user_id"] = user_id
    
    # Create ChatMessage
    message = ChatMessage(
        timestamp=datetime.now(timezone.utc),
        msg_id=uuid4(),
        content=[TextContent(type="text", text=json.dumps(request_data))],
    )
    
    try:
        # Wait for agent context to be available (agent needs to be running)
        max_wait = 10  # Wait up to 10 seconds for agent to start
        wait_count = 0
        while bridge_state.agent_context is None and wait_count < max_wait:
            await asyncio.sleep(0.5)
            wait_count += 0.5
        
        if bridge_state.agent_context is None:
            return {"error": "Bridge agent failed to start - context not available"}
        
        # Queue the message to be sent by the agent
        # The interval handler will pick it up and send it
        await bridge_state.send_queue.put((ORCHESTRATOR_AGENT_ADDRESS, message))
        
        # Wait a bit for the interval handler to process and send
        await asyncio.sleep(1)
        
        # Wait for response (with timeout)
        # Clear any stale responses first
        while not bridge_state.response_queue.empty():
            try:
                bridge_state.response_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        
        # Wait indefinitely for response (no timeout)
        response_text = await bridge_state.response_queue.get()
        
        # Clear request tracking after getting response
        bridge_state.last_request_time = None
        bridge_state.pending_request_id = None
        
        if response_text:
            try:
                response_data = json.loads(response_text)
                return response_data
            except json.JSONDecodeError as e:
                return {"error": f"Invalid JSON response: {response_text[:200]}"}
        else:
            return {"error": "No text content in response"}
                
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        # Clear request tracking on error
        bridge_state.last_request_time = None
        bridge_state.pending_request_id = None
        return {"error": f"Failed to send message: {str(e)}\n{error_trace}"}

@app.post("/api/schedule", response_model=ScheduleResponse)
async def create_schedule(request: ScheduleRequest, authorization: Optional[str] = Header(None)):
    """Create a schedule by calling the orchestrator agent"""
    try:
        # Validate inputs
        if not request.user_request or not request.location:
            raise HTTPException(status_code=400, detail="user_request and location are required")
        
        if not request.start_time or not request.end_time:
            raise HTTPException(status_code=400, detail="start_time and end_time are required")
        
        # Extract user_id from authorization token if available
        user_id = request.user_id  # Use user_id from request if provided
        if not user_id and authorization and authorization.startswith("Bearer "):
            token = authorization.replace("Bearer ", "")
            success, user_data = login_manager.verify_session(token)
            if success and user_data:
                user_id = user_data.get("user_id")
        
        # Send request to orchestrator (agent will be started in send_to_orchestrator)
        response = await send_to_orchestrator(
            request.user_request,
            request.location,
            request.start_time,
            request.end_time,
            request.budget,
            user_id
        )
        
        if "error" in response:
            return ScheduleResponse(success=False, error=response["error"])
        
        return ScheduleResponse(success=True, data=response)
        
    except Exception as e:
        return ScheduleResponse(success=False, error=str(e))

@app.post("/api/save-trip", response_model=SaveTripResponse)
async def save_trip(request: SaveTripRequest, authorization: Optional[str] = Header(None)):
    """Save a trip/itinerary to MongoDB"""
    try:
        # Get user_id from authorization token
        user_id = None
        if authorization and authorization.startswith("Bearer "):
            token = authorization.replace("Bearer ", "")
            success, user_data = login_manager.verify_session(token)
            if success and user_data:
                user_id = user_data.get("user_id")
        
        if not user_id:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        # Save trip to MongoDB
        success, message, trip_id = login_manager.save_trip(
            user_id=user_id,
            trip_data={
                "location": request.location,
                "start_time": request.start_time,
                "end_time": request.end_time,
                "budget": request.budget,
                "user_request": request.user_request,
                "activities": request.activities,
                "itinerary": request.itinerary
            }
        )
        
        if success:
            return SaveTripResponse(success=True, trip_id=trip_id, message=message)
        else:
            raise HTTPException(status_code=500, detail=message)
            
    except HTTPException:
        raise
    except Exception as e:
        return SaveTripResponse(success=False, message=f"Failed to save trip: {str(e)}")

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok", "orchestrator_address": ORCHESTRATOR_AGENT_ADDRESS}

async def send_to_booking_agent(items: List[dict], location: str, user_id: Optional[str] = None) -> dict:
    """Send booking request to booking agent via HTTP (direct call, no mailbox needed)"""
    # Get booking agent HTTP URL from env or use default
    booking_url = os.getenv("BOOKING_AGENT_HTTP_URL", "http://localhost:8007/api/booking")
    
    try:
        # Try using aiohttp first (async)
        try:
            import aiohttp
            
            async with aiohttp.ClientSession() as session:
                payload = {"items": items, "location": location}
                if user_id:
                    payload["user_id"] = user_id
                async with session.post(
                    booking_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        return {"error": f"Booking agent HTTP error {response.status}: {error_text}"}
                    
                    result = await response.json()
                    
                    if not result.get("success", False):
                        return {"error": result.get("error", "Unknown error from booking agent")}
                    
                    return result.get("data", {})
        except ImportError:
            # Fallback to requests library (sync, run in thread pool)
            import requests
            from requests.exceptions import RequestException
            
            def make_request():
                payload = {"items": items, "location": location}
                if user_id:
                    payload["user_id"] = user_id
                return requests.post(
                    booking_url,
                    json=payload,
                    timeout=30
                )
            
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, make_request)
            
            if response.status_code != 200:
                return {"error": f"Booking agent HTTP error {response.status_code}: {response.text}"}
            
            result = response.json()
            
            if not result.get("success", False):
                return {"error": result.get("error", "Unknown error from booking agent")}
            
            return result.get("data", {})
                
    except Exception as e:
        error_msg = str(e) if str(e) else "Unknown error"
        error_type = type(e).__name__
        # Check if it's a connection error
        error_lower = error_msg.lower()
        if any(keyword in error_lower for keyword in ["connection", "refused", "timeout", "unreachable", "cannot connect", "name or service not known"]):
            return {"error": f"Failed to connect to booking agent at {booking_url}: {error_msg}. Make sure the booking agent is running on port 8007."}
        return {"error": f"Failed to call booking agent ({error_type}): {error_msg if error_msg else 'No error message available'}"}

@app.post("/api/booking", response_model=BookingResponse)
async def create_booking(request: BookingRequest):
    """Create bookings and process payments for selected itinerary items"""
    try:
        # Validate inputs
        if not request.items or len(request.items) == 0:
            raise HTTPException(status_code=400, detail="items list cannot be empty")
        
        if not request.location:
            raise HTTPException(status_code=400, detail="location is required")
        
        # Send request to booking agent
        response = await send_to_booking_agent(request.items, request.location, request.user_id)
        
        if "error" in response:
            return BookingResponse(success=False, error=response["error"])
        
        if not response.get("success", False):
            return BookingResponse(success=False, error=response.get("error", "Unknown error"))
        
        return BookingResponse(success=True, data=response)
        
    except Exception as e:
        return BookingResponse(success=False, error=str(e))

@app.post("/api/reset")
async def reset_state():
    """Reset bridge state and clear all queues"""
    try:
        bridge_state.reset()
        return {"success": True, "message": "Bridge state reset successfully"}
    except Exception as e:
        return {"success": False, "error": str(e)}

def cleanup_on_exit():
    """Cleanup function called on exit"""
    bridge_state.reset()
    if bridge_state.agent_running:
        bridge_state.agent_running = False

# Register cleanup handlers
def signal_handler(sig, frame):
    """Handle shutdown signals"""
    cleanup_on_exit()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

if __name__ == "__main__":
    # Clear any stale state on startup
    bridge_state.reset()
    
    # Run FastAPI server
    # Bridge agent will be started automatically via async context manager in send_to_orchestrator
    try:
        uvicorn.run(app, host="0.0.0.0", port=8005, log_level="info")
    finally:
        cleanup_on_exit()

