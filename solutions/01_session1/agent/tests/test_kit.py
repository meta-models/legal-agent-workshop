"""Pre-built kit: document text, the case record, progress, and the tools. These pass from
the start and must keep passing."""

from __future__ import annotations

import json
import threading
import time
import unittest
from unittest import mock

from agent_kit import case_record, document_text, tools
from agent_kit.case_record import CaseError, CaseRecord
from agent_kit.progress import load_progress, new_run, resume, save_progress
from agent_kit.tools import check_signatures
from agent_kit.tools.analyze_document import analyze
from tests import support
from tests.fake_model import Refused


def call(name: str, args: dict | None = None, call_id: str = "c1") -> dict:
    return {
        "type": "function_call",
        "name": name,
        "arguments": json.dumps(args or {}),
        "call_id": call_id,
    }


class KitTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root, tmp = support.make_root()
        self.addCleanup(tmp.cleanup)
        self.fake = support.scripted(self.root, [])
        self.client = self.fake.client
        self.run_id = new_run(
            self.root, instructions="i", objective="o", verification=False
        )

    def read(self, ids: list, request: str = "status") -> dict:
        return analyze(self.client, self.root, ids, request)

    def case(self) -> CaseRecord:
        case = CaseRecord(self.root, self.run_id)
        case.set_checklist(support.CHECKLIST_ITEMS)
        return case

    def tool(self, name: str, args: dict | None = None, run_id: str = "") -> dict:
        return tools.run(
            self.client, self.root, run_id or self.run_id, call(name, args)
        )

    # ---- document text and reading --------------------------------------------------
    def test_inbox_lists_only_released_documents(self) -> None:
        ids = [d["id"] for d in document_text.list_documents(self.root)]
        self.assertEqual(sorted(support.INITIAL), sorted(ids))
        with self.assertRaises(document_text.DocumentError):
            document_text.get_document(self.root, "DOC-DRAFT")

    def test_text_is_extracted_once_and_reused(self) -> None:
        self.read(["DOC-REPORT"])
        self.read(["DOC-REPORT"], "a different request")
        extractions = [
            c
            for c in self.fake.calls
            if c[0] == "respond" and "Transcribe document" in json.dumps(c[1])
        ]
        self.assertEqual(1, len(extractions))
        self.assertEqual(1, len([c for c in self.fake.calls if c[0] == "upload"]))

    def test_reading_marks_quotes_verified_against_saved_text(self) -> None:
        record = self.read(["DOC-MINUTES"], "who said it was ready")["documents"][0][
            "evidence"
        ][0]
        self.assertTrue(record["verified"])

    def test_documents_are_read_in_parallel_in_order(self) -> None:
        state, lock, original = (
            {"now": 0, "max": 0},
            threading.Lock(),
            self.fake.responder,
        )

        def slow(kind, payload):
            with lock:
                state["now"] += 1
                state["max"] = max(state["max"], state["now"])
            time.sleep(0.1)
            try:
                return original(kind, payload)
            finally:
                with lock:
                    state["now"] -= 1

        self.fake.responder = slow
        ids = ["DOC-REPORT", "DOC-MINUTES", "DOC-MEMO", "DOC-REF"]
        self.assertEqual(ids, [d["document_id"] for d in self.read(ids)["documents"]])
        self.assertEqual(4, state["max"])

    def test_one_failing_document_does_not_sink_the_others(self) -> None:
        original = self.fake.responder

        def broken(kind, payload):
            if kind == "respond" and "DOC-MEMO" in json.dumps(payload):
                raise Refused("simulated outage")
            return original(kind, payload)

        self.fake.responder = broken
        by_id = {
            d["document_id"]: d
            for d in self.read(["DOC-REPORT", "DOC-MEMO"])["documents"]
        }
        self.assertTrue(by_id["DOC-REPORT"]["evidence"])
        self.assertIn("simulated outage", by_id["DOC-MEMO"]["note"])
        with self.assertRaises(document_text.DocumentError):
            self.read(["DOC-REPORT", "DOC-NOPE"])

    # ---- the case record -------------------------------------------------------------
    def test_record_fact_refuses_an_invented_quote_and_reports_progress(self) -> None:
        self.read(["DOC-REPORT"])
        case = self.case()
        with self.assertRaisesRegex(CaseError, "quote not found"):
            case.record_fact(
                "not_ready", "DOC-REPORT", 1, "The system was fully ready.", "claim"
            )
        fact = case.record_fact(
            "not_ready", "DOC-REPORT", 1, "Open Severity 1 defects: 21", "21 Sev-1 open"
        )
        self.assertEqual("proven", case.data["checklist"]["not_ready"]["status"])
        self.assertIn("timing", fact["progress"]["summary"])

    def test_limits_three_facts_per_item_and_three_citations_per_finding(self) -> None:
        self.read(["DOC-REPORT"])
        case = self.case()
        for _ in range(case_record.MAX_FACTS_PER_ITEM):
            case.record_fact(
                "not_ready", "DOC-REPORT", 1, "Overall status is green", "x"
            )
        with self.assertRaisesRegex(case_record.FactLimitError, "already has 3 facts"):
            case.record_fact(
                "not_ready", "DOC-REPORT", 1, "Overall status is green", "x"
            )
        citation = {
            "document_id": "DOC-REPORT",
            "page": 1,
            "quote": "Overall status is green",
        }
        finding = {
            "item": "not_ready",
            "status": "proven",
            "summary": "x",
            "citations": [citation] * 4,
        }
        with self.assertRaisesRegex(CaseError, "cites 4 facts"):
            case.file_memo(
                {"conclusion": "c", "findings": [finding], "gaps": ""}, "unverified"
            )

    def test_flagged_document_withdraws_and_blocks_facts(self) -> None:
        self.read(["DOC-MEMO"])
        case = self.case()
        case.record_fact(
            "counterevidence",
            "DOC-MEMO",
            1,
            "Attorney work product for the review team",
            "c",
        )
        case.flag_privileged("DOC-MEMO", "attorney work product")
        self.assertEqual([], case.data["facts"])
        with self.assertRaisesRegex(CaseError, "confidential"):
            case.record_fact(
                "counterevidence",
                "DOC-MEMO",
                1,
                "Attorney work product for the review team",
                "c",
            )

    def test_set_checklist_validates_and_keeps_items_with_facts(self) -> None:
        case = CaseRecord(self.root, self.run_id)
        with self.assertRaisesRegex(CaseError, "snake_case"):
            case.set_checklist([support.checklist_item("Has Spaces")])
        self.read(["DOC-REPORT"])
        case.set_checklist([support.checklist_item("not_ready")])
        case.record_fact(
            "not_ready", "DOC-REPORT", 1, "Open Severity 1 defects: 21", "c"
        )
        with self.assertRaisesRegex(CaseError, "keep the items"):
            case.set_checklist([support.checklist_item("timing")])

    def test_sam_boxes_parse(self) -> None:
        boxes = check_signatures.parse_boxes(
            "<0f>0<|box;x1=1;y1=2;x2=3;y2=4;w=10;h=20|><|mask;x=0;y=0;data=2,2,~ab|>,1<|box;x1=5;y1=6;x2=7;y2=8;w=10;h=20|><|mask;x=0;y=0;data=2,2,!c|>"
        )
        self.assertEqual([0, 1], [b["ordinal"] for b in boxes])
        self.assertEqual([], check_signatures.parse_boxes(""))

    # ---- progress and resume ---------------------------------------------------------
    def test_progress_saves_status_and_notes(self) -> None:
        save_progress(
            self.root,
            self.run_id,
            [{"role": "user", "content": "o"}],
            status="paused",
            note="x",
        )
        progress = load_progress(self.root, self.run_id)
        self.assertEqual(
            ("paused", 0, "x"),
            (progress["status"], progress["turn"], progress["notes"]["note"]),
        )

    def test_resume_after_the_turn_limit_and_nothing_to_resume(self) -> None:
        save_progress(self.root, self.run_id, [], status="paused")
        self.assertIn("more turns", resume(self.root, self.run_id)["message"])
        save_progress(self.root, self.run_id, [], status="answered")
        step = resume(self.root, self.run_id)
        self.assertEqual((None, "answered"), (step["message"], step["status"]))

    # ---- the tools ------------------------------------------------------------------
    def test_tools_run_and_errors_come_back_to_the_model(self) -> None:
        self.assertEqual({"plan": ["a"]}, self.tool("update_plan", {"plan": ["a"]}))
        self.assertIn("DOC-REPORT", str(self.tool("list_documents")))
        self.assertIn(
            "set_checklist first", self.tool("record_fact", support.FACT[1])["error"]
        )
        self.assertIn("unknown tool", self.tool("request_evidence")["error"])
        bad = dict(call("update_plan"), arguments="{not json")
        self.assertIn(
            "not valid JSON",
            tools.run(self.client, self.root, self.run_id, bad)["error"],
        )

    def test_base_tools_without_verification_and_three_more_with_it(self) -> None:
        names = [t["name"] for t in tools.definitions(self.root, self.run_id)]
        self.assertEqual(tools.BASE_TOOLS, names)
        verified = new_run(
            self.root, instructions="i", objective="o", verification=True
        )
        names = [t["name"] for t in tools.definitions(self.root, verified)]
        self.assertEqual(
            ["flag_privileged", "request_evidence", "check_signatures"], names[6:]
        )

    def test_a_filed_memo_ends_the_run_without_verification(self) -> None:
        result = self.tool("submit_memo", support.MEMO[1])
        self.assertEqual(("answered", "unverified"), (result["status"], result["memo"]))
        self.assertEqual(
            "unverified", CaseRecord(self.root, self.run_id).data["memo"]["status"]
        )

    def test_documents_read_are_remembered(self) -> None:
        self.tool("analyze_document", {"document_ids": ["DOC-REPORT"], "request": "x"})
        self.assertEqual(
            ["DOC-REPORT"], CaseRecord(self.root, self.run_id).data["read_ids"]
        )

    def test_a_check_that_is_not_built_yet_pauses_the_run(self) -> None:
        run_id = new_run(self.root, instructions="i", objective="o", verification=True)
        with mock.patch(
            "agent_kit.tools.set_checklist.importlib.import_module",
            side_effect=NotImplementedError("not implemented yet"),
        ):
            result = self.tool(
                "set_checklist", {"items": support.CHECKLIST_ITEMS}, run_id
            )
        self.assertEqual(
            ("not implemented yet", "paused"), (result["error"], result["status"])
        )

    def test_submit_memo_accepts_findings_sent_as_a_json_string(self) -> None:
        run_id = new_run(self.root, instructions="i", objective="o", verification=False)
        finding = {"item": "x", "status": "not_proven", "summary": "s", "citations": []}
        memo = {"conclusion": "c", "findings": json.dumps([finding]), "gaps": ["a", "b"]}
        self.assertTrue(self.tool("submit_memo", memo, run_id)["filed"])
        filed = CaseRecord(self.root, run_id).data["memo"]
        self.assertEqual(([finding], "a\nb"), (filed["findings"], filed["gaps"]))

    def test_submit_memo_refuses_findings_that_are_not_an_array(self) -> None:
        run_id = new_run(self.root, instructions="i", objective="o", verification=True)
        broken = '[{"item": "x", "summary": "he said "ready""}]'  # unescaped quotes
        memo = {"conclusion": "c", "findings": broken, "gaps": ""}
        result = self.tool("submit_memo", memo, run_id)
        self.assertIn("not as a string", result["error"])
        self.assertEqual(0, CaseRecord(self.root, run_id).memo_refusals())

    def test_check_signatures_is_a_placeholder_that_names_its_reference(self) -> None:
        run_id = new_run(self.root, instructions="i", objective="o", verification=True)
        args = {"document_id": "DOC-REF", "page": 1, "signer": "Dana Okafor"}
        same = dict(args, reference_document_id="DOC-REF", reference_page=1)
        self.assertIn(
            "different page", self.tool("check_signatures", same, run_id)["error"]
        )
        other = dict(args, reference_document_id="DOC-MEMO", reference_page=1)
        result = self.tool("check_signatures", other, run_id)
        self.assertEqual("unclear", result["verdict"])
        check = CaseRecord(self.root, run_id).data["signature_checks"][0]
        self.assertEqual(
            {"document_id": "DOC-MEMO", "page": 1, "boxes": []}, check["reference"]
        )

    # ---- pre-built checks ------------------------------------------------------------
    def ctx(self) -> tools.Context:
        return tools.Context(
            self.client,
            self.root,
            self.run_id,
            CaseRecord(self.root, self.run_id),
            True,
        )

    def test_verify_claims_reports_unsupported_findings(self) -> None:
        from verification import verify_claims

        memo = support.MEMO[1]
        self.assertEqual(
            {"passed": True, "feedback": []},
            verify_claims.run_verification(self.ctx(), memo),
        )
        fake = support.scripted(
            self.root,
            [],
            unsupported=lambda text: [
                {"item": "ready_statement", "reason": "off topic"}
            ],
        )
        ctx = tools.Context(
            fake.client,
            self.root,
            self.run_id,
            CaseRecord(self.root, self.run_id),
            True,
        )
        result = verify_claims.run_verification(ctx, memo)
        self.assertFalse(result["passed"])
        self.assertIn("ready_statement", result["feedback"][0])

    def test_verify_evidence_request(self) -> None:
        from verification import verify_evidence_request

        self.read(["DOC-REPORT"])
        case = self.case()
        case.mark_read(["DOC-REPORT"])
        result = verify_evidence_request.run_verification(
            self.ctx(), {"item": "timing", "need": "x"}
        )
        self.assertFalse(result["passed"])
        self.assertIn("DOC-MINUTES", result["feedback"])
        case.mark_read(list(support.INITIAL))
        self.assertTrue(
            verify_evidence_request.run_verification(
                self.ctx(), {"item": "timing", "need": "x"}
            )["passed"]
        )
        case.record_fact(
            "not_ready", "DOC-REPORT", 1, "Open Severity 1 defects: 21", "c"
        )
        result = verify_evidence_request.run_verification(
            self.ctx(), {"item": "not_ready", "need": "x"}
        )
        self.assertIn("already proven", result["feedback"])


if __name__ == "__main__":
    unittest.main()
