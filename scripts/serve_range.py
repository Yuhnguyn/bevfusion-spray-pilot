#!/usr/bin/env python3
"""Minimal threaded HTTP file server with HTTP Range support.

Serves files from a directory so large archives can be downloaded over a LAN
and resumed with `curl -C -` / `wget -c` / any download manager.

Usage: python3 serve_range.py <directory> [port]
"""
import os
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.realpath(sys.argv[1] if len(sys.argv) > 1 else ".")
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 8000


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        rel = self.path.split("?", 1)[0].lstrip("/")
        fs = os.path.realpath(os.path.join(ROOT, rel))
        if not (fs == ROOT or fs.startswith(ROOT + os.sep)):
            self.send_error(403)
            return
        if not os.path.isfile(fs):
            self.send_error(404)
            return

        size = os.path.getsize(fs)
        start, end, status = 0, size - 1, 200
        m = re.match(r"bytes=(\d*)-(\d*)", self.headers.get("Range", ""))
        if m:
            first, last = m.group(1), m.group(2)
            if first:
                start = int(first)
            if last:
                end = int(last)
            elif not first:
                start = max(0, size - int(last))
            end = min(end, size - 1)
            if start > end or start >= size:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.end_headers()
                return
            status = 206

        length = end - start + 1
        self.send_response(status)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(length))
        self.send_header("Accept-Ranges", "bytes")
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()

        with open(fs, "rb") as f:
            f.seek(start)
            remaining = length
            while remaining > 0:
                chunk = f.read(min(1 << 20, remaining))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    return
                remaining -= len(chunk)

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))


if __name__ == "__main__":
    print(f"serving {ROOT} on http://0.0.0.0:{PORT}/", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
