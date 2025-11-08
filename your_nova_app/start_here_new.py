"""
This example shows how to use the Python SDK to control a virtual KUKA KR16 R2010 robot.

This demonstrates:
- Setting up a virtual robot controller
- Connecting to the robot
- Planning and executing basic movements
- Using joint and point-to-point motion types

Key robotics concepts:
- Motion groups: Controllable robot parts (usually the arm)
- TCP (Tool Center Point): The point you control on the robot
- Joint movement (jnt): Move by specifying joint angles in radians
- Point-to-point movement (ptp): Move to a specific position/orientation (x,y,z, rotation angle in radians)
- Pose: Position (x,y,z) and orientation (rx,ry,rz) in 3D space
"""

import asyncio

import nova
from nova import api, run_program
from nova.actions import cartesian_ptp
from nova.cell import virtual_controller
from nova.core.nova import Nova
from nova.events import Cycle
from nova.program import ProgramPreconditions
from nova.types import MotionSettings, Pose
import pvporcupine
import pvrecorder
import pvrhino
import struct
import time
import platform as platform_module
import sys
from nova.core.controller import Controller 
#controller_name="urdatta10"
controller_name="ur5e"

#Todo
# The grip and relese functions are reversed and not working
# Calibration of poses needed again


# --- THIS IS THE PART YOU CONFIGURE ---
ACCESS_KEY_windows = "" 
WAKE_WORD_PATH_windows= "/Users/sumalyodatta/Local Work/Wanlebots/workspace-wandlebots/your_nova_app/windows/Felix_en_mac_v3_0_0.ppn" 
COMMAND_CONTEXT_PATH_windows = "/Users/sumalyodatta/Local Work/Wanlebots/workspace-wandlebots/your_nova_app/windows/bartender_en_mac_v3_0_0.rhn"
# --- END CONFIGURATION ---


# --- THIS IS THE PART YOU CONFIGURE ---
ACCESS_KEY_macbook = "" 
WAKE_WORD_PATH_macbook = "/Users/sumalyodatta/Local Work/Wanlebots/workspace-wandlebots/your_nova_app/macos/Felix_en_mac_v3_0_0.ppn" 
COMMAND_CONTEXT_PATH_macbook = "/Users/sumalyodatta/Local Work/Wanlebots/workspace-wandlebots/your_nova_app/macos/bartender_en_mac_v3_0_0.rhn"
# --- END CONFIGURATION ---

start_pose = Pose((102.9, -505.6, 483.4, -1.496, -2.5662, 0.0903))
#coke0 = Pose((57.6, -300.9, 312.6, 2.7865, -1.4056, 0.0077))
coke1 = Pose((56.8, -304.2, 323.7, 2.7788, -1.4014, 0.011))
coke0 = Pose((56.8, -387.9, 323.7, 2.7788, -1.4013, 0.0111))
#coke2 = Pose((56.8, -300.7, 323.7, 2.7785, -1.4013, 0.0111))
redbull0 = Pose((-30, -297.8, 320.9, 2.7793, -1.401, 0.0113))
redbull1 = Pose((-29, -385.3, 320.9, 2.779, -1.4015, 0.011))
fanta0 = Pose((-119.5, -387.7, 321, 2.7789, -1.4012, 0.011)) #new!!
customer = Pose((103.9, -699.5, 631.4, 1.2941, 2.558, -0.8835))

# Detect platform
system = platform_module.system()
if system == "Windows":
    platform = "Windows"
elif system == "Darwin":  # macOS
    platform = "MacOS"
else:
    print(f"Unsupported platform: {system}")
    print("This application only supports Windows and MacOS.")
    sys.exit(1)

print(f"Running on platform: {platform}")

porcupine = None
rhino = None

if platform == "Windows":
    porcupine = pvporcupine.create(
        access_key=ACCESS_KEY_windows,
        keyword_paths=[WAKE_WORD_PATH_windows]
    )

    rhino = pvrhino.create(
        access_key=ACCESS_KEY_windows,
        context_path=COMMAND_CONTEXT_PATH_windows
    )
elif platform == "MacOS":
    porcupine = pvporcupine.create(
        access_key=ACCESS_KEY_macbook,
        keyword_paths=[WAKE_WORD_PATH_macbook]
    )
    rhino = pvrhino.create(
        access_key=ACCESS_KEY_macbook,
        context_path=COMMAND_CONTEXT_PATH_macbook
    )

state = 'wake'

def audio_process(pcm):
    global state
    
    if state == 'wake':
        # Check for wake word
        keyword_index = porcupine.process(pcm)
        if keyword_index >= 0:
            print("Wake word detected! Listening for command...")
            state = 'command'
            
    elif state == 'command':
        # Process command with Rhino
        is_finalized = rhino.process(pcm)
        if is_finalized:
            inference = rhino.get_inference()
            if inference.is_understood:
                print(f"Intent: {inference.intent}")
                print(f"Slots: {inference.slots}")

                # Extract beverage name if available
                if 'beverage' in inference.slots:
                    print(f"\n>>> {inference.slots['beverage']}")
                    #Block the state here
                    if inference.slots['beverage'].lower() == 'coke':
                        blocking_code_coke()
                    elif inference.slots['beverage'].lower() == 'fanta':
                        blocking_code_fanta()
                    elif inference.slots['beverage'].lower() == 'sting':
                        blocking_code_sting()
                    else:
                        print("\n>>> Beverage not recognized for preparation")
                else:
                    print("\n>>> Command understood but no beverage specified")
            else:
                print(">>> Unknown beverage")
            
            # Reset to wake word detection
            state = 'wake'
            print("\nReady for next command...\n")

