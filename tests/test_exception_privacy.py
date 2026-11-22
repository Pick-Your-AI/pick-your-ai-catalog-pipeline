"""Synthetic-only regression tests for untrusted JSON exception chaining."""
import unittest

from src.security.input_controls import UnsafeJSONError, parse_untrusted_json, _decimal


class ErrorPrivacyTests(unittest.TestCase):
    def assert_sanitized(self, payload):
        with self.assertRaises(UnsafeJSONError) as ctx:
            parse_untrusted_json(payload)
        exc = ctx.exception
        self.assertIsNone(exc.__cause__, "must not expose raw parser failure as cause")
        self.assertIsNone(exc.__context__, "must not expose raw parser failure as context")
        self.assertTrue(str(exc))
        self.assertNotIn("PRIVATE_SENTINEL_3749", str(exc))

    def test_json_syntax_error_does_not_retain_input(self):
        self.assert_sanitized('{"secret":"PRIVATE_SENTINEL_3749", "broken": }')

    def test_bad_utf8_does_not_retain_input(self):
        self.assert_sanitized(b'{"secret":"PRIVATE_SENTINEL_3749"}\xff')

    def test_invalid_python_unicode_does_not_retain_input(self):
        self.assert_sanitized('"PRIVATE_SENTINEL_3749\ud800"')

    def test_escaped_unicode_scalar_does_not_retain_input(self):
        self.assert_sanitized('"PRIVATE_SENTINEL_3749\\ud800"')

    def test_duplicate_field_and_nonfinite_are_still_rejected(self):
        for payload in ('{"x":1,"x":2}', '[NaN]', '[Infinity]', '[0,1,2] trailing'):
            with self.subTest(payload=payload):
                self.assert_sanitized(payload)

    def test_decimal_internal_error_has_no_exception_chain(self):
        with self.assertRaises(UnsafeJSONError) as ctx:
            _decimal('PRIVATE_SENTINEL_3749')
        self.assertIsNone(ctx.exception.__cause__)
        self.assertIsNone(ctx.exception.__context__)

    def test_exact_decimal_unmodified(self):
        self.assertEqual(str(parse_untrusted_json('{"value":1.200}')["value"]), '1.200')
        self.assertEqual(parse_untrusted_json('null'), None)


if __name__ == '__main__':
    unittest.main()
