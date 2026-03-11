# BASSLINE recorder Backend
import os, time, socket, struct, subprocess, threading, psutil, fcntl, json
from flask import Flask, jsonify, request, render_template

# OLED Setup
try:
    from luma.core.interface.serial import i2c
    from luma.core.render import canvas
    from luma.oled.device import ssd1306
    serial = i2c(port=1, address=0x3C)
    device = ssd1306(serial)
    HAS_OLED = True
except Exception:
    HAS_OLED = False

app = Flask(__name__)

# 1. Setup paths
SD_PATH = "/mnt/artnet_data"
CONFIG_FILE = os.path.join(os.path.dirname(__file__), "config.json")

# 2. Define STATE (Must come before any dictionary assignments)
STATE = {
    "slot": 1, "next_slot": 1, "recording": False, "armed": False,
    "playing": False, "paused": False, "loop": False, "speed": 1.0,
    "rUni": 0, "pUni": 0, "pIP": "", "ip": "0.0.0.0", "version": "2.2",
    "bO": False, "oled_on": True, 
    "staticIP": "", "staticMask": "", "staticGW": "",
    "data_dir": SD_PATH  # Initialize with default
}

# 3. Define Configuration Functions
def save_config():
    """Saves specific STATE keys to a JSON file."""
    config_data = {
        "rUni": STATE["rUni"],
        "pUni": STATE["pUni"],
        "pIP": STATE["pIP"],
        "staticIP": STATE["staticIP"],
        "staticMask": STATE["staticMask"],
        "staticGW": STATE["staticGW"],
        "data_dir": STATE["data_dir"] # Keep track of SD vs USB
    }
    with open(CONFIG_FILE, "w") as f:
        json.dump(config_data, f)

def load_config():
    """Loads settings from JSON file into STATE on startup."""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                data = json.load(f)
                STATE["rUni"] = data.get("rUni", 0)
                STATE["pUni"] = data.get("pUni", 0)
                STATE["pIP"] = data.get("pIP", "")
                STATE["staticIP"] = data.get("staticIP", "")
                STATE["staticMask"] = data.get("staticMask", "")
                STATE["staticGW"] = data.get("staticGW", "")
                
                # Check if saved USB/Custom path still exists, otherwise fallback to SD
                saved_path = data.get("data_dir", SD_PATH)
                if os.path.exists(saved_path):
                    STATE["data_dir"] = saved_path
                else:
                    STATE["data_dir"] = SD_PATH
        except Exception as e:
            print(f"Error loading config: {e}")
    
    # Ensure the active directory actually exists on the drive
    if not os.path.exists(STATE["data_dir"]):
        os.makedirs(STATE["data_dir"], exist_ok=True)

def ip_watcher():
    """Polls for a valid IP address every 2 seconds if currently 127.0.0.1."""
    while True:
        #if STATE["ip"] in ["0.0.0.0", "127.0.0.1", "Connecting..."]:
        if not (STATE["playing"] or STATE["recording"] or STATE["armed"]):
            new_ip = get_ip()
            if new_ip != "127.0.0.1":
                STATE["ip"] = new_ip
                update_oled()
        time.sleep(2)

def get_ip():
    interfaces = psutil.net_if_addrs()
    for iface in ['eth0', 'wlan0', 'enp1s0']:
        if iface in interfaces:
            for addr in interfaces[iface]:
                if addr.family == socket.AF_INET:
                    return addr.address
    return "127.0.0.1"

def update_oled():
    if not HAS_OLED or STATE.get("done"): return
    
    # NEW LOGIC: Ignore the "off" setting if we are rebooting or shutting down
    is_system_action = STATE.get("rebooting") or STATE.get("shutting_down")
    if not STATE.get("oled_on", True) and not is_system_action: 
        return 

    try:
        display_ip = STATE["ip"]
        if display_ip in ["127.0.0.1", "0.0.0.0"]:
            display_ip = "Connecting..."

        with canvas(device) as draw:
            # Check for system overrides first
            if STATE.get("shutting_down"):
                draw.rectangle((0, 0, 127, 63), outline="white", fill="black")
                draw.text((10, 20), "SHUTTING DOWN...", fill="white")
                return
            if STATE.get("rebooting"):
                draw.rectangle((0, 0, 127, 63), outline="white", fill="black")
                draw.text((35, 25), "REBOOTING...", fill="white")
                return

            # Normal UI
            draw.text((0, 0), f"IP: {display_ip}", fill="white")
            status_txt = "IDLE"
            if STATE["playing"]: status_txt = "PLAYING"
            if STATE["paused"]:  status_txt = "PAUSED"
            if STATE["armed"]:   status_txt = "WAITING..."
            if STATE["recording"]: status_txt = "RECORDING"
            draw.text((0, 18), f"MODE: {status_txt}", fill="white")
            draw.text((0, 36), f"R:{STATE['rUni']} -> P:{STATE['pUni']}", fill="white")
            draw.text((0, 52), f"Slot:{STATE['slot']}", fill="white")
            draw.text((64, 52), f"Spd:{STATE['speed']}x", fill="white")
    except Exception:
        pass

