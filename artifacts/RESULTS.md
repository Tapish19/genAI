# Measured results

Generated from committed JSON artifacts. Synthetic dataset: 8 support documents,
20 QA cases (16 answerable + 4 negatives); 8 generated A/B pairs and 8 authored
judge-validation labels. These are development fixtures, not a production or human study.

## Problem 1

| Metric | Measured value |
|---|---:|
| Recall@3 | 1.000 |
| Hit rate@3 | 1.000 |
| MRR | 0.969 |
| nDCG@3 | 0.977 |
| Context precision | 0.542 |
| Faithfulness (local judge, 0–4) | 3.200 |
| Answer relevance (local judge, 0–4) | 3.200 |
| Exact match (all 20) | 65.0% |
| Token F1 (all 20) | 0.846 |
| Answerable-only EM / F1 | 56.2% / 0.807 |
| Negative abstention rate | 100.0% |
| Positive abstention rate | 0.0% |
| Retrieval p50 / p95 | 16.16 / 19.82 ms |
| End-to-end p95 | 2596.75 ms |

Retrieval includes embedding and SQLite connection/search overhead. 100 warm serial
samples; end-to-end uses 20 actual calls. The corpus has 16
chunks. Hardware and runtime are recorded in `rag_results.json`.
Judge errors: 0. LLM quality scores are small-model judgments,
not independent human verification. Citation indices exist, but that alone does
not prove every cited passage semantically supports every generated claim.

Retrieval vs generation: retrieval hit rate is 100.0%,
while answerable exact match is 56.2%. The raw per-case results
show whether the remaining misses arise after a relevant chunk was found.
Short-answer EM is strict about wording; F1 gives a complementary lexical measure.
Neither metric proves multi-hop or out-of-domain quality.

### Chunking ablation

| Size / overlap (words) | Chunks | MRR | Context precision |
|---|---:|---:|---:|
| 60 / 12 | 32 | 0.938 | 0.417 |
| 120 / 24 | 16 | 0.969 | 0.542 |
| 180 / 36 | 8 | 1.000 | 0.625 |

### Store cost projections (USD/month)

| Vectors | sqlite-vec VM + weekly backup | Cheapest eligible managed | Savings | Managed Standard |
|---|---:|---:|---:|---:|
| 100,000 | $7.20 | $0.00 (Starter) | $-7.20 | $50.00 |
| 1,000,000 | $14.40 | $20.00 (Builder) | $5.60 | $50.00 |
| 10,000,000 | $28.80 | $50.00 (Standard) | $21.20 | $50.00 |

All assumptions and arithmetic are in `cost_comparison.json`. Initial managed
loading is shown separately there. Rates are frozen scenario inputs based on
[Pinecone pricing](https://www.pinecone.io/pricing/),
[metering rules](https://docs.pinecone.io/guides/manage-cost/understanding-cost), and
[DigitalOcean VM/backup pricing](https://www.digitalocean.com/pricing/droplets).
At small scale a free managed tier is cheaper. At 10M exact cosine scans can be
too slow despite fitting on disk. These estimates do not include LLM hardware,
staff labor, taxes or equal availability. No 10M-vector latency claim is made.

## Problem 2

| Config | Pass rate | Mean score (0–4) | Consensus win rate, all pairs |
|---|---:|---:|---:|
| A: Ungrounded-v1 | 50.0% | 3.350 | 0.0% |
| B: Grounded-v2 | 12.5% | 2.725 | 0.0% |

Declared winner: **inconclusive**, using higher two-order consensus win count.
Ties/disagreements earn neither config a win. When all pairs are rejected for
order disagreement, the result is inconclusive; no actual equivalence is claimed.

The independent gold-reference check favors **B**:
A exact match 0.0%, F1 0.041;
B exact match 50.0%, F1 0.748.
This secondary lexical check uses the same eight frozen outputs and references.
It does not replace or disguise the inconclusive LLM verdict, and lexical overlap
does not establish every rubric dimension.

| Bias / validation metric | Before | After |
|---|---:|---:|
| Position order-disagreement rate (8 pairs) | 100.0% | 100.0% |
| Position consensus coverage | 0.0% | 0.0% |
| Padding absolute score drift (1 probe) | 0.000 | 0.000 |
| Identity label score gap (1 probe pair) | 0.000 | 1.200 |
| Confidently wrong answer accepted | True | True |
| Score population standard deviation | 0.614 | 0.397 |
| Gold agreement (8 synthetic labels) | 12.5% | 75.0% |
| Cohen's kappa | -0.556 | 0.385 |

Test-retest: 0.0% pass/fail flips over
4 cases at temperature 0, seed 42.
Before/after is the same fixed probe set with an uncalibrated versus anchored
prompt, except the identity probe which compares exposed versus hidden labels.
Some mitigations may fail or worsen a metric; the table reports observed values.
Consensus abstention controls unreliable decisions; it does not establish that
the underlying model is unbiased. Small sample sizes limit conclusions.

The judge is suitable as a review aid, not an autonomous production release gate.
Human review is required for disagreements, high-impact outputs and adversarial
failures. Wider score spread is not sufficient evidence of better calibration.

## Audit and provenance

All judge/generator prompts, raw model responses and real token counts are in
`llm_audit.jsonl`; request IDs link each report to its calls. Earlier debugging
runs remain in the log and are not pooled into final metrics. To inspect or
rerun one call, use `main.py replay REQUEST_ID` or add `--rerun`.
`model_manifest.json` records exact model revisions and SHA256 hashes.
`template_validation.json`, `test_results.txt` and `http_smoke.json` record checks.
The evidence screenshots show actual audit records in the local evidence viewer.

Candidate identity/contact and mandatory independent reflections remain for the
candidate. Codex generated the implementation and technical write-up; no personal
authorship or human validation is claimed.
