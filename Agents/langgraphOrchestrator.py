"""
LangGraph Orchestrator Agent - Coordinates workflow using LangGraph
Takes user input, dispatches intent, and coordinates parallel agent calls
"""
from uagents import Agent, Context, Protocol, Model
from uagents_core.contrib.protocols.chat import (
    ChatMessage,
    TextContent,
    chat_protocol_spec,
    ChatAcknowledgement,
)
from typing import Optional, List, Dict, Any, TypedDict, Annotated
from datetime import datetime, timezone
from uuid import uuid4
import json
import os
import asyncio
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END

load_dotenv()

# ============================================================
# Models
# ============================================================

class IntentDispatcherResponse(Model):
    """Response model from intent dispatcher agent - matches ChatMessage format"""
    pass  # We'll use ChatMessage directly

class FundAllocationResponse(Model):
    """Response model from fund allocation agent - matches ChatMessage format"""
    pass  # We'll use ChatMessage directly

class EventsScraperResponse(Model):
    """Response model from events scraper agent - matches ChatMessage format"""
    pass  # We'll use ChatMessage directly

class OrchestratorState(TypedDict):
    """State for LangGraph workflow"""
    user_input: str
    sender: str
    conversation_state: Optional[Dict]
    dispatch_result: Optional[Dict]
    dispatch_plan: Optional[Dict]
    activities: List[str]
    location: str
    budget: float
    timeframe: str
    fund_allocation_response: Optional[Dict]
    events_scraper_response: Optional[Dict]
    final_output: Optional[Dict]
    error: Optional[str]

# ============================================================
# Agent Setup
# ============================================================

agent = Agent(
    name="LangGraphOrchestrator",
    seed=os.getenv("ORCHESTRATOR_AGENT_SEED", "langgraph-orchestrator-seed"),
    port=8004,
    mailbox=True,
    publish_agent_details=True,
    network="testnet"
)

chat_proto = Protocol(spec=chat_protocol_spec)

# ============================================================
# Agent Addresses (configure these with your actual agent addresses)
# ============================================================

INTENT_DISPATCHER_AGENT_ADDRESS = os.getenv(
    "INTENT_DISPATCHER_AGENT_ADDRESS",
    "agent1q2943p8ja20slch8hkgnrvwscvuasnxfre0dfhzhlf744lvrpuhqurty7j4"  # Replace with actual intent dispatcher agent address (agents.py)
)

FUND_ALLOCATION_AGENT_ADDRESS = os.getenv(
    "FUND_ALLOCATION_AGENT_ADDRESS",
    "agent1qwl6edrzmwsls5vvslkrmfh2xkg7ur88gu4k7gqtv4xa47sczv63vvj3l0z"  # Replace with actual fundAllocationAgent address
)

EVENTS_SCRAPER_AGENT_ADDRESS = os.getenv(
    "EVENTS_SCRAPER_AGENT_ADDRESS",
    "agent1q0ngan90nxrwqs27uj6q7scr2fv2ddsx42kvvkkqkv5rgunzwndeguyx9cy"  # Replace with actual eventsScraperAgent address
)

# No longer needed - using send_and_receive instead of manual future handling
# _pending_responses: Dict[str, asyncio.Future] = {}

# ============================================================
# LangGraph Workflow Nodes
# ============================================================