def show_reboot_screen():
    if not HAS_OLED: return
    try:
        with canvas(device) as draw:
            draw.rectangle((0, 0, 127, 63), outline="white", fill="black")
            draw.text((35, 25), "REBOOTING...", fill="white")
    except Exception:
        pass

def verify_storage():
    """Returns True if storage is valid, False if directory is missing."""
    # Check if the current data directory actually exists on the disk
    if not os.path.exists(STATE["data_dir"]):
        # The directory is gone! Force a reset to SD
        STATE["playing"] = False
        STATE["paused"] = False
        STATE["recording"] = False
        STATE["armed"] = False
        STATE["data_dir"] = SD_PATH
        save_config()
        update_oled()
        return False
    return True

def scan_artnet_traffic():
    found = set()
    scan_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    scan_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if hasattr(socket, 'SO_REUSEPORT'): 
        scan_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    
    try:
        scan_sock.bind(('0.0.0.0', 6454))
        scan_sock.settimeout(0.5)
        start_scan = time.time()
        while time.time() - start_scan < 3.0:
            try:
                data, addr = scan_sock.recvfrom(1024)
                if addr[0] != STATE["ip"] and len(data) > 18:
                    if data[0:8] == b'Art-Net\x00':
                        opcode = struct.unpack('<H', data[8:10])[0]
                        if opcode == 0x5000:
                            uni = struct.unpack('<H', data[14:16])[0]
                            found.add(uni)
            except socket.timeout:
                continue
    except Exception:
        pass
    finally:
        scan_sock.close()
    return sorted(list(found))

def artnet_recorder():
    last_seq = -1
    while True:
        if (STATE["recording"] or STATE["armed"]) and not STATE["playing"]:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if hasattr(socket, 'SO_REUSEPORT'):
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            
            try:
                sock.bind(('0.0.0.0', 6454))
            except Exception:
                pass
            
            sock.settimeout(0.2)
            f = None
            last_time = time.perf_counter()
            
            try:
                while (STATE["recording"] or STATE["armed"]) and not STATE["playing"]:
                    try:
                        data, addr = sock.recvfrom(1024)
                        if addr[0] == STATE["ip"]: continue 
                        
                        if len(data) > 18 and data[0:8] == b'Art-Net\x00':
                            opcode = struct.unpack('<H', data[8:10])[0]
                            if opcode == 0x5000:
                                uni = struct.unpack('<H', data[14:16])[0]
                                seq = data[12]
                                
                                if uni == int(STATE["rUni"]):
                                    if seq != last_seq or seq == 0:
                                        last_seq = seq
                                        
                                        # TRIGGER RECORDING START
                                        if STATE["armed"]:
                                            try:
                                                path = f"{STATE['data_dir']}/slot_{STATE['slot']}.bin"
                                                f = open(path, 'wb')
                                                STATE["armed"], STATE["recording"] = False, True
                                                last_time = time.perf_counter()
                                                update_oled()
                                            except (FileNotFoundError, OSError):
                                                # USB pulled or path vanished - reset and bail
                                                STATE["armed"] = False
                                                STATE["recording"] = False
                                                verify_storage() # Reverts path to SD
                                                break

                                        # WRITING DATA
                                        if STATE["recording"] and f:
                                            now = time.perf_counter()
                                            delta = int((now - last_time) * 1000)
                                            last_time = now
                                            try:
                                                f.write(struct.pack('!HH', delta, len(data)) + data)
                                            except (OSError, IOError):
                                                # Handle mid-record disconnect
                                                STATE["recording"] = False
                                                verify_storage()
                                                break

                    except socket.timeout:
                        continue
            finally:
                if f: f.close()
                sock.close()
                last_seq = -1
        time.sleep(0.1)

