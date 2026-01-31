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
from datetime import datetime
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
        timestamp=datetime.utcnow(),
        msg_id=uuid4(),
        content=content,
    )

@chat_proto.on_message(ChatMessage)
async def handle_message(ctx: Context, sender: str, msg: ChatMessage):
    ctx.logger.info(f"Got a message from {sender}: {msg.content}")
    ctx.storage.set(str(ctx.session), sender)
    
    await ctx.send(
        sender,
        ChatAcknowledgement(timestamp=datetime.utcnow(), acknowledged_msg_id=msg.msg_id),
    )
    
    for item in msg.content:
        if isinstance(item, StartSessionContent):
            ctx.logger.info(f"Got a start session message from {sender}")
            continue
        elif isinstance(item, TextContent):
            ctx.logger.info(f"Got a message from {sender}: {item.text}")
            ctx.storage.set(str(ctx.session), sender)
            
            # Use structured output to extract intent parameters
            await ctx.send(
                AI_AGENT_ADDRESS,
                StructuredOutputPrompt(
                    prompt=item.text, 
                    output_schema=IntentRequest.schema()
                ),
            )
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
        await ctx.send(
            session_sender,
            create_text_chat(
                "Sorry, I couldn't process your request. Please try again later."
            ),
        )
        return
    
    # Extract intent parameters from structured output
    try:
        intent_data = msg.output if isinstance(msg.output, dict) else {}
        user_request = intent_data.get("user_request", "")
        
        if not user_request:
            # Fallback: try to reconstruct from other fields or use raw output
            user_request = str(msg.output)
            
        ctx.logger.info(f'Processing intent request: {user_request}')
        
        # Get conversation state
        conversation_state_key = f"conversation_state_{session_sender}"
        conversation_state = ctx.storage.get(conversation_state_key)
        
        # Process intent dispatch
        result = dispatch_intent(user_request, session_sender, conversation_state)
        
        if result["type"] == "error":
            error_msg = json.dumps(result["data"], indent=2)
            await ctx.send(session_sender, create_text_chat(error_msg))
        elif result["type"] == "clarification_needed":
            # Store conversation state for next message
            ctx.storage.set(conversation_state_key, result["data"]["conversation_state"])
            await ctx.send(session_sender, create_text_chat(result["data"]["prompt"], end_session=False))
        elif result["type"] == "dispatch_plan":
            # Clear conversation state if it exists
            if conversation_state:
                ctx.storage.delete(conversation_state_key)
            
            dispatch_plan_json = json.dumps(result["data"], indent=2)
            await ctx.send(session_sender, create_text_chat(dispatch_plan_json, end_session=True))
            
    except Exception as err:
        ctx.logger.error(f"Error processing structured output: {err}")
        import traceback
        ctx.logger.error(traceback.format_exc())
        await ctx.send(
            session_sender,
            create_text_chat(
                "Sorry, I couldn't process your request. Please try again later."
            ),
        )

agent.include(chat_proto, publish_manifest=True)
agent.include(struct_output_client_proto, publish_manifest=True)

# Print agent address for mailbox setup
print(f"Your agent's address is: {agent.address}")

if __name__ == "__main__":
    agent.run()

