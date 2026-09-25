import json
import threading
from urllib.request import Request, urlopen

import pytest

from dossier.cards import STATUS_PENDING, ClaimCard
from dossier.review import apply_action, list_cards, make_server, summary
from dossier.store import Corpus, Record


def _card(card_id: str, source: str, lens: str, kind: str = "paper") -> ClaimCard:
    return ClaimCard(
        id=card_id,
        claim=f"Synthetic claim {card_id}. Not a real job.",
        citations=[f"fixture://{card_id}"],
        source=source,
        status=STATUS_PENDING,
        extras={"lens": lens, "kind": kind},
    )


def test_summary_groups_by_source_lens_and_kind(corpus: Corpus) -> None:
    corpus.put_card(_card("a", "employer", "Delivered"))
    corpus.put_card(_card("b", "employer", "skills", "workshop"))
    corpus.put_card(_card("c", "chatgpt", ""))
    data = summary(corpus)
    by_source = {item["source"]: item for item in data["sources"]}
    assert by_source["employer"]["pending"] == 2
    lenses = {(item["lens"], item["kind"]): item["pending"] for item in by_source["employer"]["groups"]}
    assert lenses[("delivered", "paper")] == 1
    assert lenses[("skills", "workshop")] == 1
    assert ("(none)", "paper") in {
        (item["lens"], item["kind"]) for item in by_source["chatgpt"]["groups"]
    }


def test_apply_action_is_scoped_to_the_group(corpus: Corpus) -> None:
    corpus.put_card(_card("a", "employer", "delivered"))
    corpus.put_card(_card("b", "employer", "skills"))
    corpus.put_card(_card("c", "git", "delivered"))
    changed = apply_action(
        corpus,
        {"action": "approve", "source": "employer", "lens": "delivered", "kind": "paper"},
    )
    assert changed == 1
    assert corpus.get_card("a").status == "approved"
    assert corpus.get_card("b").status == STATUS_PENDING
    assert corpus.get_card("c").status == STATUS_PENDING
    assert apply_action(corpus, {"action": "refuse", "ids": ["b"]}) == 1
    assert corpus.get_card("b").status == "refused"
    listed = list_cards(corpus, source="employer", status="approved", lens="delivered")
    assert listed["total"] == 1
    assert listed["cards"][0]["id"] == "a"


def test_search_escapes_wildcards_and_shows_a_snippet(corpus: Corpus) -> None:
    corpus.upsert_record(
        Record(
            id="r1",
            source="employer",
            uri="fixture://a",
            title="Oceana note",
            text="Quinn drafted a coastal governance briefing for the synthetic pack.",
        )
    )
    corpus.put_card(
        ClaimCard(
            id="a",
            claim="100% synthetic coastal claim. Not a real job.",
            citations=["fixture://a"],
            source="employer",
            status=STATUS_PENDING,
            extras={"lens": "delivered", "kind": "paper", "span": "Quinn drafted a coastal briefing."},
        )
    )
    corpus.put_card(_card("b", "employer", "delivered"))
    exact = list_cards(corpus, source="employer", q="100%")
    assert exact["total"] == 1
    assert exact["cards"][0]["id"] == "a"
    assert exact["cards"][0]["span"].startswith("Quinn drafted")
    assert "Oceana note" in exact["cards"][0]["snippet"]
    assert "coastal governance" in exact["cards"][0]["snippet"]
    assert list_cards(corpus, source="employer", q="%")["total"] == 1
    with pytest.raises(ValueError):
        list_cards(corpus, status="bogus")


def test_list_cards_pages_and_rejects_an_unscoped_action(corpus: Corpus) -> None:
    for index in range(3):
        corpus.put_card(_card(f"c{index}", "slack", "skills"))
    first = list_cards(corpus, source="slack", limit=2, offset=0)
    assert first["total"] == 3
    assert [card["id"] for card in first["cards"]] == ["c0", "c1"]
    second = list_cards(corpus, source="slack", limit=2, offset=2)
    assert [card["id"] for card in second["cards"]] == ["c2"]
    with pytest.raises(ValueError, match="pass ids or a source"):
        apply_action(corpus, {"action": "approve"})
    with pytest.raises(ValueError, match="approve, refuse, reopen, or defend"):
        apply_action(corpus, {"action": "drop", "source": "slack"})


def test_reopen_action_leaves_pending_cards(corpus: Corpus) -> None:
    corpus.put_card(_card("a", "employer", "delivered"))
    corpus.approve("a")
    corpus.put_card(_card("b", "employer", "skills"))
    assert apply_action(corpus, {"action": "reopen", "source": "employer", "lens": "delivered"}) == 1
    assert corpus.get_card("a").status == STATUS_PENDING
    assert corpus.get_card("b").status == STATUS_PENDING


def test_summary_route_stays_on_loopback(corpus: Corpus) -> None:
    corpus.put_card(_card("a", "mbox", "delivered"))
    httpd = make_server(corpus, 0)
    assert httpd.server_address[0] == "127.0.0.1"
    port = httpd.server_address[1]
    found: dict = {}

    def client() -> None:
        try:
            with urlopen(f"http://127.0.0.1:{port}/api/summary") as res:
                found["summary"] = json.loads(res.read())
            body = json.dumps({"action": "approve", "source": "mbox"}).encode()
            req = Request(
                f"http://127.0.0.1:{port}/api/act",
                data=body,
                headers={"Content-Type": "application/json"},
            )
            with urlopen(req) as res:
                found["acted"] = json.loads(res.read())
        except Exception as exc:  # noqa: BLE001
            found["error"] = exc
        finally:
            httpd.shutdown()

    thread = threading.Thread(target=client, daemon=True)
    thread.start()
    httpd.serve_forever()
    thread.join(timeout=5)
    httpd.server_close()
    assert "error" not in found
    assert found["summary"]["sources"][0]["source"] == "mbox"
    assert found["acted"]["changed"] == 1
    assert corpus.get_card("a").status == "approved"
