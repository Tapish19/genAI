"""Small local HTTP API. Ingestion is intentionally a local CLI operation."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from .rag import RAG

def serve(port=8080):
    rag = RAG()
    # Load once before accepting concurrent requests.
    rag.store.embeddings(['warmup'])
    class Handler(BaseHTTPRequestHandler):
        def send_json(self, status, data):
            payload = json.dumps(data, ensure_ascii=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):
            if self.path == '/health':
                self.send_json(200, {'status': 'ok', 'chunks': rag.store.count()})
            else:
                self.send_json(404, {'error': 'Use GET /health or POST /query'})

        def do_POST(self):
            if self.path != '/query':
                return self.send_json(404, {'error': 'Unknown endpoint'})
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 16000:
                    return self.send_json(413, {'error': 'Request body must be 1..16000 bytes'})
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict) or 'question' not in body:
                    raise ValueError('JSON object with question required')
                self.send_json(200, rag.query(body['question'], body.get('k'), body.get('category')))
            except (ValueError, TypeError) as exc:
                self.send_json(400, {'error': str(exc)})
            except Exception as exc:
                self.send_json(503, {'error': str(exc)})
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    print(f'RAG API ready at http://127.0.0.1:{port} ({rag.store.count()} chunks)', flush=True)
    server.serve_forever()

