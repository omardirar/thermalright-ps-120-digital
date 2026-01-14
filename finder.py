import hid
import sys

# --- CONFIG ---
VENDOR_ID = 0x0416
PRODUCT_ID = 0x8001
HEADER = 'dadbdcdd000000000000000000000000fc0000ff'

def send_one_led(dev, index):
    """Lights up EXACTLY one LED at the given index with White."""
    # Create a buffer of 160 'Off' (Black)
    colors = ["000000"] * 160
    
    # Set the target index to 'On' (White)
    if 0 <= index < 160:
        colors[index] = "FFFFFF"

    # Construct Message
    msg = "".join(colors)
    
    try:
        # Packet 1
        dev.write(bytes.fromhex('00' + HEADER + msg[:88]))
        # Packet 2
        dev.write(bytes.fromhex('00' + msg[88:]))
    except Exception as e:
        print(f"USB Error: {e}")

def main():
    print("--- MANUAL LED MAPPER ---")
    print("Commands:")
    print("  [Enter]  : Next LED")
    print("  b [Enter]: Back one LED")
    print("  j [Enter]: Jump to specific number (e.g. type '100')")
    print("  q [Enter]: Quit")
    
    try:
        dev = hid.Device(VENDOR_ID, PRODUCT_ID)
    except:
        print("Device not found! Check connections.")
        return

    # Start search at 60 (common start point for screens)
    current_index = 60 

    while True:
        # Send command to light up the current index
        send_one_led(dev, current_index)
        
        # Ask user what to do next
        user_input = input(f"--> Lit Index {current_index}. Command? ").strip().lower()

        if user_input == 'q':
            break
        elif user_input == 'b':
            current_index -= 1
        elif user_input.isdigit():
            current_index = int(user_input)
        else:
            # Default is next
            current_index += 1
            
        # Safety clamp
        if current_index < 0: current_index = 0
        if current_index > 159: current_index = 159

if __name__ == "__main__":
    main()
