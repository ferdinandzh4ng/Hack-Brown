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
import re
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
    start_time: Optional[str]  # ISO 8601 datetime string
    end_time: Optional[str]  # ISO 8601 datetime string
    fund_allocation_response: Optional[Dict]
    events_scraper_response: Optional[Dict]
    budget_filter_response: Optional[Dict]
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

BUDGET_FILTER_AGENT_ADDRESS = os.getenv(
    "BUDGET_FILTER_AGENT_ADDRESS",
    "agent1qdag7q4nawz3lplyhqv8pkslsxggxsuf5n5m866826f62frl4ypt5zn02rz"  # Replace with actual budgetFilterAgent address
)

# No longer needed - using send_and_receive instead of manual future handling
# _pending_responses: Dict[str, asyncio.Future] = {}

# ============================================================
# Helper Functions
# ============================================================

def remove_agent_ids(text: str) -> str:
    """
    Remove agent IDs from text in various formats.
    
    Args:
        text: Input text that may contain agent IDs
        
    Returns:
        str: Cleaned text with agent IDs removed
    """
    if not text or not isinstance(text, str):
        return text
    
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
    
    return cleaned_text if cleaned_text else text

def parse_text_to_json(text: str) -> Optional[Dict]:
    """
    Parse text into JSON format, removing agent IDs and cleaning up the input.
    Handles both direct JSON input and text with agent mentions.
    
    Args:
        text: Input text that may contain agent IDs, JSON, or plain text
        
    Returns:
        Dict: Parsed JSON data if valid JSON found, None otherwise
    """
    if not text or not isinstance(text, str):
        return None
    
    # Remove agent IDs first
    cleaned_text = remove_agent_ids(text)
    
    if not cleaned_text:
        return None
    
    # Try to parse as JSON
    try:
        data = json.loads(cleaned_text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        # Not valid JSON, return None to treat as plain text
        pass
    
    return None

# ============================================================
# LangGraph Workflow Nodes
# ============================================================

async def call_intent_dispatcher_agent(
    ctx: Context, 
    user_input: str, 
    sender: str, 
    conversation_state: Optional[Dict],
    location: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None
) -> Dict:
    """Call intent dispatcher agent via Fetch.ai using send_and_receive"""
    try:
        # If we have location, start_time, or end_time, send them as JSON to agents.py
        if location or start_time or end_time:
            message_data = {
                "user_request": user_input
            }
            if location:
                message_data["location"] = location
            if start_time:
                message_data["start_time"] = start_time
            if end_time:
                message_data["end_time"] = end_time
            
            message_text = json.dumps(message_data)
            ctx.logger.info(f"Sending JSON to intent dispatcher with location={location}, start_time={start_time}, end_time={end_time}")
        else:
            # No JSON values, send plain text
            message_text = user_input
        
        # The intent dispatcher agent expects a ChatMessage with the user input
        message = ChatMessage(
            timestamp=datetime.now(timezone.utc),
            msg_id=uuid4(),
            content=[TextContent(type="text", text=message_text)],
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
                
                # Check if it's a clarification response (has type "clarification_needed")
                if isinstance(response_data, dict) and response_data.get("type") == "clarification_needed":
                    return {
                        "type": "clarification_needed",
                        "data": {
                            "prompt": response_data.get("prompt", response_text),
                            "conversation_state": response_data.get("conversation_state", conversation_state)
                        }
                    }
                # Check if it's a dispatch plan (has activity_list)
                elif isinstance(response_data, dict) and "activity_list" in response_data:
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
                # If not JSON, it's likely a clarification prompt (plain text) - fallback for backward compatibility
                # The intent dispatcher should now send clarification prompts as JSON, but handle plain text as fallback
                ctx.logger.info("Response is not JSON, treating as clarification prompt (fallback)")
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
        location = state.get("location")
        start_time = state.get("start_time")
        end_time = state.get("end_time")
        
        # Call intent dispatcher agent via Fetch.ai with location and times
        result = await call_intent_dispatcher_agent(
            ctx, user_input, sender, conversation_state, 
            location=location, start_time=start_time, end_time=end_time
        )
        
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
    """Node 2: Extract parameters from dispatch plan and use JSON inputs"""
    try:
        dispatch_plan = state.get("dispatch_plan")
        
        if not dispatch_plan:
            state["error"] = "No dispatch plan available"
            return state
        
        # Extract activities and budget from dispatch plan (from user_request)
        activities = dispatch_plan.get("activity_list", [])
        constraints = dispatch_plan.get("constraints", {})
        
        state["activities"] = activities
        # Location, start_time, end_time come from JSON input (already set in handle_user_message)
        # Only override location if not already set from JSON
        if not state.get("location"):
            state["location"] = constraints.get("location", "")
        
        # Budget comes from dispatch plan (extracted from user_request)
        state["budget"] = constraints.get("budget") or 500.0  # Default budget if not provided
        
        # Calculate timeframe from start_time and end_time if available
        start_time = state.get("start_time")
        end_time = state.get("end_time")
        
        if start_time and end_time:
            # Try to calculate timeframe from dates
            try:
                from datetime import datetime as dt
                start = dt.fromisoformat(start_time.replace('Z', '+00:00'))
                end = dt.fromisoformat(end_time.replace('Z', '+00:00'))
                days = (end - start).days
                hours = (end - start).total_seconds() / 3600
                if days == 0:
                    if hours < 12:
                        state["timeframe"] = f"{int(hours)} hours"
                    else:
                        state["timeframe"] = "1 day"
                elif days == 1:
                    state["timeframe"] = "weekend"
                else:
                    state["timeframe"] = f"{days} days"
            except Exception as e:
                # Error calculating timeframe, use default
                state["timeframe"] = constraints.get("timeframe") or "weekend"
        else:
            state["timeframe"] = constraints.get("timeframe") or "weekend"
        
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

async def call_budget_filter_agent(ctx: Context, events_response: Dict, fund_response: Dict) -> Dict:
    """Call budget filter agent using send_and_receive with both agent outputs"""
    try:
        # Combine both responses for the budget filter
        request_data = {
            "events": events_response,
            "fund": fund_response
        }
        
        message = ChatMessage(
            timestamp=datetime.now(timezone.utc),
            msg_id=uuid4(),
            content=[TextContent(type="text", text=json.dumps(request_data))],
        )
        
        ctx.logger.info(f"Sending request to budget filter agent: {BUDGET_FILTER_AGENT_ADDRESS}")
        
        # Use send_and_receive
        reply, status = await ctx.send_and_receive(
            BUDGET_FILTER_AGENT_ADDRESS,
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
            
            ctx.logger.info(f"Received response from budget filter agent: {len(response_text)} chars")
            
            # Parse JSON response
            try:
                return json.loads(response_text)
            except json.JSONDecodeError as e:
                ctx.logger.error(f"JSON parse error: {e}, content: {response_text[:200]}")
                return {"error": "Failed to parse budget filter response"}
        else:
            ctx.logger.error(f"Failed to receive response from budget filter agent: {status}")
            return {"error": f"Failed to receive response: {status}"}
        
    except Exception as e:
        ctx.logger.error(f"Error calling budget filter agent: {e}")
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

async def call_budget_filter_node(state: OrchestratorState, ctx: Context) -> OrchestratorState:
    """Node 4: Call budget filter agent with both agent outputs"""
    try:
        fund_allocation = state.get("fund_allocation_response", {})
        events_scraper = state.get("events_scraper_response", {})
        activities = state.get("activities", [])  # These are the interest_activities
        
        # Check for errors
        if fund_allocation.get("error") or events_scraper.get("error"):
            ctx.logger.warning("One or both agents returned errors, skipping budget filter")
            state["budget_filter_response"] = {"error": "Cannot filter due to agent errors"}
            return state
        
        # Add interest_activities to events_scraper data for budget filter
        # EventsScraperAgent doesn't return interest_activities, so we add them from state
        events_with_interests = events_scraper.copy()
        events_with_interests["interest_activities"] = activities
        events_with_interests["location"] = state.get("location", "")
        events_with_interests["budget"] = state.get("budget", 0)
        events_with_interests["start_time"] = state.get("start_time")
        events_with_interests["end_time"] = state.get("end_time")
        
        # Also add to fund_allocation for consistency
        fund_with_times = fund_allocation.copy()
        fund_with_times["start_time"] = state.get("start_time")
        fund_with_times["end_time"] = state.get("end_time")
        
        ctx.logger.info("Calling budget filter agent with both agent outputs")
        
        # Call budget filter agent
        budget_filter_response = await call_budget_filter_agent(ctx, events_with_interests, fund_with_times)
        
        state["budget_filter_response"] = budget_filter_response
        return state
    except Exception as e:
        state["error"] = f"Budget filter error: {str(e)}"
        return state

def combine_outputs_node(state: OrchestratorState) -> OrchestratorState:
    """Node 5: Return budget filter output as final result"""
    try:
        budget_filter = state.get("budget_filter_response", {})
        
        # Log what we got from budget filter
        print(f"[Combine Outputs] Budget filter response type: {type(budget_filter)}")
        print(f"[Combine Outputs] Budget filter response keys: {list(budget_filter.keys()) if isinstance(budget_filter, dict) else 'not a dict'}")
        print(f"[Combine Outputs] Budget filter has error: {budget_filter.get('error') if isinstance(budget_filter, dict) else 'N/A'}")
        
        # Use filtered output if available, otherwise return error
        if budget_filter and not budget_filter.get("error"):
            # Return just the budget filter output - it contains everything needed
            state["final_output"] = budget_filter
            print(f"[Combine Outputs] Set final_output from budget_filter: {len(str(budget_filter))} chars")
        else:
            # If filter failed, return error response
            error_msg = budget_filter.get("error", "Budget filter not executed") if isinstance(budget_filter, dict) else "Budget filter response is invalid"
            state["final_output"] = {
                "type": "error",
                "message": error_msg,
                "location": state.get("location", ""),
                "budget": state.get("budget", 0)
            }
            print(f"[Combine Outputs] Set final_output to error: {error_msg}")
        
        return state
    except Exception as e:
        print(f"[Combine Outputs] Error: {e}")
        import traceback
        print(traceback.format_exc())
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
        
        def make_budget_filter_node():
            async def budget_filter_node(state: OrchestratorState) -> OrchestratorState:
                return await call_budget_filter_node(state, ctx)
            return budget_filter_node
        
        # Add nodes
        workflow.add_node("dispatch_intent", make_dispatch_node())
        workflow.add_node("extract_parameters", extract_parameters_node)
        workflow.add_node("parallel_calls", make_parallel_node())
        workflow.add_node("budget_filter", make_budget_filter_node())
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
        workflow.add_edge("parallel_calls", "budget_filter")
        workflow.add_edge("budget_filter", "combine_outputs")
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
    
    # FIRST: Check if this is from one of our target agents - ignore immediately
    # With send_and_receive, responses should be handled automatically
    # ALL messages from target agents should be ignored - they're either duplicates or stale
    if sender in [INTENT_DISPATCHER_AGENT_ADDRESS, FUND_ALLOCATION_AGENT_ADDRESS, EVENTS_SCRAPER_AGENT_ADDRESS, BUDGET_FILTER_AGENT_ADDRESS]:
        # Check message age - if it's old, definitely ignore
        try:
            now = datetime.now(timezone.utc)
            msg_time = msg.timestamp
            if msg_time.tzinfo is None:
                msg_time = msg_time.replace(tzinfo=timezone.utc)
            message_age = (now - msg_time).total_seconds()
            if message_age > 60:  # Older than 1 minute - definitely stale
                return  # Ignore silently
        except Exception:
            pass
        
        # Even if recent, ignore ALL messages from target agents
        # send_and_receive handles responses, so any message here is a duplicate or unexpected
        return  # Ignore silently - no logging to reduce noise
    
    # Now log the message (only if it's from a user, not a target agent)
    ctx.logger.info(f"=== Orchestrator received ChatMessage ===")
    ctx.logger.info(f"Sender: {sender}")
    ctx.logger.info(f"Orchestrator's own address: {ctx.agent.address}")
    ctx.logger.info(f"Message ID: {msg.msg_id}")
    
    # Check if message is stale (older than 2 minutes) - be stricter to prevent old request floods
    # Handle both timezone-aware and timezone-naive timestamps
    try:
        now = datetime.now(timezone.utc)
        msg_time = msg.timestamp
        
        # If timestamp is naive, assume it's UTC
        if msg_time.tzinfo is None:
            msg_time = msg_time.replace(tzinfo=timezone.utc)
        
        message_age = (now - msg_time).total_seconds()
        if message_age > 120:  # 2 minutes - stricter threshold
            ctx.logger.info(f"Ignoring stale message (age: {message_age:.0f}s, ID: {msg.msg_id})")
            return
    except Exception as e:
        ctx.logger.warning(f"Error checking message age: {e}, proceeding with message")
    
    # Track processed message IDs to prevent duplicate processing
    processed_messages_key = "processed_message_ids"
    processed_ids_dict = ctx.storage.get(processed_messages_key) or {}
    
    # Clean old message IDs - remove entries older than 10 minutes and keep only last 50
    now_iso = datetime.now(timezone.utc).isoformat()
    now_dt = datetime.now(timezone.utc)
    cleaned_dict = {}
    for msg_id, timestamp_str in processed_ids_dict.items():
        try:
            timestamp_dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            age = (now_dt - timestamp_dt).total_seconds()
            if age < 600:  # Keep if less than 10 minutes old
                cleaned_dict[msg_id] = timestamp_str
        except Exception:
            # Invalid timestamp, skip it
            continue
    
    # If still too many, keep only most recent 50
    if len(cleaned_dict) > 50:
        sorted_ids = sorted(cleaned_dict.items(), key=lambda x: x[1], reverse=True)[:50]
        cleaned_dict = dict(sorted_ids)
        ctx.logger.info(f"Cleared old processed message IDs, keeping {len(cleaned_dict)} most recent")
    
    processed_ids_dict = cleaned_dict
    
    # Check if we've already processed this message
    msg_id_str = str(msg.msg_id)
    if msg_id_str in processed_ids_dict:
        # Check if it's recent (within last 5 minutes)
        try:
            last_processed_time = processed_ids_dict[msg_id_str]
            last_processed_dt = datetime.fromisoformat(last_processed_time.replace('Z', '+00:00'))
            time_since_processed = (now_dt - last_processed_dt).total_seconds()
            if time_since_processed < 300:  # 5 minutes
                ctx.logger.debug(f"Ignoring duplicate message (ID: {msg.msg_id}, processed {time_since_processed:.0f}s ago)")
                return
        except Exception:
            # Can't parse timestamp, remove it and continue
            del processed_ids_dict[msg_id_str]
    
    # Mark this message as processed with timestamp
    processed_ids_dict[msg_id_str] = now_iso
    ctx.storage.set(processed_messages_key, processed_ids_dict)
    
    # Log message content
    user_input_preview = ""
    for item in msg.content:
        if isinstance(item, TextContent):
            user_input_preview = item.text[:200]
            ctx.logger.info(f"Message content preview: {user_input_preview}...")
            break
    
    
    # Check for stale error messages - ignore error messages that look like they're from previous requests
    if user_input_preview:
        error_indicators = [
            "Unable to parse input string into valid JSON",
            "Previous request failed",
            "type\": \"error\"",
            "\"error\":",
            "parse input string"  # This is the specific error from the terminal output
        ]
        if any(indicator in user_input_preview for indicator in error_indicators):
            ctx.logger.info(f"Ignoring stale error message: {user_input_preview[:100]}")
            return
        
        # Check if the message looks like old response data from agents
        # Fund allocation responses have "activities" with "activity" and "cost" fields
        # Budget filter responses have "activities" with "start_time" and scheduled data
        response_indicators = [
            '"activities":' in user_input_preview and '"leftover_budget"' in user_input_preview,  # Fund allocation response
            '"activities":' in user_input_preview and '"start_time":' in user_input_preview,  # Budget filter response
            '"activity":' in user_input_preview and '"cost":' in user_input_preview,  # Fund allocation format
        ]
        if any(response_indicators):
            ctx.logger.info(f"Ignoring message that looks like old agent response data")
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
        
        # Parse text to JSON and remove agent IDs
        parsed_json = parse_text_to_json(user_input)
        
        # Initialize variables
        user_request_text = user_input
        location_from_json = None
        start_time_from_json = None
        end_time_from_json = None
        
        if parsed_json:
            # Check if it's an error response - ignore stale error messages
            if parsed_json.get("error") or parsed_json.get("type") == "error":
                error_message = parsed_json.get("error") or parsed_json.get("message", "")
                # Check for specific stale error patterns
                stale_error_patterns = [
                    "Unable to parse input string into valid JSON",
                    "parse input string",
                    "Expected formats:",
                    "EventScraperAgent:",
                    "FundAllocationAgent:"
                ]
                if any(pattern in str(error_message) for pattern in stale_error_patterns):
                    ctx.logger.warning(f"Ignoring stale error message: {error_message[:100]}")
                    return
                ctx.logger.warning(f"Received error as input, this might be a loop: {parsed_json}")
                error_msg = create_text_chat(json.dumps({"type": "error", "message": "Previous request failed. Please try again with a new request."}))
                await ctx.send(sender, error_msg)
                return
            
            # Check if it's the new JSON format with start_time, end_time, location, user_request
            if "user_request" in parsed_json and "location" in parsed_json:
                user_request_text = parsed_json.get("user_request", "")
                location_from_json = parsed_json.get("location", "")
                start_time_from_json = parsed_json.get("start_time")
                end_time_from_json = parsed_json.get("end_time")
                ctx.logger.info(f"Parsed JSON input: location={location_from_json}, start_time={start_time_from_json}, end_time={end_time_from_json}")
            else:
                # JSON but not the expected format, treat user_request as the cleaned text
                user_request_text = remove_agent_ids(user_input)
        else:
            # Not JSON, remove agent IDs and use as plain text
            user_request_text = remove_agent_ids(user_input)
        
        ctx.logger.info(f"Processing user request: {user_request_text[:100]}...")
        
        # Get conversation state from storage
        conversation_state_key = f"conversation_state_{sender}"
        conversation_state = ctx.storage.get(conversation_state_key)
        
        # Check if conversation state is stale (older than 10 minutes) and clear it
        if conversation_state:
            state_timestamp = conversation_state.get("timestamp")
            if state_timestamp:
                try:
                    state_time = datetime.fromisoformat(state_timestamp.replace('Z', '+00:00'))
                    state_age = (datetime.now(timezone.utc) - state_time).total_seconds()
                    if state_age > 600:  # 10 minutes
                        ctx.logger.info(f"Clearing stale conversation state (age: {state_age:.0f}s)")
                        ctx.storage.set(conversation_state_key, None)
                        conversation_state = None
                except Exception as e:
                    ctx.logger.warning(f"Error checking conversation state age: {e}")
                    # If we can't parse the timestamp, clear it to be safe
                    ctx.storage.set(conversation_state_key, None)
                    conversation_state = None
        
        # Check if we're waiting for clarification from a previous vague request
        # Only use conversation_state data if:
        # 1. conversation_state exists and indicates waiting for clarification
        # 2. AND the current message is NOT a new request (i.e., no JSON data with location/user_request)
        # If user sends a new request with JSON data, treat it as a NEW request and clear old conversation_state
        is_new_request_with_json = parsed_json and "user_request" in parsed_json and "location" in parsed_json
        
        if conversation_state and conversation_state.get("waiting_for_clarification") and not is_new_request_with_json:
            # User is replying to a clarification prompt (plain text response, not a new JSON request)
            ctx.logger.info("User is replying to a clarification prompt - preserving original request data")
            # Extract original data from conversation_state (these take priority)
            original_location = conversation_state.get("location", "")
            original_start_time = conversation_state.get("start_time")
            original_end_time = conversation_state.get("end_time")
            
            # Use original values if they exist, otherwise fall back to JSON input
            location_from_json = original_location or location_from_json or ""
            start_time_from_json = original_start_time if original_start_time and original_start_time != "null" else start_time_from_json
            end_time_from_json = original_end_time if original_end_time and original_end_time != "null" else end_time_from_json
            
            ctx.logger.info(f"Using original request data: location={location_from_json}, start_time={start_time_from_json}, end_time={end_time_from_json}")
            ctx.logger.info(f"User's clarification response: {user_request_text}")
        elif is_new_request_with_json and conversation_state:
            # User sent a new request with JSON data - clear old conversation_state
            ctx.logger.info("User sent a new request with JSON data - clearing old conversation_state")
            ctx.storage.set(conversation_state_key, None)
            conversation_state = None
        
        # Initialize state with JSON values if provided (or from conversation_state if waiting for clarification)
        initial_state: OrchestratorState = {
            "user_input": user_request_text,  # Use user_request for intent dispatcher (or clarification response)
            "sender": sender,
            "conversation_state": conversation_state,
            "dispatch_result": None,
            "dispatch_plan": None,
            "activities": [],
            "location": location_from_json or "",  # Use location from JSON or conversation_state
            "budget": 0.0,
            "timeframe": "",
            "start_time": start_time_from_json,  # Use start_time from JSON or conversation_state
            "end_time": end_time_from_json,  # Use end_time from JSON or conversation_state
            "fund_allocation_response": None,
            "events_scraper_response": None,
            "budget_filter_response": None,
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
        
        ctx.logger.info(f"Sending final output to sender: {sender[:20]}... ({len(output_text)} chars)")
        ctx.logger.info(f"Final output preview: {output_text[:200]}...")
        
        response_msg = create_text_chat(
            output_text,
            end_session=final_output.get("type") != "clarification_needed"
        )
        
        try:
            await ctx.send(sender, response_msg)
            ctx.logger.info(f"Successfully sent response to {sender[:20]}...")
        except Exception as send_err:
            ctx.logger.error(f"Failed to send response: {send_err}")
            import traceback
            ctx.logger.error(traceback.format_exc())
        
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

# Cleanup handler that runs once on startup
_startup_cleanup_done = False

@agent.on_interval(period=1.0)
async def startup_cleanup_once(ctx: Context):
    """Clean up old processed message IDs once on startup"""
    global _startup_cleanup_done
    if _startup_cleanup_done:
        return  # Only run once
    
    _startup_cleanup_done = True
    processed_messages_key = "processed_message_ids"
    old_ids = ctx.storage.get(processed_messages_key)
    if old_ids:
        ctx.storage.set(processed_messages_key, {})
        ctx.logger.info(f"Cleared {len(old_ids)} old processed message IDs on startup")

if __name__ == "__main__":
    print(f"LangGraph Orchestrator Agent address: {agent.address}")
    print(f"Intent Dispatcher Agent address: {INTENT_DISPATCHER_AGENT_ADDRESS}")
    print(f"Fund Allocation Agent address: {FUND_ALLOCATION_AGENT_ADDRESS}")
    print(f"Events Scraper Agent address: {EVENTS_SCRAPER_AGENT_ADDRESS}")
    print(f"Budget Filter Agent address: {BUDGET_FILTER_AGENT_ADDRESS}")
    print("\nStarting orchestrator agent...")
    print("Will clear old processed message IDs on startup...")
    agent.run()

