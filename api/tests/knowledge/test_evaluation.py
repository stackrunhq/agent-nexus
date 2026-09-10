import httpx
from agent_nexus_cli.evaluate import evaluate


def test_evaluation_scores_sources_refusal_and_errors_without_raw_text():
    responses = iter(
        [
            {
                "status": "answered",
                "answer": "private",
                "citations": [{"filename": "a.md", "text": "secret"}],
            },
            {"status": "insufficient_evidence", "citations": []},
        ]
    )
    with httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=next(responses)))
    ) as client:
        report = evaluate(
            client,
            "http://test",
            [
                {"id": "a", "query": "a", "expected_files": ["a.md"]},
                {"id": "b", "query": "b", "expect_refusal": True},
            ],
            "embed",
            "chat",
        )
    assert report["passed"] == report["scored"] == 2
    assert "private" not in str(report) and "secret" not in str(report)
