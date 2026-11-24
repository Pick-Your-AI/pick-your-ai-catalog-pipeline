"""Regression tests for caller-independent Decimal parsing."""
from decimal import Context, Decimal, Inexact, InvalidOperation, ROUND_DOWN, localcontext
import unittest

from src.security.input_controls import UnsafeJSONError, parse_untrusted_json


class DecimalContextTests(unittest.TestCase):
    def test_decimal_parsing_preserves_caller_context_and_flags(self):
        seed = Context(prec=1, rounding=ROUND_DOWN, Emin=-9, Emax=9, clamp=1)
        seed.traps[InvalidOperation] = False
        seed.flags[Inexact] = True

        with localcontext(seed) as caller:
            traps_before = caller.traps.copy()
            flags_before = caller.flags.copy()
            settings_before = (caller.prec, caller.rounding, caller.Emin, caller.Emax, caller.clamp)

            for token in ("1.00000000000000000001", "1e308", "1e-308"):
                with self.subTest(exact_token=token):
                    flags_before = caller.flags.copy()
                    self.assertEqual(parse_untrusted_json(token), Decimal(token))
                    self.assertEqual(caller.flags, flags_before)

            for payload in (
                b'{"n":1e99999999999999999999}',
                '{"n":1e99999999999999999999}',
            ):
                with self.subTest(payload_type=type(payload).__name__):
                    with self.assertRaises(UnsafeJSONError) as caught:
                        parse_untrusted_json(payload)
                    self.assertEqual(str(caught.exception), "Invalid decimal number")
                    self.assertIsNone(caught.exception.__cause__)
                    self.assertIsNone(caught.exception.__context__)

            self.assertEqual(caller.traps, traps_before)
            self.assertEqual(caller.flags, flags_before)
            self.assertEqual(
                (caller.prec, caller.rounding, caller.Emin, caller.Emax, caller.clamp),
                settings_before,
            )

    def test_all_untrapped_context_does_not_leak_decimal_flags(self):
        rejected_tokens = (
            "1e" + "9" * 26,
            "1e-" + "9" * 26,
            "1e309",
            "1e-309",
            "1." + "9" * 64,
        )
        accepted_tokens = (
            "1e308",
            "1e-308",
            "1.00000000000000000001",
            "-0.0",
            "1." + "9" * 63,
        )
        for trap in (True, False):
            with self.subTest(invalid_operation_trap=trap), localcontext() as caller:
                caller.traps[InvalidOperation] = trap
                for token in rejected_tokens:
                    with self.subTest(token=token):
                        flags_before = caller.flags.copy()
                        with self.assertRaises(UnsafeJSONError):
                            parse_untrusted_json(token)
                        self.assertEqual(caller.flags, flags_before)

                caller.prec = 2
                for token in accepted_tokens:
                    with self.subTest(token=token):
                        flags_before = caller.flags.copy()
                        value = parse_untrusted_json(token)
                        self.assertIs(type(value), Decimal)
                        self.assertEqual(value.as_tuple(), Decimal(token).as_tuple())
                        self.assertEqual(caller.flags, flags_before)


if __name__ == "__main__":
    unittest.main()
