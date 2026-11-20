"""Synthetic-only Python caller-object boundary tests for PR #89 exact head.

Does not represent a network JSON payload or production ingestion.
"""
import unittest
from src.security.input_controls import UnsafeJSONError, parse_untrusted_json

class ForgedClassAdmissionTests(unittest.TestCase):
    def test_nonbytes_forging_bytes_class_is_denied_without_calling_methods(self):
        touched = []
        class ForgedBytes:
            @property
            def __class__(self):
                touched.append('class')
                return bytes
            def __len__(self):
                touched.append('len')
                return 1
            def decode(self, *args, **kwargs):
                touched.append('decode')
                return '{"synthetic":true}'
        with self.assertRaises(UnsafeJSONError):
            parse_untrusted_json(ForgedBytes())
        self.assertEqual(touched, [])

    def test_nonstr_forging_str_class_is_denied_without_calling_methods(self):
        touched = []
        class ForgedStr:
            @property
            def __class__(self):
                touched.append('class')
                return str
            def encode(self, *args, **kwargs):
                touched.append('encode')
                return b'{"synthetic":true}'
        with self.assertRaises(UnsafeJSONError):
            parse_untrusted_json(ForgedStr())
        self.assertEqual(touched, [])

    def test_real_builtin_types_remain_accepted(self):
        self.assertEqual(parse_untrusted_json(b'{"synthetic":true}'), {'synthetic': True})
        self.assertEqual(parse_untrusted_json('{"synthetic":true}'), {'synthetic': True})

if __name__ == '__main__':
    unittest.main()
