import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from parking import SourceError, parse_xml
import storage

def xml(value=12, total=80):
    return f'<response><header><resultCode>00</resultCode></header><body><item><name>합성 주차장</name><lat>36.35</lat><lon>127.38</lon><address>합성 주소</address><tel>합성 연락처</tel><totalQty>{total}</totalQty><resQty>{value}</resQty></item><totalCount>1</totalCount></body></response>'

class CoreTests(unittest.TestCase):
    def test_normalized_and_private_field_omitted(self):
        items,count=parse_xml(xml());self.assertEqual(count,1)
        self.assertEqual(items[0]['available'],12)
        self.assertIsNone(items[0]['source_time'])
        self.assertNotIn('tel',items[0]['raw'])

    def test_zero_capacity_is_unknown(self):
        self.assertIsNone(parse_xml(xml(0,0))[0][0]['available'])

    def test_empty_capacity_is_unknown_but_removed_field_is_schema(self):
        item=parse_xml(xml(0,''))[0][0]
        self.assertIsNone(item['total'])
        self.assertIsNone(item['available'])
        with self.assertRaises(SourceError):
            parse_xml(xml().replace('<totalQty>80</totalQty>',''))

    def test_negative_availability_is_unknown_not_zero(self):
        item=parse_xml(xml(-5,31))[0][0]
        self.assertIsNone(item['available'])
        self.assertEqual(item['raw']['resQty'],'-5')
        self.assertTrue(item['quality_note'])

    def test_schema_and_upstream_codes(self):
        for payload,code in [(xml(99),'schema'),('<bad','schema'),('<r><resultCode>20</resultCode></r>','denied'),('<r><resultCode>22</resultCode></r>','rate_limit')]:
            with self.assertRaises(SourceError) as cm:parse_xml(payload)
            self.assertEqual(cm.exception.code,code)

    def test_same_day_upsert_and_next_day(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as temp, patch.dict(os.environ,{},clear=True), patch.object(storage,'__file__',str(Path(temp)/'storage.py')):
            item=parse_xml(xml())[0][0]
            snapshot=dict(items=[item],fetched_at='2030-01-01T23:59:00+09:00',day='2030-01-01',source_url='https://fixtures.aleph.invalid/test')
            storage.save(snapshot);item['available']=15;storage.save(snapshot);storage.save(snapshot)
            self.assertEqual(len(storage.history(item['id'])),1)
            snapshot['day']='2030-01-02';snapshot['fetched_at']='2030-01-02T00:01:00+09:00';storage.save(snapshot)
            records=storage.history(item['id']);self.assertEqual(len(records),2)
            self.assertEqual(records[0]['available'],15)
            self.assertEqual(storage.latest()['day'],'2030-01-02')

if __name__=='__main__':unittest.main()
