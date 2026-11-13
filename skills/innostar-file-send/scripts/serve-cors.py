#!/usr/bin/env python3
"""Minimal CORS file server for innostar-file-send large-file injection.

Serves a directory over http://127.0.0.1:<port> with permissive CORS so the
self-signed-intranet https page can fetch local files (Chrome loopback is a
trustworthy origin; Private Network Access preflight is answered explicitly):

    Access-Control-Allow-Origin: *
    Access-Control-Allow-Headers: *
    Access-Control-Allow-Private-Network: true

Usage:
    python serve-cors.py [directory] [port]     # defaults: cwd, 18731

Then inject from the page (main-document eval reaches same-origin iframe):
    fetch('http://127.0.0.1:<port>/<file>')
      -> arrayBuffer -> new iframeWindow.File([bytes], name)
      -> DataTransfer -> input.files = dt.files -> dispatch input/change
See references/flow.md (排错表 / inject-upload 大文件分支).
"""
import http.server
import os
import sys


class CorsHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Headers', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, HEAD, OPTIONS')
        self.send_header('Access-Control-Allow-Private-Network', 'true')
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()

    def log_message(self, fmt, *args):
        sys.stderr.write('[serve-cors] %s\n' % (fmt % args))


def main():
    directory = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 18731
    os.chdir(directory)
    server = http.server.ThreadingHTTPServer(('127.0.0.1', port), CorsHandler)
    sys.stderr.write('[serve-cors] serving %s at http://127.0.0.1:%d\n' % (directory, port))
    server.serve_forever()


if __name__ == '__main__':
    main()
