# Local RAG + Auditable LLM Judge

Two runnable projects for the Applied AI / ML Engineering assignment. Python,
sqlite-vec, MiniLM embeddings, Qwen2.5-0.5B generation, and SmolLM2-1.7B judging.
Models run locally with llama.cpp on CPU. No paid service or API key is required.

The original brief and template are in `submission/source/`. The populated Word
document is `submission/completed_submission.docx`. Reports contain real model
outputs, not simulated scores. Synthetic test documents and labels are explicitly
identified. The template's mandatory personal reflections must be completed by the
candidate without AI help; those fields are clearly marked. This implementation,
technical write-up, fixtures and artifact preparation were AI-assisted by Codex.

## Quick start (Windows PowerShell)

Requires Python 3.11–3.13, Windows x64, about 4 GB free RAM and 5 GB free disk
for the environment, CPU runtime and models. The verified runtime here is Python
3.13. Internet is needed for initial downloads; inference is local afterwards.
Download time depends on the connection; the models total about 1.5 GB. A cached
installation starts in seconds. Full evaluation takes longer than the quickstart.

From the extracted `gen-ai-assignment` folder:

```powershell
python scripts/bootstrap.py
.\.venv\Scripts\python.exe main.py models start
.\.venv\Scripts\python.exe main.py ingest corpus
.\.venv\Scripts\python.exe main.py query "How long do I have to request a refund?" --category billing
.\.venv\Scripts\python.exe main.py serve --port 8080
```

