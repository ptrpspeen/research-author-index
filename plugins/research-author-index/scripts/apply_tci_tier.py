#!/usr/bin/env python3
"""Apply reviewed, captured Tier claims; separate historical and current status."""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import re
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlparse
from export_excel import check_date, validate_payload, validate_tier_source
from reconcile_records import title_key
from inspect_thaijo_journal import clean, journal_identity

TIERS = {'Tier 1','Tier 2','Tier 3'}


def journal_key(url):
    return journal_identity(url)[0].casefold()


def years_in(text):
    return {int(x)-543 if int(x)>=2400 else int(x) for x in re.findall(r'(?<!\d)(?:20|25)\d{2}(?!\d)',text)}


def proof(entry, claim):
    docs = {x['id']:x for x in entry['documents']}
    doc = docs.get(claim.get('document_id'))
    if not doc: raise ValueError('review must name a captured document_id')
    for path_field, hash_field in [('file','sha256'),('text_file','text_sha256')]:
        if hashlib.sha256(Path(doc[path_field]).read_bytes()).hexdigest()!=doc[hash_field]:
            raise ValueError('captured evidence changed: '+doc[path_field])
    quote = clean(claim.get('quote',''))
    if not quote: raise ValueError('review needs the exact evidence quote/transcription')
    txt = clean(Path(doc['text_file']).read_text(encoding='utf-8'))
    if claim.get('visual_reviewed') is True:
        if doc['kind'] not in {'image','pdf'}: raise ValueError('visual transcription requires an image/PDF')
    elif quote not in txt:
        raise ValueError('review quote is not in captured text; images/scanned PDFs require visual_reviewed')
    tier = claim.get('tier')
    if tier not in TIERS: raise ValueError('use Tier 1, Tier 2 or Tier 3')
    normalized = quote.translate(str.maketrans('๐๑๒๓๔๕๖๗๘๙','0123456789'))
    digit = tier[-1]
    if not re.search(r'(?:tier\s*|กลุ่ม\s*(?:ที่\s*)?)'+digit+r'(?!\d)',normalized,re.I):
        raise ValueError('Tier is not explicit in the reviewed quote')
    # Use the document itself when source validator accepts it. For linked public
    # assets use the captured journal page linking to it, retaining the document in audit.
    source = doc['url']
    by_url = {x['url']:x for x in entry['documents']}
    path_seen = set()
    while True:
        try:
            validate_tier_source(source,entry['journal_url']+'/article/view/evidence','Tier source')
            break
        except ValueError:
            if source in path_seen or source not in by_url: raise ValueError('no captured journal source binds this evidence')
            path_seen.add(source)
            source = by_url[source].get('discovered_from','')
    return doc,source,normalized


def reviewed_journals(info):
    if info.get('schema_version')!=2:
        raise ValueError('Tier evidence schema 2 required; recollect and review legacy badge-only journal-info')
    result = {}
    for entry in info.get('journals',[]):
        key = journal_key(entry['journal_url'])
        if key in result: raise ValueError('duplicate journal: '+key)
        if not entry.get('reviewed_evidence'): continue
        if entry.get('identity_verified') is not True: raise ValueError(key+': verify journal identity/title/ISSN first')
        checked = check_date(entry['checked_at'],'checked_at')
        if checked>date.today().isoformat(): raise ValueError('future evidence check date')
        titles = entry.get('journal_titles') or [entry.get('journal_title','')]
        if not titles or not all(isinstance(x,str) and x.strip() for x in titles): raise ValueError('verified journal title required')
        claims = []
        for c in entry['reviewed_evidence']:
            if c.get('reviewed') is not True: raise ValueError('each claim must be explicitly reviewed')
            doc,source,quote = proof(entry,c)
            scope = c.get('scope')
            start = end = None
            if scope in {'period','since'}:
                start = c.get('start_year')
                end = c.get('end_year') if scope=='period' else int(checked[:4])
                if type(start)!=int or type(end)!=int or not 1900<=start<=end<=2200:
                    raise ValueError('invalid CE evidence years')
                observed = years_in(quote)
                if start not in observed or (scope=='period' and end not in observed):
                    raise ValueError('year bounds are not in the reviewed evidence; never invent badge dates')
                if scope=='period' and not re.search(r'(?:20|25)\d{2}[^\n]{0,80}(?:–|—|ถึง|\bto\b|-)\s*[^\n]{0,80}(?:20|25)\d{2}',quote,re.I):
                    raise ValueError('period requires an explicit range, not unrelated years on the page')
                if scope=='since' and not re.search(r'\bsince\b|ตั้งแต่',quote,re.I):
                    raise ValueError('since scope requires an explicit continuous since statement')
                if scope=='since' and c.get('end_year') is not None:
                    raise ValueError('since statement has no certification expiry; omit end_year')
            elif scope=='current':
                if c.get('start_year') is not None or c.get('end_year') is not None:
                    raise ValueError('current-only evidence must not have historical bounds')
            else: raise ValueError('scope must be current, period or since')
            claims.append(dict(tier=c['tier'],scope=scope,start=start,end=end,source=source,
                               checked_at=checked,document_id=doc['id'],document_url=doc['url'],quote=clean(c['quote'])))
        for i,a in enumerate(claims):
            for b in claims[i+1:]:
                a_range=(int(checked[:4]),int(checked[:4])) if a['scope']=='current' else (a['start'],a['end'])
                b_range=(int(checked[:4]),int(checked[:4])) if b['scope']=='current' else (b['start'],b['end'])
                if a['tier']!=b['tier'] and max(a_range[0],b_range[0])<=min(a_range[1],b_range[1]):
                    raise ValueError(key+': conflicting Tier claims; resolve source/period before applying')
        result[key] = dict(titles=titles,claims=claims)
    return result