async def call_intent_dispatcher_agent(ctx: Context, user_input: str, sender: str, conversation_state: Optional[Dict]) -> Dict:
    """Call intent dispatcher agent via Fetch.ai using send_and_receive"""
    try:
        # The intent dispatcher agent expects a ChatMessage with the user input
        message = ChatMessage(
            timestamp=datetime.now(timezone.utc),
            msg_id=uuid4(),
            content=[TextContent(type="text", text=user_input)],
        )
        
        ctx.logger.info(f"Sending request to intent dispatcher agent: {INTENT_DISPATCHER_AGENT_ADDRESS}")
        ctx.logger.info(f"Orchestrator address (for dispatcher to respond to): {ctx.agent.address}")
        
        # Use send_and_receive - acknowledgements are disabled in agents.py
        ctx.logger.info("Waiting for response from intent dispatcher using send_and_receive...")
        reply, status = await ctx.send_and_receive(
            INTENT_DISPATCHER_AGENT_ADDRESS,
            message,
            response_type=ChatMessage,  # Expect ChatMessage response
            timeout=120.0
        )
        
        if isinstance(reply, ChatMessage):
            # Extract text content from ChatMessage
            response_text = ""
            for item in reply.content:
                if isinstance(item, TextContent):
                    response_text = item.text
                    break
            
            if not response_text:
                return {"type": "error", "data": {"error": "No text content in response"}}
            
            ctx.logger.info(f"✓ Received response from intent dispatcher: {len(response_text)} chars")
            ctx.logger.info(f"Intent dispatcher response: {response_text[:200]}...")
            
            # Try to parse as JSON first
            try:
                response_data = json.loads(response_text)
                
                # Check if it's a dispatch plan (has activity_list)
                if isinstance(response_data, dict) and "activity_list" in response_data:
                    return {
                        "type": "dispatch_plan",
                        "data": response_data
                    }
                # Check if it's an error
                elif isinstance(response_data, dict) and response_data.get("type") == "error":
                    return {
                        "type": "error",
                        "data": response_data
                    }
                # Otherwise, treat as dispatch plan if it's a dict
                elif isinstance(response_data, dict):
                    return {
                        "type": "dispatch_plan",
                        "data": response_data
                    }
            except json.JSONDecodeError:
                # If not JSON, it's likely a clarification prompt (plain text)
                # The intent dispatcher sends clarification prompts as plain text
                ctx.logger.info("Response is not JSON, treating as clarification prompt")
                return {
                    "type": "clarification_needed",
                    "data": {
                        "prompt": response_text,
                        "conversation_state": conversation_state
                    }
                }
            
            return {"type": "error", "data": {"error": "Unable to parse intent dispatcher response"}}
        else:
            ctx.logger.error(f"Failed to receive response from intent dispatcher: {status}")
            return {"type": "error", "data": {"error": f"Failed to receive response: {status}"}}
        
    except Exception as e:
        ctx.logger.error(f"Error calling intent dispatcher agent: {e}")
        import traceback
        ctx.logger.error(traceback.format_exc())
        return {"type": "error", "data": {"error": str(e)}}

async def dispatch_intent_node(state: OrchestratorState, ctx: Context) -> OrchestratorState:
    """Node 1: Dispatch user intent by calling intent dispatcher agent"""
    try:
        user_input = state["user_input"]
        sender = state["sender"]
        conversation_state = state.get("conversation_state")
        
        # Call intent dispatcher agent via Fetch.ai
        result = await call_intent_dispatcher_agent(ctx, user_input, sender, conversation_state)
        
        state["dispatch_result"] = result
        
        # If we got a dispatch plan, extract the data
        if result.get("type") == "dispatch_plan":
            state["dispatch_plan"] = result.get("data", {})
        elif result.get("type") == "clarification_needed":
            # Store conversation state for next interaction
            state["conversation_state"] = result.get("data", {}).get("conversation_state")
        
        return state
    except Exception as e:
        state["error"] = f"Intent dispatch error: {str(e)}"
        return state

