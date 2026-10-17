"""Independent model clients with real usage and append-only raw audit records."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import threading
import time
import urllib.request
import urllib.error
import uuid

from .config import ROOT

_lock = threading.Lock()

def append_jsonl(path, record):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _lock, path.open('a', encoding='utf-8') as out:
        out.write(json.dumps(record, ensure_ascii=False) + '\n')

class ModelClient:
    def __init__(self, role='judge'):
        self.role = role
        prefix = role.upper()
        default_port = 8092 if role == 'judge' else 8091
        self.base_url = os.getenv(prefix + '_BASE_URL', f'http://127.0.0.1:{default_port}/v1').rstrip('/')
        self.model = os.getenv(prefix + '_MODEL', 'smollm2-1.7b-instruct-q4_k_m' if role == 'judge' else 'qwen2.5-0.5b-instruct-q4_k_m')
        self.family = os.getenv(prefix + '_FAMILY', 'smollm' if role == 'judge' else 'qwen')
        self.api_key = os.getenv(prefix + '_API_KEY', '')
        self.calls = 0
        self.tokens = {'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0}

    def complete(self, messages, schema=None, max_tokens=320, tag='', temperature=0, seed=42):
        payload = {'model': self.model, 'messages': messages, 'temperature': temperature,
                   'seed': seed, 'max_tokens': max_tokens}
        if schema:
            payload['response_format'] = {'type': 'json_object', 'schema': schema}
        request_id = uuid.uuid4().hex
        record = {'request_id': request_id, 'time': datetime.now(timezone.utc).isoformat(),
                  'role': self.role, 'model': self.model, 'family': self.family, 'tag': tag,
                  'request': payload}
        headers = {'Content-Type': 'application/json'}
        if self.api_key:
            headers['Authorization'] = 'Bearer ' + self.api_key
        start = time.perf_counter()
        self.calls += 1
        try:
            req = urllib.request.Request(self.base_url + '/chat/completions',
                                         json.dumps(payload).encode(), headers)
            with urllib.request.urlopen(req, timeout=float(os.getenv('LLM_TIMEOUT', '180'))) as response:
                raw = response.read().decode()
            result = json.loads(raw)
            content = result['choices'][0]['message']['content']
            if isinstance(content, list):
                content = ''.join(part.get('text', '') for part in content)
            usage = result.get('usage', {})
            for key in self.tokens:
                self.tokens[key] += usage.get(key, 0)
            record.update(raw_response=raw, usage=usage, finish_reason=result['choices'][0].get('finish_reason'))
            return {'text': content, 'usage': usage, 'request_id': request_id,
                    'latency_ms': (time.perf_counter() - start) * 1000,
                    'finish_reason': result['choices'][0].get('finish_reason')}
        except Exception as exc:
            record['error'] = str(exc)
            if isinstance(exc, urllib.error.HTTPError):
                record['error_body'] = exc.read().decode(errors='replace')
            raise RuntimeError(f'{self.role} model call failed: {record.get("error_body", str(exc))}') from exc
        finally:
            record['latency_ms'] = (time.perf_counter() - start) * 1000
            append_jsonl(os.getenv('AUDIT_LOG', str(ROOT / 'artifacts/llm_audit.jsonl')), record)

