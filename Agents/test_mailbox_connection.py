"""
Test script to verify mailbox connectivity between Intent Dispatcher and Orchestrator
Run this script to send a test message from the intent dispatcher to the orchestrator.
"""
import asyncio
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

# Agent addresses
INTENT_DISPATCHER_AGENT_ADDRESS = os.getenv(
    "INTENT_DISPATCHER_AGENT_ADDRESS",
    "agent1q2943p8ja20slch8hkgnrvwscvuasnxfre0dfhzhlf744lvrpuhqurty7j4"
)

ORCHESTRATOR_AGENT_ADDRESS = os.getenv(
    "ORCHESTRATOR_AGENT_ADDRESS",
    "agent1qg2akmff6ke58spye465yje4e5fvdk6faku59h2akjjtu5hmkf8rqy346qj"
)

# Create a temporary agent to send the test message
test_agent = Agent(
    name="MailboxTestAgent",
    seed="test-mailbox-connection-seed",
    port=8005,
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
            print(f"{item.text[:500]}...")
            if len(item.text) > 500:
                print(f"\n... (truncated, full length: {len(item.text)} chars)")
            break
    
    print(f"\n{'='*60}")
    print("Test completed successfully!")
    print(f"{'='*60}\n")

test_agent.include(chat_proto, publish_manifest=False)

async def send_test_message():
    """Send a test message from intent dispatcher to orchestrator"""
    print(f"\n{'='*60}")
    print("Mailbox Connection Test")
    print(f"{'='*60}")
    print(f"Intent Dispatcher Address: {INTENT_DISPATCHER_AGENT_ADDRESS}")
    print(f"Orchestrator Address: {ORCHESTRATOR_AGENT_ADDRESS}")
    print(f"Test Agent Address: {test_agent.address}")
    print(f"{'='*60}\n")
    
    # Create test message
    test_message = ChatMessage(
        timestamp=datetime.now(timezone.utc),
        msg_id=uuid4(),
        content=[
            TextContent(
                type="text",
                text="This is a test message from the intent dispatcher to verify mailbox connectivity."
            )
        ],
    )
    
    print("Sending test message...")
    print(f"Message ID: {test_message.msg_id}")
    print(f"Message content: {test_message.content[0].text}")
    print("\nWaiting for response (timeout: 30 seconds)...\n")
    
    # Start the agent
    async with test_agent:
        # Send message to orchestrator
        try:
            await test_agent.send(ORCHESTRATOR_AGENT_ADDRESS, test_message)
            print(f"✓ Message sent successfully to {ORCHESTRATOR_AGENT_ADDRESS}")
            print("Waiting for response...\n")
            
            # Wait for response (with timeout)
            await asyncio.sleep(30)  # Wait up to 30 seconds for response
            
        except Exception as e:
            print(f"\n✗ Error sending message: {e}")
            import traceback
            traceback.print_exc()
    
    print("\nTest completed. If no response was received, check:")
    print("1. Both agents are online and running")
    print("2. Both agents have mailbox=True enabled")
    print("3. Both agents are registered on Agentverse")
    print("4. Network connectivity is working")

if __name__ == "__main__":
    print("\nStarting mailbox connection test...")
    print("Make sure both the Intent Dispatcher and Orchestrator agents are running!\n")
    
    try:
        asyncio.run(send_test_message())
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user.")
    except Exception as e:
        print(f"\n\nTest failed with error: {e}")
        import traceback
        traceback.print_exc()

