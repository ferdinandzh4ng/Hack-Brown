"""
Diagnostic script to check agent configuration and connectivity
Run this to verify your agent is properly set up to receive messages
"""
import os
from dotenv import load_dotenv
from uagents import Agent, Context, Protocol
from uagents_core.contrib.protocols.chat import (
    ChatMessage,
    TextContent,
    chat_protocol_spec,
)

load_dotenv()

# Create a test agent to verify configuration
test_agent = Agent(
    name="DiagnosticAgent",
    seed="diagnostic-test-seed",
    port=8006,
    mailbox=True,
    publish_agent_details=True,
    network="testnet"
)

chat_proto = Protocol(spec=chat_protocol_spec)

@chat_proto.on_message(ChatMessage)
async def handle_test_message(ctx: Context, sender: str, msg: ChatMessage):
    """Handle test messages to verify agent can receive"""
    ctx.logger.info(f"✓ SUCCESS: Received message from {sender}")
    for item in msg.content:
        if isinstance(item, TextContent):
            ctx.logger.info(f"Message content: {item.text}")
    
    # Send response back
    response = ChatMessage(
        timestamp=msg.timestamp,
        msg_id=msg.msg_id,
        content=[TextContent(type="text", text="Diagnostic agent received your message!")]
    )
    await ctx.send(sender, response)

test_agent.include(chat_proto, publish_manifest=True)

def print_diagnostics():
    """Print diagnostic information"""
    print("\n" + "="*60)
    print("AGENT DIAGNOSTICS")
    print("="*60)
    print(f"\nAgent Address: {test_agent.address}")
    print(f"Mailbox Enabled: {test_agent.mailbox}")
    print(f"Publish Agent Details: {test_agent.publish_agent_details}")
    print(f"Network: {test_agent.network}")
    print(f"Port: {test_agent.port}")
    
    print("\n" + "="*60)
    print("CHECKLIST FOR RECEIVING MESSAGES FROM ASI:ONE")
    print("="*60)
    print("✓ 1. mailbox=True (configured)")
    print("✓ 2. publish_agent_details=True (configured)")
    print("✓ 3. network='testnet' (configured)")
    print("✓ 4. Protocol included with publish_manifest=True (configured)")
    print("\n⚠ IMPORTANT:")
    print("  - Make sure your agent is running and stays online")
    print("  - Complete all 7 setup steps in Agentverse 'Overview' tab")
    print("  - The 'Unable to publish manifest' warning may resolve after:")
    print("    * Waiting a few minutes for Agentverse to sync")
    print("    * Checking your internet connection")
    print("    * Verifying Agentverse service status")
    print("\n" + "="*60)
    print("To test if your agent receives messages:")
    print(f"  1. Keep this agent running")
    print(f"  2. Send a message to: {test_agent.address}")
    print(f"  3. Check the logs for 'Received message' entries")
    print("="*60 + "\n")

if __name__ == "__main__":
    print_diagnostics()
    print("Starting diagnostic agent...")
    print("Press CTRL+C to stop\n")
    test_agent.run()

