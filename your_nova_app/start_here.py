import asyncio

import nova
from nova.actions import jnt, ptp
from nova.cell import virtual_controller
from nova.core.nova import Nova
from nova.program import ProgramPreconditions
from nova.types import MotionSettings, Pose
from wandelbots_api_client import models as wbmodels


@nova.program(
    name="start_here",  # add this line for a 3D visualization
    preconditions=ProgramPreconditions(
        controllers=[
            virtual_controller(
                name="urdatta10",
                manufacturer=wbmodels.Manufacturer.UNIVERSALROBOTS,
                type=wbmodels.VirtualControllerTypes.UNIVERSALROBOTS_MINUS_UR5E,
            )
        ],
        cleanup_controllers=False,
    ),
)
# Configure the robot program
async def start():
    """Main robot control function."""
    async with Nova() as nova:
        cell = nova.cell()
        controller = await cell.controller("urdatta10")

        async with controller[0] as motion_group:
            home_joints = await motion_group.joints()
            tcp_names = await motion_group.tcp_names()
            tcp = tcp_names[0]

            # close
            await controller.write("tool_out[0]",False)
            await controller.write("tool_out[1]",True)

            # Get current TCP pose and create target poses
            current_pose = await motion_group.tcp_pose(tcp)
            target_pose = current_pose @ Pose((50, 0, 0, 0, 0, 0))
            # Define movement sequence
            actions = [
                jnt(home_joints, MotionSettings(tcp_velocity_limit=100)),  # Move to home position
                ptp(target_pose),
                jnt(home_joints)  # Move to target pose
            ]
            # Plan the movements (shows in 3D viewer or creates an rrd file)
            joint_trajectory = await motion_group.plan(actions, tcp)
            print("Executing planned movements...")
            await motion_group.execute(joint_trajectory, tcp, actions=actions)
            print("Movement execution completed!")

            await asyncio.sleep(3.0)

            # open
            await controller.write("tool_out[1]",False)
            await controller.write("tool_out[0]",True)

                        # Get current TCP pose and create target poses
            current_pose = await motion_group.tcp_pose(tcp)
            target_pose = current_pose @ Pose((50, 0, 0, 0, 0, 0))
            # Define movement sequence
            actions = [
                jnt(home_joints, MotionSettings(tcp_velocity_limit=100)),  # Move to home position
                ptp(target_pose),
                jnt(home_joints)  # Move to target pose
            ]
            # Plan the movements (shows in 3D viewer or creates an rrd file)
            joint_trajectory = await motion_group.plan(actions, tcp)
            print("Executing planned movements...")
            await motion_group.execute(joint_trajectory, tcp, actions=actions)
            print("Movement execution completed!")

if __name__ == "__main__":
    asyncio.run(start())
