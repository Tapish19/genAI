"""Page-aware extraction and deterministic word windows."""
from html.parser import HTMLParser
from pathlib import Path
import re
from pypdf import PdfReader

class TextHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style', 'noscript'):
            self.hidden += 1
        if tag in ('p', 'div', 'br', 'h1', 'h2', 'h3', 'li'):
            self.parts.append('\n')

    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'noscript'):
            self.hidden = max(0, self.hidden - 1)
        if tag in ('p', 'div', 'h1', 'h2', 'h3', 'li'):
            self.parts.append('\n')

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)

def extract(path):
    path = Path(path)
    if path.suffix.lower() == '.pdf':
        reader = PdfReader(path)
        pages = [(i + 1, page.extract_text() or '') for i, page in enumerate(reader.pages)]
        if not any(text.strip() for _, text in pages):
            raise ValueError(f'{path.name}: no extractable text; scanned PDFs need OCR')
        return pages
    text = path.read_text(encoding='utf-8')
    if path.suffix.lower() in ('.html', '.htm'):
        parser = TextHTML()
        parser.feed(text)
        text = ''.join(parser.parts)
    return [(1, text)]

def chunk_words(text, size=120, overlap=24):
    if not 0 <= overlap < size:
        raise ValueError('Require 0 <= overlap < size')
    words = text.split()
    chunks = []
    for start in range(0, len(words), size - overlap):
        chunks.append(' '.join(words[start:start + size]))
        if start + size >= len(words):
            break
    return chunks

def category_for(pages):
    match = re.search(r'Category:\s*([\w-]+)', '\n'.join(text for _, text in pages), re.I)
    return match.group(1).lower() if match else 'general'

