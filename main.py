"""Single entry point for the two assignment projects."""
import argparse
import json
import sys
from pathlib import Path
from src.config import ROOT

def print_json(value):
    print(json.dumps(value, indent=2, ensure_ascii=False, default=str), flush=True)

def main():
    parser = argparse.ArgumentParser(description='Free local RAG and LLM-as-Judge assignment')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('prepare')
    commands.add_parser('test')
    commands.add_parser('stop-evaluation')
    p = commands.add_parser('models'); p.add_argument('action', choices=['start', 'stop', 'status'])
    p = commands.add_parser('ingest'); p.add_argument('folder', nargs='?', default='corpus'); p.add_argument('--chunk-size', type=int); p.add_argument('--overlap', type=int)
    p = commands.add_parser('query'); p.add_argument('question'); p.add_argument('--k', type=int, default=3); p.add_argument('--category')
    p = commands.add_parser('serve'); p.add_argument('--port', type=int, default=8080)
    p = commands.add_parser('judge'); p.add_argument('suite'); p.add_argument('--output', default='artifacts/suite_report.json'); p.add_argument('--uncalibrated', action='store_true')
    p = commands.add_parser('compare'); p.add_argument('suite', nargs='?', default='data/comparison_suite.json'); p.add_argument('--output', default='artifacts/ab_comparison.json')
    p = commands.add_parser('evaluate'); p.add_argument('part', choices=['rag', 'generate-ab', 'bias', 'ablation', 'all'], default='all', nargs='?')
    commands.add_parser('package')
    commands.add_parser('verify')
    p = commands.add_parser('replay'); p.add_argument('request_id'); p.add_argument('--rerun', action='store_true')
    commands.add_parser('costs')
    args = parser.parse_args()
    if args.command == 'stop-evaluation':
        import os
        import psutil
        for proc in psutil.process_iter(['pid', 'cmdline', 'cwd']):
            try:
                command = proc.info['cmdline'] or []
                if proc.pid != os.getpid() and proc.info['cwd'] and Path(proc.info['cwd']).resolve() == ROOT and 'main.py' in command and 'evaluate' in command:
                    proc.terminate()
                    print('Stopped assignment evaluation process', proc.pid)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    elif args.command == 'prepare':
        from scripts.make_data import main as prepare
        prepare()
    elif args.command == 'models':
        from scripts.local_models import main as models
        sys.argv = [sys.argv[0], args.action]
        models()
    elif args.command == 'test':
        import unittest
        suite = unittest.defaultTestLoader.discover(str(ROOT / 'tests'))
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        raise SystemExit(not result.wasSuccessful())
    elif args.command == 'ingest':
        from src.store import Store
        from src.config import Settings
        settings = Settings()
        if args.chunk_size is not None: settings.chunk_size = args.chunk_size
        if args.overlap is not None: settings.overlap = args.overlap
        settings.__post_init__()
        print_json(Store(settings).ingest(args.folder))
    elif args.command == 'query':
        from src.rag import RAG
        print_json(RAG().query(args.question, args.k, args.category))
    elif args.command == 'serve':
        from src.service import serve
        serve(args.port)
    elif args.command in ('judge', 'compare', 'evaluate'):
        from src import evaluation as ev
        if args.command == 'judge':
            print_json(ev.run_suite(args.suite, args.output, not args.uncalibrated)['summary'])
        elif args.command == 'compare':
            report = ev.compare(args.suite, args.output)
            print_json({key: report[key] for key in ['A', 'B', 'winner', 'position_bias']})
        else:
            if args.part in ('all', 'ablation'): ev.chunk_ablation()
            if args.part in ('all', 'rag'): ev.rag_evaluate()
            if args.part in ('all', 'generate-ab'): ev.build_comparison()
            if args.part in ('all', 'bias'): ev.bias_validate()
            if args.part == 'all': ev.compare('data/comparison_suite.json', 'artifacts/ab_comparison.json')
    elif args.command == 'package':
        from scripts.package_submission import main as package
        package()
    elif args.command == 'verify':
        from scripts.verify_project import main as verify
        verify()
    elif args.command == 'costs':
        from scripts.costs import calculate
        print_json(calculate())
    elif args.command == 'replay':
        from src.llm import ModelClient
        import os
        records = [json.loads(line) for line in Path(os.getenv('AUDIT_LOG', str(ROOT/'artifacts/llm_audit.jsonl'))).read_text(encoding='utf-8').splitlines()]
        record = next((r for r in records if r['request_id'] == args.request_id), None)
        if record is None: raise SystemExit('Request ID not found')
        if args.rerun:
            request = record['request']
            client = ModelClient(record['role']); client.model = record['model']
            print_json(client.complete(request['messages'], schema=request.get('response_format', {}).get('schema'),
                max_tokens=request['max_tokens'], temperature=request['temperature'], seed=request['seed'], tag='replay:' + args.request_id))
        else:
            print_json(record)

if __name__ == '__main__':
    main()
