#!/usr/bin/env python3
"""Collect bounded, linked journal evidence; never infer a Tier from a crawl."""
from __future__ import annotations
import argparse
import hashlib
import io
import json
import re
import sys
import time
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, urldefrag, urljoin, urlparse
from urllib.request import Request, urlopen

TIER_RE = re.compile(r'\bTCI\b|\btier\s*[123๑๒๓]|กลุ่ม\s*(?:ที่\s*)?[123๑๒๓]|ฐานข้อมูลศูนย์ดัชนี', re.I)
LINK_RE = re.compile(r'\bTCI\b|tier|indexing|indexed|abstracting|assessment|accredit|ประเมิน|รับรอง|ดัชนี|จัดกลุ่ม|ฐานข้อมูล', re.I)
BLOCKS = {'p','div','section','article','li','h1','h2','h3','h4','br','tr'}


def clean(text: str) -> str:
    return ' '.join(text.split())


class JournalParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts, self.title_parts, self.links, self.images = [], [], [], []
        self._title, self._skip, self._anchor = False, 0, None

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if tag in {'script','style','noscript'}: self._skip += 1
        if tag == 'title': self._title = True
        if self._skip: return
        if tag in BLOCKS: self.parts.append('\n')
        if tag == 'a': self._anchor = {'url': (d.get('href') or '').strip(), 'text': ''}
        if tag == 'img':
            self.images.append({'url': (d.get('src') or '').strip(), 'text': d.get('alt') or ''})
            if self._anchor: self._anchor['text'] += ' ' + (d.get('alt') or '')

    def handle_endtag(self, tag):
        if tag in {'script','style','noscript'}: self._skip = max(0,self._skip-1)
        if tag == 'title': self._title = False
        if tag in BLOCKS: self.parts.append('\n')
        if tag == 'a' and self._anchor:
            self._anchor['context'] = clean(''.join(self.parts[-30:]))[-700:]
            self.links.append(self._anchor)
            self._anchor = None

    def handle_data(self, data):
        if self._skip: return
        self.parts.append(data)
        if self._title: self.title_parts.append(data)
        if self._anchor: self._anchor['text'] += data

    @property
    def text(self):
        return '\n'.join(clean(x) for x in ''.join(self.parts).splitlines() if clean(x))

    @property
    def journal_title(self):
        return clean(' '.join(self.title_parts))


def journal_identity(url):
    p = urlparse(url)
    host = p.hostname or ''
    if p.scheme != 'https' or p.username or p.port not in {None,443} or not (host == 'tci-thaijo.org' or host.endswith('.tci-thaijo.org')):
        raise ValueError('expected a public HTTPS ThaiJO journal/article URL')
    m = re.match(r'^/index\.php/([A-Za-z0-9._-]+)(?:/|$)', p.path)
    if not m: raise ValueError('URL must contain /index.php/<journal-slug>')
    return f'https://{host}/index.php/{m[1]}', m[1]


def get_bytes(url, limit, expected_host=None):
    req = Request(url, headers={'User-Agent':'ResearchAuthorIndex/0.1 (public journal evidence)'})
    with urlopen(req, timeout=25) as response:
        final = urlparse(response.url)
        if response.status != 200 or final.scheme != 'https' or (expected_host and final.hostname != expected_host):
            raise ValueError(f'unexpected journal response: {response.status} {response.url}')
        raw = response.read(limit+1)
        if len(raw)>limit: raise ValueError('response exceeds size limit')
        return raw, response.headers.get('content-type','')


def valid_medal_url(url, slug):
    p = urlparse(url)
    return (p.scheme == 'https' and p.hostname == 'www.tci-thaijo.org' and not p.username
            and p.path == '/public/tinfo.php' and parse_qs(p.query).get('path',[''])[0].casefold() == slug.casefold())


def public_source(url):
    p = urlparse(url)
    host = p.hostname or ''
    return (p.scheme == 'https' and not p.username and p.port in {None,443}
            and any(host == d or host.endswith('.'+d) for d in ('tci-thaijo.org','tci-thailand.org')))


