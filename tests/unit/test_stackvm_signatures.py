import unittest
from pocketcode.core.stackvm_analysis import analyze_stackvm_ast

class TestStackVmSignatures(unittest.TestCase):
    def test_signature_mismatch_inputs(self):
        # Body needs 2 items but signature says 1
        source = '[ + ] ( int -- int ) "add-one" define'
        analysis = analyze_stackvm_ast(parse_source(source))
        diagnostics = analysis.get("diagnostics", [])
        mismatches = [d for d in diagnostics if d["code"] == "signature-mismatch"]
        self.assertTrue(any("inputs but body requires 2" in d["message"] for d in mismatches))

    def test_signature_mismatch_outputs(self):
        # Body leaves 1 item but signature says 2
        source = '[ 1 ] ( -- int int ) "two-ones" define'
        analysis = analyze_stackvm_ast(parse_source(source))
        diagnostics = analysis.get("diagnostics", [])
        mismatches = [d for d in diagnostics if d["code"] == "signature-mismatch"]
        self.assertTrue(any("outputs but body leaves 1" in d["message"] for d in mismatches))

    def test_schema_dict_get_valid(self):
        # schema-apply should allow getting 'value' then a valid field from the schema
        source = '''
        "{ \\"name\\": \\"foo\\" }" yaml>
        "{ \\"type\\": \\"object\\", \\"properties\\": { \\"name\\": { \\"type\\": \\"string\\" } } }" yaml>
        schema-apply
        "value" dict-get
        "name" dict-get
        '''
        analysis = analyze_stackvm_ast(parse_source(source))
        diagnostics = analysis.get("diagnostics", [])
        field_errors = [d for d in diagnostics if d["code"] == "unknown-dict-key"]
        self.assertEqual(len(field_errors), 0)

    def test_schema_dict_get_invalid(self):
        # schema-apply should warn if we get a missing field from the validated dict
        source = '''
        "{ \\"name\\": \\"foo\\" }" yaml>
        "{ \\"type\\": \\"object\\", \\"properties\\": { \\"name\\": { \\"type\\": \\"string\\" } } }" yaml>
        schema-apply
        "value" dict-get
        "age" dict-get
        '''
        analysis = analyze_stackvm_ast(parse_source(source))
        diagnostics = analysis.get("diagnostics", [])
        field_errors = [d for d in diagnostics if d["code"] == "unknown-dict-key"]
        self.assertTrue(any("'age' is not statically known" in d["message"] for d in field_errors))

def parse_source(source):
    from pocketcode.core.stackvm_parser import parse_stackvm_source
    return parse_stackvm_source(source)

if __name__ == "__main__":
    unittest.main()
