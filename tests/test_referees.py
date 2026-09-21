"""Synthetic referee shortlist. No network, no real names."""

import json
from datetime import date
from pathlib import Path

import httpx
import pytest

from dossier.cli import main
from dossier.referees.load import load_people, load_policy
from dossier.referees.rank import Person, Policy, rank
from dossier.referees.twenty import _QUERY, fetch_people, people_from_payload

FIXTURES = Path(__file__).parent / "fixtures"
TODAY = date(2026, 9, 21)
POSTING = "We need coastal governance methods and marine policy at Coastal Lab."


def test_employer_overlap_outranks_keyword_only() -> None:
    people = load_people(FIXTURES / "synthetic_people.json")
    policy = load_policy(FIXTURES / "synthetic_referee_policy.json")
    shortlist = rank(POSTING, people, policy, employer="Coastal Lab", today=TODAY)
    names = [item.name for item in shortlist]
    assert names[0] == "Ada Overlap"
    assert names.index("Ada Overlap") < names.index("Bev Keywords")
    assert shortlist[0].score > shortlist[names.index("Bev Keywords")].score


def test_hard_skip_needs_review_ruled_out_and_inbox_dropped() -> None:
    people = load_people(FIXTURES / "synthetic_people.json")
    policy = load_policy(FIXTURES / "synthetic_referee_policy.json")
    names = {item.name for item in rank(POSTING, people, policy, employer="Coastal Lab", today=TODAY)}
    assert "Pat Skip" not in names
    assert "Revie Stub" not in names
    assert "Rue Ledout" not in names
    assert "Stu Dent" not in names
    assert "Inbox Only" not in names


def test_students_included_when_asked() -> None:
    people = load_people(FIXTURES / "synthetic_people.json")
    policy = load_policy(FIXTURES / "synthetic_referee_policy.json")
    names = {
        item.name
        for item in rank(
            POSTING,
            people,
            policy,
            employer="Coastal Lab",
            include_students=True,
            today=TODAY,
        )
    }
    assert "Stu Dent" in names


def test_scarce_name_kept_with_warning() -> None:
    people = load_people(FIXTURES / "synthetic_people.json")
    policy = load_policy(FIXTURES / "synthetic_referee_policy.json")
    shortlist = rank(POSTING, people, policy, employer="Coastal Lab", today=TODAY)
    scarce = next(item for item in shortlist if item.name == "Sam Scarce")
    assert "do not spend" in scarce.warning
    assert "hiring-firm overlap" in scarce.why


def test_alias_counts_as_hiring_firm() -> None:
    person = Person(name="Ali As", company="CL Coast", enrichment_status="REVIEWED")
    policy = Policy(employer_aliases={"Coastal Lab": ("CL Coast",)})
    shortlist = rank("unrelated posting text", [person], policy, employer="Coastal Lab", today=TODAY)
    assert shortlist[0].why.startswith("hiring-firm overlap")


def test_empty_people_does_not_rank() -> None:
    assert rank(POSTING, [], Policy.empty(), employer="Coastal Lab", today=TODAY) == []


def test_shortlist_caps_at_seven() -> None:
    people = [
        Person(name=f"Person {index:02d}", company="Match Org", enrichment_status="REVIEWED")
        for index in range(8)
    ]
    shortlist = rank("Match Org role", people, employer="Match Org", today=TODAY)
    assert len(shortlist) == 7
    assert "Person 07" not in {item.name for item in shortlist}


def test_stale_contact_is_not_recent() -> None:
    person = Person(
        name="Old Contact",
        company="Far Institute",
        job_title="Accountant",
        last_contact_at="2020-01-01T00:00:00Z",
        enrichment_status="REVIEWED",
    )
    shortlist = rank("nothing shared", [person], today=TODAY)
    assert shortlist == []


def test_graphql_payload_maps_notes_and_skips_writes() -> None:
    payload = {
        "data": {
            "people": {
                "edges": [
                    {
                        "node": {
                            "name": {"firstName": "Nia", "lastName": "Note"},
                            "jobTitle": "Fellow",
                            "keywords": "governance",
                            "bio": "",
                            "enrichmentStatus": "REVIEWED",
                            "coAuthorWithGlen": 1,
                            "lastContactAt": "2026-08-01T00:00:00Z",
                            "company": {"name": "Coastal Lab"},
                            "noteTargets": {
                                "edges": [
                                    {"node": {"note": {"bodyV2": {"markdown": "Sofia line."}}}}
                                ]
                            },
                            "timelineActivities": {"edges": [{"node": {"id": "t1"}}]},
                        }
                    }
                ]
            }
        }
    }
    person = people_from_payload(payload)[0]
    assert person.name == "Nia Note"
    assert person.company == "Coastal Lab"
    assert person.note == "Sofia line."
    assert person.timeline_count == 1
    assert person.co_author_with_glen == 1
    query = _QUERY.lower()
    for forbidden in ("tasktargets", "messageparticipants", "pointofcontactforopportunities"):
        assert forbidden not in query


