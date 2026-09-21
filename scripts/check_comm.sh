#!/bin/bash
# =============================================================================
# EWS Communication Check (check_comm.sh)
# =============================================================================
# Goal: end-to-end verification of the EFWS communication path — not just a check
# is ews_network_setup.sh successful, but:
#
#   1. ModemManager: modem SIM7600 detected, state & primary port
#   2. nmcli: profile EWS-4G is active and interface wwan0 has IP
#   3. Default route: traffic to the internet exits via interface GSM
#   4. Tailscale: does not shift the default route or hijack DNS
#   5. Real reachability to EFWS_API_URL (DNS resolve + HTTP)
#
# No longer calls sim_detector.py or any Python code.
# Can be run at any time without having to stop efws.service.
#
# Usage:
#   sudo /home/uwfadmin/ews/scripts/check_comm.sh
# =============================================================================

set -u

PROJECT_DIR="/home/uwfadmin/ews"
CONNECTION_NAME="EWS-4G"

pass=0; warn=0; fail=0

log()  { printf '\n\033[1;36m== %s ==\033[0m\n' "$*"; }
ok()   { printf '  \033[1;32m[OK]\033[0m   %s\n' "$*";   pass=$((pass+1)); }
w()    { printf '  \033[1;33m[WARN]\033[0m %s\n' "$*";   warn=$((warn+1)); }
f()    { printf '  \033[1;31m[FAIL]\033[0m %s\n' "$*";   fail=$((fail+1)); }
info() { printf '  %s\n' "$*"; }

# =============================================================================
# 1. ModemManager: modem SIM7600 detected?
# =============================================================================
log "1. ModemManager & SIM7600"

MODEM_ID=$(mmcli -L 2>/dev/null | grep -oP 'Modem/\K[0-9]+' | head -n1 || true)
if [ -z "$MODEM_ID" ]; then
    f "mmcli doesn't find the modem at all. Check 'lsusb' and 'ls /dev/ttyUSB*'."
else
    ok "Modem detected ModemManager, ID=$MODEM_ID"
    MM_INFO=$(mmcli -m "$MODEM_ID" --output-keyvalue 2>/dev/null)

    MODEL=$(echo "$MM_INFO" | grep -oP 'modem\.generic\.model\s*:\s*\K.*' || true)
    STATE=$(echo "$MM_INFO" | grep -oP 'modem\.generic\.state\s*:\s*\K.*' | tr -d '[:space:]' || true)
    PRIMARY_PORT=$(echo "$MM_INFO" | grep -oP 'modem\.generic\.primary-port\s*:\s*\K.*' | tr -d '[:space:]' || true)
    SIM_STATUS=$(echo "$MM_INFO" | grep -oP 'modem\.generic\.sim-status\s*:\s*\K.*' | tr -d '[:space:]' || true)

    info "Model         : ${MODEL:-unknown}"
    info "State         : ${STATE:-unknown}"
    info "Primary port  : ${PRIMARY_PORT:-unknown}"
    info "SIM status    : ${SIM_STATUS:-unknown}"

    case "$STATE" in
        connected)   ok "The modem is in the 'connected' state." ;;
        registered)  ok "The modem has registered to the network (not yet connected — maybe the bearer is not active yet)." ;;
        searching)   w  "The modem is searching for a network. Wait a moment." ;;
        locked)      f  "The modem is 'locked' — SIM needs PIN. Disable PIN SIM." ;;
        disabled)    w  "Modem status is 'disabled'." ;;
        *)           info "Modem state: ${STATE:-unknown}" ;;
    esac

    # Signal quality
    SIG=$(mmcli -m "$MODEM_ID" --signal-get 2>/dev/null \
        | grep -oP 'rssi\s*:\s*\K[0-9.-]+' | head -n1 || true)
    if [ -n "$SIG" ]; then
        info "Signal RSSI   : ${SIG} dBm"
    else
        # Fallback to CSQ via AT command if signal-get is empty
        CSQ_LINE=$(mmcli -m "$MODEM_ID" 2>/dev/null \
            | grep -i "signal" | head -n1 || true)
        [ -n "$CSQ_LINE" ] && info "Signal info   : $CSQ_LINE"
    fi

    # check if /dev/ttyUSB2 exists (AT command port SIM7600)
    if [ -e "/dev/ttyUSB2" ]; then
        ok "AT port /dev/ttyUSB2 available."
    else
        w "/dev/ttyUSB2 not found — make sure SIM7600 is installed and the QMI/CDC driver is loaded."
        info "Check: ls /dev/ttyUSB* && lsusb"
    fi
fi

# =============================================================================
# 2. nmcli: EWS-4G profile & interface GSM
# =============================================================================
log "2. nmcli — Profile $CONNECTION_NAME & Interface GSM"

if ! nmcli connection show "$CONNECTION_NAME" &>/dev/null; then
    f "Nmcli profile '$CONNECTION_NAME' not found. Run 'sudo systemctl start gsm-connect' or create it manually."
else
    ok "The nmcli profile '$CONNECTION_NAME' exists."

    CONN_STATE=$(nmcli -t -f GENERAL.STATE connection show --active "$CONNECTION_NAME" 2>/dev/null \
        | cut -d: -f2 || true)
    CONN_APN=$(nmcli -t -g gsm.apn connection show "$CONNECTION_NAME" 2>/dev/null || true)

    info "APN profile : ${CONN_APN:-unknown}"
    info "Active state: ${CONN_STATE:-inactive}"

    if nmcli connection show --active "$CONNECTION_NAME" &>/dev/null; then
        ok "Profile '$CONNECTION_NAME' is ACTIVE."
    else
        f "Profile '$CONNECTION_NAME' EXISTS but is not ACTIVE. Try: sudo nmcli connection up $CONNECTION_NAME"
    fi
