"""Read-only evaluation against an already published, tenant-scoped knowledge API."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import time

import httpx


def evaluate(client, root, cases, model, chat_model):
    results = []
    for case in cases:
        started = time.monotonic()
        body = {"model": model, "query": case["query"], "limit": 5}
        if chat_model:
            body["chat_model"] = chat_model
        try:
            response = client.post(
                root + ("/answers" if chat_model else "/hybrid-search"), json=body
            )
        except httpx.RequestError:
            results.append(
                {
                    "id": case["id"],
                    "passed": False,
                    "error": "transport_error",
                    "seconds": round(time.monotonic() - started, 3),
                }
            )
            continue
        item = {
            "id": case["id"],
            "http_status": response.status_code,
            "seconds": round(time.monotonic() - started, 3),
        }
        if response.is_success:
            data = response.json()
            sources = data.get("citations", []) if chat_model else data.get("data", [])
            found = {source["filename"] for source in sources}
            expected = set(case.get("expected_files", []))
            item["expected_source_hit"] = bool(expected & found) if expected else None
            item["refused"] = data.get("status") == "insufficient_evidence" if chat_model else None
            item["passed"] = (
                item["refused"]
                if case.get("expect_refusal") and chat_model
                else item["expected_source_hit"]
            )
            # Preserve identifiers, never raw manual text or generated answers in the report.
            item["source_files"] = sorted(found)
        else:
            item["passed"] = False
        results.append(item)
    scored = [item for item in results if item.get("passed") is not None]
    return {
        "cases": results,
        "scored": len(scored),
        "passed": sum(bool(item["passed"]) for item in scored),
        "note": "Source hits do not establish semantic correctness; human review is required.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--application", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--chat-model")
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    token = os.environ.get("NEXUS_EVAL_TOKEN")
    if not token:
        parser.error("Set NEXUS_EVAL_TOKEN to a tenant-scoped test credential")
    cases = json.loads(args.cases.read_text(encoding="utf-8"))
    if not isinstance(cases, list) or not 1 <= len(cases) <= 100:
        parser.error("Provide 1..100 evaluation cases")
    ids = set()
    for case in cases:
        if (
            not isinstance(case, dict)
            or not isinstance(case.get("id"), str)
            or case["id"] in ids
            or not isinstance(case.get("query"), str)
            or not case["query"].strip()
            or len(case["query"]) > 200
            or not isinstance(case.get("expected_files", []), list)
            or any(not isinstance(name, str) for name in case.get("expected_files", []))
        ):
            parser.error("Invalid or duplicate case; queries must contain 1..200 characters")
        ids.add(case["id"])
    from urllib.parse import quote, urlsplit

    url = urlsplit(args.base_url)
    if (
        url.scheme not in {"http", "https"}
        or not url.hostname
        or url.username
        or url.password
        or url.query
        or url.fragment
    ):
        parser.error("Use an HTTP(S) URL without credentials, query or fragment")
    if url.scheme == "http" and url.hostname not in {"localhost", "127.0.0.1", "::1"}:
        parser.error("Use HTTPS for remote evaluation")
    root = (
        args.base_url.rstrip("/")
        + "/api/v1/applications/"
        + quote(args.application, safe="")
        + "/versions/"
        + quote(args.version, safe="")
    )
    with httpx.Client(headers={"Authorization": "Bearer " + token}, timeout=180) as client:
        report = evaluate(client, root, cases, args.model, args.chat_model)
    report["configuration"] = {
        "model": args.model,
        "chat_model": args.chat_model,
        "application": args.application,
        "version": args.version,
        "cases_sha256": hashlib.sha256(args.cases.read_bytes()).hexdigest(),
    }
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Scored {report['scored']}; passed {report['passed']}. Report: {args.output}")


if __name__ == "__main__":
    main()
