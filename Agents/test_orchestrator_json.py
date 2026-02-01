"""
Test script to send JSON input to the orchestrator
Usage: python test_orchestrator_json.py
"""
import asyncio
import json
import os
from datetime import datetime, timezone
from uuid import uuid4
from dotenv import load_dotenv

from uagents import Agent, Context, Protocol
from uagents_core.contrib.protocols.chat import (
    ChatMessage,
    TextContent,
    chat_protocol_spec,
)

# Load environment variables
load_dotenv()

# Orchestrator agent address
ORCHESTRATOR_AGENT_ADDRESS = os.getenv(
    "ORCHESTRATOR_AGENT_ADDRESS",
    "agent1qg2akmff6ke58spye465yje4e5fvdk6faku59h2akjjtu5hmkf8rqy346qj"  # Replace with your orchestrator address
)

# Create a test agent to send the message
test_agent = Agent(
    name="OrchestratorTestAgent",
    seed="test-orchestrator-json-seed",
    port=8007,
    mailbox=True,
    publish_agent_details=True,
    network="testnet"
)

chat_proto = Protocol(spec=chat_protocol_spec)

@chat_proto.on_message(ChatMessage)
async def handle_response(ctx: Context, sender: str, msg: ChatMessage):
    """Handle response from orchestrator"""
    print(f"\n{'='*60}")
    print(f"✓ SUCCESS: Received response from {sender}")
    print(f"{'='*60}")
    
    for item in msg.content:
        if isinstance(item, TextContent):
            print(f"\nResponse content:")
            try:
                # Try to pretty print if it's JSON
                response_data = json.loads(item.text)
                print(json.dumps(response_data, indent=2))
            except json.JSONDecodeError:
                # Not JSON, print as text
                print(item.text)
            break
    
    print(f"\n{'='*60}")
    print("Test completed successfully!")
    print(f"{'='*60}\n")

test_agent.include(chat_proto, publish_manifest=False)

async def send_test_json():
    """Send test JSON to orchestrator"""
    print(f"\n{'='*60}")
    print("Orchestrator JSON Input Test")
    print(f"{'='*60}")
    print(f"Orchestrator Address: {ORCHESTRATOR_AGENT_ADDRESS}")
    print(f"Test Agent Address: {test_agent.address}")
    print(f"{'='*60}\n")
    
    # Load test JSON
    json_path = os.path.join(os.path.dirname(__file__), "test_orchestrator_input.json")
    try:
        with open(json_path, 'r') as f:
            test_json = json.load(f)
    except FileNotFoundError:
        print(f"Error: Could not find {json_path}")
        return
    
    print("Test JSON input:")
    print(json.dumps(test_json, indent=2))
    print()
    
    # Create test message with JSON as text
    test_message = ChatMessage(
        timestamp=datetime.now(timezone.utc),
        msg_id=uuid4(),
        content=[
            TextContent(
                type="text",
                text=json.dumps(test_json)
            )
        ],
    )
    
    print("Sending test message...")
    print(f"Message ID: {test_message.msg_id}")
    print("\nWaiting for response (timeout: 120 seconds)...\n")
    
    # Start the agent
    async with test_agent:
        # Send message to orchestrator
        try:
            await test_agent.send(ORCHESTRATOR_AGENT_ADDRESS, test_message)
            print(f"✓ Message sent successfully to {ORCHESTRATOR_AGENT_ADDRESS}")
            print("Waiting for response...\n")
            
            # Wait for response (with timeout)
            await asyncio.sleep(120)  # Wait up to 120 seconds for response
            
        except Exception as e:
            print(f"\n✗ Error sending message: {e}")
            import traceback
            traceback.print_exc()
    
    print("\nTest completed. If no response was received, check:")
    print("1. Orchestrator agent is online and running")
    print("2. Both agents have mailbox=True enabled")
    print("3. Both agents are registered on Agentverse")
    print("4. Network connectivity is working")

if __name__ == "__main__":
    print("\nStarting orchestrator JSON test...")
    print("Make sure the Orchestrator agent is running!\n")
    
    try:
        asyncio.run(send_test_json())
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user.")
    except Exception as e:
        print(f"\n\nTest failed with error: {e}")
        import traceback
        traceback.print_exc()

