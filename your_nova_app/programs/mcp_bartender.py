"""
MCP Server for Robot Bartender.

Exposes robot bartender capabilities via Model Context Protocol (MCP).
AI assistants can use this to serve beverages through natural language.

Available tools:
- serve_drink: Pick and deliver a beverage to the customer
- check_inventory: See what beverages are available
- go_home: Return robot to start position
"""

import asyncio
import logging
import sys

from mcp.server.models import InitializationOptions
from mcp.server import NotificationOptions, Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from nova.actions import cartesian_ptp
from nova.core.nova import Nova
from nova.types import Pose

# Configure logging to stderr (MCP requirement)
# logging.basicConfig(
#     level=logging.INFO,
#     stream=sys.stderr,
#     format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
# )
logging.basicConfig(stream=sys.stderr, level=logging.ERROR)
logger = logging.getLogger(__name__)

# --- CONFIGURATION ---
CONTROLLER_NAME = "ur5e"

# Robot poses
START_POSE = Pose((102.9, -505.6, 483.4, -1.496, -2.5662, 0.0903))
COKE_0 = Pose((-170.6, -609.6, 340, 2.7917, -1.4176, -0.0117))
COKE_1 = Pose((-162.3, -501.4, 334.1, 2.7916, -1.4181, -0.0115))
REDBULL_0 = Pose((-64.4, -484.6, 332.3, 2.7873, -1.4154, 0.0118))
REDBULL_1 = Pose((-74.2, -606.2, 334.7, 2.7871, -1.4156, -0.0122))
FANTA_0 = Pose((35.8, -313.2, 333.9, 2.7879, -1.4062, 0.0075))
CUSTOMER = Pose((103.9, -699.5, 631.4, 1.2941, 2.558, -0.8835))

# Initial inventory
INITIAL_INVENTORY = {
    "coke": [COKE_0, COKE_1],
    "redbull": [REDBULL_0, REDBULL_1],
    "fanta": [FANTA_0],
}


class RobotBartender:
    """Manages robot state and beverage serving operations."""
    
    def __init__(self):
        self.inventory: dict[str, list[Pose]] = {}
        self.nova_instance = None
        self.controller = None
        self.motion_group = None
        self.tcp = None
        self.initialized = False
    
    async def initialize(self) -> None:
        """Initialize robot connection and move to start position."""
        if self.initialized:
            logger.warning("Robot already initialized")
            return
        
        logger.info("Initializing robot bartender...")
        
        # Reset inventory
        self.inventory = {k: list(v) for k, v in INITIAL_INVENTORY.items()}
        
        try:
            # Connect to robot
            self.nova_instance = Nova()
            await self.nova_instance.__aenter__()
            
            cell = self.nova_instance.cell()
            self.controller = await cell.controller(CONTROLLER_NAME)
            self.motion_group = await self.controller[0].__aenter__()
            
            tcp_names = await self.motion_group.tcp_names()
            self.tcp = tcp_names[1]
            
            # Move to start position
            logger.info("Moving to start position...")
            actions = [cartesian_ptp(START_POSE)]
            joint_traj = await self.motion_group.plan(actions, self.tcp)
            await self.motion_group.execute(joint_traj, self.tcp, actions=actions)
            
            self.initialized = True
            logger.info("Robot ready!")
            
        except Exception as e:
            logger.error(f"Failed to initialize robot: {e}")
            raise
    
    async def serve_beverage(self, beverage: str) -> str:
        """
        Serve a beverage to the customer.
        
        Args:
            beverage: Name of the beverage to serve
            
        Returns:
            Status message
        """
        if not self.initialized:
            return "❌ Robot not initialized"
        
        beverage = beverage.lower()
        
        if beverage not in self.inventory:
            available = ", ".join(self.inventory.keys())
            return f"❌ Unknown beverage '{beverage}'. Available: {available}"
        
        if not self.inventory[beverage]:
            return f"❌ Sorry, {beverage} is out of stock!"
        
        # Get next available pose
        target_pose = self.inventory[beverage].pop(0)
        remaining = len(self.inventory[beverage])
        
        try:
            logger.info(f"Serving {beverage} ({remaining} remaining)...")
            
            # Move to pickup
            actions = [
                cartesian_ptp(START_POSE),
                cartesian_ptp(target_pose @ (0, 0, -70, 0, 0, 0)),
                cartesian_ptp(target_pose)
            ]
            joint_traj = await self.motion_group.plan(actions, self.tcp)
            await self.motion_group.execute(joint_traj, self.tcp, actions=actions)
            
            # Grip
            await self.controller.write("tool_out[1]", False)
            await self.controller.write("tool_out[0]", True)
            await asyncio.sleep(3.0)
            
            # Deliver to customer
            actions = [
                cartesian_ptp(target_pose @ (0, 0, -70, 0, 0, 0)),
                cartesian_ptp(CUSTOMER),
            ]
            joint_traj = await self.motion_group.plan(actions, self.tcp)
            await self.motion_group.execute(joint_traj, self.tcp, actions=actions)
            
            # Release
            await asyncio.sleep(2.0)
            await self.controller.write("tool_out[0]", False)
            await self.controller.write("tool_out[1]", True)
            await asyncio.sleep(4.0)
            
            # Return home
            actions = [cartesian_ptp(START_POSE)]
            joint_traj = await self.motion_group.plan(actions, self.tcp)
            await self.motion_group.execute(joint_traj, self.tcp, actions=actions)
            
            return f"✅ Successfully served {beverage}! ({remaining} left in stock)"
            
        except Exception as e:
            logger.error(f"Error serving {beverage}: {e}")
            
            # Try to recover
            try:
                actions = [cartesian_ptp(START_POSE)]
                joint_traj = await self.motion_group.plan(actions, self.tcp)
                await self.motion_group.execute(joint_traj, self.tcp, actions=actions)
            except Exception as recovery_error:
                logger.error(f"Recovery failed: {recovery_error}")
            
            return f"❌ Error serving {beverage}: {str(e)}"
    
    def check_inventory(self) -> str:
        """Get current inventory status."""
        if not self.inventory:
            return "📦 Inventory is empty"
        
        lines = ["📦 Current Inventory:"]
        for beverage, poses in sorted(self.inventory.items()):
            count = len(poses)
            status = "✅" if count > 0 else "❌"
            lines.append(f"  {status} {beverage.capitalize()}: {count} available")
        
        return "\n".join(lines)
    
    async def go_home(self) -> str:
        """Move robot to start position."""
        if not self.initialized:
            return "❌ Robot not initialized"
        
        try:
            logger.info("Moving to home position...")
            actions = [cartesian_ptp(START_POSE)]
            joint_traj = await self.motion_group.plan(actions, self.tcp)
            await self.motion_group.execute(joint_traj, self.tcp, actions=actions)
            return "✅ Robot returned to home position"
        except Exception as e:
            logger.error(f"Error going home: {e}")
            return f"❌ Error: {str(e)}"


