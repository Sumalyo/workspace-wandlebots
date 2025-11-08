"""
Robot bartender controlled by voice commands.

This demonstrates:
- Voice activation with Picovoice wake word + command detection
- Thread-safe integration of blocking audio with async robot control
- Inventory management for available beverages
- Safe robot motion planning and execution
"""

import asyncio
import logging
import platform as platform_module
import sys
import threading
from queue import Queue
from typing import Optional

import pvporcupine
import pvrecorder
import pvrhino

import nova
from nova import api, run_program
from nova.actions import cartesian_ptp
from nova.cell import virtual_controller
from nova.core.nova import Nova
from nova.events import Cycle
from nova.program import ProgramPreconditions
from nova.types import MotionSettings, Pose

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- CONFIGURATION ---
controller_name = "ur5e"

# Platform-specific Picovoice settings
ACCESS_KEY_windows = ""
WAKE_WORD_PATH_windows = "/Users/sumalyodatta/Local Work/Wanlebots/workspace-wandlebots/your_nova_app/windows/Felix_en_mac_v3_0_0.ppn"
COMMAND_CONTEXT_PATH_windows = "/Users/sumalyodatta/Local Work/Wanlebots/workspace-wandlebots/your_nova_app/windows/bartender_en_mac_v3_0_0.rhn"

ACCESS_KEY_macbook = ""
WAKE_WORD_PATH_macbook = "/Users/sumalyodatta/Local Work/Wanlebots/workspace-wandlebots/your_nova_app/macos/Felix_en_mac_v3_0_0.ppn"
COMMAND_CONTEXT_PATH_macbook = "/Users/sumalyodatta/Local Work/Wanlebots/workspace-wandlebots/your_nova_app/macos/bartender_en_mac_v3_0_0.rhn"

# Robot poses
start_pose = Pose((102.9, -505.6, 483.4, -1.496, -2.5662, 0.0903))
coke1 = Pose((56.8, -304.2, 323.7, 2.7788, -1.4014, 0.011))
coke0 = Pose((56.8, -387.9, 323.7, 2.7788, -1.4013, 0.0111))
#coke2 = Pose((56.8, -300.7, 323.7, 2.7785, -1.4013, 0.0111))
redbull0 = Pose((-30, -297.8, 320.9, 2.7793, -1.401, 0.0113))
redbull1 = Pose((-29, -385.3, 320.9, 2.779, -1.4015, 0.011))
fanta0 = Pose((-119.5, -387.7, 321, 2.7789, -1.4012, 0.011)) #new!!
customer = Pose((103.9, -699.5, 631.4, 1.2941, 2.558, -0.8835))

# Inventory: maps beverage name to list of available poses
INVENTORY = {
    "coke": [coke0, coke1],
    "redbull": [redbull0, redbull1],
    "fanta": [fanta0],
    "sting": [redbull0, redbull1],  # Assuming "sting" uses redbull poses
}

# Thread-safe command queue
command_queue: Queue[str] = Queue()


