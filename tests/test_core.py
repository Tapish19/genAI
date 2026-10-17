import json
import math
from pathlib import Path
import tempfile
import unittest

from src.config import Settings
from src.ingestion import chunk_words, extract
from src.judge import Judge, VerdictError, parse_object, aggregate, load_suite
from src.metrics import retrieval_metrics, answer_metrics, kappa, percentile
from src.rag import RAG, ABSTENTION
from src.store import Store

class StubEmbedder:
    def __init__(self):
        self.calls = 0
    def embed(self, texts):
        self.calls += 1
        return [[1.0] + [0.0] * 383 for _ in texts]

class StubClient:
    family = 'test-judge'
    model = 'stub'
    def __init__(self, responses):
        self.responses = iter(responses)
        self.messages = []
    def complete(self, messages, **kwargs):
        self.messages.append(messages)
        return {'text': next(self.responses), 'request_id': str(len(self.messages)), 'usage': {}, 'latency_ms': 0}

class MetricsTests(unittest.TestCase):
    def test_rank_metrics_known_example(self):
        result = retrieval_metrics(['x', 'a', 'b'], ['a', 'b', 'c'], 3)
        self.assertAlmostEqual(result['recall_at_k'], 2/3)
        self.assertEqual(result['mrr'], .5)
        self.assertAlmostEqual(result['context_precision'], 2/3)
        self.assertAlmostEqual(result['ndcg_at_k'], (1/math.log2(3)+.5)/(1+1/math.log2(3)+.5))
    def test_unanswerable_not_in_positive_denominator(self):
        with self.assertRaises(ValueError): retrieval_metrics([], [], 3)
    def test_multiset_f1_does_not_double_count(self):
        self.assertAlmostEqual(answer_metrics('a a a', 'a')['f1'], .5)
        self.assertEqual(answer_metrics('Paris [1]', 'Paris')['em'], 1)
    def test_kappa_and_quantile(self):
        self.assertEqual(kappa([True,False],[True,False]), 1)
        self.assertAlmostEqual(percentile([0,10], 95), 9.5)

class IngestionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.corpus = self.root / 'corpus'
        self.corpus.mkdir()
        self.embedder = StubEmbedder()
        self.store = Store(Settings(db=self.root/'test.db', chunk_size=12, overlap=3), self.embedder)
    def tearDown(self): self.temp.cleanup()
    def test_overlap_and_no_duplicate_tail(self):
        self.assertEqual(chunk_words('a b c d e f g', 4, 1), ['a b c d', 'd e f g'])
        self.assertEqual(chunk_words('', 4, 1), [])
        with self.assertRaises(ValueError): chunk_words('a', 4, 4)
    def test_idempotence_replacement_and_metadata_prefilter(self):
        path = self.corpus/'a.md'
        path.write_text('Category: billing\nRefunds take five days. ' * 4)
        a = self.store.ingest(self.corpus)
        before = {c['id'] for c in self.store.all_chunks()}
        calls = self.embedder.calls
        b = self.store.ingest(self.corpus)
        self.assertEqual(a['after'], b['after'])
        self.assertEqual(b['inserted_chunks'], 0)
        self.assertEqual(self.embedder.calls, calls)
        self.assertEqual(before, {c['id'] for c in self.store.all_chunks()})
        self.assertEqual(self.store.search('refund', category='security')['chunks'], [])
        self.assertTrue(self.store.search('refund', category='billing')['chunks'])
        path.write_text('Category: security\nAES-256 encryption.')
        c = self.store.ingest(self.corpus)
        self.assertEqual(c['after'], 1)
        with self.store.connect() as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM vec_chunks').fetchone()[0], 1)
        self.assertEqual(self.store.search('refund', category='billing')['chunks'], [])
    def test_html_excludes_scripts_and_has_no_joined_words(self):
        path = self.corpus/'b.html'
        path.write_text('<p>one</p><p>two</p><script>bad</script><style>bad</style>')
        text = extract(path)[0][1]
        self.assertEqual(text.split(), ['one','two'])
    def test_failure_leaves_previous_document_intact(self):
        path = self.corpus/'a.md'; path.write_text('old valid content')
        self.store.ingest(self.corpus)
        before = self.store.all_chunks()
        path.write_text('new content')
        def fail(texts): raise RuntimeError('simulated embedding failure')
        self.embedder.embed = fail
        with self.assertRaises(RuntimeError): self.store.ingest(self.corpus)
        self.assertEqual(before, self.store.all_chunks())
    def test_sql_like_filter_is_literal(self):
        (self.corpus/'a.md').write_text('Category: billing\nHello')
        self.store.ingest(self.corpus)
        self.assertEqual(self.store.search('hello', category="billing' OR 1=1 --")['chunks'], [])
    def test_changed_embedding_model_rejected(self):
        with self.assertRaises(ValueError): Store(Settings(db=self.root/'test.db', embedding_model='different'), self.embedder)
    def test_no_context_does_not_call_llm(self):
        (self.corpus/'a.md').write_text('Category: billing\nHello')
        self.store.ingest(self.corpus)
        client = StubClient([])
        result = RAG(self.store, client).query('unknown', category='missing')
        self.assertEqual(result['answer'], ABSTENTION)
        self.assertEqual(result['usage']['total_tokens'], 0)
        self.assertEqual(client.messages, [])
    def test_invalid_citation_is_rejected(self):
        (self.corpus/'a.md').write_text('Category: billing\nHello')
        self.store.ingest(self.corpus)
        result = RAG(self.store, StubClient(['{"answer":"Invented", "citations":[99]}'])).query('hello')
        self.assertTrue(result['abstained'])

