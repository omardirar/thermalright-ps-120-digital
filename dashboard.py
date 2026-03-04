import hid
import time
import psutil
import sys
import colorsys
import json
import os
import glob
import subprocess

# --- PATH CONFIGURATION ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(SCRIPT_DIR, "config.json")

# HARDWARE CONSTANTS
VENDOR_ID = 0x0416
PRODUCT_ID = 0x8001
NUMBER_OF_LEDS = 84
MODE_CYCLE_INTERVAL = 4.0

# DEFAULT SETTINGS
settings = {
    "update_interval": 2.0,
    "wipe_speed": 0.015,
    "hue_step": 0.01,
    "brightness": 1.0,
    "left_color_offset": 0.1,
    "base_hue": 0.58,
    "saturation": 0.18
}

def get_cpu_power_linux():
    rapl_path = "/sys/class/powercap/intel-rapl/intel-rapl:0/energy_uj"
    try:
        if not os.path.exists(rapl_path):
            return None
        with open(rapl_path, 'r') as f:
            e1 = int(f.read())
        time.sleep(0.1)
        with open(rapl_path, 'r') as f:
            e2 = int(f.read())
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
    group_id: 0 = LEFT (Temp/Speed), 1 = RIGHT (Watt/Usage)
    """
    count = len(indices)
    step = (end_pos - start_pos) / count if count > 1 else 0
    for i, led_idx in enumerate(indices):
        pos = start_pos + (i * step)
        if 0 <= led_idx < NUMBER_OF_LEDS:
            led_pos_coords[led_idx] = pos
            led_group_mask[led_idx] = group_id

# ==============================================================================
# ANIMATION PATH (ORDER MATTERS FOR OVERLAPS)
# Path: Left Column (Top->Bot) then Right Column (Top->Bot)
# ==============================================================================

# --- STEP 1: BACKGROUND ELEMENTS (Set these FIRST so digits overwrite them) ---
# Usage Bar (Right Side / Group 1)
# Animation Time: 0.90 -> 1.00
assign_coords(list(range(36, 51)), 0.90, 1.00, 1)


# --- STEP 2: LEFT COLUMN (Group 0) ---

# Temperature (Top Left)
# Time: 0.00 -> 0.25
led_pos_coords[51] = 0.02; led_group_mask[51] = 0           # CPU
led_pos_coords[59] = 0.02; led_group_mask[59] = 0           # GPU
assign_coords([49, 50, 52, 48, 45, 46, 47], 0.03, 0.10, 0)  # Hundreds
assign_coords([57, 58, 60, 56, 53, 54, 55], 0.10, 0.17, 0)  # Tens
assign_coords([65, 66, 67, 64, 61, 62, 63], 0.17, 0.24, 0)  # Ones
led_pos_coords[69] = 0.25; led_group_mask[69] = 0           # C Symbol

# Speed (Bottom Left)
# Time: 0.26 -> 0.50
# CRITICAL: Since this is called AFTER the usage bar above,
# it will correctly reclaim indices 36-44 for Group 0.
assign_coords([44, 43, 42, 41, 40, 39, 38], 0.26, 0.32, 0) # Thousands
assign_coords([37, 36, 35, 34, 33, 32, 31], 0.32, 0.38, 0) # Hundreds
assign_coords([30, 29, 28, 27, 26, 25, 24], 0.38, 0.44, 0) # Tens
assign_coords([23, 22, 21, 20, 19, 18, 17], 0.44, 0.49, 0) # Ones
led_pos_coords[16] = 0.50; led_group_mask[16] = 0          # MHz


# --- STEP 3: RIGHT COLUMN (Group 1) ---

# Watts (Top Right)
# Time: 0.51 -> 0.75
assign_coords([74, 75, 76, 73, 70, 71, 72], 0.51, 0.63, 1) # Left Digit
assign_coords([81, 82, 83, 80, 77, 78, 79], 0.63, 0.75, 1) # Right Digit

# Percentage (Bottom Right)
# Time: 0.76 -> 1.00
assign_coords([14, 13, 12, 11, 10, 9, 8], 0.76, 0.82, 1)  # Tens
assign_coords([7, 6, 5, 4, 3, 2, 1],      0.82, 0.88, 1)  # Ones
led_pos_coords[0] = 0.89; led_group_mask[0] = 1           # Percent


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
        if 'coretemp-isa-0000' in temps:
            return temps['coretemp-isa-0000'][0].current
        for key in ['coretemp', 'k10temp', 'cpu_thermal', 'acpitz']:
            if key in temps:
                return temps[key][0].current
    except:
        pass
    return 0

def safe_read_int(path):
    try:
        with open(path, 'r') as f:
            text = f.read().strip().lower()
        if text.startswith('0x'):
            return int(text, 16)
        return int(text)
    except:
        return None

def parse_float_field(raw):
    try:
        field = raw.strip().split()[0]
        return float(field)
    except:
        return None

def read_gpu_speed_sysfs(card_path):
    # AMD path like: "0: 500Mhz *"
    amd_clk_path = os.path.join(card_path, 'device', 'pp_dpm_sclk')
    try:
        with open(amd_clk_path, 'r') as f:
            for line in f:
                if '*' in line and 'Mhz' in line:
                    mhz = line.split(':', 1)[1].replace('*', '').strip().replace('Mhz', '').strip()
                    return int(float(mhz))
    except:
        pass

    # Intel path
    intel_clk_path = os.path.join(card_path, 'gt_cur_freq_mhz')
    val = safe_read_int(intel_clk_path)
    return int(val) if val is not None else 0

def read_gpu_power_sysfs(card_path):
    for rel in [
        os.path.join('device', 'hwmon', 'hwmon*', 'power1_average'),
        os.path.join('device', 'hwmon', 'hwmon*', 'power1_input'),
    ]:
        matches = sorted(glob.glob(os.path.join(card_path, rel)))
        if not matches:
            continue
        val = safe_read_int(matches[0])
        if val is None:
            continue
        # Usually microwatts in sysfs hwmon for GPUs.
        if val > 1000:
            return val / 1_000_000.0
        return float(val)
    return 0.0

def get_gpu_stats_linux():
    # Returns: temp_c, usage_pct, speed_mhz, watts
    try:
        result = subprocess.run(
            [
                'nvidia-smi',
                '--query-gpu=temperature.gpu,utilization.gpu,clocks.current.graphics,power.draw',
                '--format=csv,noheader,nounits'
            ],
            capture_output=True,
            text=True,
            timeout=1.0,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            line = result.stdout.strip().splitlines()[0]
            parts = [p.strip() for p in line.split(',')]
            if len(parts) >= 4:
                t = parse_float_field(parts[0])
                u = parse_float_field(parts[1])
                s = parse_float_field(parts[2])
                w = parse_float_field(parts[3])
                return int(t or 0), int(u or 0), int(s or 0), int(w or 0)
    except:
        pass

    for card_path in sorted(glob.glob('/sys/class/drm/card[0-9]*')):
        vendor = safe_read_int(os.path.join(card_path, 'device', 'vendor'))
        if vendor not in (0x1002, 0x8086, 0x10DE):
            continue

        temp = 0
        usage = 0
        speed = 0
        watts = 0.0

        temp_candidates = sorted(glob.glob(os.path.join(card_path, 'device', 'hwmon', 'hwmon*', 'temp1_input')))
        if temp_candidates:
            t_raw = safe_read_int(temp_candidates[0])
            if t_raw is not None:
                temp = int(t_raw / 1000) if t_raw > 1000 else int(t_raw)

        busy = safe_read_int(os.path.join(card_path, 'device', 'gpu_busy_percent'))
        if busy is None:
            busy = safe_read_int(os.path.join(card_path, 'gt_busy_percent'))
        if busy is not None:
            usage = int(busy)

        speed = read_gpu_speed_sysfs(card_path)
        watts = read_gpu_power_sysfs(card_path)

        if temp > 0 or usage > 0 or speed > 0 or watts > 0:
            return max(0, int(temp)), max(0, int(usage)), max(0, int(speed)), max(0, int(watts))

    return 0, 0, 0, 0

def clamp_int(value, low, high):
    try:
        n = int(value)
    except:
        n = low
    if n < low:
        return low
    if n > high:
        return high
    return n

def main():
    print(f"Starting Overlap-Fixed Dashboard...")
    load_config()

    last_data_time = 0
    last_config_check = 0
    last_mode_switch = time.time()

    cached_temp = 0
    cached_usage = 0
    cached_speed = 0
    cached_watts = 0

    cached_gpu_temp = 0
    cached_gpu_usage = 0
    cached_gpu_speed = 0
    cached_gpu_watts = 0

    show_cpu_mode = True
    leds_on_mask = [False] * NUMBER_OF_LEDS

    current_hue = float(settings.get("base_hue", 0.58)) % 1.0
    target_hue = (current_hue + float(settings.get("hue_step", 0.0))) % 1.0
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

                cycle_interval = float(settings.get('cycle_interval', MODE_CYCLE_INTERVAL))
                if cycle_interval < 0.5:
                    cycle_interval = 0.5
                if now - last_mode_switch > cycle_interval:
                    show_cpu_mode = not show_cpu_mode
                    last_mode_switch = now

                if now - last_data_time > settings["update_interval"]:
                    cached_temp = get_cpu_temp()
                    cached_usage = psutil.cpu_percent()
                    cached_watts = get_cpu_power_linux()
                    if cached_watts is None:
                        cached_watts = 0
                    cached_watts = int(cached_watts)
                    try:
                        f = psutil.cpu_freq()
                        cached_speed = int(f.current) if f else 0
                    except:
                        cached_speed = 0

                    cached_gpu_temp, cached_gpu_usage, cached_gpu_speed, cached_gpu_watts = get_gpu_stats_linux()
                    last_data_time = now

                    leds_on_mask = [False] * NUMBER_OF_LEDS

                    active_temp = cached_temp if show_cpu_mode else cached_gpu_temp
                    active_usage = cached_usage if show_cpu_mode else cached_gpu_usage
                    active_speed = cached_speed if show_cpu_mode else cached_gpu_speed
                    active_watts = cached_watts if show_cpu_mode else cached_gpu_watts

                    disp_temp = clamp_int(active_temp, 0, 199)
                    disp_usage = clamp_int(active_usage, 0, 100)
                    disp_speed = clamp_int(active_speed, 0, 9999)
                    disp_watts = clamp_int(active_watts, 0, 99)

                    # 1. Temp (Top Left)
                    t_str = f"{disp_temp: >3}"
                    for i, c in enumerate(t_str):
                        if c in digit_shapes:
                            for idx, on in enumerate(digit_shapes[c]):
                                if on:
                                    leds_on_mask[temp_digits_indices[i][idx]] = True

                    # 2. Usage (Bottom Right)
                    u_val = int(disp_usage)
                    if disp_usage > 0 and u_val == 0:
                        u_val = 1
                    u_str = f"{min(u_val, 99):02}"
                    for i, c in enumerate(u_str):
                        if c in digit_shapes:
                            for idx, on in enumerate(digit_shapes[c]):
                                if on:
                                    leds_on_mask[usage_digits_indices[i][idx]] = True

                    # 3. Speed (Bottom Left)
                    s_str = f"{disp_speed: >4}"
                    for i, c in enumerate(s_str):
                        if c in digit_shapes:
                            for idx, on in enumerate(digit_shapes[c]):
                                if on:
                                    leds_on_mask[speed_digits_indices[i][idx]] = True

                    # 4. Watts (Top Right)
                    w_val = disp_watts
                    w_str = f"{w_val:02}"
                    for i, c in enumerate(w_str):
                        if c in digit_shapes:
                            for idx, on in enumerate(digit_shapes[c]):
                                if on:
                                    leds_on_mask[watt_digits_indices[i][idx]] = True

                    # 5. Static symbols only (usage bar disabled to prevent segment overlap artifacts)

                    leds_on_mask[0] = True     # %
                    leds_on_mask[16] = True    # MHz
                    leds_on_mask[69] = True    # C
                    leds_on_mask[51] = show_cpu_mode
                    leds_on_mask[59] = not show_cpu_mode

                # ANIMATION
                wipe_progress += settings["wipe_speed"]
                hue_step = float(settings.get("hue_step", 0.0))
                base_hue = float(settings.get("base_hue", 0.58)) % 1.0
                saturation = max(0.0, min(1.0, float(settings.get("saturation", 0.18))))
                if abs(hue_step) < 1e-9:
                    # Fixed color mode (e.g. white if saturation=0.0)
                    current_hue = base_hue
                    target_hue = base_hue
                if wipe_progress >= 1.2:
                    wipe_progress = 0.0
                    current_hue = target_hue
                    target_hue = (target_hue + hue_step) % 1.0

                # --- COLOR LOGIC ---
                offset = settings.get("left_color_offset", 0.1)

                # Base (Right Side)
                r_base, g_base, b_base = colorsys.hsv_to_rgb(current_hue, saturation, 1.0)
                col_right_old = f"{int(r_base*255):02X}{int(g_base*255):02X}{int(b_base*255):02X}"
                r_base_n, g_base_n, b_base_n = colorsys.hsv_to_rgb(target_hue, saturation, 1.0)
                col_right_new = f"{int(r_base_n*255):02X}{int(g_base_n*255):02X}{int(b_base_n*255):02X}"

                # Offset (Left Side)
                hue_left = (current_hue + offset) % 1.0
                target_hue_left = (target_hue + offset) % 1.0
                r_left, g_left, b_left = colorsys.hsv_to_rgb(hue_left, saturation, 1.0)
                col_left_old = f"{int(r_left*255):02X}{int(g_left*255):02X}{int(b_left*255):02X}"
                r_left_n, g_left_n, b_left_n = colorsys.hsv_to_rgb(target_hue_left, saturation, 1.0)
                col_left_new = f"{int(r_left_n*255):02X}{int(g_left_n*255):02X}{int(b_left_n*255):02X}"

                # Brightness
                col_right_old = apply_brightness(col_right_old, settings["brightness"])
                col_right_new = apply_brightness(col_right_new, settings["brightness"])
                col_left_old = apply_brightness(col_left_old, settings["brightness"])
                col_left_new = apply_brightness(col_left_new, settings["brightness"])

                colors = ["000000"] * NUMBER_OF_LEDS
                for i in range(NUMBER_OF_LEDS):
                    if leds_on_mask[i]:
                        is_right = (led_group_mask[i] == 1)
                        c_old = col_right_old if is_right else col_left_old
                        c_new = col_right_new if is_right else col_left_new

                        if wipe_progress >= led_pos_coords[i]:
                            colors[i] = c_new
                        else:
                            colors[i] = c_old

                sys.stdout.write(
                    f"\rMode: {'CPU' if show_cpu_mode else 'GPU'} | "
                    f"CPU T/U/S/W: {int(cached_temp)}C/{int(cached_usage)}%/{int(cached_speed)}MHz/{int(cached_watts)}W | "
                    f"GPU T/U/S/W: {int(cached_gpu_temp)}C/{int(cached_gpu_usage)}%/{int(cached_gpu_speed)}MHz/{int(cached_gpu_watts)}W   "
                )
                sys.stdout.flush()

                header = 'dadbdcdd000000000000000000000000fc0000ff'
                message = "".join(colors)
                dev.write(bytes.fromhex(header + message[:128-len(header)]))
                payload = message[88:]
                for i in range(4):
                    if payload[i*128 : (i+1)*128]:
                        dev.write(bytes.fromhex('00' + payload[i*128:(i+1)*128]))

                time.sleep(0.20)

        except Exception as e:
            print(f"\nWaiting... {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
