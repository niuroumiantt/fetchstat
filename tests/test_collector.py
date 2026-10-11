import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from collector import allowed, collect
from helpers import candidate, html
from validate_handoff import validate

class Acceptance(unittest.TestCase):
    def setUp(self):
        self.source = json.loads(Path('sources.json').read_text())
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.native = self.root / 'input.html'
        self.native.write_bytes(b'<html><body>fixture 7.5</body></html>')
        self.row = candidate('company','SYNTHETIC',{},'fixture.value',7.5,'test_unit','synthetic only','reported','body','7.5','fixture 7.5')
    def run_one(self):
        with patch('adapter.extract', return_value=[copy.deepcopy(self.row)]):
            return collect(self.source,self.root/'data',self.native,'synthetic catalog fixture','a'*40)
    def test_replay_keeps_bytes_and_first_clock(self):
        first = self.run_one(); p=Path(first['package']); before=(p/'manifest.json').read_bytes()
        again = self.run_one()
        self.assertTrue(again['replayed']);self.assertEqual(before,(p/'manifest.json').read_bytes())
        row=json.loads((p/'observations.jsonl').read_text());self.assertEqual(row['target_ids'],[])
        self.assertIsNone(json.loads(before)['items'][0]['retrieved_at'])
    def test_changed_bytes_preserve_old_original(self):
        a=self.run_one();self.native.write_bytes(b'<html><body>fixture 8.5</body></html>');b=self.run_one()
        self.assertNotEqual(a['delivery_id'],b['delivery_id']);self.assertTrue(Path(a['package']).exists())
    def test_tampering_is_rejected(self):
        r=self.run_one();p=Path(r['package']);m=json.loads((p/'manifest.json').read_text())
        (p/m['items'][0]['path']).write_bytes(b'wrong');self.assertFalse(validate(p)['offline_valid'])
    def test_unresolved_is_not_a_fake_match(self):
        r=self.run_one();p=Path(r['package']);row=json.loads((p/'observations.jsonl').read_text())
        row['object']['canonical_id']='fake';(p/'observations.jsonl').write_text(json.dumps(row)+'\n')
        self.assertFalse(validate(p)['offline_valid'])
    def test_html_skips_script_as_evidence(self):
        self.assertEqual(html(b'<html><script>fake</script><p>real</p></html>').text,'real')
    def test_source_host_boundary(self):
        with self.assertRaises(ValueError):allowed('https://evil.invalid/a',self.source['hosts'])
        with self.assertRaises(ValueError):allowed('https://user:secret@'+self.source['hosts'][0],self.source['hosts'])
    def test_import_needs_provenance(self):
        with self.assertRaises(ValueError):collect(self.source,self.root/'data',self.native,revision='a'*40)
    def test_archive_reuse_does_not_invent_observation_time(self):
        with patch('adapter.extract',return_value=[copy.deepcopy(self.row)]) as extract:
            collect(self.source,self.root/'data',self.native,'fixture','a'*40)
            self.assertIsNone(extract.call_args.args[3])
    def test_no_extraction_does_not_fabricate_package(self):
        with patch('adapter.extract',return_value=[]),self.assertRaises(ValueError):
            collect(self.source,self.root/'data',self.native,'fixture','a'*40)
        self.assertFalse((self.root/'data/deliveries').exists())

if __name__=='__main__':unittest.main()