def extract_parameters_node(state: OrchestratorState) -> OrchestratorState:
    """Node 2: Extract parameters from dispatch plan"""
    try:
        dispatch_plan = state.get("dispatch_plan")
        
        if not dispatch_plan:
            state["error"] = "No dispatch plan available"
            return state
        
        # Extract activities (these are general categories like "eat", "sightsee", etc.)
        activities = dispatch_plan.get("activity_list", [])
        constraints = dispatch_plan.get("constraints", {})
        
        state["activities"] = activities
        state["location"] = constraints.get("location", "")
        state["budget"] = constraints.get("budget") or 500.0  # Default budget if not provided
        state["timeframe"] = constraints.get("timeframe") or "weekend"  # Default timeframe
        
        # Extract timeframe from start_time and end_time if available
        start_time = constraints.get("start_time")
        end_time = constraints.get("end_time")
        
        if start_time and end_time:
            # Try to calculate timeframe from dates
            try:
                from datetime import datetime as dt
                start = dt.fromisoformat(start_time.replace('Z', '+00:00'))
                end = dt.fromisoformat(end_time.replace('Z', '+00:00'))
                days = (end - start).days
                if days == 0:
                    state["timeframe"] = "1 day"
                elif days == 1:
                    state["timeframe"] = "weekend"
                else:
                    state["timeframe"] = f"{days} days"
            except:
                pass
        
        return state
    except Exception as e:
        state["error"] = f"Parameter extraction error: {str(e)}"
        return state

async def call_fund_allocation_agent(ctx: Context, activities: List[str], location: str, budget: float) -> Dict:
    """Call fund allocation agent using send_and_receive"""
    try:
        request_data = {
            "activities": activities,
            "location": location,
            "budget": budget
        }
        
        message = ChatMessage(
            timestamp=datetime.now(timezone.utc),
            msg_id=uuid4(),
            content=[TextContent(type="text", text=json.dumps(request_data))],
        )
        
        ctx.logger.info(f"Sending request to fund allocation agent: {FUND_ALLOCATION_AGENT_ADDRESS}")
        
        # Use send_and_receive
        reply, status = await ctx.send_and_receive(
            FUND_ALLOCATION_AGENT_ADDRESS,
            message,
            response_type=ChatMessage,
            timeout=120.0
        )
        
        if isinstance(reply, ChatMessage):
            # Extract text content
            response_text = ""
            for item in reply.content:
                if isinstance(item, TextContent):
                    response_text = item.text
                    break
            
            if not response_text:
                return {"error": "No text content in response"}
            
            ctx.logger.info(f"Received response from fund allocation agent: {len(response_text)} chars")
            
            # Parse JSON response
            try:
                return json.loads(response_text)
            except json.JSONDecodeError as e:
                ctx.logger.error(f"JSON parse error: {e}, content: {response_text[:200]}")
                return {"error": "Failed to parse fund allocation response"}
        else:
            ctx.logger.error(f"Failed to receive response from fund allocation agent: {status}")
            return {"error": f"Failed to receive response: {status}"}
        
    except Exception as e:
        ctx.logger.error(f"Error calling fund allocation agent: {e}")
        import traceback
        ctx.logger.error(traceback.format_exc())
        return {"error": str(e)}

async def call_events_scraper_agent(ctx: Context, activities: List[str], location: str, budget: float, timeframe: str) -> Dict:
    """Call events scraper agent using send_and_receive"""
    try:
        request_data = {
            "location": location,
            "timeframe": timeframe,
            "budget": budget,
            "interest_activities": activities  # Events scraper expects interest_activities
        }
        
        message = ChatMessage(
            timestamp=datetime.now(timezone.utc),
            msg_id=uuid4(),
            content=[TextContent(type="text", text=json.dumps(request_data))],
        )
        
        ctx.logger.info(f"Sending request to events scraper agent: {EVENTS_SCRAPER_AGENT_ADDRESS}")
        
        # Use send_and_receive
        reply, status = await ctx.send_and_receive(
            EVENTS_SCRAPER_AGENT_ADDRESS,
            message,
            response_type=ChatMessage,
            timeout=120.0
        )
        
        if isinstance(reply, ChatMessage):
            # Extract text content
            response_text = ""
            for item in reply.content:
                if isinstance(item, TextContent):
                    response_text = item.text
                    break
            
            if not response_text:
                return {"error": "No text content in response"}
            
            ctx.logger.info(f"Received response from events scraper agent: {len(response_text)} chars")
            
            # Parse JSON response
            try:
                return json.loads(response_text)
            except json.JSONDecodeError as e:
                ctx.logger.error(f"JSON parse error: {e}, content: {response_text[:200]}")
                return {"error": "Failed to parse events scraper response"}
        else:
            ctx.logger.error(f"Failed to receive response from events scraper agent: {status}")
            return {"error": f"Failed to receive response: {status}"}
        
    except Exception as e:
        ctx.logger.error(f"Error calling events scraper agent: {e}")
        import traceback
        ctx.logger.error(traceback.format_exc())
        return {"error": str(e)}

