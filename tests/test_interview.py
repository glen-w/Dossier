from pathlib import Path

from dossier.cards import STATUS_APPROVED, STATUS_PENDING, ClaimCard
from dossier.cli import main
from dossier.config import Config
from dossier.interview import conduct, decompose_question
from dossier.llm.budget import CallBudget
from dossier.llm.client import CompletionRequest, LLMClientError
from dossier.packs import follow_up, posting_pack
from dossier.passages import split_passages
from dossier.store import Corpus, Record


class _Boom:
    provider = "boom"

    def check_config(self, model: str) -> tuple[bool, str]:
        return True, "ok"

    def complete(self, request) -> str:
        raise AssertionError("model should not be called")

    def complete_json(self, request) -> dict:
        raise AssertionError("model should not be called")


class _Once:
    provider = "fake"

    def __init__(self) -> None:
        self.calls = 0

    def check_config(self, model: str) -> tuple[bool, str]:
        return True, "ok"

    def complete(self, request) -> str:
        return ""

    def complete_json(self, request) -> dict:
        self.calls += 1
        return {
            "answer": "You wrote a synthetic paper on coastal governance.",
            "citations": ["zotero://fixture/1"],
        }


def _cfg(**kwargs) -> Config:
    base = dict(
        ask_fts=False,
        ask_passages=True,
        ask_cards_first=True,
        ask_hops=1,
        ask_decompose="auto",
        ask_planner="off",
        llm_max_calls=6,
        ask_limit=5,
        lexicon=(),
    )
    base.update(kwargs)
    return Config(**base)


def test_approved_card_beats_a_weaker_record(corpus: Corpus) -> None:
    corpus.upsert_record(
        Record(
            id="r1",
            source="pubs",
            uri="zotero://fixture/1",
            title="Note",
            text="Quinn wrote a synthetic paper on coastal governance.",
        )
    )
    corpus.put_card(
        ClaimCard(
            id="card1",
            claim="Synthetic paper on coastal governance.",
            citations=["zotero://fixture/1"],
            source="pubs",
            status=STATUS_APPROVED,
        )
    )
    result = conduct(
        corpus,
        "coastal governance paper",
        _cfg(),
        _Boom(),
        mode="exact",
        limit=5,
    )
    assert not result.refused
    assert result.text == "Synthetic paper on coastal governance."
    assert result.citations == ["zotero://fixture/1"]


def test_pending_card_is_ignored(corpus: Corpus) -> None:
    corpus.upsert_record(
        Record(
            id="r1",
            source="pubs",
            uri="zotero://fixture/1",
            title="Note",
            text="Quinn wrote a synthetic paper on coastal governance.",
        )
    )
    corpus.put_card(
        ClaimCard(
            id="card1",
            claim="Synthetic paper on coastal governance.",
            citations=["zotero://fixture/1"],
            source="pubs",
            status=STATUS_PENDING,
        )
    )
    result = conduct(
        corpus,
        "coastal governance paper",
        _cfg(),
        _Boom(),
        mode="exact",
        limit=5,
    )
    assert not result.refused
    assert "coastal governance" in result.text
    assert result.route == "exact"


def test_passage_cites_the_parent_uri(corpus: Corpus) -> None:
    long = (
        "Intro paragraph about shipping schedules.\n\n"
        "Quinn drafted the GSR ocean chapter on coastal governance.\n\n"
        "Closing notes about catering."
    )
    corpus.upsert_record(
        Record(
            id="slack1",
            source="slack",
            uri="slack://C/1.0",
            title="Ocean thread",
            text=long,
        )
    )
    assert len(corpus.passage_rows()) >= 2
    hits = __import__("dossier.ask", fromlist=["collect_hits"]).collect_hits(
        corpus,
        "coastal governance chapter",
        _cfg(ask_passages=True),
        limit=5,
    )
    assert hits
    assert hits[0].uri == "slack://C/1.0"
    assert "coastal governance" in hits[0].text


