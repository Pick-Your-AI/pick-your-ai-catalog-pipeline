"""Synthetic regression: exact-type admission before any input-defined hooks."""
import unittest

from src.security.input_controls import DEFAULT_MAX_BYTES, UnsafeJSONError, parse_untrusted_json


class LyingBytes(bytes):
    def __len__(self):
        return 1


class ReplacingText(str):
    def encode(self, *args, **kwargs):
        return b'null'


class InputSubclassBoundaryTests(unittest.TestCase):
    def test_bytes_subclass_cannot_bypass_byte_limit(self):
        oversized = LyingBytes(b' ' * (DEFAULT_MAX_BYTES + 1) + b'null')
        with self.assertRaises(UnsafeJSONError):
            parse_untrusted_json(oversized)

    def test_str_subclass_cannot_replace_input_with_encode_hook(self):
        with self.assertRaises(UnsafeJSONError):
            parse_untrusted_json(ReplacingText('not JSON'))


if __name__ == '__main__':
    unittest.main()