def apply(payload,journal_info):
    validate_payload(payload)
    payload = copy.deepcopy(payload)
    reviewed = reviewed_journals(journal_info)
    updated = current = outside = unmatched = 0
    used = {}
    for row in payload['tci']:
        key = journal_key(row['article_url'])
        entry = reviewed.get(key)
        if not entry:
            unmatched += 1
            continue
        if title_key(row['journal']) not in {title_key(x) for x in entry['titles']}:
            raise ValueError(row['article_url']+': journal title does not match reviewed identity')
        claims = entry['claims']
        used[key] = claims
        current_claims = [x for x in claims if x['scope']=='current' or x['start']<=int(x['checked_at'][:4])<=x['end']]
        if current_claims:
            c = sorted(current_claims,key=lambda x:({'period':0,'current':1,'since':2}[x['scope']],x['source']))[0]
            old_date = row.get('current_tier_checked_at','')
            if old_date>c['checked_at']: raise ValueError('cannot replace a newer current Tier observation')
            if old_date==c['checked_at'] and row.get('current_tier') and row['current_tier']!=c['tier']:
                raise ValueError('conflicting current Tier on same observation date')
            row.update(current_tier=c['tier'],current_tier_checked_at=c['checked_at'],current_tier_source_url=c['source'])
            current += 1
        matches = [x for x in claims if x['scope']!='current' and x['start']<=row['publication_year']<=x['end']]
        if not matches:
            outside += 1
            continue
        c = sorted(matches,key=lambda x:(x['scope']!='period',x['end']-x['start'],x['source']))[0]
        if row.get('tier') and row['tier']!=c['tier']:
            raise ValueError(row['article_url']+': historical Tier conflicts with existing value')
        period = f"{c['start']} – {c['end']}"
        basis = 'explicit_period'
        if c['scope']=='since':
            basis = 'publisher_since'
            period += f" (publisher states since; observed {c['checked_at']}; no certified expiry)"
        row.update(tier=c['tier'],tier_period=period,tier_source_url=c['source'],tier_evidence_basis=basis)
        updated += 1
    summary = dict(updated=updated,current_updated=current,outside_period=outside,unmatched_or_unreviewed=unmatched,
                   collection_errors=len(journal_info.get('errors',[]))+sum(len(x.get('errors',[])) for x in journal_info.get('journals',[])),
                   pending_links=sum(len(x.get('pending_links',[])) for x in journal_info.get('journals',[])))
    payload.setdefault('audit',{})['tier_evidence'] = dict(schema_version=2,journals=used,summary=summary)
    validate_payload(payload)
    return payload,summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',required=True,type=Path)
    p.add_argument('--journal-info',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path)
    a = p.parse_args()
    if a.output.resolve()==a.input.resolve(): p.error('output must differ from input')
    try:
        data,summary = apply(json.loads(a.input.read_text(encoding='utf-8')),json.loads(a.journal_info.read_text(encoding='utf-8')))
        a.output.parent.mkdir(parents=True,exist_ok=True)
        a.output.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(summary,ensure_ascii=False))
        return 0
    except (ValueError,KeyError,TypeError,OSError) as e:
        print('Error: '+str(e),file=sys.stderr)
        return 1
if __name__=='__main__': sys.exit(main())
