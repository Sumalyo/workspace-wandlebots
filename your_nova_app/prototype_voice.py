import pvporcupine
import pvrecorder
import pvrhino
import struct
import time
import platform as platform_module
import sys

# --- THIS IS THE PART YOU CONFIGURE ---
ACCESS_KEY_windows = "s5KKYJPIv04/59FCvVZ5TdPdeXAmlFd/HEQnRDP/BfFQTDAckHUhvg==" 
WAKE_WORD_PATH_windows= "/Users/sumalyodatta/Local Work/Wanlebots/workspace-wandlebots/your_nova_app/windows/Felix_en_mac_v3_0_0.ppn" 
COMMAND_CONTEXT_PATH_windows = "/Users/sumalyodatta/Local Work/Wanlebots/workspace-wandlebots/your_nova_app/windows/bartender_en_mac_v3_0_0.rhn"
# --- END CONFIGURATION ---


# --- THIS IS THE PART YOU CONFIGURE ---
ACCESS_KEY_macbook = "vTLczUgJU2TJvrnELUiFPuEAwPX/HdATIwIPy9a4YgRQJ4LmcD31tA==" 
WAKE_WORD_PATH_macbook = "/Users/sumalyodatta/Local Work/Wanlebots/workspace-wandlebots/your_nova_app/macos/Felix_en_mac_v3_0_0.ppn" 
COMMAND_CONTEXT_PATH_macbook = "/Users/sumalyodatta/Local Work/Wanlebots/workspace-wandlebots/your_nova_app/macos/bartender_en_mac_v3_0_0.rhn"
# --- END CONFIGURATION ---

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

# State machine: 'wake' or 'command'
state = 'wake'

def blocking_code_coke():
    state = 'preparing coke'
    print("Getting your coke...Not taking any new orders right now.")
    time.sleep(10)
    print("Done !! Here is your coke.")
    state = 'wake'

def blocking_code_fanta():
    state = 'preparing fanta'
    print("Getting your fanta...Not taking any new orders right now.")
    time.sleep(10)
    print("Done !! Here is your fanta.")
    state = 'wake'


def blocking_code_sting():
    state = 'preparing sting'
    print("Making your sting...Not taking any new orders right now.")
    time.sleep(10)
    print("Done !! Here is your sting.")
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

try:
    recorder = pvrecorder.PvRecorder(
        device_index=-1,
        frame_length=porcupine.frame_length
    )
    
    print("Picovoice is running... Say your wake word ('Felix').")
    print(f"Listening on: {recorder.selected_device}")
    print("-" * 40)
    recorder.start()
    
    while True:
        pcm = recorder.read()
        audio_process(pcm)

except KeyboardInterrupt:
    print("\nStopping...")
except Exception as e:
    print(f"An error occurred: {e}")
finally:
    if 'recorder' in locals() and recorder is not None:
        recorder.delete()
    if 'porcupine' in locals():
        porcupine.delete()
    if 'rhino' in locals():
        rhino.delete()