# Create MCP server
server = Server("robot-bartender")
bartender = RobotBartender()


@server.list_tools()
async def handle_list_tools() -> list[Tool]:
    """List all available MCP tools."""
    return [
        Tool(
            name="serve_drink",
            description="Serve a beverage to the customer. Available drinks: coke, redbull, fanta",
            inputSchema={
                "type": "object",
                "properties": {
                    "beverage": {
                        "type": "string",
                        "description": "Name of the beverage to serve (coke, redbull, or fanta)",
                    }
                },
                "required": ["beverage"],
            },
        ),
        Tool(
            name="check_inventory",
            description="Check what beverages are currently available and how many of each",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="go_home",
            description="Move the robot back to its home/start position",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
    ]


@server.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> list[TextContent]:
    """
    Execute a tool requested by the AI assistant.
    
    Args:
        name: Tool name
        arguments: Tool-specific arguments
        
    Returns:
        Result message
    """
    logger.info(f"Tool called: {name} with args: {arguments}")
    
    # Initialize robot on first tool call
    if not bartender.initialized:
        try:
            await bartender.initialize()
        except Exception as e:
            error_msg = f"❌ Failed to initialize robot: {str(e)}"
            logger.error(error_msg)
            return [TextContent(type="text", text=error_msg)]
    
    try:
        if name == "serve_drink":
            beverage = arguments.get("beverage", "")
            result = await bartender.serve_beverage(beverage)
        elif name == "check_inventory":
            result = bartender.check_inventory()
        elif name == "go_home":
            result = await bartender.go_home()
        else:
            result = f"❌ Unknown tool: {name}"
        
        return [TextContent(type="text", text=result)]
        
    except Exception as e:
        logger.error(f"Error executing tool {name}: {e}")
        return [TextContent(type="text", text=f"❌ Error: {str(e)}")]


async def main() -> None:
    """Main entry point for the MCP server."""
    logger.info("Starting MCP bartender server...")
    
    try:
        async with stdio_server() as (read_stream, write_stream):
            init_options = InitializationOptions(
                server_name="robot-bartender",
                server_version="1.0.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            )
            await server.run(
                read_stream,
                write_stream,
                init_options,
            )
    except Exception as e:
        logger.error(f"Server error: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())