class VoiceListener:
    """Handles wake word detection and command recognition in a separate thread."""

    def __init__(self, access_key: str, wake_word_path: str, context_path: str):
        self.porcupine = pvporcupine.create(
            access_key=access_key,
            keyword_paths=[wake_word_path]
        )
        self.rhino = pvrhino.create(
            access_key=access_key,
            context_path=context_path
        )
        self.recorder: Optional[pvrecorder.PvRecorder] = None
        self.state = 'wake'
        self.running = False
        self.thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Start the voice listening thread."""
        if self.running:
            logger.warning("Voice listener already running")
            return

        self.recorder = pvrecorder.PvRecorder(
            device_index=-1,
            frame_length=self.porcupine.frame_length
        )
        
        logger.info(f"Starting voice listener on: {self.recorder.selected_device}")
        logger.info("Say 'Felix' to wake, then give a command like 'get me a coke'")
        
        self.running = True
        self.thread = threading.Thread(target=self._listen_loop, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        """Stop the voice listening thread."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)
        if self.recorder:
            self.recorder.delete()
        self.porcupine.delete()
        self.rhino.delete()
        logger.info("Voice listener stopped")

    def _listen_loop(self) -> None:
        """Main audio processing loop (runs in separate thread)."""
        try:
            self.recorder.start()
            
            while self.running:
                pcm = self.recorder.read()
                
                if self.state == 'wake':
                    keyword_index = self.porcupine.process(pcm)
                    if keyword_index >= 0:
                        logger.info("Wake word detected! Listening for command...")
                        self.state = 'command'
                        
                elif self.state == 'command':
                    is_finalized = self.rhino.process(pcm)
                    if is_finalized:
                        inference = self.rhino.get_inference()
                        
                        if inference.is_understood:
                            logger.info(f"Command understood - Intent: {inference.intent}, Slots: {inference.slots}")
                            
                            if 'beverage' in inference.slots:
                                beverage = inference.slots['beverage'].lower()
                                logger.info(f"Queuing beverage request: {beverage}")
                                command_queue.put(beverage)
                            else:
                                logger.warning("Command understood but no beverage specified")
                        else:
                            logger.warning("Command not understood")
                        
                        # Reset to wake word detection
                        self.state = 'wake'
                        logger.info("Ready for next command (say 'Felix')...\n")
                        
        except Exception as e:
            logger.error(f"Error in voice listener: {e}")
            self.running = False

async def initialize_grippers(controller):
    """Function to initialize the grippers to open state."""
    await controller.write("tool_out[0]", True)
    await controller.write("tool_out[1]", False)
    await controller.write("tool_out[0]", False)

async def close_grippers(controller):
    # Activate gripper (close)
    await controller.write("tool_out[0]", False)
    await controller.write("tool_out[1]", True)

async def open_grippers(controller):
    # Activate gripper (open)
    await controller.write("tool_out[1]", False)
    await controller.write("tool_out[0]", True)

async def serve_beverage(
    beverage: str,
    motion_group,
    controller,
    tcp: str,
    inventory: dict[str, list[Pose]]
) -> bool:
    """
    Pick and serve a beverage to the customer.
    
    Returns:
        True if successful, False if beverage unavailable
    """
    if beverage not in inventory:
        logger.error(f"Unknown beverage: {beverage}")
        return False
    
    if not inventory[beverage]:
        logger.error(f"Sorry, {beverage} is out of stock!")
        return False
    
    # Get next available pose for this beverage
    target_pose = inventory[beverage].pop(0)
    logger.info(f"Serving {beverage} - {len(inventory[beverage])} remaining")
    
    try:
        # Initialize grippers to open state
        # await controller.write("tool_out[0]", True)
        # await controller.write("tool_out[1]", False)
        # await controller.write("tool_out[0]", False)
        await initialize_grippers(controller)
        # --- Move to pickup ---
        logger.info(f"Moving to pick up {beverage}...")
        actions = [
            cartesian_ptp(start_pose),
            cartesian_ptp(target_pose @ (0, 0, -70, 0, 0, 0)),
            cartesian_ptp(target_pose)
        ]
        joint_traj = await motion_group.plan(actions, tcp)
        await motion_group.execute(joint_traj, tcp, actions=actions)
        
        # Activate gripper (close)
        logger.info("Gripping beverage...")
        # Activate gripper (close)
        # await controller.write("tool_out[0]", False)
        # await controller.write("tool_out[1]", True)
        await close_grippers(controller)
        await asyncio.sleep(3.0)
        
        # --- Move to customer ---
        logger.info("Delivering to customer...")
        actions = [
            cartesian_ptp(target_pose @ (0, 0, -200, 0, 0, 0)),
            cartesian_ptp(customer),
        ]
        joint_traj = await motion_group.plan(actions, tcp)
        await motion_group.execute(joint_traj, tcp, actions=actions)
        
        # Release item (open gripper)
        logger.info("Releasing beverage...")
        await asyncio.sleep(2.0)
        # await controller.write("tool_out[1]", False)
        # await controller.write("tool_out[0]", True)
        await open_grippers(controller)
        await asyncio.sleep(4.0)
        
        # --- Return home ---
        logger.info("Returning to start position...")
        actions = [cartesian_ptp(start_pose)]
        joint_traj = await motion_group.plan(actions, tcp)
        await motion_group.execute(joint_traj, tcp, actions=actions)
        
        logger.info(f"Successfully served {beverage}!")
        return True
        
    except Exception as e:
        logger.error(f"Error serving {beverage}: {e}")
        # Try to return home safely
        try:
            actions = [cartesian_ptp(start_pose)]
            joint_traj = await motion_group.plan(actions, tcp)
            await motion_group.execute(joint_traj, tcp, actions=actions)
        except Exception as recovery_error:
            logger.error(f"Could not return home: {recovery_error}")
        return False