def priority(url, label, journal_url):
    """Only observed relevant links; ignore articles, account and submission flows."""
    p = urlparse(url)
    path = p.path.lower().rstrip('/')
    if re.search(r'/(article|issue|user|login|search|payments)(/|$)', path): return 0
    if path.endswith('/public/api/infotier.php'): return 0
    if not path and not label: return 0
    if LINK_RE.search(label): return 100
    if re.search(r'/(indexing|abstracting|history|tci)(/|$)', path): return 90
    if path == urlparse(journal_url).path.lower()+'/about': return 80
    if '/announcement/view/' in path: return 40
    if path.endswith('/announcement'): return 60
    return 0


def snippets(text):
    # Bounded excerpts for review; complete captured text remains in the artifact.
    ranges = []
    for m in TIER_RE.finditer(text):
        start, end = max(0,m.start()-200), min(len(text),m.end()+600)
        if ranges and start <= ranges[-1][1]: ranges[-1][1] = min(ranges[-1][0]+1800, max(end,ranges[-1][1]))
        else: ranges.append([start,end])
    return [text[a:b] for a,b in ranges[:24]]


def extract(raw, content_type):
    ct = content_type.lower()
    if raw.startswith(b'%PDF-'):
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(raw))
            if len(reader.pages)>60: return 'pdf','','needs_visual_review: PDF exceeds 60 pages',None
            txt = '\n'.join(page.extract_text() or '' for page in reader.pages)
            return 'pdf',txt,'' if txt.strip() else 'needs_visual_review: scanned PDF',None
        except Exception as e:
            return 'pdf','',f'needs_visual_review: PDF extraction unavailable ({type(e).__name__})',None
    if ct.startswith('image/'):
        return 'image','','needs_visual_review',None
    if 'html' not in ct: raise ValueError('unsupported evidence content type: '+content_type)
    parser = JournalParser()
    parser.feed(raw.decode('utf-8','replace'))
    return 'html',parser.text,'',parser


