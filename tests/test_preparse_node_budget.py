"""Synthetic offline regression: reject excessive nodes before JSON materialization."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tracemalloc
import unittest
from unittest.mock import patch

from src.security.input_controls import UnsafeJSONError, parse_untrusted_json

ROOT = Path(__file__).resolve().parents[1]


class PreparseNodeBudgetTests(unittest.TestCase):
    def test_large_array_rejected_without_calling_json_decoder(self):
        payload = b"[" + b"0," * 24_999 + b"0]"
        with patch("src.security.input_controls.json.loads",
                   side_effect=AssertionError("decoder called before node rejection")):
            with self.assertRaisesRegex(UnsafeJSONError, "JSON node limit exceeded"):
                parse_untrusted_json(payload, max_nodes=10)

    def test_large_object_rejected_without_calling_json_decoder(self):
        payload = "{" + ",".join(f'"k{i}":0' for i in range(100)) + "}"
        with patch("src.security.input_controls.json.loads",
                   side_effect=AssertionError("decoder called before node rejection")):
            with self.assertRaisesRegex(UnsafeJSONError, "JSON node limit exceeded"):
                parse_untrusted_json(payload, max_nodes=20)

    def test_exact_node_budget_for_nested_values_and_empty_containers(self):
        samples = (
            ("[]", 1), ("{}", 1), ("[[],{}]", 3),
            ('{"x":{"y":[1,2,{"z":3}]}}', 7),
            (r'["commas,:{}[]","a\"b",null]', 4),
            ('{"a":[true,false],"b":{}}', 5),
        )
        for payload, budget in samples:
            with self.subTest(payload=payload):
                parse_untrusted_json(payload, max_nodes=budget)
                if budget > 1:
                    with self.assertRaisesRegex(UnsafeJSONError, "JSON node limit exceeded"):
                        parse_untrusted_json(payload, max_nodes=budget - 1)

    def test_escaped_punctuation_is_never_counted_as_structure(self):
        self.assertEqual(
            parse_untrusted_json(r'["[,]{}:,,","\\","\""]', max_nodes=4),
            ["[,]{}:,,", "\\", '"'],
        )

    def test_existing_malformed_input_error_is_preserved(self):
        with self.assertRaisesRegex(UnsafeJSONError, "Malformed UTF-8 or JSON input"):
            parse_untrusted_json('[1,2,]')


    def test_excessive_depth_rejected_before_decoder_and_stack_growth(self):
        # 20k synthetic array levels fit the byte and node budgets but violate
        # the configured depth limit. Reject before creating a large stack.
        was_tracing = tracemalloc.is_tracing()
        env = dict(os.environ)
        env.pop("PYTHONTRACEMALLOC", None)
        command = [sys.executable, "-c", "\n".join((
            "import json, tracemalloc",
            "from unittest.mock import patch",
            "from src.security.input_controls import UnsafeJSONError, parse_untrusted_json",
            "payload = '[' * 20_000 + '0' + ']' * 20_000",
            "tracemalloc.start()",
            "try:",
            "    with patch('src.security.input_controls.json.loads', side_effect=AssertionError('decoder called before depth rejection')):",
            "        try:",
            "            parse_untrusted_json(payload, max_depth=32, max_nodes=50_000)",
            "        except UnsafeJSONError as error:",
            "            assert str(error) == 'JSON nesting limit exceeded'",
            "        else:",
            "            raise AssertionError('overdeep JSON was accepted')",
            "    print(json.dumps(tracemalloc.get_traced_memory()[1]))",
            "finally:",
            "    tracemalloc.stop()",
        ))]
        result = subprocess.run(
            command, cwd=ROOT, env=env, capture_output=True, text=True, timeout=30
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(tracemalloc.is_tracing(), was_tracing)
        peak = json.loads(result.stdout)
        self.assertLess(peak, 512 * 1024,
                        f"preflight allocated {peak} bytes for overdeep JSON")

    def test_container_depth_limit_does_not_reject_valid_boundary(self):
        self.assertEqual(parse_untrusted_json("[{}]", max_depth=2), [{}])
        with self.assertRaisesRegex(UnsafeJSONError, "JSON nesting limit exceeded"):
            parse_untrusted_json("[{}]", max_depth=1)


if __name__ == "__main__":
    unittest.main()
