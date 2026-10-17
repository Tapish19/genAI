# Deliverable map

- **Problem 1 ingestion / metadata / citations**: src/ingestion.py, src/store.py, src/rag.py; artifacts/http_smoke.json
- **Problem 1 retrieval / quality / latency**: artifacts/rag_results.json; data/rag_questions.json
- **Problem 1 scale costs**: configs/cost_assumptions.json; artifacts/cost_comparison.json
- **Problem 1 idempotency**: artifacts/idempotency.json; artifacts/idempotency.png
- **Problem 2 rubric / structured fallback**: src/judge.py; artifacts/test_results.txt
- **Problem 2 bias / validation**: artifacts/judge_validation.json; artifacts/ab_comparison.json
- **Problem 2 generated A/B outputs**: data/comparison_suite.json; artifacts/generation_usage.json
- **Problem 2 exact prompt / raw response / usage**: artifacts/llm_audit.jsonl; main.py replay REQUEST_ID
- **Architecture / screenshots**: docs/*.mmd; artifacts/*_architecture.png; artifacts/evidence.html; evidence PNGs
- **Original template populated**: submission/completed_submission.docx; artifacts/template_validation.json
- **Candidate review**: Verify personal details, reported personal work and compliance with the template's independent-reflection requirement. The edited Word document is preserved when creating the archive.
