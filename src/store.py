"""Transactional sqlite-vec index with config-aware idempotent ingestion."""
import hashlib
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import threading
import time

import sqlite_vec
from .config import ROOT, Settings
from .ingestion import extract, category_for, chunk_words

def digest(value):
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()

class Embedder:
    def __init__(self, model='sentence-transformers/all-MiniLM-L6-v2'):
        from fastembed import TextEmbedding
        self.name = model
        self.model = TextEmbedding(model_name=model, cache_dir=str(ROOT / '.runtime/embeddings'), threads=2)
        self.lock = threading.Lock()

    def embed(self, texts):
        with self.lock:
            vectors = [v.tolist() for v in self.model.embed(texts, batch_size=32)]
        if any(len(v) != 384 for v in vectors):
            raise ValueError('This index requires 384-dimensional embeddings')
        return vectors

class Store:
    def __init__(self, settings=None, embedder=None):
        self.settings = settings or Settings()
        self.settings.db = Path(self.settings.db)
        self.settings.db.parent.mkdir(parents=True, exist_ok=True)
        self.embedder = embedder
        with self.connect() as conn:
            conn.executescript('''
                CREATE TABLE IF NOT EXISTS index_config(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS documents(id TEXT PRIMARY KEY, source TEXT NOT NULL,
                    fingerprint TEXT NOT NULL, root TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS chunks(rowid INTEGER PRIMARY KEY, id TEXT UNIQUE NOT NULL,
                    document_id TEXT NOT NULL REFERENCES documents(id), source TEXT NOT NULL,
                    page INTEGER NOT NULL, ordinal INTEGER NOT NULL, category TEXT NOT NULL, text TEXT NOT NULL);
                CREATE VIRTUAL TABLE IF NOT EXISTS vec_chunks USING vec0(
                    embedding float[384] distance_metric=cosine, category text);
            ''')
            stored = conn.execute("SELECT value FROM index_config WHERE key='model'").fetchone()
            if stored and stored[0] != self.settings.embedding_model:
                raise ValueError('Embedding model changed; use a fresh RAG_DB or rebuild the index')
            conn.execute("INSERT OR IGNORE INTO index_config VALUES ('model', ?)", (self.settings.embedding_model,))

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(str(self.settings.db), timeout=30)
        conn.row_factory = sqlite3.Row
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        conn.execute('PRAGMA foreign_keys=ON')
        conn.execute('PRAGMA journal_mode=WAL')
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def embeddings(self, texts):
        if self.embedder is None:
            self.embedder = Embedder(self.settings.embedding_model)
        return self.embedder.embed(texts)

    def count(self):
        with self.connect() as conn:
            return conn.execute('SELECT count(*) FROM chunks').fetchone()[0]

    def ingest(self, folder):
        root = Path(folder).resolve()
        if not root.is_dir():
            raise ValueError(f'Corpus directory does not exist: {root}')
        started = time.perf_counter()
        stats = {'processed': 0, 'skipped': 0, 'inserted_chunks': 0, 'replaced_chunks': 0, 'before': self.count()}
        files = sorted(p for p in root.rglob('*') if p.suffix.lower() in ('.pdf', '.html', '.htm', '.md') and p.is_file())
        for path in files:
            source = path.relative_to(root).as_posix()
            doc_id = digest(str(root) + '/' + source)
            cfg = f'{self.settings.chunk_size}/{self.settings.overlap}/{self.settings.embedding_model}'
            fingerprint = digest(path.read_bytes() + cfg.encode())
            with self.connect() as conn:
                prior = conn.execute('SELECT fingerprint FROM documents WHERE id=?', (doc_id,)).fetchone()
            if prior and prior[0] == fingerprint:
                stats['skipped'] += 1
                continue
            pages = extract(path)
            category = category_for(pages)
            parts = [(page, i, text) for page, content in pages for i, text in enumerate(chunk_words(content, self.settings.chunk_size, self.settings.overlap))]
            vectors = self.embeddings([text for _, _, text in parts]) if parts else []
            # Complete extraction and embedding BEFORE changing the previous valid document.
            with self.connect() as conn:
                old = conn.execute('SELECT rowid FROM chunks WHERE document_id=?', (doc_id,)).fetchall()
                for row in old:
                    conn.execute('DELETE FROM vec_chunks WHERE rowid=?', (row[0],))
                conn.execute('DELETE FROM chunks WHERE document_id=?', (doc_id,))
                conn.execute('INSERT INTO documents VALUES (?,?,?,?) ON CONFLICT(id) DO UPDATE SET fingerprint=excluded.fingerprint',
                             (doc_id, source, fingerprint, str(root)))
                for (page, ordinal, text), vector in zip(parts, vectors):
                    chunk_id = digest(f'{doc_id}/{fingerprint}/{page}/{ordinal}/{text}')[:20]
                    rowid = conn.execute('INSERT INTO chunks(id,document_id,source,page,ordinal,category,text) VALUES (?,?,?,?,?,?,?)',
                        (chunk_id, doc_id, source, page, ordinal, category, text)).lastrowid
                    conn.execute('INSERT INTO vec_chunks(rowid,embedding,category) VALUES (?,?,?)',
                                 (rowid, sqlite_vec.serialize_float32(vector), category))
            stats['processed'] += 1
            stats['inserted_chunks'] += len(parts)
            stats['replaced_chunks'] += len(old)
        stats.update(after=self.count(), latency_ms=(time.perf_counter() - started) * 1000)
        return stats

    def all_chunks(self):
        with self.connect() as conn:
            return [dict(row) for row in conn.execute('SELECT * FROM chunks ORDER BY rowid')]

    def search(self, question, k=3, category=None, threshold=None):
        if not isinstance(question, str) or not question.strip() or len(question) > 2000:
            raise ValueError('question must contain 1..2000 characters')
        if isinstance(k, bool) or not isinstance(k, int) or not 1 <= k <= 20:
            raise ValueError('k must be an integer from 1 to 20')
        if category is not None and (not isinstance(category, str) or len(category) > 100):
            raise ValueError('category must be a string of at most 100 characters')
        start = time.perf_counter()
        vector = sqlite_vec.serialize_float32(self.embeddings([question])[0])
        embedded_ms = (time.perf_counter() - start) * 1000
        sql = 'SELECT rowid, distance FROM vec_chunks WHERE embedding MATCH ? AND k=?'
        args = [vector, k]
        if category is not None:
            sql += ' AND category=?'
            args.append(category)
        sql += ' ORDER BY distance'
        sql_start = time.perf_counter()
        with self.connect() as conn:
            hits = conn.execute(sql, args).fetchall()
            results = []
            for hit in hits:
                score = 1 - hit['distance']
                if threshold is not None and score < threshold:
                    continue
                row = dict(conn.execute('SELECT * FROM chunks WHERE rowid=?', (hit['rowid'],)).fetchone())
                row.update(similarity=score)
                results.append(row)
        return {'chunks': results, 'embedding_ms': embedded_ms,
                'vector_search_ms': (time.perf_counter() - sql_start) * 1000,
                'retrieval_ms': (time.perf_counter() - start) * 1000}