async def parallel_agent_calls_node(state: OrchestratorState, ctx: Context) -> OrchestratorState:
    """Node 3: Call both agents in parallel"""
    try:
        activities = state["activities"]
        location = state["location"]
        budget = state["budget"]
        timeframe = state["timeframe"]
        
        if not activities or not location:
            state["error"] = "Missing required parameters: activities or location"
            return state
        
        ctx.logger.info(f"Calling agents in parallel: activities={activities}, location={location}, budget={budget}")
        
        # Create tasks for parallel execution
        fund_allocation_task = call_fund_allocation_agent(ctx, activities, location, budget)
        events_scraper_task = call_events_scraper_agent(ctx, activities, location, budget, timeframe)
        
        # Execute both in parallel
        fund_allocation_response, events_scraper_response = await asyncio.gather(
            fund_allocation_task,
            events_scraper_task,
            return_exceptions=True
        )
        
        # Handle exceptions
        if isinstance(fund_allocation_response, Exception):
            ctx.logger.error(f"Fund allocation error: {fund_allocation_response}")
            state["fund_allocation_response"] = {"error": str(fund_allocation_response)}
        else:
            state["fund_allocation_response"] = fund_allocation_response
        
        if isinstance(events_scraper_response, Exception):
            ctx.logger.error(f"Events scraper error: {events_scraper_response}")
            state["events_scraper_response"] = {"error": str(events_scraper_response)}
        else:
            state["events_scraper_response"] = events_scraper_response
        
        return state
    except Exception as e:
        state["error"] = f"Parallel agent calls error: {str(e)}"
        return state

def combine_outputs_node(state: OrchestratorState) -> OrchestratorState:
    """Node 4: Combine outputs from both agents"""
    try:
        fund_allocation = state.get("fund_allocation_response", {})
        events_scraper = state.get("events_scraper_response", {})
        location = state.get("location", "")
        budget = state.get("budget", 0)
        
        # Combine the outputs
        combined_output = {
            "location": location,
            "budget": budget,
            "fund_allocation": fund_allocation,
            "events_scraper": events_scraper,
            "summary": {
                "activities_found": len(events_scraper.get("activities", [])),
                "total_estimated_cost": fund_allocation.get("activities", []),
                "leftover_budget": fund_allocation.get("leftover_budget", 0)
            }
        }
        
        state["final_output"] = combined_output
        return state
    except Exception as e:
        state["error"] = f"Combine outputs error: {str(e)}"
        return state

def should_continue(state: OrchestratorState) -> str:
    """Conditional edge: Check if we should continue or handle errors/clarifications"""
    if state.get("error"):
        return "error"
    
    dispatch_result = state.get("dispatch_result", {})
    if dispatch_result.get("type") == "clarification_needed":
        return "clarification"
    
    if dispatch_result.get("type") == "dispatch_plan":
        return "continue"
    
    return "error"

def handle_clarification_node(state: OrchestratorState) -> OrchestratorState:
    """Handle clarification needed"""
    dispatch_result = state.get("dispatch_result", {})
    clarification_data = dispatch_result.get("data", {})
    state["final_output"] = {
        "type": "clarification_needed",
        "prompt": clarification_data.get("prompt", "Please provide more information"),
        "conversation_state": clarification_data.get("conversation_state")
    }
    return state

def handle_error_node(state: OrchestratorState) -> OrchestratorState:
    """Handle errors"""
    error = state.get("error", "Unknown error")
    state["final_output"] = {
        "type": "error",
        "message": error
    }
    return state