def test_hop_finds_a_kind_the_first_query_missed(corpus: Corpus) -> None:
    corpus.upsert_record(
        Record(
            id="weak",
            source="slack",
            uri="slack://a-weak",
            title="Ocean note",
            text=(
                "Lens: delivered\nKind: chapter\n"
                "Drafted.\nOcean.\nChapter.\nWorkshop.\nMethods."
            ),
        )
    )
    corpus.upsert_record(
        Record(
            id="strong",
            source="slack",
            uri="slack://b-strong",
            title="GSR",
            text=(
                "Lens: delivered\nKind: chapter\n"
                "Quinn drafted the ocean chapter for the workshop methods."
            ),
        )
    )
    question = "drafted ocean chapter workshop methods"
    refused = conduct(
        corpus,
        question,
        _cfg(ask_hops=0, ask_passages=False),
        _Boom(),
        mode="exact",
        limit=5,
    )
    assert refused.refused
    result = conduct(
        corpus,
        question,
        _cfg(ask_hops=1, ask_passages=False),
        _Boom(),
        mode="exact",
        limit=5,
    )
    assert not result.refused
    assert result.citations == ["slack://b-strong"]


def test_planner_spends_one_call_then_quotes(corpus: Corpus) -> None:
    corpus.upsert_record(
        Record(
            id="a",
            source="pubs",
            uri="zotero://a",
            title="Workshop",
            text="Quinn convened a workshop on coastal methods.",
        )
    )
    corpus.upsert_record(
        Record(
            id="b",
            source="pubs",
            uri="zotero://b",
            title="Paper",
            text="Quinn wrote a paper on coastal governance.",
        )
    )

    class _Plan:
        provider = "fake"

        def __init__(self) -> None:
            self.calls = 0
            self.model = ""
            self.think = None
            self.tokens = None

        def complete_json(self, request) -> dict:
            self.calls += 1
            self.model = request.model
            self.think = request.think
            self.tokens = request.max_tokens
            if "Split the question" in request.prompt:
                return {
                    "questions": [
                        "workshop methods",
                        "coastal governance paper",
                    ]
                }
            raise AssertionError("unexpected completion")

    client = _Plan()
    result = conduct(
        corpus,
        "tell me everything about the work",
        _cfg(ask_passages=False, ask_planner="rich", ask_decompose="off"),
        client,
        mode="auto",
        limit=5,
    )
    assert client.calls == 1
    assert client.model == "qwen2.5:3b"
    assert client.think is False
    assert client.tokens == 512
    assert not result.refused
    assert result.route == "exact"


