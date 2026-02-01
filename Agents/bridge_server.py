#!/usr/bin/env python3
"""
HTTP Bridge Server for Orchestrator Agent
Provides REST API endpoint to communicate with the LangGraph Orchestrator agent
"""
import asyncio
import json
import os
from datetime import datetime, timezone
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

# Response storage for bridge communication
_response_queue: Optional[asyncio.Queue] = None
_send_queue: Optional[asyncio.Queue] = None
_agent_running = False

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
    """Handle response from orchestrator"""
    global _response_queue
    
    # Check if this is a response from orchestrator
    if sender == ORCHESTRATOR_AGENT_ADDRESS and _response_queue is not None:
        # Extract text content
        response_text = ""
        for item in msg.content:
            if isinstance(item, TextContent):
                response_text = item.text
                break
        
        # Put response in queue
        if response_text:
            await _response_queue.put(response_text)

# Interval handler to process send queue
@bridge_agent.on_interval(period=0.5)
async def process_send_queue(ctx: Context):
    """Periodically check send queue and send messages"""
    global _send_queue
    if _send_queue is not None:
        try:
            # Process all messages in queue
            while not _send_queue.empty():
                try:
                    target_address, message_to_send = _send_queue.get_nowait()
                    await ctx.send(target_address, message_to_send)
                    ctx.logger.info(f"Sent message to {target_address}")
                except asyncio.QueueEmpty:
                    break
                except Exception as e:
                    ctx.logger.error(f"Error sending queued message: {e}")
        except Exception as e:
            ctx.logger.error(f"Error processing send queue: {e}")

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
    global _response_queue, _send_queue, _agent_running
    
    # Initialize queues if needed
    if _response_queue is None:
        _response_queue = asyncio.Queue()
    if _send_queue is None:
        _send_queue = asyncio.Queue()
    
    # Start agent in background if not running
    if not _agent_running:
        _agent_running = True
        # Run agent in background thread
        import threading
        def run_agent():
            bridge_agent.run()
        
        agent_thread = threading.Thread(target=run_agent, daemon=True)
        agent_thread.start()
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
        # Queue the message to be sent by the agent
        # The interval handler will pick it up and send it
        await _send_queue.put((ORCHESTRATOR_AGENT_ADDRESS, message))
        
        # Wait a bit for the interval handler to process and send
        await asyncio.sleep(1)
        
        # Wait for response (with timeout)
        try:
            response_text = await asyncio.wait_for(_response_queue.get(), timeout=120.0)
            
            if response_text:
                try:
                    response_data = json.loads(response_text)
                    return response_data
                except json.JSONDecodeError:
                    return {"error": f"Invalid JSON response: {response_text[:200]}"}
            else:
                return {"error": "No text content in response"}
        except asyncio.TimeoutError:
            return {"error": "Timeout waiting for response from orchestrator"}
                
    except Exception as e:
        return {"error": f"Failed to send message: {str(e)}"}

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

if __name__ == "__main__":
    # Run FastAPI server
    # Bridge agent will be started automatically via async context manager in send_to_orchestrator
    uvicorn.run(app, host="0.0.0.0", port=8005, log_level="info")

