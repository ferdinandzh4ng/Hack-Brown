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
from typing import Optional
from dotenv import load_dotenv

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

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
        print("Bridge state reset - queues cleared")

# Global state instance
bridge_state = BridgeState()

# Create bridge agent to communicate with orchestrator
bridge_agent = Agent(
    name="BridgeAgent",
    seed="bridge-server-seed",
    port=8008,
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
    # Check if this is a response from orchestrator
    if sender == ORCHESTRATOR_AGENT_ADDRESS:
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
        
        # Only process if we have a pending request (within last 2 minutes)
        if bridge_state.last_request_time:
            time_since_request = (datetime.now(timezone.utc) - bridge_state.last_request_time).total_seconds()
            if time_since_request > 120:  # 2 minutes
                ctx.logger.warning(f"Ignoring message - no recent request (last request: {time_since_request:.0f}s ago)")
                return
        
        # Extract text content
        response_text = ""
        for item in msg.content:
            if isinstance(item, TextContent):
                response_text = item.text
                break
        
        # Put response in queue
        if response_text and bridge_state.response_queue is not None:
            try:
                await bridge_state.response_queue.put(response_text)
                ctx.logger.info(f"Received response from orchestrator: {len(response_text)} chars")
            except Exception as e:
                ctx.logger.error(f"Error putting response in queue: {e}")
                import traceback
                ctx.logger.error(traceback.format_exc())

# Interval handler to process send queue
@bridge_agent.on_interval(period=0.5)
async def process_send_queue(ctx: Context):
    """Periodically check send queue and send messages - clear stale messages"""
    bridge_state.agent_context = ctx  # Store context for use in send_to_orchestrator
    
    if bridge_state.send_queue is not None:
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
                    
                    await ctx.send(target_address, message_to_send)
                    ctx.logger.info(f"Sent message to {target_address}")
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

class ScheduleResponse(BaseModel):
    success: bool
    data: Optional[dict] = None
    error: Optional[str] = None

async def send_to_orchestrator(user_request: str, location: str, start_time: str, end_time: str) -> dict:
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
                print(f"Error running bridge agent: {e}")
                import traceback
                traceback.print_exc()
            finally:
                bridge_state.agent_running = False
        
        bridge_state.agent_thread = threading.Thread(target=run_agent, daemon=True)
        bridge_state.agent_thread.start()
        # Give agent time to start
        await asyncio.sleep(3)
    
    # Create request JSON
    request_data = {
        "user_request": user_request,
        "location": location,
        "start_time": start_time,
        "end_time": end_time
    }
    
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
        
        try:
            response_text = await asyncio.wait_for(bridge_state.response_queue.get(), timeout=120.0)
            
            # Clear request tracking after getting response
            bridge_state.last_request_time = None
            bridge_state.pending_request_id = None
            
            if response_text:
                try:
                    response_data = json.loads(response_text)
                    return response_data
                except json.JSONDecodeError:
                    return {"error": f"Invalid JSON response: {response_text[:200]}"}
            else:
                return {"error": "No text content in response"}
        except asyncio.TimeoutError:
            # Clear request tracking on timeout
            bridge_state.last_request_time = None
            bridge_state.pending_request_id = None
            return {"error": "Timeout waiting for response from orchestrator"}
                
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        # Clear request tracking on error
        bridge_state.last_request_time = None
        bridge_state.pending_request_id = None
        return {"error": f"Failed to send message: {str(e)}\n{error_trace}"}

@app.post("/api/schedule", response_model=ScheduleResponse)
async def create_schedule(request: ScheduleRequest):
    """Create a schedule by calling the orchestrator agent"""
    try:
        # Validate inputs
        if not request.user_request or not request.location:
            raise HTTPException(status_code=400, detail="user_request and location are required")
        
        if not request.start_time or not request.end_time:
            raise HTTPException(status_code=400, detail="start_time and end_time are required")
        
        # Send request to orchestrator (agent will be started in send_to_orchestrator)
        response = await send_to_orchestrator(
            request.user_request,
            request.location,
            request.start_time,
            request.end_time
        )
        
        if "error" in response:
            return ScheduleResponse(success=False, error=response["error"])
        
        return ScheduleResponse(success=True, data=response)
        
    except Exception as e:
        return ScheduleResponse(success=False, error=str(e))

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok", "orchestrator_address": ORCHESTRATOR_AGENT_ADDRESS}

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
    print("Cleaning up bridge server...")
    bridge_state.reset()
    if bridge_state.agent_running:
        bridge_state.agent_running = False

# Register cleanup handlers
def signal_handler(sig, frame):
    """Handle shutdown signals"""
    print("\nShutdown signal received, cleaning up...")
    cleanup_on_exit()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

if __name__ == "__main__":
    # Clear any stale state on startup
    print("Starting bridge server - clearing stale state...")
    bridge_state.reset()
    
    # Run FastAPI server
    # Bridge agent will be started automatically via async context manager in send_to_orchestrator
    try:
        uvicorn.run(app, host="0.0.0.0", port=8005, log_level="info")
    finally:
        cleanup_on_exit()

