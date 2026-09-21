from dossier.contributions import CONTRIBUTIONS


def test_registry_starts_empty() -> None:
    assert CONTRIBUTIONS == []