@nova.program(
    id="voice_bartender",
    name="Voice-Controlled Bartender",
    preconditions=ProgramPreconditions(
        controllers=[
            virtual_controller(
                name=controller_name,
                manufacturer=api.models.Manufacturer.UNIVERSALROBOTS,
                type=api.models.VirtualControllerTypes.UNIVERSALROBOTS_MINUS_UR5E,
            )
        ],
        cleanup_controllers=False,
    ),
)
async def voice_bartender():
    """Main program: continuously listen for voice commands and serve beverages."""
    
    # Detect platform and configure Picovoice
    system = platform_module.system()
    if system == "Windows":
        access_key = ACCESS_KEY_windows
        wake_word_path = WAKE_WORD_PATH_windows
        context_path = COMMAND_CONTEXT_PATH_windows
    elif system == "Darwin":
        access_key = ACCESS_KEY_macbook
        wake_word_path = WAKE_WORD_PATH_macbook
        context_path = COMMAND_CONTEXT_PATH_macbook
    else:
        logger.error(f"Unsupported platform: {system}")
        return
    
    logger.info(f"Running on platform: {system}")
    
    # Start voice listener in background thread
    listener = VoiceListener(access_key, wake_word_path, context_path)
    listener.start()
    
    # Copy inventory (so we can track what's left)
    inventory = {k: list(v) for k, v in INVENTORY.items()}
    
    try:
        async with Nova() as nova_instance:
            cell = nova_instance.cell()
            controller = await cell.controller(controller_name)
            
            async with controller[0] as motion_group:
                tcp_names = await motion_group.tcp_names()
                tcp = tcp_names[1]
                
                # Move to start position
                logger.info("Moving to start position...")
                actions = [cartesian_ptp(start_pose)]
                joint_traj = await motion_group.plan(actions, tcp)
                await motion_group.execute(joint_traj, tcp, actions=actions)
                logger.info("Ready to serve! Say 'Felix' to start.\n")
                
                # Main command processing loop
                while True:
                    # Check for commands (non-blocking with timeout)
                    try:
                        # Use run_in_executor to avoid blocking the async loop
                        beverage = await asyncio.get_event_loop().run_in_executor(
                            None, 
                            lambda: command_queue.get(timeout=0.1)
                        )
                        
                        logger.info(f"\n{'='*50}")
                        logger.info(f"Processing order: {beverage}")
                        logger.info(f"{'='*50}\n")
                        
                        await serve_beverage(beverage, motion_group, controller, tcp, inventory)
                        
                    except:
                        # No command available, just wait a bit
                        await asyncio.sleep(0.1)
                        
    except KeyboardInterrupt:
        logger.info("\nShutting down bartender...")
    except Exception as e:
        logger.error(f"Error in main loop: {e}")
    finally:
        listener.stop()


if __name__ == "__main__":
    run_program(voice_bartender)