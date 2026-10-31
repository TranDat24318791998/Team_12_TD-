"""Validate the active React entry pages and local build assets without third-party packages."""
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit
import json
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / 'frontend'

class PageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.refs = []
        self.ids = []
        self.language = None
        self.module = False
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'html': self.language = attrs.get('lang')
        if 'id' in attrs: self.ids.append(attrs['id'])
        if tag == 'script' and attrs.get('type') == 'module': self.module = True
        if tag in ('script', 'img', 'link'):
            self.refs.append(attrs.get('src') or attrs.get('href') or '')

pages = list(FRONTEND.glob('*.html'))
assert {p.name for p in pages} == {'index.html','demo.html','updated.html','night.html','proof.html'}
for page in pages:
    parser = PageParser()
    parser.feed(page.read_text())
    assert parser.language == 'vi' and parser.module, page.name
    assert 'root' in parser.ids and len(parser.ids) == len(set(parser.ids)), page.name
    for ref in parser.refs:
        if ref and not urlsplit(ref).scheme:
            assert (page.parent / ref).is_file(), f'Missing resource: {page.name}: {ref}'
for svg in (FRONTEND / 'img').glob('*.svg'): ET.parse(svg)
assert (FRONTEND / 'js/app.js').stat().st_size > 0
assert (FRONTEND / 'js/app.js.LEGAL.txt').is_file()
package = json.loads((FRONTEND / 'package.json').read_text())
assert 'react' in package['dependencies'] and 'react-dom' in package['dependencies']
print('PASS: 5 React entry pages, compiled bundle, license notice, CSS and SVG assets')
print('Run npm test inside frontend/ for API and React rendering tests. Browser QA is separate.')
