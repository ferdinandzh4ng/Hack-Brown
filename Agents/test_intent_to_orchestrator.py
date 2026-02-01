"""
Simple test to send a message from Intent Dispatcher to Orchestrator
This simulates what the intent dispatcher does when sending a response.
"""
import os
from datetime import datetime, timezone
from uuid import uuid4
from dotenv import load_dotenv

from uagents import Agent, Context
from uagents_core.contrib.protocols.chat import (
    ChatMessage,
    TextContent,
    EndSessionContent,
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

# Create a test agent that acts like the intent dispatcher
test_dispatcher = Agent(
    name="TestIntentDispatcher",
    seed="test-intent-dispatcher-seed",
    port=8006,
    mailbox=True,
    publish_agent_details=True,
    network="testnet"
)

# Flag to track if message was sent
message_sent = False

@test_dispatcher.on_interval(period=2.0)
async def send_test_message(ctx: Context):
    """Send test message on first interval"""
    global message_sent
    if message_sent:
        return
    
    message_sent = True
    
    print(f"\n{'='*60}")
    print("Test: Intent Dispatcher → Orchestrator")
    print(f"{'='*60}")
    print(f"Intent Dispatcher Address: {INTENT_DISPATCHER_AGENT_ADDRESS}")
    print(f"Orchestrator Address: {ORCHESTRATOR_AGENT_ADDRESS}")
    print(f"Test Agent Address (acting as dispatcher): {test_dispatcher.address}")
    print(f"{'='*60}\n")
    
    # Create test message - simulating what intent dispatcher sends
    test_response = {
        "type": "dispatch_plan",
        "data": {
            "activity_list": ["eat", "sightsee", "shop"],
            "constraints": {
                "location": "Toronto",
                "budget": 500,
                "timeframe": "night",
                "start_time": "5pm",
                "end_time": "11pm"
            },
            "agents_to_call": [],
            "notes": "Test dispatch plan for mailbox connectivity verification"
        }
    }
    
    import json
    test_message_json = json.dumps(test_response, indent=2)
    
    # Create message exactly as intent dispatcher does
    content = [TextContent(type="text", text=test_message_json)]
    content.append(EndSessionContent(type="end-session"))
    test_message = ChatMessage(
        timestamp=datetime.now(timezone.utc),
        msg_id=uuid4(),
        content=content,
    )
    
    print("Sending test message (simulating intent dispatcher response)...")
    print(f"Message ID: {test_message.msg_id}")
    print(f"Message type: dispatch_plan")
    print(f"Message length: {len(test_message_json)} chars")
    print(f"\nMessage preview:")
    print(f"{test_message_json[:200]}...")
    print(f"\n{'='*60}\n")
    
    try:
        print(f"Sending to orchestrator: {ORCHESTRATOR_AGENT_ADDRESS}")
        await ctx.send(ORCHESTRATOR_AGENT_ADDRESS, test_message)
        print(f"✓ Message sent successfully!")
        print(f"\nWaiting for orchestrator to process...")
        print(f"(Check orchestrator logs for: '=== Orchestrator received ChatMessage ===')\n")
        print(f"\nTest message sent. The agent will continue running for 10 seconds...")
        print(f"Press Ctrl+C to stop early.\n")
        
    except Exception as e:
        print(f"\n✗ Error sending message: {e}")
        import traceback
        traceback.print_exc()

# No need to include protocol - we're just sending, not receiving

if __name__ == "__main__":
    print("\n" + "="*60)
    print("Intent Dispatcher → Orchestrator Mailbox Test")
    print("="*60)
    print("\nThis test simulates the intent dispatcher sending a message")
    print("to the orchestrator, exactly as it would in production.")
    print("\nMake sure the Orchestrator agent is running!")
    print("\nThe test agent will send a message and then run for 10 seconds.")
    print("Press Ctrl+C to stop early.\n")
    
    try:
        # Run the agent - it will send the message on the first interval
        import signal
        import sys
        
        def signal_handler(sig, frame):
            print("\n\nTest stopped by user.")
            sys.exit(0)
        
        signal.signal(signal.SIGINT, signal_handler)
        
        # Run for 10 seconds then exit
        import threading
        import time
        
        def stop_after_delay():
            time.sleep(10)
            print(f"\n{'='*60}")
            print("Test completed (10 seconds elapsed).")
            print(f"{'='*60}")
            print("\nIf the orchestrator received the message, you should see in orchestrator logs:")
            print("  - '=== Orchestrator received ChatMessage ==='")
            print("  - 'Sender: <test agent address>'")
            print("  - The message should be processed by the handler")
            print("\nIf no message was received, check:")
            print("  1. Orchestrator agent is running")
            print("  2. Both agents have mailbox=True enabled")
            print("  3. Both agents are registered on Agentverse")
            print("  4. Check orchestrator logs for incoming messages")
            os._exit(0)
        
        stop_thread = threading.Thread(target=stop_after_delay, daemon=True)
        stop_thread.start()
        
        test_dispatcher.run()
        
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user.")
    except Exception as e:
        print(f"\n\nTest failed with error: {e}")
        import traceback
        traceback.print_exc()
