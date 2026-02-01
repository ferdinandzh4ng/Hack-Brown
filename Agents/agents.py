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
from typing import Any, Dict
from uagents import Model
import json
import os
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
    
    for attempt in range(max_retries + 1):
        try:
            await ctx.send(destination, message)
            ctx.logger.info(f"Successfully sent message to {destination}")
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
                return False
    
    return False

@chat_proto.on_message(ChatMessage)
async def handle_message(ctx: Context, sender: str, msg: ChatMessage):
    ctx.logger.info(f"Got a message from {sender}: {msg.content}")
    ctx.storage.set(str(ctx.session), sender)
    
    # Send acknowledgement (non-blocking, don't fail if it doesn't work)
    try:
        await ctx.send(
            sender,
            ChatAcknowledgement(timestamp=datetime.now(timezone.utc), acknowledged_msg_id=msg.msg_id),
        )
    except Exception as e:
        ctx.logger.warning(f"Error sending acknowledgement to {sender}: {e}")
        # Don't fail the entire message handling if acknowledgement fails
    
    for item in msg.content:
        if isinstance(item, StartSessionContent):
            ctx.logger.info(f"Got a start session message from {sender}")
            continue
        elif isinstance(item, TextContent):
            ctx.logger.info(f"Got a message from {sender}: {item.text}")
            ctx.storage.set(str(ctx.session), sender)
            
            # Store the original message text for fallback if structured output fails
            original_message_key = f"original_message_{ctx.session}"
            ctx.storage.set(original_message_key, item.text)
            
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
    session_sender = ctx.storage.get(str(ctx.session))
    if session_sender is None:
        ctx.logger.error(
            "Discarding message because no session sender found in storage"
        )
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
            
        ctx.logger.info(f'Processing intent request: {user_request}')
        
        # Get conversation state
        conversation_state_key = f"conversation_state_{session_sender}"
        conversation_state = ctx.storage.get(conversation_state_key)
        
        # Process intent dispatch
        result = dispatch_intent(user_request, session_sender, conversation_state)
        
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
            await safe_send(ctx, session_sender, create_text_chat(dispatch_plan_json, end_session=True))
            
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