def artnet_player():
    try:
        os.nice(-10) 
    except Exception:
        pass 

    while True:
        if (STATE["playing"] or STATE["paused"]) and not (STATE["recording"] or STATE["armed"]):
            current_running_slot = STATE["slot"]
            filename = f"{STATE['data_dir']}/slot_{current_running_slot}.bin"
            
            # --- GUARD: If slot is empty, stop playing immediately ---
            if not os.path.exists(filename):
                STATE["playing"] = STATE["paused"] = False
                update_oled()
                time.sleep(0.1)
                continue

            send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            send_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if hasattr(socket, 'SO_REUSEPORT'):
                send_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            send_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            
            try:
                send_sock.bind(('', 6454))
                with open(filename, 'rb') as f:
                    header = None
                    while (STATE["playing"] or STATE["paused"]):
                        if STATE["paused"]:
                            time.sleep(0.05)
                            continue 
                        
                        header = f.read(4)
                        if not header:
                            # End of file reached: Check if user changed slot mid-play
                            if STATE["slot"] != current_running_slot:
                                break # Exit this file and check the new one
                            
                            if STATE["loop"]:
                                f.seek(0)
                                continue
                            else:
                                break
                        
                        delta_ms, data_len = struct.unpack('!HH', header)
                        packet = bytearray(f.read(data_len))
                        struct.pack_into('<H', packet, 14, int(STATE["pUni"]))
                        
                        wait_time = (delta_ms / 1000.0) / float(STATE["speed"])
                        target_time = time.perf_counter() + wait_time
                        
                        while time.perf_counter() < target_time:
                            if (target_time - time.perf_counter()) > 0.003:
                                time.sleep(0.001)
                        
                        if STATE["playing"]:
                            dest = STATE["pIP"] if STATE["pIP"].strip() else "255.255.255.255"
                            send_sock.sendto(packet, (dest, 6454))
                            
                        # Instant exit if slot changes mid-packet
                        if STATE["slot"] != current_running_slot:
                            break

            except Exception:
                pass
            finally:
                send_sock.close()

            # --- WRAP-UP: Decide if we continue playing or stop ---
            # If we exited because the slot changed, check if the NEW slot has data
            new_filename = f"{STATE['data_dir']}/slot_{STATE['slot']}.bin"
            if not os.path.exists(new_filename) or (not STATE["loop"] and not header):
                STATE["playing"] = STATE["paused"] = False
            
            update_oled()
        
        time.sleep(0.1)

@app.route('/status')
def status(): 
    if STATE["ip"] == "0.0.0.0": STATE["ip"] = get_ip()
    return jsonify(STATE)

@app.route('/setSlot')
def set_slot(): 
    n = int(request.args.get('n', 1))
    STATE["next_slot"] = n
    if not STATE["recording"]: 
        STATE["slot"] = n
        update_oled()
    return "ok"

@app.route('/getUnis')
def get_unis():
    if not (STATE["playing"] or STATE["recording"] or STATE["armed"]):
        return jsonify(scan_artnet_traffic())
    return jsonify([])

@app.route('/arm')
def arm():
    if not verify_storage():
        return "USB Drive Disconnected. Reverting to SD.", 400 
    STATE["playing"] = STATE["paused"] = STATE["recording"] = False
    STATE["armed"] = True
    target = f"{STATE['data_dir']}/slot_{STATE['slot']}.bin"
    if os.path.exists(target): os.remove(target)
    update_oled()
    return "ok"

@app.route('/play')
def play():
    if not verify_storage():
        return "USB Drive Disconnected. Reverting to SD.", 400
    if os.path.exists(f"{STATE['data_dir']}/slot_{STATE['next_slot']}.bin"):
        STATE["playing"] = True
        STATE["paused"] = False
        STATE["bO"] = False  # Reset B/O
        update_oled()
        return "ok"
    return "No Data", 404

@app.route('/pause')
def pause():
    if STATE["playing"]:
        STATE["playing"], STATE["paused"] = False, True
        STATE["bO"] = False  # Reset B/O
        update_oled()
    return "ok"

@app.route('/stop')
def stop():
    STATE["recording"] = STATE["playing"] = STATE["armed"] = STATE["paused"] = False
    STATE["bO"] = False  # Reset B/O
    update_oled()
    return "ok"