# ============================================================
# LangGraph Workflow Setup
# ============================================================

# Store workflow per context (since we need ctx in nodes)
_workflows: Dict[str, Any] = {}

def get_or_create_workflow(ctx: Context) -> Any:
    """Get or create workflow for a context"""
    ctx_id = str(id(ctx))
    
    if ctx_id not in _workflows:
        workflow = StateGraph(OrchestratorState)
        
        # Create wrapper functions that capture ctx
        def make_dispatch_node():
            async def dispatch_node(state: OrchestratorState) -> OrchestratorState:
                return await dispatch_intent_node(state, ctx)
            return dispatch_node
        
        def make_parallel_node():
            async def parallel_node(state: OrchestratorState) -> OrchestratorState:
                return await parallel_agent_calls_node(state, ctx)
            return parallel_node
        
        # Add nodes
        workflow.add_node("dispatch_intent", make_dispatch_node())
        workflow.add_node("extract_parameters", extract_parameters_node)
        workflow.add_node("parallel_calls", make_parallel_node())
        workflow.add_node("combine_outputs", combine_outputs_node)
        workflow.add_node("handle_clarification", handle_clarification_node)
        workflow.add_node("handle_error", handle_error_node)
        
        # Set entry point
        workflow.set_entry_point("dispatch_intent")
        
        # Add edges
        workflow.add_conditional_edges(
            "dispatch_intent",
            should_continue,
            {
                "continue": "extract_parameters",
                "clarification": "handle_clarification",
                "error": "handle_error"
            }
        )
        
        workflow.add_edge("extract_parameters", "parallel_calls")
        workflow.add_edge("parallel_calls", "combine_outputs")
        workflow.add_edge("combine_outputs", END)
        workflow.add_edge("handle_clarification", END)
        workflow.add_edge("handle_error", END)
        
        _workflows[ctx_id] = workflow.compile()
    
    return _workflows[ctx_id]

# ============================================================
# Message Handlers
# ============================================================

