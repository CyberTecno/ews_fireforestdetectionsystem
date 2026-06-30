"""
Mock API server lokal (stdlib saja, tanpa Flask) - simulasi webhook.site
untuk testing tanpa internet/koneksi 4G dulu.

Usage: python3 tools/mock_api_server.py
Lalu set EFWS_API_URL=http://<ip-komputer-ini>:5000/api/v1/efws di .env
"""
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from datetime import datetime

HOST, PORT = "0.0.0.0", 5000


class Handler(BaseHTTPRequestHandler):
    def _read_json(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b""
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"raw": raw.decode(errors="ignore")}

    def do_POST(self):
        payload = self._read_json()
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"\n[{ts}] POST {self.path}")
        print(json.dumps(payload, indent=2))
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"status": "received"}).encode())

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"status": "EFWS mock API server alive"}).encode())

    def log_message(self, format, *args):
        pass


if __name__ == "__main__":
    server = HTTPServer((HOST, PORT), Handler)
    print(f"Mock API server jalan di http://{HOST}:{PORT}")
    print("Tekan Ctrl+C untuk stop. Menunggu request...\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
