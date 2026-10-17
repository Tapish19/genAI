"""Archive current files without regenerating or overwriting the edited submission."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import zipfile

ROOT=Path(__file__).resolve().parents[1]
EXCLUDED={'.git','.venv','.runtime','.tools','__pycache__','node_modules'}

def main():
    submission=ROOT/'submission'
    submission.mkdir(exist_ok=True)
    bundle=submission/'project-history.bundle'
    if (ROOT/'.git').exists():
        subprocess.run(['git','bundle','create',str(bundle),'--all'],cwd=ROOT,check=True)
    paths=[]
    for current,dirs,files in os.walk(ROOT):
        dirs[:]=[directory for directory in dirs if directory not in EXCLUDED]
        for name in files:
            path=Path(current)/name
            if name=='file_manifest.json' or name=='.env' or (name.startswith('.env.') and name!='.env.example'):
                continue
            if path.suffix.lower() in ('.zip','.pyc','.db','.gguf') or name.endswith(('.db-wal','.db-shm','.zip.partial')):
                continue
            paths.append(path)
    paths.sort()
    hashes={path.relative_to(ROOT).as_posix():hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    manifest=submission/'file_manifest.json'
    manifest.write_text(json.dumps(hashes,indent=2),encoding='utf-8')
    archive=submission/'gen-ai-assignment-submission.zip'
    temporary=archive.with_suffix('.zip.partial')
    with zipfile.ZipFile(temporary,'w',zipfile.ZIP_DEFLATED) as output:
        for path in paths+[manifest]:
            output.write(path,Path('gen-ai-assignment')/path.relative_to(ROOT))
    temporary.replace(archive)
    print(f'Archived {len(paths)} files; edited Word document preserved.\n{archive}')

if __name__=='__main__': main()
