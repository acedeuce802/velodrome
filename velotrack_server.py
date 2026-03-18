#!/usr/bin/env python3
"""
VeloTrack Local Server
======================
Relays race state from the race manager (Chrome) to the OBS overlay.
No internet required — everything stays on your machine.

HOW TO RUN:
  Windows:  Double-click this file, OR open Command Prompt and run:
               python velotrack_server.py
  Mac/Linux: Open Terminal and run:
               python3 velotrack_server.py

Then open velodrome_night.html in Chrome.
Set OBS Browser Source URL to: http://localhost:7878/overlay

Press Ctrl+C to stop the server.
"""

import sys
import os
import json
import threading
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime

PORT = 7878

# ── Serve the overlay file from the same directory as this script ──
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OVERLAY_FILE = os.path.join(SCRIPT_DIR, 'velodrome_overlay.html')

# ── Shared state ──
state = {"view": "idle", "data": {}, "ts": 0, "seq": 0}
state_lock = threading.Lock()
request_count = 0


def log(msg):
    now = datetime.now().strftime('%H:%M:%S')
    print(f"[{now}] {msg}")


class Handler(BaseHTTPRequestHandler):

    def do_OPTIONS(self):
        """Handle CORS preflight requests."""
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_GET(self):
        global request_count
        if self.path == '/state':
            # Race manager or overlay reading current state
            with state_lock:
                body = json.dumps(state).encode()
            self.send_response(200)
            self._cors()
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', len(body))
            self.end_headers()
            self.wfile.write(body)
            request_count += 1

        elif self.path == '/overlay' or self.path == '/overlay.html':
            # Serve the overlay HTML file directly
            if os.path.exists(OVERLAY_FILE):
                with open(OVERLAY_FILE, 'rb') as f:
                    body = f.read()
                self.send_response(200)
                self._cors()
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', len(body))
                self.end_headers()
                self.wfile.write(body)
            else:
                self._not_found(f'velodrome_overlay.html not found in {SCRIPT_DIR}')

        elif self.path == '/status':
            # Simple status page
            with state_lock:
                current_view = state.get('view', 'idle')
                ts = state.get('ts', 0)
                seq = state.get('seq', 0)
            body = json.dumps({
                'status': 'online',
                'view': current_view,
                'last_update': ts,
                'seq': seq,
                'requests_served': request_count,
            }).encode()
            self.send_response(200)
            self._cors()
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(body)

        else:
            self._not_found()

    def do_PUT(self):
        if self.path == '/state':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length)
            try:
                new_state = json.loads(body)
                with state_lock:
                    global state
                    incoming_seq = new_state.get('seq', 0)
                    current_seq  = state.get('seq', 0)
                    if incoming_seq < current_seq:
                        # Out-of-order write — discard silently
                        self.send_response(200)
                        self._cors()
                        self.send_header('Content-Type', 'application/json')
                        self.end_headers()
                        self.wfile.write(b'{"ok":true,"discarded":true}')
                        return
                    state = new_state
                view = new_state.get('view', '?')
                seq  = new_state.get('seq', '?')
                log(f"State updated → view: {view}  seq: {seq}")
                self.send_response(200)
                self._cors()
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(b'{"ok":true}')
            except json.JSONDecodeError as e:
                log(f"Bad JSON received: {e}")
                self.send_response(400)
                self._cors()
                self.end_headers()
                self.wfile.write(b'{"error":"invalid json"}')
        else:
            self._not_found()

    def _cors(self):
        """Add CORS headers so Chrome and OBS can both reach us."""
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, PUT, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def _not_found(self, msg='Not found'):
        self.send_response(404)
        self._cors()
        self.end_headers()
        self.wfile.write(json.dumps({'error': msg}).encode())

    def log_message(self, format, *args):
        """Suppress default per-request logging (we do our own)."""
        pass


def print_banner():
    print()
    print("=" * 54)
    print("  VELOTRACK LOCAL SERVER")
    print("=" * 54)
    print(f"  Server running at:  http://localhost:{PORT}")
    print(f"  Overlay URL (OBS):  http://localhost:{PORT}/overlay")
    print(f"  Status check:       http://localhost:{PORT}/status")
    print()
    print("  HOW TO USE:")
    print("  1. Set OBS Browser Source URL to:")
    print(f"       http://localhost:{PORT}/overlay")
    print("  2. Open velodrome_night.html in Chrome")
    print("  3. The green dot = server is online")
    print()
    print("  Press Ctrl+C to stop")
    print("=" * 54)
    print()


if __name__ == '__main__':
    print_banner()

    server = HTTPServer(('localhost', PORT), Handler)

    try:
        log(f"Listening on port {PORT}...")
        server.serve_forever()
    except KeyboardInterrupt:
        log("Shutting down.")
        server.shutdown()
        sys.exit(0)
    except OSError as e:
        if 'Address already in use' in str(e) or 'Only one usage' in str(e):
            print(f"\nERROR: Port {PORT} is already in use.")
            print(f"Either another instance is running, or change PORT at the top of this file.")
        else:
            raise