# Configure the robot program



# async def open_grippers(controller: Controller):
#     """Function to open the grippers."""
#     await controller.write("tool_out[1]", False)
#     await controller.write("tool_out[0]", True)
#     await asyncio.sleep(2.0)

# async def close_grippers(controller : Controller):
#     """Function to close the grippers."""
#     await controller.write("tool_out[0]", False)
#     await controller.write("tool_out[1]", True)
#     await asyncio.sleep(2.0)

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


@nova.program(
    id="start_here",  # Unique identifier of the program. If not provided, the function name will be used.
    name="Start Here",  # Readable name of the program
    #viewer=nova.viewers.Rerun(),  # add this line for a 3D visualization
    preconditions=ProgramPreconditions(
        controllers=[
            virtual_controller(
                #name="ur5e",
                name=controller_name,
                manufacturer=api.models.Manufacturer.UNIVERSALROBOTS,
                type=api.models.VirtualControllerTypes.UNIVERSALROBOTS_MINUS_UR5E,
            )
        ],
        cleanup_controllers=False,
    ),
)
async def start():
    """Main robot control function."""
    async with Nova() as nova:
        cell = nova.cell()
        controller = await cell.controller(controller_name)
        cycle = Cycle(cell=cell, extra={"program": "start_here"})

        slow = MotionSettings(tcp_velocity_limit=50)

        async with controller[0] as motion_group:
            home_joints = await motion_group.joints()
            tcp_names = await motion_group.tcp_names()
            #print(f"Available TCPs: {tcp_names}")
            tcp = tcp_names[1]
            #print(f"Using TCP: {tcp}")
            # Define poses

            # Define item list
            available_items = {
                "coke": ["coke1", "coke0"],
                "redbull": ["redbull0", "redbull1"],
                "fanta": ["fanta0"],
            }

            poses = {
                "coke0": coke0,
                "coke1": coke1,
                "redbull0": redbull0,
                "redbull1": redbull1,
                "fanta0": fanta0,
            }

            # Choose item
            target_pose_name = available_items["coke"].pop(0)
            #hardcode for testing we need to get this from voice command
            #also show an error if pop fails and inventory is empty
            target_pose = poses[target_pose_name]

            # Initialize grippers to open state
            await initialize_grippers(controller)
            # --- Move to pickup ---
            actions = [
                cartesian_ptp(start_pose),
                cartesian_ptp(target_pose @ (0, 0, -70, 0, 0, 0)),
                cartesian_ptp(target_pose)

            ]
            joint_traj = await motion_group.plan(actions, tcp)
            await motion_group.execute(joint_traj, tcp, actions=actions)

            # Activate gripper (close)
            # await controller.write("tool_out[0]", False)
            # await controller.write("tool_out[1]", True)
            # await asyncio.sleep(3.0)
            await close_grippers(controller)
            await asyncio.sleep(3.0)
            #exit()

            # --- Move to customer ---
            actions = [
                cartesian_ptp(target_pose @ (0, 0, -200, 0, 0, 0)),
                cartesian_ptp(customer),
            ]
            joint_traj = await motion_group.plan(actions, tcp)
            await motion_group.execute(joint_traj, tcp, actions=actions)

            # Release item (open gripper)
            await asyncio.sleep(2.0)
            await open_grippers(controller)
            await asyncio.sleep(4.0)

            # --- Return home ---
            actions = [
                cartesian_ptp(start_pose),
            ]
            joint_traj = await motion_group.plan(actions, tcp)
            await motion_group.execute(joint_traj, tcp, actions=actions)
            await initialize_grippers(controller)
    
            print("Movement execution completed!")


if __name__ == "__main__":
    run_program(start)
    # try:
    # recorder = pvrecorder.PvRecorder(
    #     device_index=-1,
    #     frame_length=porcupine.frame_length
    # )
    
    # print("Picovoice is running... Say your wake word ('Felix').")
    # print(f"Listening on: {recorder.selected_device}")
    # print("-" * 40)
    # recorder.start()
    
    # while True:
    #     pcm = recorder.read()
    #     audio_process(pcm)

    # except KeyboardInterrupt:
    #     print("\nStopping...")
    # except Exception as e:
    #     print(f"An error occurred: {e}")
    # finally:
    #     if 'recorder' in locals() and recorder is not None:
    #         recorder.delete()
    #     if 'porcupine' in locals():
    #         porcupine.delete()
    #     if 'rhino' in locals():
    #         rhino.delete()

