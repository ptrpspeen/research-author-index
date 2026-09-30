"""Regression tests for Tier discovery, evidence binding and temporal scope."""
import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from inspect_thaijo_journal import inspect, extract
from apply_tci_tier import apply
from export_excel import export, validate_payload, validate_tier_source
from incremental_update import load_excel, refresh_tci
from metric_cache import apply_cache, collect_cache
from test_regressions import payload, tci

HOME='https://so01.tci-thaijo.org/index.php/example'
ABOUT=HOME+'/about'

class TierEvidence(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def collected(self, text='Example Journal has TCI Tier 1 certification for 2025–2029.'):
        pages={HOME:(b'<title>Example Journal</title><a href="/index.php/example/about">About</a>','text/html'),
               ABOUT:(('<title>About | Example Journal</title><p>'+text+'</p>').encode(),'text/html')}
        with patch('inspect_thaijo_journal.get_bytes',side_effect=lambda u,*a:pages[u]):
            entry=inspect(HOME,self.root,8,0)
        entry['identity_verified']=True
        entry['reviewed_evidence']=[dict(document_id=entry['documents'][1]['id'],quote=text,tier='Tier 1',
            scope='period',start_year=2025,end_year=2029,reviewed=True)]
        return dict(schema_version=2,journals=[entry],errors=[])

    def test_discovers_about_from_observed_anchor(self):
        info=self.collected()
        self.assertEqual([d['url'] for d in info['journals'][0]['documents']],[HOME,ABOUT])
        self.assertEqual(len(info['journals'][0]['candidates']),1)
        report,summary=apply(payload(t=[tci()]),info)
        self.assertEqual(report['tci'][0]['tier'],'Tier 1')
        self.assertEqual(report['tci'][0]['current_tier'],'Tier 1')
        self.assertEqual(summary['updated'],1)

    def test_since_is_publisher_assertion_not_expiry(self):
        info=self.collected('Since January 1, 2015, Example Journal has been indexed in TCI (Tier 1).')
        c=info['journals'][0]['reviewed_evidence'][0]
        c.update(scope='since',start_year=2015)
        del c['end_year']
        report,_=apply(payload(t=[tci(publication_year=2018)]),info)
        row=report['tci'][0]
        self.assertEqual(row['tier_evidence_basis'],'publisher_since')
        self.assertIn('no certified expiry',row['tier_period'])
        self.assertIn('2015 – 2026',row['tier_period'])
        info['journals'][0]['reviewed_evidence'][0]['end_year']=2029
        with self.assertRaisesRegex(ValueError,'no certification expiry'): apply(payload(t=[tci()]),info)

    def test_undated_current_cannot_be_backfilled(self):
        info=self.collected('Example Journal อยู่ใน TCI กลุ่มที่ 2')
        c=info['journals'][0]['reviewed_evidence'][0]
        c.update(tier='Tier 2',scope='current')
        del c['start_year'],c['end_year']
        report,summary=apply(payload(t=[tci(publication_year=2017)]),info)
        self.assertEqual(report['tci'][0].get('tier',''),'')
        self.assertEqual(report['tci'][0]['current_tier'],'Tier 2')
        self.assertEqual(summary['outside_period'],1)
        c.update(scope='period',start_year=2025,end_year=2029)
        with self.assertRaisesRegex(ValueError,'year bounds'): apply(payload(t=[tci()]),info)

    def test_quote_tamper_missing_identity_wrong_title_and_raw_tamper_rejected(self):
        info=self.collected()
        for mutation in ('quote','identity','title','raw'):
            x=copy.deepcopy(info)
            e=x['journals'][0]
            if mutation=='quote': e['reviewed_evidence'][0]['quote']='Invented TCI Tier 1 2025–2029'
            if mutation=='identity': e['identity_verified']=False
            if mutation=='title': e['journal_title']='Other Journal'
            if mutation=='raw': Path(e['documents'][1]['file']).write_bytes(b'changed')
            with self.subTest(mutation=mutation),self.assertRaises(ValueError): apply(payload(t=[tci()]),x)

    def test_conflicting_overlapping_periods_rejected(self):
        text='TCI Tier 1: 2025–2029. TCI Tier 2: 2024–2028.'
        info=self.collected(text)
        first=info['journals'][0]['reviewed_evidence'][0]
        second=dict(first,tier='Tier 2',start_year=2024,end_year=2028)
        info['journals'][0]['reviewed_evidence'].append(second)
        with self.assertRaisesRegex(ValueError,'conflicting Tier'): apply(payload(t=[tci()]),info)

    def test_different_periods_and_buddhist_years(self):
        info=self.collected('TCI Tier 1: 2568–2572. TCI Tier 2: 2563–2567.')
        first=info['journals'][0]['reviewed_evidence'][0]
        info['journals'][0]['reviewed_evidence'].append(dict(first,tier='Tier 2',start_year=2020,end_year=2024))
        report,_=apply(payload(t=[tci(publication_year=2022)]),info)
        self.assertEqual(report['tci'][0]['tier'],'Tier 2')
        self.assertEqual(report['tci'][0]['current_tier'],'Tier 1')

    def test_missing_period_and_generic_legacy_rejected(self):
        with self.assertRaisesRegex(ValueError,'schema 2'): apply(payload(t=[tci()]),{'journals':[]})
        info=self.collected('Example Journal TCI Tier 1. Launched 2025. Copyright 2029.')
        with self.assertRaisesRegex(ValueError,'explicit range'): apply(payload(t=[tci()]),info)

    def test_partial_crawl_errors_do_not_block_verified_journal(self):
        info=self.collected()
        info['errors']=[dict(url='https://example.com',error='timeout')]
        report,summary=apply(payload(t=[tci()]),info)
        self.assertEqual(summary['collection_errors'],1)
        self.assertEqual(report['tci'][0]['tier'],'Tier 1')

    def test_bounds_and_no_guessed_pages(self):
        with patch('inspect_thaijo_journal.get_bytes',return_value=(b'<title>Journal</title><a href="/index.php/example/about">About</a>','text/html')) as get:
            result=inspect(HOME,self.root,1,0)
        self.assertEqual(get.call_count,1)
        self.assertTrue(result['coverage_limited'])
        self.assertEqual(result['pending_links'][0]['url'],ABOUT)
        self.assertFalse(result['reviewed_evidence'])

    def test_pdf_and_image_require_visual_review_when_text_unavailable(self):
        for raw,ct in [(b'%PDF-not-valid','application/pdf'),(b'\x89PNG\r\n','image/png')]:
            kind,text,status,_=extract(raw,ct)
            self.assertEqual(text,'')
            self.assertIn('needs_visual_review',status)

    def test_same_journal_url_and_external_binding(self):
        validate_tier_source(ABOUT,HOME+'/article/view/1','source')
        with self.assertRaises(ValueError): validate_tier_source(ABOUT.replace('example/about','other/about'),HOME+'/article/view/1','source')

    def test_excel_roundtrip_and_old_header(self):
        report,_=apply(payload(t=[tci()]),self.collected())
        out=self.root/'report.xlsx'
        export(validate_payload(report),out,allow_partial=True)
        restored=load_excel(out)
        self.assertEqual(restored['tci'][0]['current_tier'],'Tier 1')
        self.assertEqual(restored['tci'][0]['tier_evidence_basis'],'explicit_period')
        from openpyxl import load_workbook
        wb=load_workbook(out)
        for c in wb['TCI'][1]:
            if c.value=='Tier ในปีตีพิมพ์': c.value='Tier วารสาร'
        wb.save(out)
        self.assertEqual(load_excel(out)['tci'][0]['tier'],'Tier 1')

    def test_cache_keeps_since_basis_and_date(self):
        info=self.collected('Since 2015, Example Journal is TCI Tier 1.')
        c=info['journals'][0]['reviewed_evidence'][0]
        c.update(scope='since',start_year=2015)
        del c['end_year']
        report,_=apply(payload(t=[tci(publication_year=2018)]),info)
        cache=collect_cache(report)
        fresh=payload(t=[tci(publication_year=2019)])
        apply_cache(fresh,cache)
        self.assertEqual(fresh['tci'][0]['tier_evidence_basis'],'publisher_since')
        rows,_=refresh_tci(report['tci'],[tci(publication_year=2018)],False)
        self.assertEqual(rows[0]['current_tier_checked_at'],report['tci'][0]['current_tier_checked_at'])

    def test_overlapping_same_tier_cache_prefers_explicit_period(self):
        info=self.collected('Since 2015, Example Journal is TCI Tier 1.')
        c=info['journals'][0]['reviewed_evidence'][0]
        c.update(scope='since',start_year=2015)
        del c['end_year']
        report,_=apply(payload(t=[tci(publication_year=2018)]),info)
        cache=collect_cache(report)
        explicit=dict(cache['tci'][0],tier_period='2025 – 2029',tier_evidence_basis='explicit_period')
        cache['tci'].append(explicit)
        fresh,_=apply_cache(payload(t=[tci()]),cache)
        self.assertEqual(fresh['tci'][0]['tier_evidence_basis'],'explicit_period')
        explicit['tier']='Tier 2'
        with self.assertRaisesRegex(ValueError,'cache'): apply_cache(payload(t=[tci()]),cache)

    def test_linked_pdf_discovery_and_text_evidence(self):
        try:
            import pypdf
        except ImportError:
            self.skipTest('optional pypdf is unavailable')
        # Minimal real PDF with selectable text, without a PDF-generation dependency.
        quote='Example Journal TCI Tier 1 2025-2029'
        content=('BT /F1 12 Tf 50 750 Td ('+quote+') Tj ET').encode()
        objects=[b'<< /Type /Catalog /Pages 2 0 R >>',
                 b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
                 b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
                 b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
                 b'<< /Length '+str(len(content)).encode()+b' >>\nstream\n'+content+b'\nendstream']
        raw=b'%PDF-1.4\n';offsets=[]
        for i,obj in enumerate(objects,1):
            offsets.append(len(raw));raw+=str(i).encode()+b' 0 obj\n'+obj+b'\nendobj\n'
        offset=len(raw)
        raw+=b'xref\n0 6\n0000000000 65535 f \n'+b''.join(('%010d 00000 n \n'%n).encode() for n in offsets)
        raw+=b'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n'+str(offset).encode()+b'\n%%EOF\n'
        pdf='https://so01.tci-thaijo.org/public/site/certification.pdf'
        pages={HOME:(('<title>Example Journal</title><a href="'+pdf+'">TCI certification</a>').encode(),'text/html'),pdf:(raw,'application/pdf')}
        with patch('inspect_thaijo_journal.get_bytes',side_effect=lambda u,*a:pages[u]):
            entry=inspect(HOME,self.root,8,0)
        doc=entry['documents'][1]
        self.assertEqual(doc['kind'],'pdf')
        self.assertIn(quote,Path(doc['text_file']).read_text())
        entry.update(identity_verified=True,reviewed_evidence=[dict(document_id=doc['id'],quote=quote,tier='Tier 1',scope='period',start_year=2025,end_year=2029,reviewed=True)])
        report,_=apply(payload(t=[tci()]),dict(schema_version=2,journals=[entry]))
        self.assertEqual(report['tci'][0]['tier_source_url'],HOME)
        self.assertEqual(report['audit']['tier_evidence']['journals'][HOME][0]['document_url'],pdf)

if __name__=='__main__': unittest.main()
