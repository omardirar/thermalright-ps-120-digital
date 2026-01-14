import hid
import time
import psutil
import sys
import colorsys
import json
import os

# --- PATH CONFIGURATION ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(SCRIPT_DIR, "config.json")

# HARDWARE CONSTANTS
VENDOR_ID = 0x0416
PRODUCT_ID = 0x8001
NUMBER_OF_LEDS = 84

# DEFAULT SETTINGS
settings = {
    "update_interval": 2.0,
    "wipe_speed": 0.01,
    "hue_step": 0.02,
    "brightness": 1.0,
    "color_offset": 0.5 # 0.5 = Opposite colors
}

def get_cpu_power_linux():
    rapl_path = "/sys/class/powercap/intel-rapl/intel-rapl:0/energy_uj"
    try:
        if not os.path.exists(rapl_path): return None
        with open(rapl_path, 'r') as f: e1 = int(f.read())
        time.sleep(0.1)
        with open(rapl_path, 'r') as f: e2 = int(f.read())
        return (e2 - e1) / 0.1 / 1_000_000
    except:
        return None

def load_config():
    global settings
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                content = f.read()
            if content.strip():
                settings.update(json.loads(content))
    except Exception as e:
        sys.stdout.write(f"\n[ERROR] Config Load Failed: {e}\n")

def apply_brightness(hex_color, brightness):
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    r = int(r * brightness)
    g = int(g * brightness)
    b = int(b * brightness)
    return f"{min(r,255):02X}{min(g,255):02X}{min(b,255):02X}"

# --- MAPPING COORDINATES ---
led_pos_coords = [0.0] * NUMBER_OF_LEDS
led_group_mask = [0] * NUMBER_OF_LEDS 

def assign_coords(indices, start_pos, end_pos, group_id):
    """
    group_id: 0 = LEFT SIDE (Temp/Speed), 1 = RIGHT SIDE (Watt/Usage)
    """
    count = len(indices)
    step = (end_pos - start_pos) / count if count > 1 else 0
    for i, led_idx in enumerate(indices):
        pos = start_pos + (i * step)
        if 0 <= led_idx < NUMBER_OF_LEDS: 
            led_pos_coords[led_idx] = pos
            led_group_mask[led_idx] = group_id

# ==============================================================================
# VISUAL LAYOUT & GROUPS (Based on your correction)
# Path: Top-Left -> Top-Right -> Bottom-Right -> Bottom-Left
# ==============================================================================

# 1. TEMPERATURE (Top Left) -> LEFT GROUP (0)
# Timeline: 0.00 -> 0.25
led_pos_coords[51] = 0.02; led_group_mask[51] = 0           # CPU
assign_coords([49, 50, 52, 48, 45, 46, 47], 0.03, 0.10, 0)  # Hundreds
assign_coords([57, 58, 60, 56, 53, 54, 55], 0.10, 0.17, 0)  # Tens
assign_coords([65, 66, 67, 64, 61, 62, 63], 0.17, 0.24, 0)  # Ones
led_pos_coords[69] = 0.25; led_group_mask[69] = 0           # C Symbol

# 2. WATTS (Top Right) -> RIGHT GROUP (1)
# Timeline: 0.26 -> 0.50
# Path: Left Digit -> Right Digit
assign_coords([74, 75, 76, 73, 70, 71, 72], 0.26, 0.38, 1) 
assign_coords([81, 82, 83, 80, 77, 78, 79], 0.38, 0.50, 1) 

# 3. PERCENTAGE (Bottom Right) -> RIGHT GROUP (1)
# Timeline: 0.51 -> 0.75
assign_coords([14, 13, 12, 11, 10, 9, 8], 0.51, 0.58, 1)  # Tens
assign_coords([7, 6, 5, 4, 3, 2, 1],      0.58, 0.65, 1)  # Ones
led_pos_coords[0] = 0.66; led_group_mask[0] = 1           # Percent
assign_coords(list(range(36, 51)), 0.67, 0.75, 1)         # Usage Bar