@chat_proto.on_message(ChatMessage)
async def handle_user_message(ctx: Context, sender: str, msg: ChatMessage):
    """Handle incoming user messages and orchestrate workflow"""
    ctx.logger.info(f"=== Orchestrator received ChatMessage ===")
    ctx.logger.info(f"Sender: {sender}")
    ctx.logger.info(f"Orchestrator's own address: {ctx.agent.address}")
    ctx.logger.info(f"Message ID: {msg.msg_id}")
    
    # Log message content
    for item in msg.content:
        if isinstance(item, TextContent):
            ctx.logger.info(f"Message content preview: {item.text[:200]}...")
            break
    
    # Check if this is from one of our target agents (shouldn't happen with send_and_receive, but handle just in case)
    if sender in [INTENT_DISPATCHER_AGENT_ADDRESS, FUND_ALLOCATION_AGENT_ADDRESS, EVENTS_SCRAPER_AGENT_ADDRESS]:
        ctx.logger.warning(f"Received unexpected message from target agent {sender[:20]}... This shouldn't happen with send_and_receive - message may be a late response or duplicate.")
        # Don't process as user input - just log it
        return
    
    # Otherwise, this is a user message - send acknowledgement
    try:
        await ctx.send(
            sender,
            ChatAcknowledgement(timestamp=datetime.now(timezone.utc), acknowledged_msg_id=msg.msg_id),
        )
    except Exception as e:
        ctx.logger.warning(f"Error sending acknowledgement: {e}")
    
    try:
        # Extract user input from message
        user_input = ""
        for item in msg.content:
            if isinstance(item, TextContent):
                user_input = item.text
                break
        
        if not user_input:
            error_msg = create_text_chat("No text content found in message")
            await ctx.send(sender, error_msg)
            return
        
        # Check if the input is already an error response (from a previous failed attempt)
        try:
            parsed = json.loads(user_input)
            if isinstance(parsed, dict) and parsed.get("error"):
                ctx.logger.warning(f"Received error as input, this might be a loop: {parsed}")
                # Don't process errors as user input - return error to user
                error_msg = create_text_chat(json.dumps({"type": "error", "message": "Previous request failed. Please try again with a new request."}))
                await ctx.send(sender, error_msg)
                return
        except (json.JSONDecodeError, ValueError):
            # Not JSON, continue normally
            pass
        
        ctx.logger.info(f"Processing user input: {user_input[:100]}...")
        
        # Get conversation state from storage
        conversation_state_key = f"conversation_state_{sender}"
        conversation_state = ctx.storage.get(conversation_state_key)
        
        # Initialize state
        initial_state: OrchestratorState = {
            "user_input": user_input,
            "sender": sender,
            "conversation_state": conversation_state,
            "dispatch_result": None,
            "dispatch_plan": None,
            "activities": [],
            "location": "",
            "budget": 0.0,
            "timeframe": "",
            "fund_allocation_response": None,
            "events_scraper_response": None,
            "final_output": None,
            "error": None
        }
        
        # Create and run workflow
        workflow = get_or_create_workflow(ctx)
        final_state = await workflow.ainvoke(initial_state)
        
        # Update conversation state if needed
        if final_state.get("conversation_state"):
            ctx.storage.set(conversation_state_key, final_state["conversation_state"])
        elif conversation_state and final_state.get("final_output", {}).get("type") == "dispatch_plan":
            # Clear conversation state after successful dispatch
            ctx.storage.set(conversation_state_key, None)
        
        # Send final output
        final_output = final_state.get("final_output", {})
        output_text = json.dumps(final_output, indent=2)
        
        response_msg = create_text_chat(
            output_text,
            end_session=final_output.get("type") != "clarification_needed"
        )
        
        await ctx.send(sender, response_msg)
        
    except Exception as e:
        ctx.logger.error(f"Orchestrator error: {e}")
        import traceback
        ctx.logger.error(traceback.format_exc())
        error_msg = create_text_chat(f"Error processing request: {str(e)}")
        try:
            await ctx.send(sender, error_msg)
        except:
            pass

@chat_proto.on_message(ChatAcknowledgement)
async def handle_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
    """Handle acknowledgement messages - these are expected and should not interfere with send_and_receive"""
    # Just log and ignore - acknowledgements are separate from the actual response
    ctx.logger.info(f"Orchestrator received acknowledgement from {sender} for msg {msg.acknowledged_msg_id}")
    
    # If this is from the intent dispatcher and we're waiting, log it
    if sender == INTENT_DISPATCHER_AGENT_ADDRESS:
        ctx.logger.info(f"Received acknowledgement from intent dispatcher while waiting for response")

def create_text_chat(text: str, end_session: bool = False) -> ChatMessage:
    """Helper to create text chat message"""
    from uagents_core.contrib.protocols.chat import EndSessionContent
    content = [TextContent(type="text", text=text)]
    if end_session:
        content.append(EndSessionContent(type="end-session"))
    return ChatMessage(
        timestamp=datetime.now(timezone.utc),
        msg_id=uuid4(),
        content=content,
    )

# No longer needed - using send_and_receive which handles timeouts internally
# @agent.on_interval(period=5.0)
# async def check_pending_responses(ctx: Context):
#     """Periodically check if we have pending responses waiting"""
#     pass

# Include chat protocol
agent.include(chat_proto, publish_manifest=True)

if __name__ == "__main__":
    print(f"LangGraph Orchestrator Agent address: {agent.address}")
    print(f"Intent Dispatcher Agent address: {INTENT_DISPATCHER_AGENT_ADDRESS}")
    print(f"Fund Allocation Agent address: {FUND_ALLOCATION_AGENT_ADDRESS}")
    print(f"Events Scraper Agent address: {EVENTS_SCRAPER_AGENT_ADDRESS}")
    print("\nStarting orchestrator agent...")
    agent.run()

