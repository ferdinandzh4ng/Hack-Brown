"""
Agent code for hosting on Agentverse
This is the main agent file that follows the structured output protocol pattern
"""
from uagents import Agent, Context, Protocol
from uagents_core.contrib.protocols.chat import (
    ChatAcknowledgement,
    ChatMessage,
    TextContent,
    chat_protocol_spec,
    StartSessionContent,
    EndSessionContent,
)
from functions import dispatch_intent, IntentRequest
from datetime import datetime, timezone
from uuid import uuid4
from typing import Any, Dict, Optional, Tuple
from uagents import Model
import json
import os
import re
from dotenv import load_dotenv

load_dotenv()

class StructuredOutputPrompt(Model):
    prompt: str
    output_schema: Dict[str, Any]

class StructuredOutputResponse(Model):
    output: Dict[str, Any]

# AI Agent address for structured output
AI_AGENT_ADDRESS = "agent1qtlpfshtlcxekgrfcpmv7m9zpajuwu7d5jfyachvpa4u3dkt6k0uwwp2lct"  # OpenAI AI agent address

agent = Agent(
    name="AgentCity_Intent_Dispatcher",
    seed=os.getenv("AGENT_SEED_PHRASE", "intent-dispatcher-seed"),
    port=8001,
    mailbox=True,
    publish_agent_details=True,
    readme_path="README.md",
    network="testnet"  # Use testnet to avoid needing funds for contract registration
)

chat_proto = Protocol(spec=chat_protocol_spec)
struct_output_client_proto = Protocol(
    name="StructuredOutputClientProtocol", version="0.1.0"
)