@app.route('/blackout')
def blackout():
    # 1. Send the Black-Out frame (Always do this)
    try:
        temp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        temp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        header = struct.pack('<8sHHBBHH', b'Art-Net\x00', 0x5000, 14, 0, 0, int(STATE["pUni"]), 512)
        packet = header + b'\x00' * 512
        dest = STATE["pIP"] if STATE["pIP"].strip() else "255.255.255.255"
        temp_sock.sendto(packet, (dest, 6454))
        temp_sock.close()
    except:
        pass

    # 2. State Logic
    if STATE["playing"] or STATE["paused"]:
        # If we were active, toggle the pulsing blackout mode
        if STATE["playing"]:
            STATE["playing"] = False
            STATE["paused"] = True
        STATE["bO"] = not STATE["bO"]
    else:
        # If we were IDLE, just send the frame and stay IDLE
        STATE["bO"] = False 
        STATE["playing"] = False
        STATE["paused"] = False

    return "ok"

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/setLoop')
def set_loop():
    STATE["loop"] = (request.args.get('v') == "1")
    return "ok"

@app.route('/setSpeed')
def set_speed(): 
    STATE["speed"] = float(request.args.get('v', 1.0))
    update_oled()
    return "ok"

@app.route('/storage')
def storage():
    # Run the check before doing anything else
    if not verify_storage():
        # Optional: return a dummy status so the frontend doesn't error out
        return jsonify({"used": 0, "total": 1, "slots": [], "error": "USB Missing"}), 400
        
    usage = psutil.disk_usage(STATE['data_dir'])
    slots = [i for i in range(1, 17) if os.path.exists(f"{STATE['data_dir']}/slot_{i}.bin")]
    return jsonify({"used": usage.used, "total": usage.total, "slots": slots})

@app.route('/savePlay')
def save_play():
    STATE["pUni"] = int(request.args.get('u', 0))
    STATE["pIP"] = request.args.get('ip', '')
    save_config() # <--- Add this
    update_oled()
    return "ok"
    
@app.route('/saveRec')
def save_rec():
    STATE["rUni"] = int(request.args.get('u', 0))
    save_config() # <--- Add this
    update_oled()
    return "ok"

@app.route('/setNetwork')
def set_network():
    ip = request.args.get('ip', '').strip()
    nm = request.args.get('nm', '').strip()
    gw = request.args.get('gw', '').strip()
    conn_name = "Wired connection 1"

# Update STATE so it's saved to config.json
    STATE["staticIP"] = ip
    STATE["staticMask"] = nm
    STATE["staticGW"] = gw
    save_config() # <--- Save to disk BEFORE the reboot

    try:
        if not ip:
            # --- FORCE DHCP LOGIC ---
            # 1. Set method to auto
            subprocess.run(["sudo", "nmcli", "con", "mod", conn_name, "ipv4.method", "auto"], check=True)
            # 2. Explicitly CLEAR the manual IP addresses field
            subprocess.run(["sudo", "nmcli", "con", "mod", conn_name, "ipv4.addresses", ""], check=True)
            # 3. Explicitly CLEAR the gateway
            subprocess.run(["sudo", "nmcli", "con", "mod", conn_name, "ipv4.gateway", ""], check=True)
            # 4. (Optional) Clear manual DNS if you set any
            subprocess.run(["sudo", "nmcli", "con", "mod", conn_name, "ipv4.dns", ""], check=True)
        else:
            # --- STATIC LOGIC ---
            parts = [x for x in nm.split('.') if x.strip().isdigit()]
            cidr = sum(bin(int(x)).count('1') for x in parts) if len(parts) == 4 else 24
            
            subprocess.run(["sudo", "nmcli", "con", "mod", conn_name, 
                            "ipv4.addresses", f"{ip}/{cidr}", 
                            "ipv4.gateway", gw, 
                            "ipv4.method", "manual"], check=True)

        show_reboot_screen()
        global HAS_OLED
        HAS_OLED = False 
        threading.Timer(2.0, lambda: os.system("sudo reboot")).start()
        return "ok"
        
    except Exception as e:
        return str(e), 500
    