def test_cli_referees_without_source(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("DOSSIER_DATA", str(tmp_path))
    monkeypatch.delenv("DOSSIER_PEOPLE", raising=False)
    monkeypatch.delenv("DOSSIER_TWENTY_API_URL", raising=False)
    monkeypatch.delenv("DOSSIER_TWENTY_API_KEY", raising=False)
    code = main(["referees", "--text", "coastal governance"])
    err = capsys.readouterr().err
    assert code == 1
    assert "no people source" in err
    assert not (tmp_path / "evidence.db").exists()


def test_cli_referees_prints_shortlist(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("DOSSIER_DATA", str(tmp_path))
    code = main(
        [
            "referees",
            "--text",
            POSTING,
            "--employer",
            "Coastal Lab",
            "--people",
            str(FIXTURES / "synthetic_people.json"),
            "--policy",
            str(FIXTURES / "synthetic_referee_policy.json"),
        ]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "confirm before listing" in out
    assert out.index("Ada Overlap") < out.index("Bev Keywords")
    assert "warning: do not spend" in out
    assert "Pat Skip" not in out
    assert not (tmp_path / "evidence.db").exists()


def test_posting_file_matches_company_without_employer_flag(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    monkeypatch.setenv("DOSSIER_DATA", str(tmp_path))
    posting = tmp_path / "posting.txt"
    posting.write_text("Role at Coastal Lab.\n", encoding="utf-8")
    code = main(
        [
            "referees",
            "--posting",
            str(posting),
            "--people",
            str(FIXTURES / "synthetic_people.json"),
            "--policy",
            str(FIXTURES / "synthetic_referee_policy.json"),
        ]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "Ada Overlap" in out
    assert "hiring-firm overlap: Coastal Lab" in out
    assert not (tmp_path / "evidence.db").exists()


def test_cli_people_env_and_partial_twenty_credentials(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("DOSSIER_DATA", str(tmp_path))
    monkeypatch.setenv("DOSSIER_PEOPLE", str(FIXTURES / "synthetic_people.json"))
    monkeypatch.setenv("DOSSIER_REFEREE_POLICY", str(FIXTURES / "synthetic_referee_policy.json"))
    monkeypatch.delenv("DOSSIER_TWENTY_API_URL", raising=False)
    monkeypatch.delenv("DOSSIER_TWENTY_API_KEY", raising=False)
    assert main(["referees", "--text", POSTING, "--employer", "Coastal Lab"]) == 0
    assert "Ada Overlap" in capsys.readouterr().out

    monkeypatch.delenv("DOSSIER_PEOPLE", raising=False)
    monkeypatch.setenv("DOSSIER_TWENTY_API_URL", "https://twenty.example")
    code = main(["referees", "--text", POSTING])
    assert code == 2
    assert "both" in capsys.readouterr().err


def test_empty_posting_is_refused(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("DOSSIER_DATA", str(tmp_path))
    code = main(
        [
            "referees",
            "--text",
            "   ",
            "--people",
            str(FIXTURES / "synthetic_people.json"),
        ]
    )
    assert code == 2
    assert "posting is empty" in capsys.readouterr().err


def test_this_quarter_and_recent_contact_are_why_lines() -> None:
    people = load_people(FIXTURES / "synthetic_people.json")
    policy = load_policy(FIXTURES / "synthetic_referee_policy.json")
    shortlist = rank(POSTING, people, policy, employer="Coastal Lab", today=TODAY)
    quin = next(item for item in shortlist if item.name == "Quin Quarter")
    assert quin.why == "this quarter"
    recent = Person(
        name="Ren Contact",
        company="Far Institute",
        job_title="Accountant",
        last_contact_at="2026-08-01T00:00:00Z",
        enrichment_status="REVIEWED",
    )
    hit = rank("nothing shared", [recent], today=TODAY)
    assert hit[0].why == "recent contact"


def _node(first: str, last: str) -> dict:
    return {
        "name": {"firstName": first, "lastName": last},
        "jobTitle": "Fellow",
        "keywords": "",
        "bio": "",
        "enrichmentStatus": "REVIEWED",
        "coAuthorWithGlen": 0,
        "lastContactAt": None,
        "company": {"name": "Coastal Lab"},
        "noteTargets": {"edges": []},
        "timelineActivities": {"edges": []},
    }


def test_fetch_people_paginates_read_only() -> None:
    seen: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://twenty.example/graphql"
        assert request.headers["authorization"] == "Bearer test-key"
        parsed = json.loads(request.read().decode())
        assert "mutation" not in parsed["query"].lower()
        after = parsed["variables"]["after"]
        seen.append(after)
        node = _node("Ada", "One") if after is None else _node("Bea", "Two")
        return httpx.Response(
            200,
            json={
                "data": {
                    "people": {
                        "pageInfo": {
                            "hasNextPage": after is None,
                            "endCursor": "c1" if after is None else None,
                        },
                        "edges": [{"node": node}],
                    }
                }
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    people = fetch_people("https://twenty.example", "test-key", client=client)
    client.close()
    assert [person.name for person in people] == ["Ada One", "Bea Two"]
    assert seen == [None, "c1"]


def test_fetch_people_http_error_is_runtime_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "no"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(RuntimeError, match="401"):
        fetch_people("https://twenty.example/graphql", "test-key", client=client)
    client.close()
