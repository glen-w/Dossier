from dossier.contributions import CONTRIBUTIONS
from dossier.sources.base import Source


def test_registry_is_an_explicit_list() -> None:
    assert [c.name for c in CONTRIBUTIONS] == [
        "pubs",
        "chatgpt",
        "linkedin",
        "applications",
        "transcripts",
        "slack",
        "mbox",
        "meetings",
    ]
    assert len({c.name for c in CONTRIBUTIONS}) == len(CONTRIBUTIONS)


def test_each_adapter_matches_the_source_protocol() -> None:
    for item in CONTRIBUTIONS:
        assert item.source.name == item.name
        assert isinstance(item.source, Source)
        tables = item.source.tables()
        assert tables
        assert all(isinstance(name, str) and name for name in tables)