def extract_times_from_text(text: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Extract start_time and end_time from user's text prompt.
    Looks for patterns like:
    - "from 5pm to 11pm"
    - "5pm-11pm"
    - "5:00 PM to 11:00 PM"
    - "between 5pm and 11pm"
    - "starting at 5pm until 11pm"
    - "5pm until 11pm"
    - "at 5pm" (single time - use as start_time, end_time = start_time + 6 hours)
    """
    if not text:
        return None, None
    
    text_lower = text.lower()
    start_time = None
    end_time = None
    
    # Pattern 1: "from X to Y" or "X to Y" or "X-Y" or "between X and Y"
    patterns = [
        r'(?:from|starting at|at)\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm|a\.m\.|p\.m\.)?)\s+(?:to|until|-|and)\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm|a\.m\.|p\.m\.)?)',
        r'(\d{1,2}(?::\d{2})?\s*(?:am|pm|a\.m\.|p\.m\.)?)\s+(?:to|until|-|and)\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm|a\.m\.|p\.m\.)?)',
        r'between\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm|a\.m\.|p\.m\.)?)\s+and\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm|a\.m\.|p\.m\.)?)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text_lower, re.IGNORECASE)
        if match:
            start_str = match.group(1).strip()
            end_str = match.group(2).strip()
            
            # Normalize time strings
            start_time = normalize_time_string(start_str)
            end_time = normalize_time_string(end_str)
            
            if start_time and end_time:
                return start_time, end_time
    
    # Pattern 2: Single time mentioned (e.g., "at 5pm")
    single_time_pattern = r'(?:at|starting at|from)\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm|a\.m\.|p\.m\.)?)'
    match = re.search(single_time_pattern, text_lower, re.IGNORECASE)
    if match:
        start_str = match.group(1).strip()
        start_time = normalize_time_string(start_str)
        if start_time:
            # If only start time is given, assume 6 hours duration
            end_time = add_hours_to_time(start_time, 6)
            return start_time, end_time
    
    return None, None

def normalize_time_string(time_str: str) -> Optional[str]:
    """
    Normalize time string to format like "5pm" or "5:00pm"
    Returns time in format suitable for constraints (e.g., "5pm", "11pm")
    """
    if not time_str:
        return None
    
    # Remove extra spaces
    time_str = time_str.strip()
    
    # Remove periods from a.m./p.m.
    time_str = re.sub(r'\.', '', time_str)
    
    # Extract hour and am/pm
    match = re.match(r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)', time_str, re.IGNORECASE)
    if match:
        hour = int(match.group(1))
        minute = match.group(2) if match.group(2) else "00"
        am_pm = match.group(3).lower()
        
        # Convert to 24-hour format for easier manipulation
        if am_pm == 'pm' and hour != 12:
            hour_24 = hour + 12
        elif am_pm == 'am' and hour == 12:
            hour_24 = 0
        else:
            hour_24 = hour
        
        # Return in simple format like "5pm" or "5:00pm"
        if minute == "00":
            return f"{hour}pm" if am_pm == 'pm' else f"{hour}am"
        else:
            return f"{hour}:{minute}{am_pm}"
    
    return None

def add_hours_to_time(time_str: str, hours: int) -> Optional[str]:
    """
    Add hours to a time string and return new time string
    """
    if not time_str:
        return None
    
    # Parse time string
    match = re.match(r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)', time_str, re.IGNORECASE)
    if not match:
        return None
    
    hour = int(match.group(1))
    minute = int(match.group(2)) if match.group(2) else 0
    am_pm = match.group(3).lower()
    
    # Convert to 24-hour format
    if am_pm == 'pm' and hour != 12:
        hour_24 = hour + 12
    elif am_pm == 'am' and hour == 12:
        hour_24 = 0
    else:
        hour_24 = hour
    
    # Add hours
    hour_24 = (hour_24 + hours) % 24
    
    # Convert back to 12-hour format
    if hour_24 == 0:
        new_hour = 12
        new_am_pm = 'am'
    elif hour_24 < 12:
        new_hour = hour_24
        new_am_pm = 'am'
    elif hour_24 == 12:
        new_hour = 12
        new_am_pm = 'pm'
    else:
        new_hour = hour_24 - 12
        new_am_pm = 'pm'
    
    if minute == 0:
        return f"{new_hour}{new_am_pm}"
    else:
        return f"{new_hour}:{minute:02d}{new_am_pm}"

def create_text_chat(text: str, end_session: bool = False) -> ChatMessage:
    content = [TextContent(type="text", text=text)]
    if end_session:
        content.append(EndSessionContent(type="end-session"))
    return ChatMessage(
        timestamp=datetime.now(timezone.utc),
        msg_id=uuid4(),
        content=content,
    )

async def safe_send(ctx: Context, destination: str, message: ChatMessage, max_retries: int = 2) -> bool:
    """
    Safely send a message to a destination agent with retry logic.
    Returns True if successful, False otherwise.
    """
    import asyncio
    
    # Extract message content for logging
    msg_content = ""
    for item in message.content:
        if hasattr(item, 'text'):
            msg_content = item.text[:100] if len(item.text) > 100 else item.text
            break
    
    ctx.logger.info(f"Attempting to send message to {destination}")
    ctx.logger.info(f"Message content preview: {msg_content}...")
    ctx.logger.info(f"Message ID: {message.msg_id}")
    
    for attempt in range(max_retries + 1):
        try:
            await ctx.send(destination, message)
            ctx.logger.info(f"Successfully sent message to {destination} (attempt {attempt + 1})")
            ctx.logger.info(f"Message should arrive at destination. If not received, check: 1) Agent is online, 2) Mailbox is enabled, 3) Network connectivity")
            return True
        except Exception as e:
            error_msg = str(e).lower()
            # Check if it's an endpoint resolution error
            if "unable to resolve" in error_msg or "endpoint" in error_msg:
                ctx.logger.warning(
                    f"Attempt {attempt + 1}/{max_retries + 1}: Unable to resolve endpoint for agent {destination}. "
                    f"This usually means the agent is not registered, has no mailbox, or is offline. Error: {e}"
                )
                if attempt < max_retries:
                    # Wait before retrying (exponential backoff)
                    await asyncio.sleep(2 ** attempt)
                    continue
                else:
                    ctx.logger.error(
                        f"Failed to send message to {destination} after {max_retries + 1} attempts. "
                        f"Agent may not be registered or may be offline. Please ensure the agent has: "
                        f"1. mailbox=True configured, 2. publish_agent_details=True, 3. is registered on Agentverse"
                    )
                    return False
            else:
                # Different error, log and return
                ctx.logger.error(f"Error sending message to {destination}: {e}")
                import traceback
                ctx.logger.error(traceback.format_exc())
                return False
    
    return False

@chat_proto.on_message(ChatMessage)
async def handle_message(ctx: Context, sender: str, msg: ChatMessage):
    ctx.logger.info(f"Got a message from {sender}: {msg.content}")
    ctx.logger.info(f"Current session: {ctx.session}")
    # Store sender with session AND also store it separately to ensure we can retrieve it
    ctx.storage.set(str(ctx.session), sender)
    # Also store with a more persistent key in case session changes
    ctx.storage.set(f"last_sender_{ctx.session}", sender)
    
    # NOTE: Not sending ChatAcknowledgement to avoid interfering with ctx.send_and_receive
    # The orchestrator uses send_and_receive which can match acknowledgements instead of actual responses
    
    for item in msg.content:
        if isinstance(item, StartSessionContent):
            ctx.logger.info(f"Got a start session message from {sender}")
            continue
        elif isinstance(item, TextContent):
            ctx.logger.info(f"Got a message from {sender}: {item.text}")
            # Store sender again to ensure it's saved
            ctx.storage.set(str(ctx.session), sender)
            ctx.storage.set(f"last_sender_{ctx.session}", sender)
            
            # Store the original message text for fallback if structured output fails
            original_message_key = f"original_message_{ctx.session}"
            ctx.storage.set(original_message_key, item.text)
            
            # Extract time information from user's text
            extracted_start_time, extracted_end_time = extract_times_from_text(item.text)
            if extracted_start_time or extracted_end_time:
                ctx.logger.info(f"Extracted times from text: start_time={extracted_start_time}, end_time={extracted_end_time}")
                # Store extracted times for use in structured output response handler
                ctx.storage.set(f"extracted_start_time_{ctx.session}", extracted_start_time)
                ctx.storage.set(f"extracted_end_time_{ctx.session}", extracted_end_time)
            
            # Use structured output to extract intent parameters
            try:
                await ctx.send(
                    AI_AGENT_ADDRESS,
                    StructuredOutputPrompt(
                        prompt=item.text, 
                        output_schema=IntentRequest.schema()
                    ),
                )
            except Exception as e:
                ctx.logger.error(f"Error sending structured output request to AI agent: {e}")
                # Send error message back to user
                error_msg = create_text_chat("Sorry, I encountered an error processing your request. Please try again.")
                await safe_send(ctx, sender, error_msg)
        else:
            ctx.logger.info(f"Got unexpected content from {sender}")

@chat_proto.on_message(ChatAcknowledgement)
async def handle_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
    ctx.logger.info(
        f"Got an acknowledgement from {sender} for {msg.acknowledged_msg_id}"
    )

@struct_output_client_proto.on_message(StructuredOutputResponse)
async def handle_structured_output_response(
    ctx: Context, sender: str, msg: StructuredOutputResponse
):
    ctx.logger.info(f'Here is the message from structured output {msg.output}')
    ctx.logger.info(f'Current session when receiving structured output: {ctx.session}')
    # Try to get session sender - try multiple keys in case session changed
    session_sender = ctx.storage.get(str(ctx.session))
    if session_sender is None:
        # Try the alternative key
        session_sender = ctx.storage.get(f"last_sender_{ctx.session}")
        ctx.logger.info(f'Session sender not found with primary key, trying alternative: {session_sender}')
    
    ctx.logger.info(f'Session sender retrieved from storage: {session_sender}')
    if session_sender is None:
        ctx.logger.error(
            "Discarding message because no session sender found in storage"
        )
        ctx.logger.error(f"Available storage keys might not include session: {ctx.session}")
        return
    
    if "<UNKNOWN>" in str(msg.output):
        error_msg = create_text_chat(
            "Sorry, I couldn't process your request. Please try again later."
        )
        await safe_send(ctx, session_sender, error_msg)
        return
    
    # Extract intent parameters from structured output
    try:
        intent_data = msg.output if isinstance(msg.output, dict) else {}
        
        # Check if we got the schema structure with data in 'properties'
        # Some structured output returns: {'type': 'object', 'properties': {'user_request': '...', ...}}
        if intent_data.get("type") == "object" and "properties" in intent_data:
            properties = intent_data.get("properties", {})
            # Check if properties contains actual data (not schema definitions)
            if isinstance(properties, dict) and "user_request" in properties:
                # Data is nested in properties - extract it
                user_request = properties.get("user_request", "")
                ctx.logger.info(f'Extracted data from properties field: {user_request}')
            else:
                # It's actually a schema definition, use original message
                original_message_key = f"original_message_{ctx.session}"
                user_request = ctx.storage.get(original_message_key)
                if not user_request:
                    user_request = "Unable to extract request"
                ctx.logger.warning(f'Received schema instead of data, using original message: {user_request}')
        else:
            # We got actual extracted data directly
            user_request = intent_data.get("user_request", "")
            
            if not user_request:
                # Fallback: get original message from storage
                original_message_key = f"original_message_{ctx.session}"
                user_request = ctx.storage.get(original_message_key)
                if not user_request:
                    user_request = str(msg.output)
            
            # Check if we extracted times from the text and use them if structured output didn't provide times
            extracted_start_time = ctx.storage.get(f"extracted_start_time_{ctx.session}")
            extracted_end_time = ctx.storage.get(f"extracted_end_time_{ctx.session}")
            
            # If times were extracted from text and not in structured output, add them to user_request context
            if (extracted_start_time or extracted_end_time) and not intent_data.get("start_time") and not intent_data.get("end_time"):
                ctx.logger.info(f'Using extracted times: start_time={extracted_start_time}, end_time={extracted_end_time}')
                # Append time information to user_request so dispatch_intent can use it
                if extracted_start_time and extracted_end_time:
                    user_request = f"{user_request} (Time: {extracted_start_time} to {extracted_end_time})"
                elif extracted_start_time:
                    user_request = f"{user_request} (Start time: {extracted_start_time})"
            
            ctx.logger.info(f'Processing intent request: {user_request}')
            
            # Get conversation state
            conversation_state_key = f"conversation_state_{session_sender}"
            conversation_state = ctx.storage.get(conversation_state_key)
            
            # Process intent dispatch
            result = dispatch_intent(user_request, session_sender, conversation_state)
            
            # If we have extracted times and the dispatch plan doesn't have them, add them
            if result.get("type") == "dispatch_plan" and (extracted_start_time or extracted_end_time):
                dispatch_data = result.get("data", {})
                constraints = dispatch_data.get("constraints", {})
                
                # Only add times if they're not already in constraints
                if not constraints.get("start_time") and extracted_start_time:
                    constraints["start_time"] = extracted_start_time
                    ctx.logger.info(f'Added extracted start_time to dispatch plan: {extracted_start_time}')
                
                if not constraints.get("end_time") and extracted_end_time:
                    constraints["end_time"] = extracted_end_time
                    ctx.logger.info(f'Added extracted end_time to dispatch plan: {extracted_end_time}')
                
                dispatch_data["constraints"] = constraints
                result["data"] = dispatch_data
        
        if result["type"] == "error":
            error_msg = json.dumps(result["data"], indent=2)
            await safe_send(ctx, session_sender, create_text_chat(error_msg))
        elif result["type"] == "clarification_needed":
            # Store conversation state for next message
            ctx.storage.set(conversation_state_key, result["data"]["conversation_state"])
            await safe_send(ctx, session_sender, create_text_chat(result["data"]["prompt"], end_session=False))
        elif result["type"] == "dispatch_plan":
            # Clear conversation state if it exists (set to None to clear it)
            if conversation_state:
                ctx.storage.set(conversation_state_key, None)
            
            dispatch_plan_json = json.dumps(result["data"], indent=2)
            ctx.logger.info(f'Sending dispatch plan to session_sender: {session_sender}')
            ctx.logger.info(f'Dispatch plan length: {len(dispatch_plan_json)} chars')
            ctx.logger.info(f'Intent dispatcher agent address: {ctx.agent.address}')
            
            # Try sending directly first, then fall back to safe_send
            response_message = create_text_chat(dispatch_plan_json, end_session=True)
            try:
                ctx.logger.info(f'Attempting direct send to {session_sender}...')
                await ctx.send(session_sender, response_message)
                ctx.logger.info(f'Direct send successful to {session_sender}')
            except Exception as direct_error:
                ctx.logger.warning(f'Direct send failed: {direct_error}, trying safe_send...')
                send_result = await safe_send(ctx, session_sender, response_message)
                if not send_result:
                    ctx.logger.error(f'Both direct send and safe_send failed for {session_sender}')
            
    except Exception as err:
        ctx.logger.error(f"Error processing structured output: {err}")
        import traceback
        ctx.logger.error(traceback.format_exc())
        error_msg = create_text_chat(
            "Sorry, I couldn't process your request. Please try again later."
        )
        await safe_send(ctx, session_sender, error_msg)

agent.include(chat_proto, publish_manifest=True)
agent.include(struct_output_client_proto, publish_manifest=True)

# Print agent address for mailbox setup
print(f"Your agent's address is: {agent.address}")

if __name__ == "__main__":
    agent.run()