In a second terminal:

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8080/query -Method Post -ContentType 'application/json' -Body '{"question":"Which encryption protects data at rest?","k":3,"category":"security"}'
Invoke-RestMethod http://127.0.0.1:8080/health
```

The response includes the answer, citations with source/page/chunk IDs, retrieved
chunks, embedding/search/generation/total latency, and actual model token usage.
`GET /health` reports index health; `POST /query` validates inputs and bounds k.
Bind is loopback only. This is a development HTTP service, with no authentication,
multi-tenant isolation or production deployment implied.

To stop model processes started by this project:

```powershell
.\.venv\Scripts\python.exe main.py models stop
```

macOS/Linux: create a Python environment, `pip install -r requirements.txt`, and
configure two independent llama.cpp-compatible local endpoints in `.env`. The
automatic portable binary download is Windows x64 only. Ollama can expose a
compatible endpoint, but schema-format compatibility must be verified separately.

## Configuration

Copy `.env.example` to `.env` if changing defaults. Environment variables override
the file. All variables are listed in `.env.example`; no secrets are committed.
`GENERATOR_BASE_URL`, `GENERATOR_MODEL`, `GENERATOR_FAMILY`, `GENERATOR_API_KEY`
and corresponding `JUDGE_*` variables are independent. Family names must be
honest: the pipeline rejects the same declared family for judge and generator.
`MODEL_THREADS` controls local server CPU threads; defaults to four per server.

`RAG_DB`, `EMBEDDING_MODEL`, `CHUNK_SIZE`, `CHUNK_OVERLAP`, `MIN_SIMILARITY`,
`TOP_K`, `LLM_TIMEOUT`, `AUDIT_LOG`, and `QUERY_LOG` configure index, retrieval,
timeouts and logs. The supported embedding dimension is 384. A model change
requires a fresh index; a chunking change transactionally replaces old chunks.

## Problem 1: retrieval and grounded generation

`src/ingestion.py` extracts text from PDF, HTML and Markdown. PDF pages are
retained; HTML scripts/styles are excluded. Scanned PDFs without text raise a
clear OCR-required error. Chunking uses **120 whitespace-delimited words with
24-word overlap**, constrained to 180 words to reduce MiniLM input truncation.
Words are not tokenizer tokens; unusually long technical tokens can still exceed
the embedding context, an accepted limitation of this simple chunker.

`src/store.py` uses `sentence-transformers/all-MiniLM-L6-v2` via CPU ONNX
FastEmbed, **384 float32 dimensions**, and exact cosine search in sqlite-vec.
Each chunk stores source, page, ordinal and category. Category is a native vec0
metadata prefilter, applied before selecting top k. Without the filter the index
is searched globally. Source IDs are stable for a given corpus root and relative
path; copying the corpus to another root creates a separate namespace.

Ingestion hashes file bytes, chunk configuration and model ID. An unchanged file
is skipped without embedding calls. Changed documents are fully parsed/embedded
before a transaction deletes old vectors and inserts the replacement vectors.
Chunk hashes are unique, metadata and vectors commit together, and SQLite foreign
keys are enabled. Re-ingestion does not prune files removed from the corpus;
rebuild a fresh DB for corpus deletions. Failed new embeddings preserve old data.

`src/rag.py` rejects results below cosine similarity **0.38**, generates a short
structured answer and source indices, validates citation bounds, and attaches
source metadata. No qualifying chunks means a deterministic abstention with
zero generator tokens. Invalid/missing citations also cause abstention. Similarity
is a relevance heuristic, not a proof of answerability. Citation existence is
validated; semantic support is evaluated independently, not guaranteed by JSON.

## Reproduce the evaluation

```powershell
.\.venv\Scripts\python.exe main.py test
.\.venv\Scripts\python.exe main.py evaluate all
.\.venv\Scripts\python.exe main.py package
```

Or run components:

```powershell
.\.venv\Scripts\python.exe main.py evaluate ablation
.\.venv\Scripts\python.exe main.py evaluate rag
.\.venv\Scripts\python.exe main.py evaluate generate-ab
.\.venv\Scripts\python.exe main.py evaluate bias
.\.venv\Scripts\python.exe main.py compare data/comparison_suite.json
```

The frozen QA set contains **20 cases: 16 answerable and 4 negatives**, spanning
8 fictional support documents (3 MD, 3 HTML, 2 PDF). Gold relevance is an annotated
source plus evidence substring; overlapping windows can both be relevant. Retrieval
metrics use only answerable queries: recall is relevant retrieved / all relevant,
hit rate is any hit, MRR is inverse rank of the first hit, nDCG uses binary gains
and log2 discounts, context precision is relevant / returned. Negatives are
reported separately. Embedding/index settings and data hashes are saved.

EM and multiset token F1 remove citations and normalize case/punctuation. Both
all-case and answerable-only scores are reported to expose the effect of
abstentions. Faithfulness, correctness and answer relevance are judged using
the independent SmolLM2 model with context and references. Judge errors are
reported; failed cases are not silently promoted to successful judgments.

Warm serial retrieval p50/p95 uses **100 samples** (five passes of the same 20
queries); it includes query embedding and SQLite overhead, excludes generation.
End-to-end p95 comes from the actual 20 RAG calls and includes generation.
These timings describe a tiny synthetic corpus, not production scale.

`artifacts/chunk_ablation.json` compares 60/12, 120/24 and 180/36 word settings.
`artifacts/rag_results.json` contains every prediction, retrieved chunk, judge
verdict and summary. `artifacts/RESULTS.md` summarizes the measured findings.

## Cost model and discussion

`configs/cost_assumptions.json` freezes every input. The generated
`artifacts/cost_comparison.json` estimates 100K, 1M and 10M vectors using
384 dimensions, 20-byte IDs, 768 bytes of text/metadata per record, 1,000 queries
per month and 1% monthly updates. The VM estimate includes weekly backups.
The managed comparison includes eligible free/Builder plans, plus the Standard
minimum separately. A managed free tier can beat self-hosting at small scale.

Prices are scenario estimates in USD before tax, based on
[DigitalOcean's VM pricing](https://www.digitalocean.com/pricing/droplets),
[Pinecone's pricing](https://www.pinecone.io/pricing/), and its
[metering documentation](https://docs.pinecone.io/guides/manage-cost/understanding-cost).
No cloud resource was purchased. Provider prices and plan quotas can change.
The store-only comparison excludes generation, embeddings, staff time and tax.
It does not claim equivalent availability or measured latency at projected scale.

SQLite removes a database server and simplifies local development. Its exact scan
and single writer are deliberate limits. At 10M vectors the index exceeds the
selected VM's RAM, so low query volume may keep the bill small while latency is
poor. Use a self-hosted ANN store or managed DB once strict latency, concurrent
writes, high availability, backups with recovery guarantees or operational effort
outweigh the savings. The measured retrieval-versus-generation result is discussed
in the generated results report, without extrapolating synthetic benchmark scores.

## Problem 2: independent LLM judging

```powershell
.\.venv\Scripts\python.exe main.py judge data/example_suite.yaml --output artifacts/example_report.json
.\.venv\Scripts\python.exe main.py judge data/judge_probes.json --output artifacts/probe_suite_report.json
.\.venv\Scripts\python.exe main.py compare data/comparison_suite.json --output artifacts/ab_comparison.json
```

Suites may be JSON or YAML, as a list or `{ "cases": [...] }`. Each case has
`id`, `input`, `system_prompt`, `model_output`, and optional `expected_output`,
`context`, `criteria`. The optional criteria list selects documented rubric keys;
weights are renormalized. Pairwise suites additionally require `output_b`.

The six-criterion rubric is defined in `src/judge.py`. Scores use 0–4 anchors:
0 entirely wrong/unsupported, 1 major errors, 2 mixed, 3 minor omissions,
4 fully correct/supported. Weights: correctness .30, faithfulness .25,
completeness .15, relevance .15, instruction following .10, tone/safety .05.
Each criterion includes an evidence rationale. Weighted overall scores are
computed by code; a pass requires overall >=3 and correctness >=3 when scored.

Pointwise reference-based judging supports QA with gold facts; reference-free
mode can assess instructions/style when no reference exists but cannot establish
factual truth. Pairwise comparison suits competing prompts and avoids requiring
fine-grained score resolution. This project implements both pointwise and pairwise.
Verdicts are schema-constrained, then independently validated. Parsing tries strict
or embedded/fenced JSON, trailing-comma repair, and safe Python literal parsing.
Invalid schema/ranges trigger one model repair call; a second failure is an explicit
error. No `eval` and no default passing score. Failures remain in the pass denominator.

Every actual call logs full prompt, schema, raw response, model, role, seed, tag,
latency, request ID and real token counts in `artifacts/llm_audit.jsonl`. No API
keys are logged. Local model revisions and SHA256 checksums are recorded in the
runtime manifest and copied into the submission. There is no mocked inference
in the reported evaluation. Test-only stub outputs appear only in unit tests.

Bias controls and measurements:

- **Position:** judge each pair in both orders, map displayed labels back to
  canonical model identities, report raw disagreement rate, and abstain when
  orders disagree. Report consensus coverage so abstaining cannot hide bias.
  Uncalibrated and anchored prompts are measured on the same generated pairs.
- **Verbosity:** rubric awards no credit for length and penalizes unsupported
  additions. A same-fact padded-answer probe reports absolute score drift.
- **Self-enhancement:** Qwen generator and SmolLM judge are different families;
  source labels are stripped from judgment data. An exposed-versus-blinded model
  label probe measures sensitivity. It does not prove population-wide neutrality.
- **Sycophancy/style:** per-criterion rationales, confidently wrong answers,
  and a prompt-injection probe test whether confidence/imperatives override facts.
- **Clustering:** anchored score examples plus pairwise decisions; measure score
  standard deviation on the same fixed probes. A wider spread alone is not proof
  of better judgment; gold agreement must also be considered.

Validation reports agreement and Cohen's kappa on **8 synthetic binary labels**,
test-retest on **4 cases** at temperature zero, and adversarial outcomes.
These are authored fixtures, not a human validation study. The model is small and
may fail easy probes; the raw failures are retained. This judge should assist
review and catch regressions, with human review of disagreements and high-impact
changes. It should not autonomously gate production releases on this evidence.

The A/B experiment generates 8 pairs from one fixed question per support document:
Qwen with an ungrounded prompt (A) and a context-grounded prompt (B). Both actual
outputs are frozen in `data/comparison_suite.json`; they can be rejudged without
regeneration. Reports give pass rates, mean scores, two-order consensus win rates,
flip rates and a declared winner (or an honest tie). Win-rate denominator is all
pairs, including ties/disagreements, not only decisive pairs.

## Repository and artifacts

- `src/`: ingestion, sqlite store, RAG, HTTP service, judge, metrics, evaluation.
- `scripts/`: portable runtime setup, fixtures, costs, evidence and submission.
- `tests/`: independent correctness and failure-path tests.
- `data/`: frozen QA cases, judge probes, generated A/B outputs.
- `artifacts/`: reports, logs, screenshots, diagrams, source hashes and test results.
- `submission/`: populated template, source brief/template and submission archive.

`main.py package` refreshes the technical submission from existing results. It
does not overwrite candidate reflection text with invented personal experience.
The source archive excludes model weights, virtual environments, caches and secrets.
To regenerate corpus fixtures deliberately, run `main.py prepare`; ordinary
evaluation uses the frozen files without changing them.
