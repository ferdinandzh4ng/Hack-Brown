"""
Command Agents - Simple Fetch AI agents for sending and executing commands
Agent 1 (command_sender): Sends commands as text messages
Agent 2 (command_executor): Receives commands and executes them
"""
from uagents import Agent, Bureau, Context, Model
import subprocess
import sys
import os

# ============================================================
# Models
# ============================================================

class CommandMessage(Model):
    """Message model for sending commands"""
    command: str

class CommandResponse(Model):
    """Response model for command execution results"""
    success: bool
    output: str
    error: str = ""

# ============================================================
# Agents
# ============================================================

command_sender = Agent(name="command_sender")
command_executor = Agent(name="command_executor")

# ============================================================
# Command Sender Agent
# ============================================================

@command_sender.on_interval(period=5.0)
async def send_command(ctx: Context):
    """Send a command to the executor agent"""
    command = 'print("hello world")'
    msg = CommandMessage(command=command)
    
    ctx.logger.info(f"Sending command: {command}")
    
    reply, status = await ctx.send_and_receive(
        command_executor.address, 
        msg, 
        response_type=CommandResponse,
        timeout=10.0
    )
    
    if isinstance(reply, CommandResponse):
        if reply.success:
            ctx.logger.info(f"Command executed successfully!")
            ctx.logger.info(f"Output: {reply.output}")
        else:
            ctx.logger.error(f"Command execution failed: {reply.error}")
    else:
        ctx.logger.error(f"Failed to receive response from executor: {status}")

# ============================================================
# Command Executor Agent
# ============================================================

@command_executor.on_message(model=CommandMessage)
async def handle_command(ctx: Context, sender: str, msg: CommandMessage):
    """Receive command and execute it"""
    ctx.logger.info(f"Received command: {msg.command}")
    
    try:
        # Execute the command using subprocess for safety
        # For Python code, we'll use exec() to execute it
        result = subprocess.run(
            [sys.executable, "-c", msg.command],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=os.getcwd()
        )
        
        if result.returncode == 0:
            # Command executed successfully
            response = CommandResponse(
                success=True,
                output=result.stdout.strip() if result.stdout else "Command executed successfully",
                error=""
            )
            ctx.logger.info(f"Command executed successfully. Output: {response.output}")
        else:
            # Command failed
            response = CommandResponse(
                success=False,
                output="",
                error=result.stderr.strip() if result.stderr else f"Command failed with return code {result.returncode}"
            )
            ctx.logger.error(f"Command execution failed: {response.error}")
        
        await ctx.send(sender, response)
        
    except subprocess.TimeoutExpired:
        response = CommandResponse(
            success=False,
            output="",
            error="Command execution timed out after 10 seconds"
        )
        ctx.logger.error("Command execution timed out")
        await ctx.send(sender, response)
        
    except Exception as e:
        response = CommandResponse(
            success=False,
            output="",
            error=f"Error executing command: {str(e)}"
        )
        ctx.logger.error(f"Error executing command: {e}")
        await ctx.send(sender, response)

# ============================================================
# Bureau Setup
# ============================================================

bureau = Bureau([command_sender, command_executor])

if __name__ == "__main__":
    print(f"Command Sender Agent address: {command_sender.address}")
    print(f"Command Executor Agent address: {command_executor.address}")
    print("\nStarting agents...")
    bureau.run()

