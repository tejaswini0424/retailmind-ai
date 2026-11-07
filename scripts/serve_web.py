"""Local HTTP server for the same static UI and Vercel handler."""
from functools import partial
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from web.api.index import handler

class LocalHandler(SimpleHTTPRequestHandler):
    send_json = handler.send_json
    def do_POST(self):
        if self.path.split('?')[0]=='/api/index': return handler.do_POST(self)
        self.send_error(404)
    def do_GET(self):
        if self.path.split('?')[0]=='/api/index': return handler.do_GET(self)
        return super().do_GET()

if __name__=='__main__':
    port = int(sys.argv[1]) if len(sys.argv)>1 else 3000
    print(f'RetailMind web: http://localhost:{port}',flush=True)
    ThreadingHTTPServer(('127.0.0.1',port),partial(LocalHandler,directory=str(ROOT/'web'/'public'))).serve_forever()