class JudgeTests(unittest.TestCase):
    def test_json_repairs(self):
        for raw in ['```json\n{"a": 1}\n```', 'prefix {"a":1} suffix', '{"a":1,}', "{'a': 1}"]:
            self.assertEqual(parse_object(raw)[0], {'a':1})
        with self.assertRaises(VerdictError): parse_object('not json')
    def test_invalid_score_retries_then_errors(self):
        client = StubClient(['{"correctness":{"score":9,"rationale":"x"}}'] * 2)
        result = Judge(client).pointwise({'input':'q','model_output':'x','criteria':['correctness']})
        self.assertEqual(result['status'], 'error')
        self.assertFalse(result['passed'])
        self.assertEqual(len(client.messages), 2)
    def test_swap_identity_mapping_and_disagreement_abstention(self):
        pair = {'input':'q','model_output':'first','output_b':'second'}
        stable = Judge(StubClient(['{"winner":"A","rationale":"x"}', '{"winner":"B","rationale":"x"}'])).pairwise(pair)
        self.assertEqual(stable['winner'], 'A')
        self.assertFalse(stable['flipped'])
        biased = Judge(StubClient(['{"winner":"A","rationale":"x"}'] * 2)).pairwise(pair)
        self.assertEqual(biased['winner'], 'abstain')
        self.assertTrue(biased['flipped'])
    def test_failures_count_in_pass_denominator(self):
        result = aggregate([{'status':'ok','passed':True,'overall':4}, {'status':'error','passed':False}])
        self.assertEqual(result['pass_rate'], .5)
        self.assertEqual(result['errors'], 1)
    def test_same_family_guard(self):
        with self.assertRaises(ValueError): Judge(StubClient([]), generator_family='test-judge')
    def test_boolean_is_not_integer_score(self):
        client = StubClient(['{"correctness":{"score":true,"rationale":"x"}}'] * 2)
        verdict = Judge(client).pointwise({'input':'q','model_output':'x','criteria':['correctness']})
        self.assertEqual(verdict['status'], 'error')
    def test_provenance_not_in_prompt(self):
        client = StubClient(['{"correctness":{"score":4,"rationale":"reference match"}}'])
        Judge(client).pointwise({'input':'q','model_output':'x','criteria':['correctness'], 'generator_family':'SECRET_PROVENANCE'})
        self.assertNotIn('SECRET_PROVENANCE', json.dumps(client.messages))

if __name__ == '__main__': unittest.main()