@app.route('/mount')
def mount_usb():
    if STATE["playing"] or STATE["recording"] or STATE["armed"]:
        return "System Busy", 400

    usb_mnt_point = "/media/usb"
    
    try:
        # 1. Force a hardware re-scan to clear ghost entries
        subprocess.run(["sudo", "udevadm", "trigger"], check=False)
        time.sleep(1)

        # 2. Dynamic Detection: Find ANY disk in /dev/ that starts with 'sd'
        # We list /dev/ nodes and filter for 'sd' followed by a letter and optional number
        import re
        all_nodes = os.listdir('/dev')
        # This regex looks for sda1, sdb1, sdc1, etc.
        sd_parts = [n for n in all_nodes if re.match(r'sd[a-z][1-9]', n)]
        # Fallback to sda, sdb (no partition)
        sd_disks = [n for n in all_nodes if re.match(r'sd[a-z]$', n)]
        
        target_dev = None
        if sd_parts:
            target_dev = f"/dev/{sd_parts[0]}"
        elif sd_disks:
            target_dev = f"/dev/{sd_disks[0]}"

        if not target_dev:
            STATE["data_dir"] = SD_PATH
            save_config()
            return "No USB hardware found. Reverted to SD Storage.", 404

        # 3. Force-clearing previous mount point
        subprocess.run(["sudo", "umount", "-l", usb_mnt_point], check=False)
        subprocess.run(["sudo", "mkdir", "-p", usb_mnt_point], check=True)

        # 4. Smart Mount (Attempts FAT/NTFS options first, then basic)
        res = subprocess.run([
            "sudo", "mount", "-o", "umask=000,flush", target_dev, usb_mnt_point
        ], capture_output=True, text=True)

        if res.returncode != 0:
            res = subprocess.run(["sudo", "mount", target_dev, usb_mnt_point], capture_output=True, text=True)

        if res.returncode == 0:
            # Final permission fix for non-FAT drives
            subprocess.run(["sudo", "chmod", "777", usb_mnt_point], check=False)
            
            target_path = os.path.join(usb_mnt_point, "artnet_data")
            os.makedirs(target_path, exist_ok=True)
            STATE["data_dir"] = target_path
            save_config()
            return f"Mounted {target_dev} successfully!"
        else:
            raise Exception(res.stderr)

    except Exception as e:
        STATE["data_dir"] = SD_PATH
        save_config()
        return f"Mount Error: {str(e)}"

@app.route('/clearSlot')
def clear_slot():
    if STATE["playing"] or STATE["recording"] or STATE["armed"]:
        return "System Busy", 400
    slot = request.args.get('n')
    path = f"{STATE['data_dir']}/slot_{slot}.bin"
    if os.path.exists(path):
        os.remove(path)
    return "ok"

@app.route('/clearAll')
def clear_all():
    if STATE["playing"] or STATE["recording"] or STATE["armed"]:
        return "System Busy", 400
    import glob
    files = glob.glob(f"{STATE['data_dir']}/slot_*.bin")
    for f in files:
        os.remove(f)
    return "ok"

@app.route('/toggleOLED')
def toggle_oled():
    STATE["oled_on"] = not STATE.get("oled_on", True)
    if not STATE["oled_on"]:
        # Immediately clear the screen when turned off
        if HAS_OLED:
            with canvas(device) as draw:
                pass 
    else:
        update_oled() # Refresh screen immediately when turned on
    return "ok"

@app.route('/sysReboot')
def sys_reboot():
    if STATE["playing"] or STATE["recording"] or STATE["armed"]:
        return "System Busy", 400
    # The OLED watcher will see STATE["rebooting"] and draw the screen
    STATE["rebooting"] = True 
    update_oled()
    # Trigger system reboot after a slight delay for the OLED to update
    subprocess.Popen(["sleep 2 && sudo reboot"], shell=True)
    return "ok"

@app.route('/sysShutdown')
def sys_shutdown():
    if STATE["playing"] or STATE["recording"] or STATE["armed"]:
        return "System Busy", 400
    # 1. Trigger the "SHUTTING DOWN..." text
    STATE["shutting_down"] = True 
    update_oled()
    # 2. Wait 3 seconds for the message to be readable
    time.sleep(3)
    # 3. Clear the screen (Draw empty canvas)
    if HAS_OLED:
        STATE["done"] = True # New flag to stop background updates
        with canvas(device) as draw:
            pass
    # 4. Trigger the system poweroff
    subprocess.Popen(["sleep 2 && sudo poweroff"], shell=True)
    return "ok"

# --- Init ---
load_config()  # <--- Load saved settings first!
STATE["ip"] = get_ip()
update_oled()

threading.Thread(target=artnet_recorder, daemon=True).start()
threading.Thread(target=artnet_player, daemon=True).start()
threading.Thread(target=ip_watcher, daemon=True).start()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80, debug=False, threaded=True)