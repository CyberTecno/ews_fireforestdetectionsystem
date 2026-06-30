#!/usr/bin/env bash
# ============================================================
#  EFWS — Script kontrol proses (start/stop/restart/status/logs)
#  Pakai ini untuk testing manual TANPA systemd (lebih cepat untuk
#  iterasi sambil prototyping). Untuk produksi, pakai systemd
#  (efws.service) karena auto-start saat boot & auto-restart saat crash.
#
#  Letakkan file ini di:  <root-project>/scripts/efws_ctl.sh
#  Struktur project ini FLAT - main.py ada langsung di root project
#  (sejajar dengan folder venv/, .env, scripts/, run/).
#
#  Usage:
#    ./scripts/efws_ctl.sh start
#    ./scripts/efws_ctl.sh stop
#    ./scripts/efws_ctl.sh restart      <- jalankan tiap kali update kode
#    ./scripts/efws_ctl.sh status
#    ./scripts/efws_ctl.sh logs
# ============================================================
set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PYTHON="$PROJECT_ROOT/venv/bin/python"
PID_FILE="$PROJECT_ROOT/run/efws.pid"
STDOUT_LOG="$PROJECT_ROOT/run/efws_stdout.log"

mkdir -p "$(dirname "$PID_FILE")"

is_running() {
    [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null
}

start() {
    if is_running; then
        echo "EFWS sudah berjalan (PID $(cat "$PID_FILE"))."
        return 0
    fi
    if [ ! -x "$VENV_PYTHON" ]; then
        echo "ERROR: venv python tidak ditemukan di $VENV_PYTHON"
        echo "Jalankan dulu: python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt"
        exit 1
    fi
    if [ ! -f "$PROJECT_ROOT/.env" ]; then
        echo "ERROR: .env tidak ditemukan di $PROJECT_ROOT/.env"
        echo "Jalankan dulu: cp .env.example .env  lalu isi EFWS_API_URL"
        exit 1
    fi
    echo "Starting EFWS..."
    cd "$PROJECT_ROOT"
    nohup "$VENV_PYTHON" main.py >> "$STDOUT_LOG" 2>&1 &
    echo $! > "$PID_FILE"
    disown
    sleep 1.5
    if is_running; then
        echo "EFWS started (PID $(cat "$PID_FILE")). Log: tail -f $PROJECT_ROOT/logs/efws.log"
    else
        echo "EFWS GAGAL start - cek isi: $STDOUT_LOG"
        rm -f "$PID_FILE"
        exit 1
    fi
}

stop() {
    if ! is_running; then
        echo "EFWS tidak sedang berjalan."
        rm -f "$PID_FILE"
        return 0
    fi
    PID=$(cat "$PID_FILE")
    echo "Stopping EFWS (PID $PID)..."
    kill "$PID"
    for i in $(seq 1 10); do
        if ! kill -0 "$PID" 2>/dev/null; then break; fi
        sleep 1
    done
    if kill -0 "$PID" 2>/dev/null; then
        echo "Belum berhenti, force kill..."
        kill -9 "$PID"
    fi
    rm -f "$PID_FILE"
    echo "EFWS stopped."
}

restart() {
    echo "=== Restarting EFWS (gunakan ini setiap kali update kode) ==="
    stop
    sleep 1
    start
}

status() {
    if is_running; then
        echo "EFWS sedang RUNNING (PID $(cat "$PID_FILE"))."
        ps -p "$(cat "$PID_FILE")" -o pid,etime,%cpu,%mem,cmd 2>/dev/null
    else
        echo "EFWS TIDAK berjalan."
    fi
}

logs() {
    echo "Tail logs/efws.log (Ctrl+C untuk berhenti memantau - proses TETAP jalan):"
    tail -f "$PROJECT_ROOT/logs/efws.log"
}

case "${1:-}" in
    start)   start ;;
    stop)    stop ;;
    restart) restart ;;
    status)  status ;;
    logs)    logs ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|logs}"
        exit 1
        ;;
esac
