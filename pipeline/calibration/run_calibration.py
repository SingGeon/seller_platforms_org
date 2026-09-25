"""Calibration set for signal answering (GIG-26).

    python calibration/run_calibration.py --provider heuristic
    ANTHROPIC_API_KEY=... python calibration/run_calibration.py --provider anthropic

Reports accuracy over all cases and precision of "yes" answers (the metric that
matters to a sales rep: a wrong "yes" wastes an outreach).
"""
from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sales_pipeline import CompanyInfo, Document, QuestionSpec, make_backend, run_signal_pipeline

CASES = Path(__file__).with_name("cases.json")


async def evaluate(provider: str) -> dict:
    llm = make_backend(provider)
    now = datetime.now(timezone.utc)
    rows = []
    for case in json.loads(CASES.read_text()):
        docs = [
            Document(source_type=d["source_type"], url=f"https://calibration.example/{case['id']}/{i}", title=d["title"], text=d["text"], published_at=now - timedelta(days=d["days_ago"]))
            for i, d in enumerate(case["documents"])
        ]
        q = QuestionSpec(key="q:1", text=case["question"], keywords=case.get("keywords", []))
        res = await run_signal_pipeline(llm, CompanyInfo(name=case["company"]), [q], docs, detect_events=False)
        got = res.answers[0].answer
        rows.append({"id": case["id"], "expected": case["expected"], "got": got, "ok": got == case["expected"], "reasoning": res.answers[0].reasoning})
    yes = [r for r in rows if r["got"] == "yes"]
    return {
        "provider": llm.name,
        "accuracy": round(sum(r["ok"] for r in rows) / len(rows), 3),
        "yes_precision": round(sum(r["expected"] == "yes" for r in yes) / len(yes), 3) if yes else None,
        "cases": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", default=None, choices=["anthropic", "heuristic"])
    args = parser.parse_args()
    report = asyncio.run(evaluate(args.provider))
    for r in report["cases"]:
        print(f"{'OK ' if r['ok'] else 'ERR'} {r['id']:30} expected={r['expected']:8} got={r['got']:8} {r['reasoning'][:80]}")
    print(f"\nprovider={report['provider']} accuracy={report['accuracy']} yes_precision={report['yes_precision']}")


if __name__ == "__main__":
    main()
