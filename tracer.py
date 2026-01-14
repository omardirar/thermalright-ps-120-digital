import hid
import sys
import tty
import termios

VENDOR_ID = 0x0416
PRODUCT_ID = 0x8001
NUMBER_OF_LEDS = 84

def get_key():
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(sys.stdin.fileno())
        ch = sys.stdin.read(1)
        if ch == '\x1b':  # Arrow keys start with ESC
            ch += sys.stdin.read(2)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    return ch

def light_led(dev, index):
    colors = ["000000"] * NUMBER_OF_LEDS
    if 0 <= index < NUMBER_OF_LEDS:
        colors[index] = "FF0000" # Red

    header = 'dadbdcdd000000000000000000000000fc0000ff'
    message = "".join(colors)
    dev.write(bytes.fromhex(header + message[:128-len(header)]))
    payload = message[88:]
    for i in range(4):
        if payload[i*128 : (i+1)*128]:
            dev.write(bytes.fromhex('00' + payload[i*128:(i+1)*128]))

try:
    dev = hid.Device(VENDOR_ID, PRODUCT_ID)
    print("Manual LED Tracer")
    print("UP Arrow:   Next LED")
    print("DOWN Arrow: Previous LED")
    print("q:          Quit")
    
    current_led = 40 # Start near where Block B was
    light_led(dev, current_led)
    print(f"\rLit LED: {current_led}   ", end="")

    while True:
        key = get_key()
        if key == '\x1b[A': # Up Arrow
            current_led += 1
        elif key == '\x1b[B': # Down Arrow
            current_led -= 1
        elif key == 'q':
            break
            
        # Wrap around
        if current_led < 0: current_led = 0
        if current_led >= NUMBER_OF_LEDS: current_led = NUMBER_OF_LEDS - 1
            
        light_led(dev, current_led)
        print(f"\rLit LED: {current_led}   ", end="")

except Exception as e:
    print(e)
