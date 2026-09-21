# Deploy EFWS on a Raspberry Pi

Follow this guide to install and run EFWS as a systemd service on a Raspberry Pi.

**Route through this guide:** [Wire hardware](#stage-0--physical-wiring) → [prepare the OS](#stage-2--os-setup-once-only) → [configure EFWS](#stage-4--configuration-env) → [test 4G](#stage-5--4g-connection-setup-gsm-connectservice) → [test sensors](#stage-7--test-each-sensor-important-sequence-hardware-mode) → [start services](#stage-9--install-all-services-production).

Before starting, assemble the hardware listed in [SensorSpecification.md](SensorSpecification.md) and [PowerSystem.md](PowerSystem.md). This guide assumes a Raspberry Pi 4, a 32 GB microSD card, the documented sensor set, one 4G modem, a 5 V relay, a 12 V siren, and the solar battery system. The SIM7600 instructions use a Waveshare HAT and a Telkomsel SIM as examples; adjust the APN and modem details for your hardware.

Keep the project layout flat: `main.py`, `.env`, `scripts/`, `logs/`, and `database/` belong in the same project root. The virtual environment is created there as `venv/`.

The Raspberry Pi runs these services:
- `gsm-connect.service` — 4G connection + GPS fetch (run first, once at boot)
- `efws.service` — main application EFWS (start after gsm-connect is complete)
- `ews-gps-refresh.timer` — refreshes GPS every 30 minutes in background

---

## STAGE 0 — Physical wiring

Read the [pinout](Pinout.md) and [power guide](PowerSystem.md) before connecting anything. Pay particular attention to these points:

- The MCP3008 uses a **3.3 V reference**. Never connect a 5 V analog output directly to it. The original design routes MQ-2, MQ-135, and soil probe outputs through a four-channel logic-level converter, but that digital converter can distort analog values. Verify the interface and calibrate the readings before deployment.
- Battery voltage sensor and Flame Sensor AO directly to MCP3008 **without LLC**
  (already native 3.3 V).
- Power the 12 V siren through the relay contacts, never from a GPIO pin.
- Wind Direction JL-FSX2 requires kernel prerequisites (see STAGE 2).
- The 4-20 mA pressure sensor requires a separate 12 V PSU for the loop and a 100 Ω burden resistor.
- Connect the SIM7600 HAT to the Pi with a USB data cable and install both LTE and GNSS antennas.

After wiring, complete the operating system setup before running the application.

---

## STAGE 1 — Move the project to the Raspberry Pi

```bash
# From laptop/PC:
scp -r ews_1 uwfadmin@<ip-raspberry-pi>:/home/uwfadmin/ews

# SSH login:
ssh uwfadmin@<ip-raspberry-pi>
cd /home/uwfadmin/ews
```

> Match the username `uwfadmin` and destination folder name to your setup.
> This path must be consistent with `WorkingDirectory=` and `ExecStart=` in all `.service` files.

---

## STAGE 2 — OS setup (once only)

### 2a. Install system dependencies

```bash
sudo apt update && sudo apt install -y \
    python3-venv python3-pip \
    i2c-tools \
    usb-modeswitch modemmanager \
    network-manager \
    git
```

> `network-manager` and `modemmanager` are **required** for SIM7600 connection via nmcli.

### 2b. Activate the ModemManager and NetworkManager services

```bash
sudo systemctl enable --now ModemManager
sudo systemctl enable --now NetworkManager
```

Check modem status after SIM7600 is plugged in:

```bash
mmcli -L
# Should appear: /org/freedesktop/ModemManager1/Modem/0 [QUALCOMM] SIMCOM_SIM7600...
```

### 2c. Enable hardware interfaces

```bash
sudo raspi-config
# Interface Options → SPI       → Yes   (MCP3008)
# Interface Options → I2C       → Yes   (BME280, Rainfall SEN0575)
# Interface Options → Serial Port:
#   "login shell over serial" → No
#   "serial port hardware"    → Yes     (Wind Direction UART)

sudo reboot
```

### 2d. Enable full UART for Wind Direction (JL-FSX2)

The wind direction sensor uses GPIO14/GPIO15 (UART). On a Raspberry Pi 4, the default serial configuration can leave these pins on the clock-sensitive mini-UART while Bluetooth uses the PL011 UART.

```bash
# Add to /boot/config.txt (or /boot/firmware/config.txt in Bookworm):
sudo nano /boot/config.txt
# Add at the end:
#   dtoverlay=disable-bt

# After save:
sudo systemctl disable hciuart
sudo reboot
```

After rebooting, `/dev/serial0` should point to the PL011 UART with a stable baud rate.

### 2e. Add the user to the hardware group

```bash
# Change "uwfadmin" according to the username used:
sudo usermod -aG gpio,spi,i2c,dialout uwfadmin
sudo reboot
```

### 2f. Verify device detected

```bash
lsusb                    # should appear: SIMCom or Qualcomm (SIM7600)
ls /dev/ttyUSB*          # SIM7600 commonly exposes ttyUSB0–ttyUSB3; RS485 port number may vary
ls /dev/spidev*          # should be: /dev/spidev0.0 (MCP3008)
i2cdetect -y 1           # should be: 0x76 (BME280) AND 0x1D (Rainfall SEN0575)
ls /dev/serial0          # should exist for the wind direction sensor
```

> Port SIM7600 (Waveshare HAT):
> - `ttyUSB0` = DM (diagnostic), `ttyUSB1` = AT secondary, `ttyUSB2` = **AT command** ← used script
> - `ttyUSB3` = PPP/modem (do not use together with nmcli)
>
> If an expected device is missing, check its wiring and the interface settings in `raspi-config` before continuing.

---

## STAGE 3 — Setup Python environment

```bash
cd /home/uwfadmin/ews
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
deactivate
```

---

## STAGE 4 — Configuration `.env`

```bash
cp .env.example .env
nano .env
```

### Required settings

```ini
# Device identity (unique per unit in the field)
EFWS_DEVICE_ID=DEV-JAM-001
EFWS_DEVICE_TOKEN=token_from_backend

# For initial prototyping: open https://webhook.site, copy unique URL
EFWS_API_URL=https://webhook.site/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
EFWS_API_KEY=

# Mode: "mock" first for testing without hardware, "hardware" for production
EFWS_RUN_MODE=mock

# Static fallback coordinates (used ONLY if GPS has never been fixed at all)
# When GPS has been fixed, the /tmp/ews_gps_cache.json cache is used (not this)
EFWS_LAT=-6.2146
EFWS_LON=106.8208

# SIM card APN (Telkomsel = internet, Tri = 3data)
# If not filled in, ews_network_setup.sh auto-detects the operator code
EFWS_APN=internet
```

### Intervals (optional defaults)

```ini
EFWS_READ_INTERVAL=180              # sensor sampling every 3 minutes
EFWS_TELEMETRY_INTERVAL_SEC=1800 # send telemetry every 30 minutes (normal)
EFWS_EMERGENCY_TELEMETRY_INTERVAL_SEC=600  # every 10 minutes during an emergency
EFWS_LOCATION_INTERVAL_SEC=1800     # send location every 30 minutes (always fixed)
EFWS_HEARTBEAT_INTERVAL_SEC=300     # heartbeat every 5 minutes (always constant)
EFWS_CONNECTIVITY_CHECK_SEC=120     # Retry offline queue every 2 minutes
```

### SIM7600 settings (optional Waveshare HAT defaults)

```ini
# EFWS_SIM_PORT=/dev/ttyUSB2    # AT command port SIM7600 (default: ttyUSB2)
# EFWS_SIM_BAUD=115200          # baudrate AT port
# EFWS_GPS_CACHE=/tmp/ews_gps_cache.json # cache file GPS (reads main.py)
```

---

## STAGE 5 — 4G connection setup (gsm-connect.service)

Complete the 4G connection before testing API delivery.

### 5a. Install services and scripts

```bash
# Copy service files to systemd
sudo cp /home/uwfadmin/ews/gsm-connect.service     /etc/systemd/system/
sudo cp /home/uwfadmin/ews/ews-gps-refresh.service /etc/systemd/system/
sudo cp /home/uwfadmin/ews/ews-gps-refresh.timer   /etc/systemd/system/

# Set executable
chmod +x /home/uwfadmin/ews/scripts/ews_network_setup.sh
chmod +x /home/uwfadmin/ews/scripts/gps_refresh.sh
chmod +x /home/uwfadmin/ews/scripts/check_comm.sh

# Reload systemd
sudo systemctl daemon-reload
```

### 5b. Manual 4G connection test (before enabling service)

```bash
sudo bash /home/uwfadmin/ews/scripts/ews_network_setup.sh
```

Check the script output:
```
[1/8] Check ModemManager & NetworkManager...
[2/8] Enable WWAN radio...
[3/8] Wait for modem SIM7600... ← should display "Modem found: Modem/0"
[4/8] Define APN... ← should appear Provider: Telkomsel / APN: internet
[5/8] EWS-4G profile configuration...
[6/8] Set WiFi as backup...
[7/8] Activate EWS-4G connection... ← should display "active successfully!"
[8/8] Verify connection... ← should appear IP + interface (wwan0 / cdc-wdm0)
[GPS] Start GPS fetch via AT command... (takes ~5-10 minutes)
```

Manual verification after the script is complete:

```bash
# Check active interface
nmcli device status
# Must be: cdc-wdm0 gsm connected EWS-4G

# Check the default route via modem (not WiFi)
ip route get 8.8.8.8
# Expect: dev wwan0 or another modem interface (not wlan0)

# Check IP obtained
ip addr show wwan0   # or cdc-wdm0

# Test internet
ping -c 4 8.8.8.8

# Check cache GPS (takes a few minutes)
cat /tmp/ews_gps_cache.json
# If fixed: {"fix":true,"lat":-6.xxx,"lon":106.xxx,...}
# If not fixed: {"fix":false,...} — move the GNSS antenna outdoors and wait
```

### 5c. If the route is still via WiFi (troubleshoot metric)

```bash
# Check the installed metrics
ip route show

# Force the 4G metric to be smaller than WiFi
sudo nmcli connection modify "EWS-4G" ipv4.route-metric 50
sudo nmcli connection modify "<your-wifi-profile>" ipv4.route-metric 600
sudo nmcli connection up "EWS-4G"
```

### 5d. Enable service to auto-start at boot

```bash
sudo systemctl enable gsm-connect.service
sudo systemctl enable ews-gps-refresh.timer
```

### 5e. Run complete diagnostics

```bash
sudo bash /home/uwfadmin/ews/scripts/check_comm.sh
```

All lines should be `[OK]` or `[WARN]` (not `[FAIL]`).

---

## STAGE 6 — Test connection API (mock mode)

```bash
source venv/bin/activate
python3 tests/test_webhook_api.py
```

Check the webhook.site page for a JSON POST. Its arrival confirms that the Pi can reach the test endpoint over the active network connection.

> No internet connection yet? Run `tools/mock_api_server.py` on the laptop (one
> Wi-Fi network with the Pi), then set `EFWS_API_URL=http://<ip-laptop>:5000`.

---

## STAGE 7 — Test each sensor (IMPORTANT SEQUENCE, hardware mode)

First change `.env`:
```ini
EFWS_RUN_MODE=hardware
```

Run the tests **in order**. Resolve a failed test before proceeding.

```bash
source venv/bin/activate

# 1. MCP3008 — foundation for the analog sensors
python3 tests/test_mcp3008.py

# 2. MQ-2 & MQ-135 (analog via MCP3008 + LLC)
python3 tests/test_gas_sensors.py

# 3. BME280 (I2C)
python3 tests/test_bme280.py

# 4. Rainfall Sensor SEN0575 (I2C)
python3 tests/test_rainfall.py

# 5. Soil Moisture × 2 (analog via MCP3008 + LLC)
python3 tests/test_soil.py

# 6. Submersible Pressure Sensor (4-20mA via burden resistor → MCP3008)
python3 tests/test_pressure.py

# 7. Battery Voltage Sensor (analog via MCP3008, native 3.3V)
python3 tests/test_battery.py

# 8. Flame Sensor (AO analog via MCP3008 CH6)
python3 tests/test_flame.py

# 9. Anemometer RS485 (Modbus RTU via USB-RS485)
python3 tests/test_anemometer.py

# 10. Wind Direction JL-FSX2 (UART /dev/serial0)
python3 tests/test_weather.py

# 11. Relay + Siren (⚠️ LOUD 120 dB — keep away from ears)
python3 tests/test_relay_siren.py

# 12. All sensors at once (final check before main.py)
python3 tests/test_all_sensors.py

# 13. Offline queue integrity (simulation of broken network)
python3 tests/test_offline_queue_integrity.py
```

> The network setup script handles the SIM7600 and writes the GPS cache. `main.py` reads that cache. Check it with `cat /tmp/ews_gps_cache.json`.

---

## STAGE 8 — Run full EFWS (foreground first)

```bash
source venv/bin/activate
python3 main.py
```

Observe several cycles (default every 3 minutes). Make sure:
- All sensors read (no unexpected `NullSensor`)
- The log displays `READ | all values NORMAL` or the expected threshold
- `[Telemetry Publisher] Normal Scheduled Send` appears and webhook.site receives the data
- `[Location Publisher]` appears and displays `📍 [GPS] Cache valid — lat=..., lon=...`
  or `GPS cache missing / fix=false` (if GPS has no fix), then uses configured coordinates
- `[Heartbeat Publisher]` appears every 5 minutes

Press `Ctrl+C` to stop. EFWS shuts down gracefully, turning off the siren and closing connections.

---

## STAGE 9 — Install all services (production)

### 9a. Copy and enable all services

```bash
# Copy service files to systemd (if not already from STAGE 5)
sudo cp /home/uwfadmin/ews/gsm-connect.service     /etc/systemd/system/
sudo cp /home/uwfadmin/ews/ews-gps-refresh.service /etc/systemd/system/
sudo cp /home/uwfadmin/ews/ews-gps-refresh.timer   /etc/systemd/system/
sudo cp /home/uwfadmin/ews/efws.service             /etc/systemd/system/

sudo systemctl daemon-reload

# Enable all (auto-start at boot)
sudo systemctl enable gsm-connect.service
sudo systemctl enable ews-gps-refresh.timer
sudo systemctl enable efws.service
```

### 9b. Starting for the first time (important sequence)

```bash
# 1. Run network setup first
sudo systemctl start gsm-connect
# Wait for it to finish (oneshot — can take 5-15 minutes for GPS)
sudo systemctl status gsm-connect   # must be: active (exited)

# 2. Start GPS timer
sudo systemctl start ews-gps-refresh.timer

# 3. Start EFWS
sudo systemctl start efws
```

> After this, when the Raspberry Pi **reboots**, `gsm-connect` automatically starts first,
> `efws` waits for `gsm-connect` to finish, then starts.
> This is guaranteed by `After=gsm-connect.service` and `Requires=gsm-connect.service`
> at `efws.service`.

### 9c. Daily operations

```bash
# ── Status ───────────────────────────────────────────────────────────
sudo systemctl status efws            # main EFWS state
sudo systemctl status gsm-connect    # status network setup
systemctl list-timers ews-gps*       # status timer GPS refresh

# ── Log real-time ────────────────────────────────────────────────────
sudo journalctl -u efws -f            # log EFWS (Ctrl+C just stops monitoring, service still running)
sudo journalctl -u gsm-connect -f     # log network setup
sudo journalctl -u ews-gps-refresh -f # log GPS refresh
tail -f /home/uwfadmin/ews/logs/network_setup.log  # network logs (more details)
tail -f /home/uwfadmin/ews/logs/gps_refresh.log    # log GPS refresh
tail -f /home/uwfadmin/ews/logs/efws.log           # log EFWS (timestamp ms)

# ── Restart (MANDATORY after updating code or editing .env) ───────────────
sudo systemctl restart efws

# ── GPS manual check ──────────────────────── ─────────────────────────
cat /tmp/ews_gps_cache.json           # see the last position of GPS
sudo bash /home/uwfadmin/ews/scripts/gps_refresh.sh  # force a GPS refresh
sudo journalctl -u ews-gps-refresh -n 30 # recent GPS refresh logs

# ── Complete connection diagnostics ──────────────────── ────────────────────
sudo bash /home/uwfadmin/ews/scripts/check_comm.sh
```

### 9d. Script helper (alternative for development)

```bash
chmod +x scripts/efws_ctl.sh
./scripts/efws_ctl.sh start     # run in the background
./scripts/efws_ctl.sh status    # check + CPU/RAM
./scripts/efws_ctl.sh logs      # tail log real-time
./scripts/efws_ctl.sh restart   # restart after each code update
./scripts/efws_ctl.sh stop      # stop
```

---

## STAGE 10 — Reboot command permission setup

The backend can send a `Reboot` command in a heartbeat response. EFWS handles it by running `sudo systemctl restart efws.service` from a child process. Add this narrowly scoped sudoers rule so the service can run that command without an interactive password:

```bash
sudo visudo -f /etc/sudoers.d/efws
```

File contents:
```
uwfadmin ALL=(root) NOPASSWD: /usr/bin/systemctl restart efws.service
```

> Without this line, the command `Reboot` from the backend will always fail with status `FAILED`.

---

## STAGE 11 — Move to production API

When the production backend is ready, replace the test endpoint in `.env`:

```bash
nano .env
```

Set the following values inside the file:

```ini
EFWS_API_URL=https://your-api.example/v1
EFWS_API_KEY=token_from_backend
```

```bash
sudo systemctl restart efws
```

Verify in the log that `[Telemetry Publisher]` sends to the new URL and
`⚙️ Remote thresholds updated from backend:` appears if the backend returns `config`.

---

## Troubleshooting

### 4G connection

| Symptom | Possible Cause | Solution |
|--------|----------------------|--------|
| `mmcli -L` → `No modems were found` |SIM7600 not detected USB|`lsusb` + `ls /dev/ttyUSB*`; check data cable USB; press the modem button PWRKEY; replace port USB|
| `cdc-wdm0 gsm disconnected` |The modem is detected but the connection is not active|`sudo nmcli connection up EWS-4G` or `sudo systemctl restart gsm-connect`|
|Route still via `wlan0` (WiFi)|The route metric is incorrect|`ip route show` → make sure EWS-4G metric 50, WiFi metric 600; run `sudo nmcli connection up EWS-4G`|
| `gsm-connect` status `failed` | Script error |`journalctl -u gsm-connect -n 50`; check `tail -f logs/network_setup.log`|
|There is no IP on `wwan0`|APN is incorrect or the modem has not been registered|Check operator code: `mmcli -m 0\|grep operator-code`; adjust the APN in `.env`|

### GPS

| Symptom | Possible Cause | Solution |
|--------|----------------------|--------|
|`fix=false` in cache JSON|GNSS antenna is not installed / indoors|Make sure the GNSS antenna (not the LTE antenna) is installed and there is open sky; cold fix takes 2-5 minutes|
|`/tmp/ews_gps_cache.json` does not exist|Script not running / AT port error| `sudo bash scripts/gps_refresh.sh` + `journalctl -u ews-gps -n 30` |
|`port_busy` in cache|The ttyUSB2 port is used by another process|`fuser /dev/ttyUSB2`; kill the process; rerun gps_refresh|
| `port_not_found` |SIM7600 does not mount as ttyUSB2|`ls /dev/ttyUSB*`; change `EFWS_SIM_PORT=/dev/ttyUSBx` in `.env`|
|Location in EFWS is always from config (lat=..env..)|Cache GPS is missing / fix=false|Wait for GPS warm-up or check GNSS antenna|

### Sensor

| Component | Symptom | Possible Cause |
|----------|--------|----------------------|
| MCP3008 | `test_mcp3008.py` error |SPI is not active yet (`raspi-config`); wiring CLK/MISO/MOSI/CS incorrect; `spidev` is not installed|
| MQ-2/MQ-135 |Clipping value / is always max|There is no Logic Level Converter on the 5V analog line|
| MQ-2/MQ-135 |ppm doesn't make sense|The sensor needs 24–48 hours of preheat for full accuracy|
| BME280 |`i2cdetect -y 1` is empty|I2C is not active yet; SDA/SCL reversed; try `EFWS_BME280_ADDR=0x77`|
| Rainfall SEN0575 |`RuntimeError: PID/VID mismatch`|Sensor not installed / incorrect I2C address (`0x1D`); I2C is not active yet|
| Soil Probe |`moisture_percent` is always 0% or 100%|Calibrate `dry_raw` and `wet_raw` in `sensors/soil.py`|
| Flame Sensor |`flame_detected` is always True/False|Threshold `EFWS_FLAME_AO_THRESHOLD_V` has not been calibrated; see `python sensors/flame.py`|
| Pressure Sensor | `fault_open_loop=True`, `current_ma≈0` |4-20 mA loop breaks; PSU 12 V loop is not on; The burden resistor is not installed|
| Battery Sensor |`voltage`/`percent` is incorrect|`EFWS_BATTERY_SENSOR_MAX_V` (default 16.5V) or `EFWS_BATTERY_MAX_V`/`MIN_V` need to be customized|
| Anemometer RS485 |Exception when reading|Incorrect Slave ID / Modbus register; A/B wiring reversed; `EFWS_ANEM_PORT` is incorrect|
| Wind Direction |Random/non-existent data|`disable-bt` is not set; console serial login is still active; TX/RX wiring is reversed|
| Relay |Click but the siren doesn't sound|The 12 V siren source is not connected; COM/NO wiring is faulty|
| Relay |Doesn't click|GPIO pin on `.env` does not match physical wiring; check `EFWS_GPIO_RELAY`|

### System and services

| Symptom | Possible Cause | Solution |
|--------|----------------------|--------|
|API send fails continuously|No internet|`ping 8.8.8.8`; check route (`ip route get 8.8.8.8`); make sure EWS-4G is active|
| `efws` status `failed` |Python module missing / `.env` not read|`journalctl -u efws -n 50`; activate venv + check `requirements.txt`|
| Reboot command `FAILED` |Sudoers rule has not been added|See STAGE 10|
| SQLite continues to grow | Retention loop has a problem | Check log `🧹 Retention:`; make sure `EFWS_DB_RETENTION_DAYS=3` |

---

## Check System Condition — Useful Commands

```bash
# ── Network ──────────────────────────── ─────────────────────────────
nmcli device status                   # status of all interfaces
ip route get 8.8.8.8                  # check the route to the internet (must be via wwan0/cdc-wdm0)
mmcli -L                              # list of detected modems
mmcli -m 0                            # detail modem (signal, state, operator)
sudo bash scripts/check_comm.sh # complete diagnostics (modem + connection + GPS + API)

# ── GPS ──────────────────────────────────────────────────────────────
cat /tmp/ews_gps_cache.json           # cache GPS (written by ews_network_setup / gps_refresh)
sudo bash scripts/gps_refresh.sh      # force a GPS refresh now
systemctl list-timers ews-gps*        # inspect the GPS refresh timer (last and next run)
journalctl -u ews-gps-refresh -n 40  # recent GPS refresh logs

# ── EFWS ─────────────────────────────────────────────────────────────
sudo journalctl -u efws -f            # log real-time
sudo journalctl -u efws -n 100 --no-pager  # Last 100 lines
tail -f logs/efws.log # log file (timestamp ms, more details)

# ── Local database ───────────────────────── ──────────────────────────
python3 -c "
from database.db_manager import DBManager
import json
db = DBManager()
print('Pending queue:', db.count_pending_queue(), 'item')
for r in db.recent_readings(5): print(r)
db.close()
"

# ── Additional tools ───────────────────────────────────────────────────
python3 tools/modbus_register_scan.py   # scan register Modbus anemometer
```
