"""Install a private environment and free CPU models; no system installation."""
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import urllib.request
import venv
import zipfile
import zlib

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / '.runtime'

def get_json(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'gen-ai-assignment/1.0'})
    with urllib.request.urlopen(req, timeout=60) as response:
        return json.load(response)

def download(url, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        print('Downloading ' + destination.name, flush=True)
        partial = destination.with_suffix(destination.suffix + '.partial')
        req = urllib.request.Request(url, headers={'User-Agent': 'gen-ai-assignment/1.0'})
        with urllib.request.urlopen(req, timeout=180) as response, partial.open('wb') as output:
            while block := response.read(4 * 1024 * 1024):
                output.write(block)
        partial.replace(destination)
    with destination.open('rb') as handle:
        digest = hashlib.file_digest(handle, 'sha256').hexdigest()
    return {'url': url, 'file': str(destination.relative_to(ROOT)),
            'bytes': destination.stat().st_size, 'sha256': digest}

def extract_runtime(archive_path):
    destination=RUNTIME/'llama'
    destination.mkdir(exist_ok=True)
    with zipfile.ZipFile(archive_path) as archive:
        for info in archive.infolist():
            target=(destination/info.filename).resolve()
            if not target.is_relative_to(destination.resolve()):
                raise RuntimeError('Unsafe path in runtime archive')
            if info.is_dir():
                target.mkdir(parents=True,exist_ok=True)
                continue
            # Do not overwrite DLLs loaded by running local servers on Windows.
            if target.exists() and target.stat().st_size==info.file_size:
                if zlib.crc32(target.read_bytes()) & 0xffffffff == info.CRC:
                    continue
            try:
                archive.extract(info,destination)
            except PermissionError as exc:
                raise RuntimeError('Stop local models before replacing a changed runtime: main.py models stop') from exc

def main():
    os.chdir(ROOT)
    RUNTIME.mkdir(exist_ok=True)
    python = ROOT / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    if not python.exists():
        venv.create(ROOT / '.venv', with_pip=True)
    requirements = 'requirements.lock.txt' if (ROOT / 'requirements.lock.txt').exists() else 'requirements.txt'
    subprocess.run([str(python), '-m', 'pip', 'install', '-r', requirements], check=True)
    lock = ROOT / 'configs/runtime.lock.json'
    if lock.exists():
        manifest = json.loads(lock.read_text(encoding='utf-8'))
        for item in manifest['downloads']:
            destination = ROOT / item['file'].replace('\\', '/')
            info = download(item['url'], destination)
            if info['sha256'] != item['sha256']:
                raise RuntimeError('Checksum mismatch: ' + item['file'])
            if destination.suffix == '.zip':
                extract_runtime(destination)
        (RUNTIME / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        print('Pinned runtime/model setup complete.', flush=True)
        return
    manifest = {'platform': platform.platform(), 'downloads': []}
    if os.name == 'nt':
        releases = get_json('https://api.github.com/repos/ggml-org/llama.cpp/releases?per_page=20')
        assets = [(r, a) for r in releases for a in r.get('assets', [])
                  if a['name'].endswith('bin-win-cpu-x64.zip')]
        if not assets:
            raise RuntimeError('No Windows CPU runtime release found')
        release, asset = assets[0]
        info = download(asset['browser_download_url'], RUNTIME / asset['name'])
        expected = asset.get('digest', '').removeprefix('sha256:')
        if expected and info['sha256'] != expected:
            raise RuntimeError('Runtime checksum mismatch')
        manifest['llama_cpp_release'] = release['tag_name']
        manifest['downloads'].append(info)
        extract_runtime(RUNTIME / asset['name'])
    repositories = [('Qwen/Qwen2.5-0.5B-Instruct-GGUF', 'generator.gguf'),
                    ('HuggingFaceTB/SmolLM2-1.7B-Instruct-GGUF', 'judge.gguf')]
    tasks = []
    for repo, name in repositories:
        metadata = get_json('https://huggingface.co/api/models/' + repo)
        files = [s['rfilename'] for s in metadata['siblings']
                 if 'q4_k_m' in s['rfilename'].lower() and s['rfilename'].endswith('.gguf')]
        if len(files) != 1:
            raise RuntimeError(f'Expected one Q4_K_M file in {repo}, got {files}')
        url = f'https://huggingface.co/{repo}/resolve/{metadata["sha"]}/{files[0]}'
        tasks.append((url, RUNTIME / 'models' / name))
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        for info in pool.map(lambda args: download(*args), tasks):
            manifest['downloads'].append(info)
    (RUNTIME / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print('Bootstrap complete. Run .venv\\Scripts\\python scripts/local_models.py start', flush=True)

if __name__ == '__main__':
    main()