# 4. SPEED (Bottom Left) -> LEFT GROUP (0)
# Timeline: 0.76 -> 1.00
assign_coords([44, 43, 42, 41, 40, 39, 38], 0.76, 0.82, 0) # Thousands
assign_coords([37, 36, 35, 34, 33, 32, 31], 0.82, 0.88, 0) # Hundreds
assign_coords([30, 29, 28, 27, 26, 25, 24], 0.88, 0.94, 0) # Tens
assign_coords([23, 22, 21, 20, 19, 18, 17], 0.94, 0.99, 0) # Ones
led_pos_coords[16] = 1.00; led_group_mask[16] = 0          # MHz


# --- DATA INDICES ---
watt_digits_indices = [[74, 75, 76, 73, 70, 71, 72], [81, 82, 83, 80, 77, 78, 79]]
temp_digits_indices = [[49, 50, 52, 48, 45, 46, 47], [57, 58, 60, 56, 53, 54, 55], [65, 66, 67, 64, 61, 62, 63]]
usage_digits_indices = [[14, 13, 12, 11, 10, 9, 8], [7, 6, 5, 4, 3, 2, 1]]
speed_digits_indices = [[44, 43, 42, 41, 40, 39, 38], [37, 36, 35, 34, 33, 32, 31], [30, 29, 28, 27, 26, 25, 24], [23, 22, 21, 20, 19, 18, 17]]
bar_usage_indices = list(range(36, 51))

digit_shapes = {
    '0':[1,1,1,0,1,1,1], '1':[0,0,1,0,0,0,1], '2':[0,1,1,1,1,1,0], '3':[0,1,1,1,0,1,1],
    '4':[1,0,1,1,0,0,1], '5':[1,1,0,1,0,1,1], '6':[1,1,0,1,1,1,1], '7':[0,1,1,0,0,0,1],
    '8':[1,1,1,1,1,1,1], '9':[1,1,1,1,0,1,1], ' ':[0,0,0,0,0,0,0]
}

def get_cpu_temp():
    try:
        temps = psutil.sensors_temperatures()
        if 'coretemp-isa-0000' in temps: return temps['coretemp-isa-0000'][0].current
        for key in ['coretemp', 'k10temp', 'cpu_thermal', 'acpitz']:
            if key in temps: return temps[key][0].current
    except: pass
    return 0

