from dataclasses import dataclass, field
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def load_env():
    path = ROOT / '.env'
    if path.exists():
        for line in path.read_text(encoding='utf-8').splitlines():
            if line.strip() and not line.lstrip().startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

load_env()

@dataclass
class Settings:
    db: Path = field(default_factory=lambda: Path(os.getenv('RAG_DB', str(ROOT / 'data/rag.db'))))
    embedding_model: str = field(default_factory=lambda: os.getenv('EMBEDDING_MODEL', 'sentence-transformers/all-MiniLM-L6-v2'))
    dimension: int = 384
    chunk_size: int = field(default_factory=lambda: int(os.getenv('CHUNK_SIZE', '120')))
    overlap: int = field(default_factory=lambda: int(os.getenv('CHUNK_OVERLAP', '24')))
    min_similarity: float = field(default_factory=lambda: float(os.getenv('MIN_SIMILARITY', '0.38')))
    top_k: int = field(default_factory=lambda: int(os.getenv('TOP_K', '3')))

    def __post_init__(self):
        if not 0 <= self.overlap < self.chunk_size:
            raise ValueError('Require 0 <= overlap < chunk_size')
        if self.chunk_size > 180:
            raise ValueError('MiniLM has a short context: use chunk_size <= 180 words')