def inspect(url, badge_dir, max_pages=8, delay=0.3, extra_urls=()):
    journal_url, slug = journal_identity(url)
    dest = Path(badge_dir).resolve()
    dest.mkdir(parents=True,exist_ok=True)
    result = dict(journal_url=journal_url,journal_slug=slug,journal_title='',checked_at=date.today().isoformat(),
                  status='needs_review',documents=[],candidates=[],reviewed_evidence=[],errors=[],pending_links=[],ignored_links=[])
    queue = [(1000,journal_url,'','homepage')]
    seen, discovered = set(), set()
    requested = set(extra_urls)
    while queue and len(seen)<max_pages:
        queue.sort(key=lambda x:-x[0])
        _, source, parent, label = queue.pop(0)
        if source in seen: continue
        seen.add(source)
        if len(seen)>1 and delay: time.sleep(delay)
        try:
            raw, ct = get_bytes(source, 5_000_000, urlparse(source).hostname)
            kind, txt, status, parser = extract(raw,ct)
            digest = hashlib.sha256(raw).hexdigest()
            ident = hashlib.sha256((source+digest).encode()).hexdigest()[:16]
            suffix = {'html':'.html','pdf':'.pdf'}.get(kind, '.png' if raw.startswith(b'\x89PNG') else '.img')
            file = dest/(ident+suffix)
            file.write_bytes(raw)
            text_file = dest/(ident+'.txt')
            text_file.write_bytes(txt.encode('utf-8'))  # Preserve hash-identical LF bytes on Windows.
            doc = dict(id=ident,url=source,discovered_from=parent,link_text=clean(label),kind=kind,
                       file=str(file),sha256=digest,text_file=str(text_file),
                       text_sha256=hashlib.sha256(txt.encode()).hexdigest(),status=status)
            result['documents'].append(doc)
            if source == journal_url and parser: result['journal_title'] = parser.journal_title
            for i, excerpt in enumerate(snippets(txt)):
                result['candidates'].append(dict(id=f'{ident}:{i}',document_id=ident,excerpt=excerpt))
            if kind == 'image' or (kind == 'pdf' and not txt):
                result['candidates'].append(dict(id=f'{ident}:visual',document_id=ident,excerpt='',needs_visual_review=True))
            if not parser: continue
            for link in parser.links+parser.images:
                target = urldefrag(urljoin(source,link['url']))[0]
                if not link['url'] or target in seen or target in discovered: continue
                asset = bool(re.search(r'\.(pdf|png|jpg|jpeg)(?:[?#]|$)',target,re.I))
                context = link['text'] + (' '+link.get('context','') if asset else '')
                score = 110 if valid_medal_url(target,slug) else priority(target,context,journal_url)
                if '/public/api/infoTier.php' in target or (urlparse(target).hostname in {'tci-thailand.org','www.tci-thailand.org'} and urlparse(target).path in {'','/'}):
                    if target not in discovered:
                        discovered.add(target)
                        result['ignored_links'].append(dict(url=target,reason='generic TCI landing/redirect is not journal-specific evidence'))
                    continue
                if target in requested: score = 120
                if not score: continue
                discovered.add(target)
                same = target.lower().startswith(journal_url.lower()+'/')
                asset = bool(re.search(r'\.(pdf|png|jpg|jpeg)(?:[?#]|$)',target,re.I))
                official = 'tci-thailand.org' in (urlparse(target).hostname or '')
                # Cross-journal navigation is not evidence for this journal.
                if public_source(target) and (same or asset or official or valid_medal_url(target,slug)):
                    queue.append((score,target,source,link['text']))
                else:
                    result['pending_links'].append(dict(url=target,discovered_from=source,reason='review external publisher/source in browser'))
        except Exception as e:
            result['errors'].append(dict(url=source,error=str(e)))
    result['pending_links'] += [dict(url=u,discovered_from=p,reason='crawl limit; continue review') for _,u,p,_ in queue if u not in seen]
    for u in requested-discovered:
        if u not in seen: result['errors'].append(dict(url=u,error='extra evidence URL was not observed in visited pages'))
    result['coverage_limited'] = bool(result['pending_links'] or result['errors'])
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--url',action='append',required=True)
    p.add_argument('--output',required=True,type=Path)
    p.add_argument('--badge-dir',type=Path,help='legacy alias for evidence directory')
    p.add_argument('--evidence-dir',type=Path)
    p.add_argument('--evidence-url',action='append',default=[],help='prioritize an actual observed link (single journal only)')
    p.add_argument('--max-pages',type=int,default=8,help='bounded requests per journal; includes assets')
    p.add_argument('--delay',type=float,default=0.3)
    a = p.parse_args()
    if not 1<=a.max_pages<=40 or a.delay<0: p.error('max-pages must be 1..40; delay nonnegative')
    if a.evidence_url and len(a.url)!=1: p.error('--evidence-url requires one journal')
    results,errors,seen = [],[],set()
    for url in a.url:
        try:
            key,_ = journal_identity(url)
            if key.lower() in seen: continue
            seen.add(key.lower())
            results.append(inspect(url,a.evidence_dir or a.badge_dir or a.output.parent/'tier-evidence',a.max_pages,a.delay,a.evidence_url))
        except Exception as e: errors.append(dict(url=url,error=str(e)))
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(dict(schema_version=2,journals=results,errors=errors),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(journals=len(results),documents=sum(len(x['documents']) for x in results),
                         candidates=sum(len(x['candidates']) for x in results),
                         errors=len(errors)+sum(len(x['errors']) for x in results),
                         coverage_limited=sum(x['coverage_limited'] for x in results),output=str(a.output))))
    return 1 if errors or any(x['errors'] for x in results) else 0

if __name__=='__main__': sys.exit(main())
