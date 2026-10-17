# Free runtime and model components

The project source is provided under the included MIT license. The following
third-party components retain their respective licenses; no ownership is claimed.

- [Qwen2.5-0.5B-Instruct GGUF](https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF): Apache-2.0.
- [SmolLM2-1.7B-Instruct GGUF](https://huggingface.co/HuggingFaceTB/SmolLM2-1.7B-Instruct-GGUF): Apache-2.0.
- [all-MiniLM-L6-v2](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2): Apache-2.0.
- [llama.cpp](https://github.com/ggml-org/llama.cpp): MIT.
- [sqlite-vec](https://github.com/asg017/sqlite-vec): MIT / Apache-2.0.
- [FastEmbed](https://github.com/qdrant/fastembed): Apache-2.0.
- Python packages: see installed package metadata and pinned requirements.

Model weights, inference binaries and virtual environments are excluded from the
submission archive. The bootstrap fetches the original publishers' artifacts;
runtime/model SHA256 hashes and revision URLs are recorded in
`configs/runtime.lock.json`. License conditions still apply to downloaded files.
