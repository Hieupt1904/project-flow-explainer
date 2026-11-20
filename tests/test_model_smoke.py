"""Guards for scripts/run_model_smoke.py: what may count as evidence.

These tests pin the two ways the harness lied about itself before 0.7.4:

1. It scored a session it did not boot. Matching the marker in any text line,
   or reading "--profile" out of the first line that contains it, selected the
   agent's own transcript and reported its content as the model's context.
2. It read "no failure" as "verified". Zero tool calls produced an empty error
   list, an empty missing list and a trivially ordered sequence, so a session
   with no observation passed every check.

Run: python -m unittest tests.test_model_smoke -v
"""
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import run_model_smoke as smoke  # noqa: E402

MARKER = "PFE-SMOKE-0123456789abcdef"


def event(kind, data):
    return json.dumps({"type": kind, "seq": 1, "data": data}, ensure_ascii=False)


def user_message(text):
    return event("user/message", {"content": [{"type": "text", "text": text}]})


def tool_call(call_id, name):
    return event("tool/call", {"turn": 1, "step": 1, "callId": call_id, "name": name,
                              "arguments": "{}"})


def tool_result(call_id, text, is_error=False):
    return event("tool/result", {"turn": 1, "step": 1, "message": {
        "role": "tool", "toolCallId": call_id, "isError": is_error,
        "content": [{"type": "text", "text": text}],
    }})


GOOD_CONTEXT = ('Entry point: server.js:7 · route: /api/reports/:id\n'
                '"entry_points": ["server.js"]\nservices/report_service.js:1 report_service\n'
                'related_routes: /api/legacy/preview\ntests/report_service.test.js:1\n'
                'downstream_modules: services/report_service.js')


class MarkerTests(unittest.TestCase):
    def test_prompt_event_identifies_the_session(self):
        log = "\n".join([event("turn/start", {"turn": 1}), user_message("x " + MARKER)])
        self.assertTrue(smoke._marker_in_user_message(log, MARKER))

    def test_agent_echo_is_not_the_session(self):
        # The agent's own turn contains the marker because it quoted a record.
        log = "\n".join([
            event("tool/call", {"name": "bash", "callId": "c1",
                                "arguments": '{"command": "grep ' + MARKER + '"}'}),
            tool_result("c1", "found " + MARKER),
        ])
        self.assertFalse(smoke._marker_in_user_message(log, MARKER))

    def test_other_marker_does_not_match(self):
        self.assertFalse(smoke._marker_in_user_message(user_message(MARKER), "PFE-SMOKE-ffffffffffffffff"))

    def test_marker_is_stripped_from_answer(self):
        self.assertNotIn(MARKER, smoke.strip_marker("done " + MARKER, MARKER))


class ProfileIdentityTests(unittest.TestCase):
    def test_named_profile_is_read(self):
        log = event("request/header", {"header": {"profile": "pfe-model", "config": {}}})
        self.assertEqual(smoke._loader_profile_from_session(log),
                         ("pfe-model", "session_metadata"))

    def test_profile_path_is_reduced_to_its_name(self):
        log = event("session", {"profileDir": "/home/u/.dsh/profiles/pfe-model"})
        self.assertEqual(smoke._loader_profile_from_session(log),
                         ("pfe-model", "session_metadata"))

    def test_unnamed_boot_is_ambiguous_not_guessed(self):
        # `session: {}` is what a real pfe-model boot writes.
        log = "\n".join([event("session", {}),
                         event("request/header", {"header": {"config": {"model": "m"}}})])
        self.assertEqual(smoke._loader_profile_from_session(log),
                         ("ambiguous", "not_recorded"))

    def test_argv_in_transcript_is_not_identity(self):
        log = event("tool/call", {"name": "bash", "callId": "c1",
                                  "arguments": '{"command": "dsh --profile pfe-test"}'})
        self.assertEqual(smoke._loader_profile_from_session(log),
                         ("ambiguous", "not_recorded"))

    def test_tool_surface_is_named_as_the_evidence(self):
        # DSH writes `session: {}` and no profile field, so the observable fact is
        # the tool list: if project_* tools are in the header, the plugin loaded.
        log = event("request/header", {"header": {"config": {}, "tools": [
            {"name": "bash"}, {"name": "project_context_pack"}]}})
        self.assertEqual(smoke._loader_profile_from_session(log),
                         ("ambiguous", "tool_surface_in_request_header"))


