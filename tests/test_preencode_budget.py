"""Synthetic offline regression: enforce budget before UTF-8 allocation."""
import tracemalloc
import unittest
from src.security.input_controls import parse_untrusted_json, UnsafeJSONError

class ByteBudgetMemoryTests(unittest.TestCase):
    def test_large_plain_string_rejects_before_encoding_allocation(self):
        # Construct before tracing so the metric isolates parser-owned copies.
        payload = ' ' * (8 * 1024 * 1024)
        tracemalloc.start()
        try:
            with self.assertRaisesRegex(UnsafeJSONError, 'Payload byte limit exceeded'):
                parse_untrusted_json(payload, max_bytes=16)
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        self.assertLess(peak, 2 * 1024 * 1024,
                        f'parser allocated {peak} bytes despite a 16-byte budget')

    def test_multibyte_utf8_still_enforces_encoded_limit(self):
        # Character count is a safe lower bound, not the final byte count.
        self.assertEqual(parse_untrusted_json('"é"', max_bytes=4), 'é')
        with self.assertRaisesRegex(UnsafeJSONError, 'Payload byte limit exceeded'):
            parse_untrusted_json('"é"', max_bytes=3)

if __name__ == '__main__': unittest.main()
