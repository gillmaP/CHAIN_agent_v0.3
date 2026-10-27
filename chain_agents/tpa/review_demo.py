"""Local synthetic weight-entry preview: python -m chain_agents.tpa.review_demo.

Not a deployment API. Binds to loopback, stores no records and uses research defaults.
"""
import argparse
import json
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from .manual import weight_preview


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != '/':
            self.send_error(404)
            return
        body = Path(__file__).with_name('weight_demo.html').read_bytes()
        self.send_response(200)
        self.send_header('Content-Type','text/html; charset=utf-8')
        self.send_header('Cache-Control','no-store')
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != '/weight-preview':
            self.send_error(404)
            return
        if self.headers.get('Origin') not in (None, 'http://' + self.headers.get('Host','')):
            self.send_error(403)
            return
        try:
            length = int(self.headers.get('Content-Length','0'))
            if not 0 < length <= 2048:
                raise ValueError('Invalid request size')
            data = json.loads(self.rfile.read(length))
            if set(data) != {'weight_kg','method'}:
                raise ValueError('Expected weight_kg and method only')
            value = weight_preview(data['weight_kg'],method=data['method'],staff_id='SYNTHETIC-DEMO',
                entry_id='DEMO-WEIGHT',version=1,recorded_at=datetime.now(timezone.utc).isoformat())
            status = 200
        except (ValueError, TypeError) as error:
            value, status = {'error':str(error)}, 400
        self.send_response(status)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Cache-Control','no-store')
        self.end_headers()
        self.wfile.write(json.dumps(value,ensure_ascii=False,allow_nan=False).encode('utf-8'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=8091)
    args = parser.parse_args()
    print(f'SYNTHETIC RESEARCH PREVIEW http://127.0.0.1:{args.port}/',flush=True)
    ThreadingHTTPServer(('127.0.0.1',args.port),Handler).serve_forever()
