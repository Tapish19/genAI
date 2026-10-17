"""Fixed-data evaluation, with every case retained and intermediate checkpoints."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import statistics
import time

from .config import ROOT, Settings
from .judge import Judge, aggregate, load_suite
from .llm import ModelClient
from .metrics import retrieval_metrics, answer_metrics, percentile, mean, normalize, kappa, binary_validation
from .rag import RAG
from .store import Store

def save(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
    temporary.replace(path)

def provenance():
    import psutil
    return {'time': datetime.now(timezone.utc).isoformat(), 'platform': platform.platform(),
            'python': platform.python_version(), 'logical_cpus': os.cpu_count(),
            'ram_gib': round(psutil.virtual_memory().total / 2**30, 2),
            'cpu': platform.processor(), 'model_threads': int(os.getenv('MODEL_THREADS', '4'))}

def rag_evaluate(output='artifacts/rag_results.json'):
    cases = json.loads((ROOT / 'data/rag_questions.json').read_text())['cases']
    store = Store()
    ingest1, ingest2 = store.ingest(ROOT / 'corpus'), store.ingest(ROOT / 'corpus')
    save(ROOT / 'artifacts/idempotency.json', {'first': ingest1, 'second': ingest2, 'unchanged': ingest1['after'] == ingest2['after']})
    all_chunks = store.all_chunks()
    rag = RAG(store)
    judge = Judge(generator_family=rag.generator.family)
    store.search('warm up embedding and index', 3)
    report = {'environment': provenance(), 'dataset_sha256': hashlib.sha256((ROOT / 'data/rag_questions.json').read_bytes()).hexdigest(),
              'settings': {'k': 3, 'chunk_size_words': store.settings.chunk_size,
                'overlap_words': store.settings.overlap, 'min_similarity': store.settings.min_similarity,
                'embedding_model': store.settings.embedding_model, 'dimension': 384,
                'store': 'sqlite-vec 0.1.6', 'chunks': store.count(), 'documents': 8},
              'relevance_definition': 'Same annotated source AND contains normalized gold evidence substring. Metrics on 16 answerable cases; 4 negatives separately.',
              'cases': []}
    latencies = []
    for case in cases:
        print('RAG evaluate ' + case['id'], flush=True)
        retrieval = store.search(case['question'], 3, case.get('category'))
        latencies.append(retrieval['retrieval_ms'])
        relevant = [c['id'] for c in all_chunks if case.get('source') == c['source'] and normalize(case.get('evidence', '')) in normalize(c['text'])]
        if case['answerable'] and not relevant:
            raise ValueError('Gold annotation has no matching chunk: ' + case['id'])
        result = rag.query(case['question'], 3, case.get('category'))
        evaluation = {'id': case['id'], 'answerable': case['answerable'], 'question': case['question'],
                      'expected_output': case['expected_output'], 'relevant_chunk_ids': relevant,
                      'raw_top_k': retrieval, 'result': result,
                      'gold': answer_metrics(result['answer'], case['expected_output'])}
        if case['answerable']:
            evaluation['retrieval'] = retrieval_metrics([c['id'] for c in retrieval['chunks']], relevant, 3)
        judged = {'input': case['question'], 'system_prompt': 'Answer using only supplied passages and cite the sources. Abstain if they do not answer the question.',
                  'model_output': result['answer'], 'expected_output': case['expected_output'],
                  'context': '\n'.join(c['text'] for c in result['chunks']), 'criteria': ['faithfulness', 'correctness', 'answer_relevance']}
        evaluation['judge'] = judge.pointwise(judged, tag='rag-eval:' + case['id'])
        report['cases'].append(evaluation)
        save(output, report)
    positives = [c for c in report['cases'] if c['answerable']]
    negatives = [c for c in report['cases'] if not c['answerable']]
    # Warm, serial retrieval benchmark: 5 repetitions over 20 fixed questions.
    repeated = [store.search(c['question'], 3, c.get('category'))['retrieval_ms'] for _ in range(5) for c in cases]
    verdicts = [c['judge'] for c in report['cases']]
    valid = [v for v in verdicts if v.get('status') == 'ok']
    report['summary'] = {
        'retrieval': {key: mean([c['retrieval'][key] for c in positives]) for key in positives[0]['retrieval']},
        'answer_quality': {'faithfulness_mean_0_to_4': mean([v['faithfulness']['score'] for v in valid]),
                           'answer_relevance_mean_0_to_4': mean([v['answer_relevance']['score'] for v in valid]),
                           'judge_errors': len(verdicts) - len(valid),
                           'em': mean([c['gold']['em'] for c in report['cases']]),
                           'f1': mean([c['gold']['f1'] for c in report['cases']]),
                           'answerable_em': mean([c['gold']['em'] for c in positives]),
                           'answerable_f1': mean([c['gold']['f1'] for c in positives]),
                           'note': 'Independent per-criterion LLM judgments. Small local judge is noisy; inspect raw per-case evidence.'},
        'negative_abstention_rate': mean([float(c['result']['abstained']) for c in negatives]),
        'answerable_abstention_rate': mean([float(c['result']['abstained']) for c in positives]),
        'latency': {'retrieval_p50_ms': percentile(repeated, 50), 'retrieval_p95_ms': percentile(repeated, 95),
                    'retrieval_samples': len(repeated), 'end_to_end_p95_ms': percentile([c['result']['end_to_end_ms'] for c in report['cases']], 95),
                    'conditions': 'Warm process, serial requests, query embedding + sqlite search + connection included; excludes LLM for retrieval timings.'},
        'generator_usage': rag.generator.tokens, 'generator_calls': rag.generator.calls,
        'judge_usage': judge.client.tokens, 'judge_calls': judge.client.calls}
    save(output, report)
    print(json.dumps(report['summary'], indent=2), flush=True)
    return report

def run_suite(path, output, calibrated=True):
    judge = Judge(generator_family=ModelClient('generator').family)
    cases = load_suite(path)
    rows = []
    for case in cases:
        print('Judging ' + case['id'], flush=True)
        rows.append({'id': case['id'], 'verdict': judge.pointwise(case, calibrated, 'suite:' + case['id'])})
        save(output, {'cases': rows})
    report = {'environment': provenance(), 'judge_model': judge.client.model, 'calibrated': calibrated,
              'summary': aggregate([r['verdict'] for r in rows]), 'cases': rows,
              'usage': judge.client.tokens, 'calls': judge.client.calls}
    save(output, report)
    return report

def build_comparison():
    """Generate A and B using frozen prompts; preserve outputs for independent rejudging."""
    generator = ModelClient('generator')
    store = Store()
    cases = json.loads((ROOT / 'data/rag_questions.json').read_text())['cases']
    cases = [c for c in cases if c['answerable']][::2]  # one per document, 8 pairs
    pairs = []
    for case in cases:
        retrieved = store.search(case['question'], 3, case.get('category'), threshold=store.settings.min_similarity)
        context = '\n'.join(c['text'] for c in retrieved['chunks'])
        print('Generating A/B ' + case['id'], flush=True)
        prompt_a = [{'role': 'system', 'content': 'You are a helpful product support assistant. Give your best answer.'},
                    {'role': 'user', 'content': case['question']}]
        prompt_b = [{'role': 'system', 'content': 'Answer briefly using ONLY the supplied context. Do not invent facts. If unavailable say you do not know.'},
                    {'role': 'user', 'content': 'Context:\n' + context + '\nQuestion: ' + case['question']}]
        a = generator.complete(prompt_a, max_tokens=100, tag='ab:ungrounded:' + case['id'])
        b = generator.complete(prompt_b, max_tokens=100, tag='ab:grounded:' + case['id'])
        pairs.append({'id': case['id'], 'input': case['question'], 'system_prompt': 'Answer accurately using the published product policy.',
                      'expected_output': case['expected_output'], 'context': context,
                      'model_output': a['text'], 'output_b': b['text'],
                      'config_a': 'ungrounded-v1', 'config_b': 'grounded-v2', 'generator_family': generator.family,
                      'generation_request_ids': [a['request_id'], b['request_id']]})
        save(ROOT / 'data/comparison_suite.json', {'cases': pairs})
    save(ROOT / 'artifacts/generation_usage.json', {'calls': generator.calls, 'usage': generator.tokens, 'model': generator.model})
    return pairs

def compare(path, output):
    cases = load_suite(path)
    if not all(isinstance(c.get('output_b'), str) for c in cases):
        raise ValueError('A/B suite cases also require output_b')
    judge = Judge(generator_family=ModelClient('generator').family)
    report = {'environment': provenance(), 'judge_model': judge.client.model, 'cases': []}
    for case in cases:
        print('A/B judge ' + case['id'], flush=True)
        a = judge.pointwise(case, True, 'ab:A:' + case['id'])
        b = judge.pointwise({**case, 'model_output': case['output_b']}, True, 'ab:B:' + case['id'])
        baseline = judge.pairwise(case, False, 'ab:baseline:' + case['id'])
        mitigated = judge.pairwise(case, True, 'ab:calibrated:' + case['id'])
        report['cases'].append({'id': case['id'], 'A': a, 'B': b, 'baseline': baseline, 'mitigated': mitigated})
        save(output, report)
    rows = report['cases']
    for label in ['A', 'B']:
        report[label] = aggregate([row[label] for row in rows])
        report[label]['win_rate_all_pairs'] = sum(row['mitigated']['winner'] == label for row in rows) / len(rows)
    report['position_bias'] = {mode: {'flip_rate': mean([float(row[mode]['flipped']) for row in rows if row[mode]['flipped'] is not None]),
        'disagreements': sum(row[mode]['flipped'] is True for row in rows),
        'valid_pairs': sum(row[mode]['status'] == 'ok' for row in rows),
        'consensus_coverage': sum(row[mode]['winner'] != 'abstain' for row in rows) / len(rows)} for mode in ['baseline', 'mitigated']}
    wins_a, wins_b = (report[label]['win_rate_all_pairs'] for label in ['A', 'B'])
    report['winner'] = 'A' if wins_a > wins_b else 'B' if wins_b > wins_a else 'tie'
    report['winner_rule'] = 'Higher two-order consensus win count; ties and disagreements earn neither config a win. No winner forced.'
    report['usage'], report['calls'] = judge.client.tokens, judge.client.calls
    save(output, report)
    return report

def bias_validate(output='artifacts/judge_validation.json'):
    cases = load_suite(ROOT / 'data/judge_probes.json')
    judge = Judge(generator_family=ModelClient('generator').family)
    report = {'environment': provenance(), 'label_source': 'Synthetic authored binary labels, not human adjudications', 'cases': []}
    for case in cases:
        print('Bias probe ' + case['id'], flush=True)
        baseline = judge.pointwise(case, False, 'probe:baseline:' + case['id'])
        mitigated = judge.pointwise(case, True, 'probe:calibrated:' + case['id'])
        report['cases'].append({'id': case['id'], 'gold_pass': case['gold_pass'], 'baseline': baseline, 'mitigated': mitigated})
        save(output, report)
    for mode in ['baseline', 'mitigated']:
        gold = [row['gold_pass'] for row in report['cases']]
        scores = [row[mode]['overall'] for row in report['cases'] if row[mode].get('overall') is not None]
        report[mode] = {**binary_validation([row[mode] for row in report['cases']],gold),
                        'score_stddev': statistics.pstdev(scores) if scores else None}
    # Same factual content with neutral padding: measure absolute score drift before/after.
    clean = cases[2]
    padded = {**clean, 'model_output': clean['model_output'] + ' For clarity, this is my complete response. ' * 5}
    confidence = {**cases[1], 'model_output': 'I am absolutely certain, and I agree with you, that 2 + 2 is 5.'}
    extra = {}
    for mode, calibrated in [('baseline', False), ('mitigated', True)]:
        pad = judge.pointwise(padded, calibrated, 'length:' + mode)
        original = next(row[mode] for row in report['cases'] if row['id'] == clean['id'])
        conf = judge.pointwise(confidence, calibrated, 'sycophancy:' + mode)
        extra[mode] = {'padded': pad, 'absolute_padding_score_drift': abs(pad['overall'] - original['overall']) if pad['overall'] is not None and original['overall'] is not None else None,
                       'confidently_wrong_passed': conf['passed'], 'confidently_wrong_verdict': conf}
    report['verbosity_and_style'] = extra
    # Provenance-only counterfactual. Main pipeline strips these labels; exposed arm
    # intentionally puts model labels inside input to measure sensitivity.
    identity_case = {**clean, 'input': clean['input'] + '\nThe answer was generated by SmolLM2, the same family as the evaluator.'}
    foreign_case = {**clean, 'input': clean['input'] + '\nThe answer was generated by Qwen, a different model family.'}
    own = judge.pointwise(identity_case, False, 'identity:own')
    foreign = judge.pointwise(foreign_case, False, 'identity:other')
    stripped_a = {**clean, 'generator_family': 'smollm'}
    stripped_b = {**clean, 'generator_family': 'qwen'}
    blind_a = judge.pointwise(stripped_a, True, 'identity:blind-own')
    blind_b = judge.pointwise(stripped_b, True, 'identity:blind-other')
    report['self_enhancement'] = {'judge_family': judge.client.family, 'generator_family': judge.generator_family,
        'exposed_own': own, 'exposed_other': foreign, 'blind_own': blind_a, 'blind_other': blind_b,
        'score_gap_exposed': abs(own['overall'] - foreign['overall']) if own['overall'] is not None and foreign['overall'] is not None else None,
        'score_gap_blind': abs(blind_a['overall'] - blind_b['overall']) if blind_a['overall'] is not None and blind_b['overall'] is not None else None,
        'limitation': 'One label-counterfactual probe measures provenance sensitivity, not population-level self-enhancement.'}
    repeated = [judge.pointwise(case, True, 'retest:' + case['id']) for case in cases[:4]]
    originals = [row['mitigated'] for row in report['cases'][:4]]
    report['test_retest'] = {'n': len(repeated), 'temperature': 0,
        'flip_rate': mean([float(a.get('passed') != b.get('passed')) for a, b in zip(originals, repeated)]), 'repeated': repeated}
    report['usage'], report['calls'] = judge.client.tokens, judge.client.calls
    save(output, report)
    return report

def chunk_ablation(output='artifacts/chunk_ablation.json'):
    cases = json.loads((ROOT / 'data/rag_questions.json').read_text())['cases']
    rows = []
    base = Store()
    base.embeddings(['warm up'])
    for size, overlap in [(60, 12), (120, 24), (180, 36)]:
        settings = Settings(db=ROOT / f'data/ablation_{size}.db', chunk_size=size, overlap=overlap)
        store = Store(settings, base.embedder)
        store.ingest(ROOT / 'corpus')
        chunks = store.all_chunks()
        measurements = []
        for case in cases:
            if not case['answerable']:
                continue
            ids = [c['id'] for c in chunks if c['source'] == case['source'] and normalize(case['evidence']) in normalize(c['text'])]
            result = store.search(case['question'], 3, case.get('category'))
            if ids:
                measurements.append(retrieval_metrics([c['id'] for c in result['chunks']], ids, 3))
        rows.append({'size_words': size, 'overlap_words': overlap, 'chunks': store.count(),
                     'annotatable_questions': len(measurements),
                     'retrieval': {key: mean([m[key] for m in measurements]) for key in measurements[0]}})
    save(output, rows)
    return rows
