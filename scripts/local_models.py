"""Start local model servers, or stop only tracked processes with verified identity."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]

def healthy(port):
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/health', timeout=2) as response:
            return response.status == 200
    except Exception:
        return False

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['start', 'status', 'stop'])
    args = parser.parse_args()
    statefile = ROOT / '.runtime/processes.json'
    if args.action == 'status':
        print(json.dumps({role: healthy(port) for role, port in [('generator', 8091), ('judge', 8092)]}))
        return
    if args.action == 'stop':
        import psutil
        for item in json.loads(statefile.read_text()) if statefile.exists() else []:
            try:
                proc = psutil.Process(item['pid'])
                if abs(proc.create_time() - item['created']) < 1 and str(ROOT / '.runtime') in proc.exe():
                    proc.terminate()
                    print('Stopped ' + item['role'])
            except psutil.NoSuchProcess:
                pass
        return
    executables = list((ROOT / '.runtime/llama').rglob('llama-server.exe'))
    if not executables:
        raise SystemExit('Run python scripts/bootstrap.py first, or configure external local endpoints.')
    import psutil
    processes = json.loads(statefile.read_text()) if statefile.exists() else []
    for role, port in [('generator', 8091), ('judge', 8092)]:
        if healthy(port):
            print(f'{role} already healthy on {port}', flush=True)
            continue
        command = [str(executables[0]), '-m', str(ROOT / f'.runtime/models/{role}.gguf'),
                   '--host', '127.0.0.1', '--port', str(port), '-c', '4096',
                   '-t', os.getenv('MODEL_THREADS', '4'), '-np', '1', '-ngl', '0',
                   '--alias', 'smollm2-1.7b-instruct-q4_k_m' if role == 'judge' else 'qwen2.5-0.5b-instruct-q4_k_m']
        log = (ROOT / f'.runtime/{role}.log').open('ab')
        kwargs = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {'start_new_session': True}
        proc = subprocess.Popen(command, cwd=executables[0].parent, stdout=log, stderr=log, stdin=subprocess.DEVNULL, **kwargs)
        log.close()
        processes.append({'role': role, 'pid': proc.pid, 'created': psutil.Process(proc.pid).create_time(), 'command': command})
        statefile.write_text(json.dumps(processes, indent=2), encoding='utf-8')
        for _ in range(120):
            if healthy(port):
                print(f'{role} ready on {port}; PID {proc.pid}', flush=True)
                break
            if proc.poll() is not None:
                raise SystemExit(f'{role} exited. See .runtime/{role}.log')
            time.sleep(1)
        else:
            raise SystemExit(f'{role} startup timed out. See .runtime/{role}.log')

if __name__ == '__main__':
    main()