def main():
    print(f"Starting Left/Right Split Dashboard...")
    load_config()
    
    last_data_time = 0
    last_config_check = 0
    cached_temp = 0
    cached_usage = 0
    cached_speed = 0
    cached_watts = 0
    leds_on_mask = [False] * NUMBER_OF_LEDS
    
    current_hue = 0.0         
    target_hue = settings["hue_step"]
    wipe_progress = 0.0       

    while True:
        try:
            dev = hid.Device(VENDOR_ID, PRODUCT_ID)
            print("\nConnected.")
            
            while True:
                now = time.time()
                
                if now - last_config_check > 2.0:
                    load_config()
                    last_config_check = now

                if now - last_data_time > settings["update_interval"]:
                    cached_temp = get_cpu_temp()
                    cached_usage = psutil.cpu_percent()
                    cached_watts = get_cpu_power_linux()
                    if cached_watts is None: cached_watts = 0
                    try:
                        f = psutil.cpu_freq()
                        cached_speed = int(f.current) if f else 0
                    except: cached_speed = 0
                    last_data_time = now
                    
                    leds_on_mask = [False] * NUMBER_OF_LEDS
                    
                    # 1. Temp (Left)
                    t_str = f"{min(int(cached_temp), 199): >3}"
                    for i, c in enumerate(t_str):
                        if c in digit_shapes:
                             for idx, on in enumerate(digit_shapes[c]): 
                                 if on: leds_on_mask[temp_digits_indices[i][idx]] = True
                    
                    # 2. Usage (Right)
                    u_val = int(cached_usage)
                    if cached_usage > 0 and u_val == 0: u_val = 1
                    u_str = f"{min(u_val, 99):02}"
                    for i, c in enumerate(u_str):
                        if c in digit_shapes:
                            for idx, on in enumerate(digit_shapes[c]):
                                if on: leds_on_mask[usage_digits_indices[i][idx]] = True

                    # 3. Speed (Left)
                    s_str = f"{min(cached_speed, 9999): >4}"
                    for i, c in enumerate(s_str):
                         if c in digit_shapes:
                             for idx, on in enumerate(digit_shapes[c]):
                                 if on: leds_on_mask[speed_digits_indices[i][idx]] = True
                    
                    # 4. Watts (Right)
                    w_val = int(cached_watts)
                    w_str = f"{min(w_val, 99):02}"
                    for i, c in enumerate(w_str):
                        if c in digit_shapes:
                            for idx, on in enumerate(digit_shapes[c]):
                                if on: leds_on_mask[watt_digits_indices[i][idx]] = True

                    # 5. Usage Bar & Static
                    u_lit = int((cached_usage / 100.0) * len(bar_usage_indices))
                    for i in range(u_lit): leds_on_mask[bar_usage_indices[i]] = True
                    leds_on_mask[0]=True; leds_on_mask[16]=True; leds_on_mask[51]=True; leds_on_mask[69]=True

                # ANIMATION
                wipe_progress += settings["wipe_speed"]
                if wipe_progress >= 1.2: 
                    wipe_progress = 0.0
                    current_hue = target_hue
                    target_hue = (target_hue + settings["hue_step"]) % 1.0

                # Color Group 0 (Left)
                r0, g0, b0 = colorsys.hsv_to_rgb(current_hue, 1.0, 1.0)
                base_0_old = f"{int(r0*255):02X}{int(g0*255):02X}{int(b0*255):02X}"
                r0n, g0n, b0n = colorsys.hsv_to_rgb(target_hue, 1.0, 1.0)
                base_0_new = f"{int(r0n*255):02X}{int(g0n*255):02X}{int(b0n*255):02X}"
                
                # Color Group 1 (Right)
                hue_1 = (current_hue + settings.get("color_offset", 0.5)) % 1.0
                hue_1n = (target_hue + settings.get("color_offset", 0.5)) % 1.0
                r1, g1, b1 = colorsys.hsv_to_rgb(hue_1, 1.0, 1.0)
                base_1_old = f"{int(r1*255):02X}{int(g1*255):02X}{int(b1*255):02X}"
                r1n, g1n, b1n = colorsys.hsv_to_rgb(hue_1n, 1.0, 1.0)
                base_1_new = f"{int(r1n*255):02X}{int(g1n*255):02X}{int(b1n*255):02X}"

                # Brightness
                dim_0_old = apply_brightness(base_0_old, settings["brightness"])
                dim_0_new = apply_brightness(base_0_new, settings["brightness"])
                dim_1_old = apply_brightness(base_1_old, settings["brightness"])
                dim_1_new = apply_brightness(base_1_new, settings["brightness"])

                colors = ["000000"] * NUMBER_OF_LEDS
                for i in range(NUMBER_OF_LEDS):
                    if leds_on_mask[i]:
                        is_group_1 = (led_group_mask[i] == 1)
                        col_old = dim_1_old if is_group_1 else dim_0_old
                        col_new = dim_1_new if is_group_1 else dim_0_new
                        
                        if wipe_progress >= led_pos_coords[i]: colors[i] = col_new
                        else: colors[i] = col_old

                sys.stdout.write(f"\rWatts: {cached_watts:.1f} | Temp: {int(cached_temp)}C | Use: {int(cached_usage)}%   ")
                sys.stdout.flush()

                header = 'dadbdcdd000000000000000000000000fc0000ff'
                message = "".join(colors)
                dev.write(bytes.fromhex(header + message[:128-len(header)]))
                payload = message[88:]
                for i in range(4):
                     if payload[i*128 : (i+1)*128]: dev.write(bytes.fromhex('00' + payload[i*128:(i+1)*128]))
                
                time.sleep(0.05)

        except Exception as e:
            print(f"\nWaiting... {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
