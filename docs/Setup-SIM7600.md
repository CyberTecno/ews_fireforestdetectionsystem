# Set up SIM7600E as the primary Raspberry Pi connection

> **Scope:** This guide covers the SIM7600E-H modem. EFWS also supports A7670E, but its network setup is not covered here. Some A7670E firmware identifies itself as SIM7670E in the ATI response; the detector handles both names.

This guide configures a SIM7600E-H modem as the Raspberry Pi 4's primary internet connection, with Wi-Fi as backup.

Use the [deployment guide](Deployment.md) for the complete EFWS installation. This page focuses on the modem and network routes.

**Route through this guide:** [Check power and USB](#2-check-the-raspberry-pi-power) → [install the network services](#4-install-networkmanager-and-modemmanager) → [set 4G as primary](#7-create-a-manual-4g-connection) → [set Wi-Fi as backup](#8-make-wifi-a-backup) → [test fallback](#11-test-automatic-fallback).

Final target:

```text
SIM7600E 4G = primary connection
WiFi = automatic backup/fallback connection
```

When the modem disconnects, NetworkManager should fall back to Wi-Fi. When it reconnects, the lower 4G route metric should make it primary again. Verify both transitions in [the fallback test](#11-test-automatic-fallback).

---

## 1. Hardware

- Raspberry Pi 4
- SIM7600E-H 4G HAT / USB modem
- Active SIM card with a suitable data plan
- LTE antenna
- USB data cable
- Stable Raspberry Pi power supply
- Working Wi-Fi connection for backup

> Connect the modem to the Pi with a **USB data cable**. A GPIO connection alone does not expose it as a network device.

---

## 2. Check the Raspberry Pi power

Before setting up the modem, check whether the Raspberry Pi is experiencing undervoltage:

```bash
vcgencmd get_throttled
```

Expected result:

```text
throttled=0x0
```

If the output is:

```text
throttled=0x50000
```

the Pi has recorded an undervoltage event since boot. Check the supply and cable. The Pi 4 needs a stable 5 V / 3 A supply; allow additional current capacity for the modem according to its hardware specifications.

Modems can draw brief current peaks while searching for a network or transmitting.

---

## 3. Check that the modem is detected by USB

Plug the SIM7600E modem into the Raspberry Pi's USB port, then run:

```bash
lsusb
```

Look for a device such as:

```text
ID 1e0e:9001 Qualcomm / Option SimTech
```

or contains the name:

```text
SIMCom
Qualcomm
```

Then check the serial ports:

```bash
ls /dev/ttyUSB*
```

Example:

```text
/dev/ttyUSB0 /dev/ttyUSB1 /dev/ttyUSB2 /dev/ttyUSB3 /dev/ttyUSB4
```

If no modem ports appear:

```text
1. Replace the USB cable with a known data-capable cable
2. Press the modem PWRKEY / POWER button 2–3 seconds
3. Try a different USB port
4. Use a more powerful power supply
5. Try a powered USB hub
```

To view logs when the modem is plugged in:

```bash
sudo dmesg -wH
```

Reconnect the modem and look for `new USB device`, `SIMCom`, or `ttyUSB` messages.

Press `Ctrl+C` to stop following the log.

---

## 4. Install NetworkManager and ModemManager

Install the packages:

```bash
sudo apt update
sudo apt install -y modemmanager network-manager
```

Enable both services:

```bash
sudo systemctl enable --now ModemManager
sudo systemctl enable --now NetworkManager
```

Restart them:

```bash
sudo systemctl restart ModemManager
sudo systemctl restart NetworkManager
```

Reboot to apply the network changes:

```bash
sudo reboot
```

---

## 5. Confirm ModemManager detects the modem

Once the Raspberry Pi turns on again:

```bash
mmcli -L
```

Example result:

```text
/org/freedesktop/ModemManager1/Modem/0 [QUALCOMM INCORPORATED] SIMCOM_SIM7600E-H
```

Check NetworkManager device status:

```bash
nmcli device status
```

Example:

```text
DEVICE         TYPE      STATE         CONNECTION
wlan0          wifi      connected     netplan-wlan0-Uwaterloo
cdc-wdm0       gsm       disconnected  --
eth0           ethernet  unavailable   --
```

If `cdc-wdm0` appears as `gsm`, ModemManager has exposed a cellular device.

---

## 6. Do not use manual AT when using NetworkManager

If you previously opened the modem in Minicom and sent commands such as:

```text
AT+NETOPEN
AT+CGACT
AT+HTTPINIT
```

stop controlling the data connection with manual AT commands. NetworkManager and ModemManager will manage it.

Close Minicom if it is still open:

```text
CTRL + A
X
Yes
```

Alternatively, stop any open serial terminal process:

```bash
sudo killall minicom 2>/dev/null
sudo killall picocom 2>/dev/null
```

---

## 7. Create a manual 4G connection

Many Indonesian providers use the APN:

```text
internet
```

Check the APN for your SIM provider; `internet` is common for AXIS/XL, Telkomsel/by.U, and some Indosat plans.

Create a connection:

```bash
sudo nmcli connection add type gsm ifname cdc-wdm0 con-name "EWS-4G" apn "internet"
```

If the profile already exists, just update it:

```bash
sudo nmcli connection modify "EWS-4G" gsm.apn "internet"
```

Give 4G a lower route metric than Wi-Fi:

```bash
sudo nmcli connection modify "EWS-4G" \
  connection.autoconnect yes \
  connection.autoconnect-priority 100 \
  ipv4.method auto \
  ipv4.route-metric 50 \
  ipv6.method ignore
```

Enable 4G connection:

```bash
sudo nmcli connection up "EWS-4G"
```

---

## 8. Make WiFi a backup

Find your Wi-Fi connection profile:

```bash
nmcli connection show
```

Example of WiFi name:

```text
netplan-wlan0-Uwaterloo
```

Set a larger Wi-Fi route metric:

```bash
sudo nmcli connection modify "netplan-wlan0-Uwaterloo" \
  connection.autoconnect yes \
  connection.autoconnect-priority 0 \
  ipv4.route-metric 600 \
  ipv6.route-metric 600
```

> Replace `netplan-wlan0-Uwaterloo` with the Wi-Fi profile name shown on your Pi.

---

## 9. Verify the primary route

Run:

```bash
nmcli device status
```

Example:

```text
cdc-wdm0       gsm       connected      EWS-4G
wlan0          wifi      connected      netplan-wlan0-Uwaterloo
```

Check internet route:

```bash
ip route get 8.8.8.8
```

If 4G is primary, the route should show the modem interface, for example:

```text
dev wwan0
```

The exact interface name varies by modem and driver.

If it still shows:

```text
dev wlan0
```

Wi-Fi is still primary; inspect the configured route metrics.

Test with ping:

```bash
ping -c 4 8.8.8.8
```

---

## 10. Optional setup script for 4G and Wi-Fi

This standalone example automates the connection settings above. It **does not install packages**. Install `network-manager` and `modemmanager` first.

Create the script file:

```bash
nano ~/ews_network_setup.sh
```

Add this script:

```bash
#!/bin/bash

set -e

CONNECTION_NAME="EWS-4G"
MODEM_METRIC=50
WIFI_METRIC=600
DEFAULT_APN="internet"

echo "======================================"
echo " EWS Network Setup - 4G Main + WiFi Backup"
echo "Without installing packages"
echo "======================================"

if [ "$EUID" -ne 0 ]; then
  echo "[ERROR] Run with sudo:"
  echo "sudo bash ~/ews_network_setup.sh"
  exit 1
fi

echo "[1/7] Check ModemManager and NetworkManager services..."

if ! systemctl is-active --quiet ModemManager; then
  echo "[WARN] ModemManager is not active. Activating..."
  systemctl enable --now ModemManager
fi

if ! systemctl is-active --quiet NetworkManager; then
  echo "[WARN] NetworkManager is not active. Activating..."
  systemctl enable --now NetworkManager
fi

echo "[OK] Service is active."

sleep 3

echo "[2/7] Detect modem..."

MODEM_ID=$(mmcli -L 2>/dev/null | grep -oP 'Modem/\K[0-9]+' | head -n 1 || true)

if [ -z "$MODEM_ID" ]; then
  echo "[WARN] The modem has not been detected by ModemManager."
  echo "[WARN] The script will continue and create the 4G profile."
  echo "[WARN] If a modem is installed later, NetworkManager will try to auto-connect."
  OPERATOR_CODE=""
else
  echo "[OK] Modem found: Modem/$MODEM_ID"

  echo "[INFO] Enable modem..."
  mmcli -m "$MODEM_ID" --enable || true

  sleep 3

  OPERATOR_CODE=$(mmcli -m "$MODEM_ID" --output-keyvalue 2>/dev/null | grep "modem.3gpp.operator-code" | cut -d: -f2 | tr -d ' ' || true)

  echo "[INFO] Operator code: ${OPERATOR_CODE:-unknown}"
fi

echo "[3/7] Define APN based on provider..."

case "$OPERATOR_CODE" in
  "51010")
    PROVIDER="Telkomsel / by.U"
    APN="internet"
    ;;
  "51011")
    PROVIDER="XL / AXIS"
    APN="internet"
    ;;
  "51001")
    PROVIDER="Indosat"
    APN="internet"
    ;;
  "51021")
    PROVIDER="Indosat / IM3"
    APN="internet"
    ;;
  "51089")
    PROVIDER="Tri"
    APN="3data"
    ;;
  *)
    PROVIDER="Unknown / Default"
    APN="$DEFAULT_APN"
    ;;
esac

echo "[INFO] Provider : $PROVIDER"
echo "[INFO] APN      : $APN"

echo "[4/7] Create or update 4G connection..."

if nmcli connection show "$CONNECTION_NAME" >/dev/null 2>&1; then
  echo "[INFO] Profile $CONNECTION_NAME already exists. Update settings..."
else
  echo "[INFO] Creating profile $CONNECTION_NAME..."
  nmcli connection add type gsm ifname "*" con-name "$CONNECTION_NAME" apn "$APN"
fi

nmcli connection modify "$CONNECTION_NAME" \
  gsm.apn "$APN" \
  connection.autoconnect yes \
  connection.autoconnect-priority 100 \
  ipv4.method auto \
  ipv4.route-metric "$MODEM_METRIC" \
  ipv6.method ignore

echo "[5/7] Set all WiFi connections as backup..."

WIFI_CONNECTIONS=$(nmcli -t -f NAME,TYPE connection show | grep ":802-11-wireless" | cut -d: -f1 || true)

if [ -z "$WIFI_CONNECTIONS" ]; then
  echo "[WARN] No profile WiFi found."
else
  echo "$WIFI_CONNECTIONS" | while read -r WIFI_NAME; do
    if [ -n "$WIFI_NAME" ]; then
      echo "[INFO] Set WiFi backup: $WIFI_NAME"
      nmcli connection modify "$WIFI_NAME" \
        connection.autoconnect yes \
        connection.autoconnect-priority 0 \
        ipv4.route-metric "$WIFI_METRIC" \
        ipv6.route-metric "$WIFI_METRIC" || true
    fi
  done
fi

echo "[6/7] Enable 4G connection..."

nmcli connection down "$CONNECTION_NAME" >/dev/null 2>&1 || true
sleep 2
nmcli connection up "$CONNECTION_NAME" || true

echo "[7/7] End state..."

echo ""
echo "======================================"
echo " MODEM"
echo "======================================"
mmcli -L || true

echo ""
echo "======================================"
echo " DEVICE STATUS"
echo "======================================"
nmcli device status || true

echo ""
echo "======================================"
echo " CONNECTION LIST"
echo "======================================"
nmcli connection show || true

echo ""
echo "======================================"
echo " IP ROUTE"
echo "======================================"
ip route || true

echo ""
echo "======================================"
echo "ROUTE TO THE INTERNET"
echo "======================================"
ip route get 8.8.8.8 || true

echo ""
echo "======================================"
echo " PING TEST"
echo "======================================"
ping -c 4 8.8.8.8 || true

echo ""
echo "======================================"
echo "FINISHED"
echo "======================================"
echo "Target:"
echo "- If the modem is installed and connected: internet via 4G"
echo "- If modem is unplugged: automatic fallback to WiFi"
echo "- If the modem is installed again: automatically returns to 4G"
echo ""
echo "Manual check:"
echo "ip route get 8.8.8.8"
echo ""
echo "If via modem usually appears:"
echo "dev wwan0 / ppp0 / usb0"
echo ""
echo "If you go through WiFi it appears:"
echo "dev wlan0"
```

Save:

```text
CTRL + O
ENTER
CTRL + X
```

Make the script executable:

```bash
chmod +x ~/ews_network_setup.sh
```

Run:

```bash
sudo bash ~/ews_network_setup.sh
```

---

## 11. Test automatic fallback

### When the modem is installed

```bash
ip route get 8.8.8.8
```

Target:

```text
dev wwan0
```

or similar modem interface.

### Disconnect the modem

Wait 30–60 seconds, then:

```bash
ip route get 8.8.8.8
```

Target:

```text
dev wlan0
```

### Plug in the modem again

Wait 60 seconds, then:

```bash
ip route get 8.8.8.8
```

Target:

```text
dev wwan0
```

---

## 12. Test the modem connection speed

Install speedtest:

```bash
sudo apt update
sudo apt install -y speedtest-cli
```

Run:

```bash
speedtest-cli --simple
```

First check the route so that the speedtest actually goes through the modem:

```bash
ip route get 8.8.8.8
```

If it's still via WiFi, don't treat the speedtest results as SIM7600E results.

---

## 13. Remote SSH

For remote access to SSH via 4G network, it is recommended to use **Tailscale** because the cellular connection is usually behind CGNAT.

Install Tailscale on Raspberry Pi:

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

Check Raspberry Pi Tailscale IP:

```bash
tailscale ip -4
```

SSH from laptop:

```bash
ssh uwfadmin@IP_TAILSCALE_RASPBERRY_PI
```

Example:

```bash
ssh uwfadmin@100.77.65.15
```

---

## 14. Troubleshooting

### A. `mmcli -L` displays `No modems were found`

Check:

```bash
lsusb
ls /dev/ttyUSB*
```

If the modem does not appear on `lsusb`, the problem is hardware:

```text
1. The USB cable is not a data cable
2. Modem is not ON / PWRKEY has not been pressed
3. Power is lacking
4. Faulty USB port
5. The modem only connects to GPIO, not USB
```

### B. `cdc-wdm0 gsm disconnected`

This means the modem is detected, but the connection has not been established/activated.

Run:

```bash
sudo nmcli connection up "EWS-4G"
```

### C. Route still via WiFi

Check metrics:

```bash
ip route
```

Make sure the modem metrics are smaller than WiFi:

```text
4G  metric 50
WiFi metric 600
```

Update again:

```bash
sudo nmcli connection modify "EWS-4G" ipv4.route-metric 50
sudo nmcli connection modify "<your-wifi-profile>" ipv4.route-metric 600
```

### D. The internet modem is not working

Check modem status:

```bash
mmcli -m 0
```

Check devices:

```bash
nmcli device status
```

Try restarting the service:

```bash
sudo systemctl restart ModemManager
sudo systemctl restart NetworkManager
sudo mmcli -S
sudo nmcli connection up "EWS-4G"
```

---

## 15. Summary of important commands

```bash
# Check power
vcgencmd get_throttled

# Check USB modem
lsusb
ls /dev/ttyUSB*

# Check the modem
mmcli -L

# Check network devices
nmcli device status

# Create a 4G connection
sudo nmcli connection add type gsm ifname cdc-wdm0 con-name "EWS-4G" apn "internet"

# Main 4G set
sudo nmcli connection modify "EWS-4G" \
  connection.autoconnect yes \
  connection.autoconnect-priority 100 \
  ipv4.method auto \
  ipv4.route-metric 50 \
  ipv6.method ignore

# Set WiFi backup
sudo nmcli connection modify "<your-wifi-profile>" \
  connection.autoconnect yes \
  connection.autoconnect-priority 0 \
  ipv4.route-metric 600 \
  ipv6.route-metric 600

# Enable 4G
sudo nmcli connection up "EWS-4G"

# Check the main route
ip route get 8.8.8.8

# Test internet
ping -c 4 8.8.8.8
```

---

## 16. Final connection layout

| Connection | Example profile | Route metric | Role |
| --- | --- | ---: | --- |
| SIM7600E-H 4G | `EWS-4G` | 50 | Primary |
| Wi-Fi | Your existing Wi-Fi profile | 600 | Backup |

The smaller route metric makes 4G the preferred path while Wi-Fi remains available for fallback.
