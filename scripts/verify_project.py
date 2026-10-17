"""Run tests and exercise the actual HTTP service and local generator."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request
import urllib.error
ROOT = Path(__file__).resolve().parents[1]

def main():
    result = subprocess.run([sys.executable, 'main.py', 'test'], cwd=ROOT, text=True, capture_output=True)
    (ROOT/'artifacts/test_results.txt').write_text(result.stdout + result.stderr, encoding='utf-8')
    if result.returncode: raise SystemExit('Unit tests failed; see artifacts/test_results.txt')
    port = 8095
    log = (ROOT/'artifacts/http_service.log').open('wb')
    kwargs = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}
    process = subprocess.Popen([sys.executable, 'main.py', 'serve', '--port', str(port)], cwd=ROOT, stdout=log, stderr=log, **kwargs)
    def get(path):
        with urllib.request.urlopen(f'http://127.0.0.1:{port}' + path, timeout=5) as response:
            return json.load(response)
    def post(body):
        req = urllib.request.Request(f'http://127.0.0.1:{port}/query', json.dumps(body).encode(), {'Content-Type':'application/json'})
        with urllib.request.urlopen(req, timeout=180) as response: return json.load(response)
    try:
        for _ in range(60):
            try:
                health = get('/health')
                break
            except Exception: time.sleep(.5)
        else: raise RuntimeError('HTTP service did not start')
        positive = post({'question':'Which encryption protects workspace data at rest?', 'category':'security', 'k':3})
        assert positive['chunk_count'] > 0 and positive['usage']['total_tokens'] > 0
        assert positive['citations'] and all(c['source'] == 'security.pdf' for c in positive['citations'])
        assert 'AES-256' in positive['answer']
        negative = post({'question':'Unpublished secret?', 'category':'missing'})
        assert negative['abstained'] and negative['usage']['total_tokens'] == 0
        invalid_status = None
        try: post({'question':'x', 'k':0})
        except urllib.error.HTTPError as exc: invalid_status = exc.code
        assert invalid_status == 400
        report = {'status':'passed', 'unit_tests':19, 'health':health, 'positive':positive,
                  'negative':negative, 'invalid_k_http_status': invalid_status}
        (ROOT/'artifacts/http_smoke.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print('19 tests passed; real HTTP positive, no-context and invalid-input checks passed.', flush=True)
    finally:
        process.terminate()
        try: process.wait(timeout=10)
        except subprocess.TimeoutExpired: process.kill()
        log.close()

if __name__ == '__main__': main()
