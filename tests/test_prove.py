from __future__ import annotations

import json
import os
from pathlib import Path

import httpx

from dossier.cli import main
from dossier.prove import run_prove
from dossier.sources.pubs import HttpPubsRetriever, PubsSource
from dossier.store import Corpus



def test_http_retriever_maps_search_hits(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/search":
            body = {
                "hits": [
                    {
                        "uri": "zotero://pubs/1",
                        "title": "Coastal paper",
                        "text": "Glen wrote on coastal governance.",
                    },
                    {
                        "uri": "zotero://pubs/2",
                        "title": "Reef note",
                        "text": "Synthetic reefs in the South Pacific.",
                    },
                ]
            }
            return httpx.Response(200, json=body)
        if request.url.path in {"/health", "/"}:
            return httpx.Response(200, json={"ok": True})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)

    class Client(httpx.Client):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    monkeypatch.setattr("dossier.sources.pubs.httpx.Client", Client)
    retriever = HttpPubsRetriever("http://127.0.0.1:8012")
    assert retriever.ping()
    rows = retriever.records()
    assert len(rows) == 2
    assert rows[0].uri == "zotero://pubs/1"
    assert "coastal governance" in rows[0].text


def test_http_retriever_empty_on_error(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    transport = httpx.MockTransport(handler)

    class Client(httpx.Client):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    monkeypatch.setattr("dossier.sources.pubs.httpx.Client", Client)
    assert HttpPubsRetriever("http://127.0.0.1:8012").records() == []


def test_non_loopback_pubs_url_is_not_contacted(monkeypatch) -> None:
    def boom(*_args, **_kwargs):
        raise AssertionError("pubs must not open a socket to a remote host")

    monkeypatch.setattr("dossier.sources.pubs.httpx.Client", boom)
    remote = HttpPubsRetriever("http://pubs.example")
    assert remote.ping() is False
    assert remote.records() == []
    assert remote.search("coastal governance") == []


def test_pubs_load_from_http_search(tmp_path: Path, corpus: Corpus, monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/search":
            return httpx.Response(
                200,
                json={
                    "hits": [
                        {
                            "uri": "zotero://pubs/live",
                            "title": "Live",
                            "text": "Glen published a live paper on ocean rights.",
                        }
                    ]
                },
            )
        return httpx.Response(200)

    transport = httpx.MockTransport(handler)

    class Client(httpx.Client):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    monkeypatch.setattr("dossier.sources.pubs.httpx.Client", Client)
    src = PubsSource(retriever=HttpPubsRetriever("http://127.0.0.1:8012"))
    src.load(Path("/nonexistent/zotero-rag-pubs"), corpus)
    assert len(corpus.records("pubs")) == 1
    assert corpus.records("pubs")[0].uri == "zotero://pubs/live"


def test_prove_on_applications_fixture(tmp_path: Path, monkeypatch) -> None:
    data = tmp_path / "prove-data"
    apps = tmp_path / "job applications"
    apps.mkdir()
    (apps / "cover.md").write_text(
        "Cover letter. Glen led the Oceana BBNJ working group on coastal governance.\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("DOSSIER_APPLICATIONS", str(apps))
    monkeypatch.setenv("DATA_DUMPS_WAREHOUSE", str(tmp_path / "missing.duckdb"))

    code = run_prove(
        data=data,
        adapters=("applications",),
        allow_overlap=True,
        with_llm=False,
    )
    assert code == 0
    ledger = json.loads((data / "ledger.json").read_text(encoding="utf-8"))
    assert ledger["records_total"] >= 1
    assert "applications" in ledger["records_by_source"]
    assert (data / "ledger.md").is_file()


def test_cli_prove_help(capsys) -> None:
    try:
        main(["prove", "--help"])
    except SystemExit as exc:
        assert exc.code == 0
    out = capsys.readouterr().out
    assert "--allow-overlap" in out
    assert "--pubs" in out


def test_prove_refuses_without_fts5(tmp_path: Path, monkeypatch, capsys) -> None:
    data = tmp_path / "prove-no-fts"
    apps = tmp_path / "job applications"
    apps.mkdir()
    (apps / "cover.md").write_text("Glen led a synthetic coastal project.\n", encoding="utf-8")
    monkeypatch.setenv("DOSSIER_APPLICATIONS", str(apps))
    monkeypatch.setenv("DATA_DUMPS_WAREHOUSE", str(tmp_path / "missing.duckdb"))

    class NoFts:
        def __init__(self, *args, **kwargs) -> None:
            self.fts_ok = False

        def records(self, source=None):
            return []

        def cards(self, status=None):
            return []

        def close(self) -> None:
            return None

    monkeypatch.setattr("dossier.prove.Corpus", NoFts)
    code = run_prove(
        data=data,
        adapters=("applications",),
        allow_overlap=False,
        with_llm=False,
    )
    assert code == 2
    err = capsys.readouterr().err
    assert "fts5 unavailable" in err
    assert (data / "ledger.json").is_file()


def test_prove_restores_env(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DOSSIER_LLM_PROVIDER", "ollama")
    monkeypatch.setenv("DOSSIER_DATA", str(tmp_path / "prior-data"))
    apps = tmp_path / "job applications"
    apps.mkdir()
    (apps / "cover.md").write_text("Glen led a synthetic coastal project.\n", encoding="utf-8")
    monkeypatch.setenv("DOSSIER_APPLICATIONS", str(apps))
    monkeypatch.setenv("DATA_DUMPS_WAREHOUSE", str(tmp_path / "missing.duckdb"))

    run_prove(
        data=tmp_path / "prove-env",
        adapters=("applications",),
        allow_overlap=True,
        with_llm=False,
    )
    assert os.environ.get("DOSSIER_LLM_PROVIDER") == "ollama"
    assert os.environ.get("DOSSIER_DATA") == str(tmp_path / "prior-data")


def test_doctor_prints_python_and_sqlite(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("DOSSIER_DATA", str(tmp_path))
    assert main(["doctor"]) == 0
    out = capsys.readouterr().out
    assert "python:" in out
    assert "sqlite:" in out
    assert "fts5:" in out
    assert "pubs_url:" in out


def test_cli_prove_empty_data_uses_temp(tmp_path: Path, monkeypatch) -> None:
    apps = tmp_path / "job applications"
    apps.mkdir()
    (apps / "cover.md").write_text("Glen led a synthetic coastal project.\n", encoding="utf-8")
    monkeypatch.setenv("DOSSIER_APPLICATIONS", str(apps))
    monkeypatch.setenv("DATA_DUMPS_WAREHOUSE", str(tmp_path / "missing.duckdb"))
    monkeypatch.chdir(tmp_path)
    code = main(["prove", "--data", "", "--adapters", "applications", "--allow-overlap"])
    assert code == 0
    assert not (tmp_path / "evidence.db").exists()
    assert not (tmp_path / "ledger.json").exists()