fi

# Check IP on interface GSM (wwan0, cdc-wdm0, usb0)
GSM_IFACE=""
for iface in wwan0 cdc-wdm0 usb0; do
    if ip addr show "$iface" 2>/dev/null | grep -q "inet "; then
        GSM_IFACE="$iface"
        break
    fi
done

if [ -n "$GSM_IFACE" ]; then
    GSM_IP=$(ip addr show "$GSM_IFACE" | grep "inet " | awk '{print $2}' | head -n1)
    ok "GSM interface $GSM_IFACE obtained IP: $GSM_IP"
else
    w "No IP on wwan0/cdc-wdm0/usb0. Check: 'ip addr show wwan0' and 'journalctl -u ews-gsm -n 30'."
fi

# =============================================================================
# 3. Default route — exit via interface GSM?
# =============================================================================
log "3. Default Route & Internet Path"

ROUTE_INFO=$(ip route get 8.8.8.8 2>&1 || true)
info "$ROUTE_INFO"
ACTIVE_IFACE=$(echo "$ROUTE_INFO" | grep -oP 'dev \K[^ ]+' | head -n1 || true)
info "Current active interface for the internet: ${ACTIVE_IFACE:-unknown}"

if echo "$ACTIVE_IFACE" | grep -qE "wwan|cdc-wdm|usb"; then
    ok "Default route exits via interface GSM ($ACTIVE_IFACE) — as desired."
elif [ -n "$ACTIVE_IFACE" ]; then
    w "Default route via '$ACTIVE_IFACE' (not GSM). If GSM is also connected, double-check the route metrics."
    info "Check: 'ip route show' and 'nmcli connection show $CONNECTION_NAME | grep metric'"
else
    f "There is no default route. Internet connection is not yet available."
fi

# =============================================================================
# 4. Tailscale — make sure not to shift the default route or DNS
# =============================================================================
log "4. Tailscale"

if ! command -v tailscale > /dev/null 2>&1; then
    info "Tailscale is not installed on this system — skipped."
else
    if ! systemctl is-active --quiet tailscaled; then
        w "tailscaled is installed but not active."
    else
        ok "active tailscaled."

        TS_PREFS=$(tailscale debug prefs 2>/dev/null || true)

        if echo "$TS_PREFS" | grep -qi '"RouteAll": *true\|"AcceptRoutes": *true'; then
            w "Tailscale AcceptRoutes is active — can shift the default route if there is an exit node in the tailnet."
        else
            ok "AcceptRoutes is off — default route GSM is not interrupted by Tailscale."
        fi

        if echo "$TS_PREFS" | grep -qi '"ExitNodeID": *""' || \
           ! echo "$TS_PREFS" | grep -qi '"ExitNodeID"'; then
            ok "Not currently using the Tailscale exit node."
        else
            w "Currently using Tailscale exit node — ALL traffic exits via tailnet, not GSM directly."
        fi

        if command -v resolvectl > /dev/null 2>&1; then
            RESOLV_INFO=$(resolvectl status 2>/dev/null || true)
            if echo "$RESOLV_INFO" | grep -q "100.100.100.100"; then
                w "Tailscale MagicDNS is the active DNS server. If DNS is slow/failing, try: sudo tailscale set --accept-dns=false"
            else
                ok "Tailscale does not take over the global resolver DNS."
            fi
        fi
    fi
fi

# =============================================================================
# 5. DNS resolve + real reachability to EFWS_API_URL
# =============================================================================
log "5. DNS & Reachability to EFWS_API_URL"

# Take EFWS_API_URL from .env project
API_URL=$(grep -m1 '^EFWS_API_URL=' "$PROJECT_DIR/.env" 2>/dev/null \
    | cut -d= -f2- \
    | sed -e 's/\r$//' -e "s/^['\"]//;s/['\"]$//" \
    || true)

if [ -z "$API_URL" ]; then
    w "Didn't find EFWS_API_URL in $PROJECT_DIR/.env — skip reachability test."
else
    API_HOST=$(echo "$API_URL" | sed -E 's#^[a-zA-Z]+://##; s#[/:].*$##')
    info "Endpoint of .env : $API_URL"
    info "Host               : $API_HOST"

    if command -v getent > /dev/null 2>&1; then
        DNS_RESULT=$(getent hosts "$API_HOST" 2>&1 || true)
        if [ -n "$DNS_RESULT" ] && ! echo "$DNS_RESULT" | grep -qi "failed\|not found\|error"; then
            ok "DNS resolve successful: $DNS_RESULT"
        else
            f "DNS resolves FAILED to '$API_HOST'. Check the 'resolvectl status' or APN operator."
        fi
    fi

    if command -v curl > /dev/null 2>&1; then
        HTTP_CODE=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$API_URL" 2>&1 || true)
        if [ -n "$HTTP_CODE" ] && [ "$HTTP_CODE" != "000" ]; then
            ok "Endpoint is reachable (HTTP $HTTP_CODE) via interface $ACTIVE_IFACE."
        else
            f "Failed to reach $API_URL (curl/HTTP: $HTTP_CODE). Check connection & firewall APN."
        fi
    fi
fi

# =============================================================================
# Summary
# =============================================================================
log "Summary"
info "OK=$pass  WARN=$warn  FAIL=$fail"
if [ "$fail" -gt 0 ]; then
    info "There are failures that need to be followed up."
    info "Starting from: journalctl -u ews-gsm -n 50"
elif [ "$warn" -gt 0 ]; then
    info "There are no fatal failures, there are a few things to check manually."
else
    info "All checks pass — communication lines are healthy."
fi
