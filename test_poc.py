import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from poc import Extraction, load_reference, validate_and_link, process, export, ollama_extract, read_jsonl, ROOT


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _, cls.index, _ = load_reference(ROOT / "references.json")

    def extract(self, text, polarity="unspecified"):
        return Extraction.model_validate({"entities":[{"text":text,"type":"pathology","assertion":{"polarity":polarity,"temporality":"unspecified","experiencer":"unspecified","context":"unspecified"},"modifiers":[]}],"needs_context":False})

    def test_exact_reference_match(self):
        entities, _ = validate_and_link("ASTHMA?", self.extract("ASTHMA"), self.index)
        self.assertEqual(entities[0]["reference_id"], "ICD10:J45")

    def test_unknown_mention_survives(self):
        entities, _ = validate_and_link("astma?", self.extract("astma"), self.index)
        self.assertEqual(entities[0]["match_status"], "unmapped")

    def test_hallucinated_evidence_rejected(self):
        entities, issues = validate_and_link("asthma", self.extract("diabetes"), self.index)
        self.assertEqual(entities, [])
        self.assertTrue(issues)

    def test_substring_is_not_evidence(self):
        self.assertEqual(validate_and_link("asthmatic", self.extract("asthma"), self.index)[0], [])

    def test_raw_unicode_offsets(self):
        text = "🙂 asthma"
        entities, _ = validate_and_link(text, self.extract("asthma"), self.index)
        self.assertEqual(text[entities[0]['start']:entities[0]['end']], 'asthma')
        self.assertEqual(entities[0]['start'], 2)

    def test_repeated_evidence_not_assigned_polarity_to_wrong_occurrence(self):
        entities, issues = validate_and_link("No asthma. History of asthma.", self.extract("asthma", "negated"), self.index)
        self.assertIsNone(entities[0]['start'])
        self.assertEqual(entities[0]['match_status'], 'not_attempted')
        self.assertTrue(issues)

    def test_competing_references_abstain(self):
        index = {('pathology','asthma'):{str(i):{'id':str(i)} for i in range(2)}}
        entities, _ = validate_and_link('asthma', self.extract('asthma'), index)
        self.assertEqual(entities[0]['match_status'], 'ambiguous')
        self.assertIsNone(entities[0]['reference_id'])

    def test_blank_input_never_calls_model(self):
        model = Mock()
        r = process({'chat_message_id':'1','country':'PT','prompt':''},1,self.index,model)
        self.assertEqual(r['status'],'invalid_input')
        model.assert_not_called()

    def test_one_call_and_negation_preserved(self):
        model = Mock(return_value=(self.extract('asthma','negated'),{}))
        r = process({'chat_message_id':'1','country':'PT','prompt':'No asthma.'},1,self.index,model)
        model.assert_called_once_with('No asthma.')
        self.assertEqual(r['entities'][0]['assertion']['polarity'],'negated')

    def test_failure_distinct_from_empty_extraction(self):
        model = Mock(side_effect=TimeoutError())
        r = process({'chat_message_id':'1','country':'PT','prompt':'asthma'},1,self.index,model)
        self.assertEqual(r['status'],'processing_error')

    def test_export_keeps_empty_records(self):
        with tempfile.TemporaryDirectory() as folder:
            r = process({'chat_message_id':'1','country':'PT','prompt':''},1,self.index,Mock())
            export([r], folder, {})
            self.assertIn('invalid_input', (Path(folder)/'review.csv').read_text())

    def test_http_contract(self):
        response = Mock()
        response.read.return_value = json.dumps({'message':{'content':'{"entities":[],"needs_context":false}'},'prompt_eval_count':5,'eval_count':3}).encode()
        context = Mock(__enter__=Mock(return_value=response), __exit__=Mock(return_value=False))
        opener = Mock()
        opener.open.return_value = context
        with patch('poc.urllib.request.build_opener',return_value=opener):
            result, usage = ollama_extract('sample','test','http://localhost:11434')
        opener.open.assert_called_once()
        self.assertEqual(usage['input_tokens'],5)
        self.assertEqual(result.entities,[])

    def test_jsonl_unicode_and_escaped_newline(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'input.jsonl'
            row = {'chat_message_id':123, 'country':'PT', 'prompt':'febre\nasthma 🙂'}
            path.write_text(json.dumps(row, ensure_ascii=False)+'\n', encoding='utf-8-sig')
            self.assertEqual(list(read_jsonl(path)), [(1, row)])

    def test_bad_lines_do_not_stop_following_records(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'input.jsonl'
            path.write_text('broken\n\n[]\nnull\n{"chat_message_id":1,"country":"GB","prompt":"asthma"}\n')
            model = Mock(return_value=(self.extract('asthma'),{}))
            results = [process(row,n,self.index,model) for n,row in read_jsonl(path)]
            self.assertEqual([r['row_id'] for r in results], [1,2,3,4,5])
            self.assertEqual([r['status'] for r in results], ['invalid_input']*4+['needs_review'])
            model.assert_called_once()

    def test_jsonl_duplicate_keys_and_nonstandard_numbers_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'input.jsonl'
            path.write_text('{"prompt":"a","prompt":"b"}\n{"prompt":NaN}\n')
            self.assertEqual(list(read_jsonl(path)), [(1,None),(2,None)])

    def test_numeric_id_supported_boolean_rejected(self):
        model = Mock(return_value=(self.extract('asthma'),{}))
        row = {'chat_message_id':123,'country':'GB','prompt':'asthma'}
        self.assertEqual(process(row,1,self.index,model)['chat_message_id'],123)
        row['chat_message_id'] = True
        self.assertEqual(process(row,2,self.index,model)['status'],'invalid_input')

    def test_missing_fields_invalid(self):
        model = Mock()
        self.assertEqual(process({'prompt':'asthma'},1,self.index,model)['status'],'invalid_input')
        model.assert_not_called()


if __name__ == '__main__':
    unittest.main()
