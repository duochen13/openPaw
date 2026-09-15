from copy import deepcopy

import pytest

from portfolio_analysis.bundle import build_bundle, bundle_hash, reusable, write_bundle
from portfolio_analysis.events.base import Document, VerifiedFact
from portfolio_analysis.moves import Move

MOVE = Move("META", "2024-04-25", -0.10, "QQQ", -0.005, 1.4, -0.093, 0.025, -3.72)


class Source:
    name = "example"

    def __init__(self, reverse=False):
        self.reverse = reverse

    def collect(self, ticker, start, end):
        docs = [
            Document.make(
                source=self.name,
                native_id=str(i),
                published_at="2024-04-25T12:00:00Z",
                title=str(i),
                url=f"https://example.com/{i}",
            )
            for i in range(3)
        ]
        facts = [VerifiedFact(key="filing", value=i, source="edgar") for i in range(2)]
        return (docs[::-1], facts[::-1]) if self.reverse else (docs, facts)


def bundle(reverse=False):
    return build_bundle(
        MOVE,
        window=("2024-04-23", "2024-04-26"),
        sources=[Source(reverse)],
        news_coverage_start="2020-01-01",
        source_status={"earnings": "missing_api_key"},
        macro_coverage={"CPI": True, "PCE": True, "FOMC": True},
        collection_key="test",
    )


def test_reordering_documents_and_facts_keeps_hash():
    assert bundle()["bundle_sha256"] == bundle(True)["bundle_sha256"]


def test_changed_evidence_and_sign_flip_invalidate_hash():
    original = bundle()
    mutated = deepcopy(original)
    mutated["move"]["return"] *= -1
    assert bundle_hash(mutated) != original["bundle_sha256"]
    mutated = deepcopy(original)
    mutated["documents"][0]["summary"] = "new evidence"
    assert bundle_hash(mutated) != original["bundle_sha256"]


def test_partial_coverage_is_explicit():
    coverage = bundle()["coverage"]
    assert coverage["source_status"]["earnings"] == "missing_api_key"
    assert coverage["complete"] is False
    assert coverage["news_coverage_known_thin"] is True
    assert coverage["documents"] == 3


def test_resume_checks_key_and_content_integrity(tmp_path):
    payload = bundle()
    path = write_bundle(tmp_path, payload)
    assert reusable(path, "test")
    assert not reusable(path, "changed")
    path.write_text(
        path.read_text().replace("new evidence", "x").replace("https://example", "https://bad")
    )
    assert not reusable(path, "test")


def test_conflicting_doc_ids_fail_instead_of_order_dependent_hash():
    class Conflict(Source):
        def collect(self, *args):
            docs, facts = super().collect(*args)
            docs.append(
                Document.make(
                    source=self.name,
                    native_id="0",
                    published_at="2024-04-25T12:00:00Z",
                    title="conflict",
                    url="https://example.com/0",
                )
            )
            return docs, facts

    with pytest.raises(ValueError, match="conflicting"):
        build_bundle(
            MOVE,
            window=("2024-04-23", "2024-04-26"),
            sources=[Conflict()],
            news_coverage_start="2020-01-01",
            source_status={},
            macro_coverage={},
            collection_key="test",
        )


def test_approximate_source_count_remains_visible_in_bundle():
    source = Source()
    source.coverage_status = "approximate_hit_count"
    payload = build_bundle(
        MOVE,
        window=("2024-04-23", "2024-04-26"),
        sources=[source],
        news_coverage_start="2020-01-01",
        source_status={},
        macro_coverage={"CPI": True},
        collection_key="test",
    )
    assert payload["coverage"]["source_status"]["example"] == "approximate_hit_count"
    assert payload["coverage"]["complete"] is False
