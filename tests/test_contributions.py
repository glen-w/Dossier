from dossier.contributions import CONTRIBUTIONS


def test_registry_lists_five_explicit_adapters() -> None:
    assert [c.name for c in CONTRIBUTIONS] == [
        "pubs",
        "chatgpt",
        "linkedin",
        "applications",
        "transcripts",
    ]
