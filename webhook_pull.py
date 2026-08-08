"""
Simple webhook server - listens for GitHub push events.
On push: git pull + restart pokemon-monitor-v2.
Port: 9876
"""
from http.server import HTTPServer, BaseHTTPRequestHandler
import subprocess
import json
import os

PORT = 9876
PROJECT_DIR = "/opt/pokemon-monitor-v2"

class WebhookHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length)
        try:
            data = json.loads(body)
            ref = data.get("ref", "")
            if "main" in ref:
                print(f"[WEBHOOK] Push to main, pulling...")
                os.chdir(PROJECT_DIR)
                result = subprocess.run(["git", "pull", "origin", "main"], capture_output=True, text=True)
                print(f"[WEBHOOK] pull: {result.stdout.strip()}")
                result2 = subprocess.run(["sudo", "systemctl", "restart", "pokemon-monitor-v2"], capture_output=True, text=True)
                print(f"[WEBHOOK] restart: rc={result2.returncode}")
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"OK pulled+restarted")
            else:
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"OK ignored")
        except Exception as e:
            print(f"[WEBHOOK] Error: {e}")
            self.send_response(500)
            self.end_headers()
            self.wfile.write(str(e).encode())

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"webhook alive")

    def log_message(self, format, *args):
        print(f"[WEBHOOK] {args[0]}")

if __name__ == "__main__":
    print(f"[WEBHOOK] Starting on port {PORT}...")
    server = HTTPServer(("0.0.0.0", PORT), WebhookHandler)
    server.serve_forever()