class ContextAccuracyTests(unittest.TestCase):
    def test_good_context_passes(self):
        log = tool_result("c1", GOOD_CONTEXT)
        accuracy = smoke.check_context_accuracy(log)
        self.assertEqual(accuracy["expected_paths_missing"], [])
        self.assertFalse(accuracy["decoy_presented_as_direct"])
        self.assertTrue(accuracy["impact_has_downstream_and_test"])

    def test_decoy_as_entry_point_fails(self):
        text = ('Entry point: 0 · route: /api/legacy/preview · file nên đọc: 7\n'
                'services/report_service.js:1 report_service\nserver.js:7 routes\n'
                'tests/report_service.test.js:1 downstream_modules')
        accuracy = smoke.check_context_accuracy(tool_result("c1", text))
        self.assertTrue(accuracy["decoy_presented_as_direct"])

    def test_empty_results_prove_nothing(self):
        accuracy = smoke.check_context_accuracy("")
        self.assertEqual(sorted(accuracy["expected_paths_missing"]),
                         sorted(smoke.EXPECTED_CONTEXT_PATHS))
        self.assertFalse(accuracy["impact_has_downstream_and_test"])

    def test_result_without_content_details_is_not_an_error(self):
        log = tool_result("c1", GOOD_CONTEXT)
        self.assertEqual(smoke.tool_outcomes(log), {"c1": "ok"})


class OrderTests(unittest.TestCase):
    def test_documented_order_passes(self):
        sequence = [{"tool": name} for name in smoke.EXPECTED_ORDER]
        order = smoke.check_order(sequence)
        self.assertEqual(order["missing"], [])
        self.assertTrue(order["ordered"])

    def test_reversed_order_fails(self):
        sequence = [{"tool": name} for name in reversed(smoke.EXPECTED_ORDER)]
        self.assertFalse(smoke.check_order(sequence)["ordered"])

    def test_empty_sequence_is_missing_everything(self):
        order = smoke.check_order([])
        self.assertEqual(order["missing"], smoke.EXPECTED_ORDER)


class VerdictTests(unittest.TestCase):
    """A pass needs positive evidence: a ran tool, a visible surface, a profile."""

    def run_session(self, log_text, surface):
        record = {"tarball_sha256": "0" * 64, "package_version": "0.7.4",
                  "wall_seconds": 1.0}
        written = {}

        def fake_write(rec):
            written["record"] = json.loads(json.dumps(rec))
            return Path("record.json")

        context = mock.patch.multiple(
            smoke,
            find_session=mock.Mock(return_value=(Path("session.v4.jsonl.zstd"), log_text)),
            probe_surface=mock.Mock(return_value=surface),
            _write_record=mock.Mock(side_effect=fake_write),
            run=mock.Mock(return_value={"exit_code": 0, "stdout": MARKER, "stderr": ""}),
            installed_version=mock.Mock(return_value="0.7.4"),
        )
        with context:
            code = smoke._run_session(record, "/tmp/repo", "0.7.4", Path("t.tar.gz"))
        return code, written["record"]

    def log_with(self, tools=True, profile=True):
        lines = [user_message("task " + MARKER)]
        if profile:
            lines.append(event("request/header", {"header": {"profile": "pfe-model"}}))
        if tools:
            for index, name in enumerate(smoke.EXPECTED_ORDER):
                lines += [tool_call("c" + str(index), name), tool_result("c" + str(index), GOOD_CONTEXT)]
        return "\n".join(lines)

    def test_full_observation_verifies(self):
        code, record = self.run_session(self.log_with(), {"has_pfe": True, "tool_count": 36})
        self.assertEqual(record["status"], "verified")
        self.assertEqual(code, 0)
        self.assertEqual(record["blocked"] if "blocked" in record else "", "")

    def test_zero_tool_calls_never_verifies(self):
        # The exact shape of the mis-scored record: no calls, no errors, and a
        # context blob that happened to contain the expected paths.
        code, record = self.run_session(self.log_with(tools=False), {"has_pfe": True})
        self.assertEqual(record["status"], "partial")
        self.assertNotEqual(code, 0)
        self.assertIn("không có tool/call", record["blocked"])

    def test_invisible_surface_blocks(self):
        code, record = self.run_session(self.log_with(), {"has_pfe": False, "tool_count": 24})
        self.assertEqual(record["status"], "partial")
        self.assertIn("HAS_PFE=False", record["blocked"])

    def test_unknown_profile_blocks(self):
        code, record = self.run_session(self.log_with(profile=False),
                                        {"has_pfe": True, "tool_count": 36})
        self.assertEqual(record["status"], "partial")
        self.assertIn("không chứng minh được boot", record["blocked"])


class RecordFolderTests(unittest.TestCase):
    def test_unverified_record_goes_to_attempts(self):
        with mock.patch.object(smoke, "REVIEW", Path("/tmp/rev-x")), \
                mock.patch.object(smoke, "ATTEMPTS", Path("/tmp/rev-x/attempts")):
            with mock.patch.object(Path, "write_text", mock.Mock(return_value=1)), \
                    mock.patch.object(Path, "mkdir", mock.Mock(return_value=None)):
                partial = smoke._write_record({"status": "partial"})
                self.assertEqual(partial.parent.name, "attempts")
                verified = smoke._write_record({"status": "verified"})
                self.assertEqual(verified.parent.name, "rev-x")


if __name__ == "__main__":
    unittest.main()