def test_toml_loads_zero_four_knobs(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DOSSIER_DATA", str(tmp_path))
    (tmp_path / "dossier.toml").write_text(
        "[ask]\ncards_first = false\nhops = 0\ndecompose = \"on\"\n"
        "planner = \"rich\"\npassages = false\n"
        "[llm]\nmax_calls = 2\ntimeout = 450\n"
        "[extract]\nchunk_chars = 2000\nmax_chunks = 3\n"
        '[run]\nposting = "/tmp/posting.txt"\n',
        encoding="utf-8",
    )
    cfg = Config.from_env()
    assert cfg.ask_cards_first is False
    assert cfg.ask_hops == 0
    assert cfg.ask_decompose == "on"
    assert cfg.ask_planner == "rich"
    assert cfg.ask_passages is False
    assert cfg.llm_max_calls == 2
    assert cfg.llm_timeout_seconds == 450.0
    assert cfg.extract_chunk_chars == 2000
    assert cfg.extract_max_chunks == 3
    assert cfg.run_posting == "/tmp/posting.txt"
    monkeypatch.setenv("DOSSIER_ASK_HOPS", "3")
    assert Config.from_env().ask_hops == 3
    monkeypatch.setenv("DOSSIER_LLM_TIMEOUT", "600")
    assert Config.from_env().llm_timeout_seconds == 600.0


def test_compound_question_stitches_without_a_model(corpus: Corpus) -> None:
    corpus.upsert_record(
        Record(
            id="a",
            source="pubs",
            uri="zotero://a",
            title="Workshop",
            text="Quinn convened a workshop on coastal methods.",
        )
    )
    corpus.upsert_record(
        Record(
            id="b",
            source="pubs",
            uri="zotero://b",
            title="Paper",
            text="Quinn wrote a paper on coastal governance.",
        )
    )
    question = "workshop methods; coastal governance paper"
    assert len(decompose_question(question, "auto")) == 2
    result = conduct(
        corpus,
        question,
        _cfg(ask_passages=False),
        _Boom(),
        mode="auto",
        limit=5,
    )
    assert not result.refused
    assert result.route == "exact"
    assert "workshop" in result.text.lower()
    assert "coastal governance" in result.text.lower()


def test_partial_miss_spends_one_call(corpus: Corpus) -> None:
    corpus.upsert_record(
        Record(
            id="a",
            source="pubs",
            uri="zotero://fixture/1",
            title="Paper",
            text="Quinn wrote a synthetic paper on coastal governance.",
        )
    )
    client = _Once()
    result = conduct(
        corpus,
        "coastal governance; lunar base command",
        _cfg(ask_passages=False, ask_decompose="on"),
        client,
        mode="auto",
        limit=5,
    )
    assert client.calls == 1
    assert result.route == "rich"


def test_budget_stops_a_sixth_call() -> None:
    budget = CallBudget(1)
    client = budget.wrap(_Once())
    req = CompletionRequest(model="x", prompt="p", json_mode=True, num_ctx=1024)
    client.complete_json(req)
    try:
        client.complete_json(req)
        raised = False
    except LLMClientError as exc:
        raised = True
        assert "budget" in str(exc)
    assert raised
    assert budget.calls == 1


def test_budget_zero_is_unlimited() -> None:
    budget = CallBudget(0)
    client = budget.wrap(_Once())
    req = CompletionRequest(model="x", prompt="p", json_mode=True, num_ctx=1024)
    for _ in range(3):
        assert budget.remaining
        client.complete_json(req)
    assert budget.calls == 3
    assert budget.remaining


def test_posting_pack_writes_under_tmp(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DOSSIER_DATA", str(tmp_path))
    monkeypatch.setenv("DOSSIER_LLM_PROVIDER", "off")
    corpus = Corpus(tmp_path / "evidence.db")
    corpus.upsert_record(
        Record(
            id="pos",
            source="linkedin",
            uri="linkedin://positions/0",
            title="Analyst at Oceans",
            text="Analyst at Oceans. Paris. Worked on coastal governance.",
            table="linkedin.positions",
        )
    )
    corpus.upsert_record(
        Record(
            id="s",
            source="slack",
            uri="slack://C/1.0",
            title="Ocean chapter",
            text="Lens: delivered\nKind: chapter\nDrafted the GSR ocean chapter.",
        )
    )
    corpus.close()
    posting = tmp_path / "posting.txt"
    posting.write_text(
        "Looking for ocean chapter editing and workshop facilitation experience.",
        encoding="utf-8",
    )
    assert main(["brief", "--posting", str(posting), "--mode", "exact"]) == 0
    briefs = list((tmp_path / "briefs").glob("*.md"))
    assert briefs
    text = briefs[0].read_text(encoding="utf-8")
    assert "mode: exact" in text or "refused:" in text
    again = Corpus(tmp_path / "evidence.db")
    try:
        assert again.cards("approved") == []
    finally:
        again.close()


def test_run_prints_ledger(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("DOSSIER_DATA", str(tmp_path))
    monkeypatch.setenv("DOSSIER_LLM_PROVIDER", "off")
    monkeypatch.setenv("DATA_DUMPS_WAREHOUSE", str(tmp_path / "missing.duckdb"))
    monkeypatch.setenv("DOSSIER_APPLICATIONS", str(tmp_path / "not-applications"))
    monkeypatch.setenv("DOSSIER_CURSOR_PROJECTS", str(tmp_path / "no-cursor"))
    monkeypatch.setenv("DOSSIER_GROK_BLOBS", str(tmp_path / "no-grok"))
    monkeypatch.setenv("DOSSIER_MAIL_ROOT", str(tmp_path / "no-mail"))
    monkeypatch.delenv("DOSSIER_EMPLOYER_PATHS", raising=False)
    monkeypatch.delenv("DOSSIER_CHATGPT_EXPORT", raising=False)
    monkeypatch.delenv("DOSSIER_SLACK_EXPORT", raising=False)
    monkeypatch.setattr("dossier.sources.pubs.HttpPubsRetriever.ping", lambda self: False)
    corpus = Corpus(tmp_path / "evidence.db")
    corpus.upsert_record(
        Record(
            id="pos",
            source="linkedin",
            uri="linkedin://positions/0",
            title="Analyst at Oceans",
            text="Analyst at Oceans. Paris.",
            table="linkedin.positions",
        )
    )
    corpus.close()
    assert main(["run", "--mode", "exact"]) == 0
    out = capsys.readouterr().out
    assert "ledger: records=" in out
    assert "model_calls=0" in out
    assert "egress=no" in out


def test_doctor_prints_fts(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("DOSSIER_DATA", str(tmp_path))
    assert main(["doctor"]) == 0
    out = capsys.readouterr().out
    assert "fts5:" in out
    assert "provider:" in out
    assert "embed_model:" in out
    assert "vectors: 0" in out
    assert "ask.pubs: no" in out
    assert "egress: no" in out
    assert "tailor: 0" in out
    assert "approve and defend before tailor will quote" in out
    assert "adapter pubs:" in out


def test_split_passages_keeps_headers() -> None:
    text = "Lens: delivered\nKind: chapter\n\nFirst block about ocean.\n\nSecond block about editing."
    parts = split_passages(text)
    assert len(parts) == 2
    assert parts[0].startswith("Lens: delivered")
    assert "Second block" in parts[1]


def test_follow_up_uses_rarest_token() -> None:
    nxt = follow_up(
        "skills",
        "what skills show facilitation",
        ["teaching editing", "teaching workshop"],
        lens="skills",
    )
    assert nxt is not None
    assert nxt.id == "skills-follow"
    assert "facilitation" in nxt.question


def test_posting_pack_uses_kinds() -> None:
    questions = posting_pack("Need a chapter editor for an ocean workshop")
    assert questions[0].id == "roles"
    assert "chapter" in questions[1].question or "workshop" in questions[1].question


def test_brief_adds_follow_up_after_refusal(corpus: Corpus) -> None:
    from dossier.brief import run_pack
    from dossier.packs import PackQuestion

    corpus.upsert_record(
        Record(
            id="shop",
            source="chatgpt",
            uri="chatgpt://c/m",
            title="Shopping",
            text="Buy milk and eggs tomorrow.",
        )
    )
    items = run_pack(
        corpus,
        [PackQuestion("skills", "what skills show facilitation")],
        _cfg(ask_passages=False),
        _Boom(),
        mode="exact",
    )
    assert len(items) == 2
    assert items[0][1].refused
    assert items[1][0].id == "skills-follow"
    assert "facilitation" in items[1][0].question


def test_budget_wraps_conduct_rich(corpus: Corpus) -> None:
    corpus.upsert_record(
        Record(
            id="a",
            source="pubs",
            uri="zotero://fixture/1",
            title="Paper",
            text="Quinn wrote a synthetic paper on coastal governance.",
        )
    )
    budget = CallBudget(1)
    client = budget.wrap(_Once())
    first = conduct(
        corpus,
        "coastal governance paper",
        _cfg(ask_passages=False, ask_cards_first=False),
        client,
        mode="rich",
        limit=5,
    )
    assert not first.refused
    assert budget.calls == 1
    second = conduct(
        corpus,
        "coastal governance paper",
        _cfg(ask_passages=False, ask_cards_first=False),
        client,
        mode="rich",
        limit=5,
    )
    assert second.refused
    assert "budget" in second.reason
