"""Read People, notes, and timeline counts from Twenty. Never writes."""

from __future__ import annotations

import httpx

from dossier.referees.rank import Person

_QUERY = """
query RefereePeople($after: String) {
  people(first: 60, after: $after) {
    pageInfo { hasNextPage endCursor }
    edges {
      node {
        name { firstName lastName }
        jobTitle
        keywords
        bio
        enrichmentStatus
        coAuthorWithGlen
        lastContactAt
        company { name }
        noteTargets(first: 8) {
          edges { node { note { bodyV2 { markdown } } } }
        }
        timelineActivities(first: 1) {
          edges { node { id } }
        }
      }
    }
  }
}
"""

_MAX_PAGES = 40


def fetch_people(url: str, key: str, *, client: httpx.Client | None = None) -> list[Person]:
    endpoint = _graphql_url(url)
    headers = {"Authorization": f"Bearer {key}"}
    own_client = client is None
    http = client or httpx.Client(timeout=30.0)
    try:
        people: list[Person] = []
        after: str | None = None
        for _ in range(_MAX_PAGES):
            payload = _post(http, endpoint, headers, after)
            people.extend(people_from_payload(payload))
            page = (payload.get("data") or {}).get("people") or {}
            info = page.get("pageInfo") or {}
            if not info.get("hasNextPage"):
                return people
            after = info.get("endCursor")
            if not after:
                return people
        return people
    finally:
        if own_client:
            http.close()


def people_from_payload(payload: dict) -> list[Person]:
    people = (payload.get("data") or {}).get("people") or {}
    edges = people.get("edges") or []
    return [_person_from_node(edge.get("node") or {}) for edge in edges]


def _graphql_url(url: str) -> str:
    root = url.strip().rstrip("/")
    if root.endswith("/graphql"):
        return root
    return f"{root}/graphql"


def _post(
    client: httpx.Client,
    endpoint: str,
    headers: dict[str, str],
    after: str | None,
) -> dict:
    try:
        response = client.post(
            endpoint,
            headers=headers,
            json={"query": _QUERY, "variables": {"after": after}},
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(f"Twenty read failed ({exc.response.status_code})") from exc
    except httpx.HTTPError as exc:
        raise RuntimeError("Twenty read failed") from exc
    payload = response.json()
    errors = payload.get("errors")
    if errors:
        message = errors[0].get("message", "Twenty query failed")
        raise RuntimeError(message)
    return payload


def _person_from_node(node: dict) -> Person:
    name = node.get("name") or {}
    full = " ".join(
        part.strip()
        for part in (str(name.get("firstName") or ""), str(name.get("lastName") or ""))
        if part and str(part).strip()
    )
    company = node.get("company") or {}
    coauthor = node.get("coAuthorWithGlen") or 0
    return Person(
        name=full,
        company=str(company.get("name") or ""),
        job_title=str(node.get("jobTitle") or ""),
        keywords=str(node.get("keywords") or ""),
        bio=str(node.get("bio") or ""),
        note=_notes(node),
        enrichment_status=str(node.get("enrichmentStatus") or ""),
        co_author_with_glen=int(coauthor),
        last_contact_at=node.get("lastContactAt") or None,
        timeline_count=_timeline_count(node),
    )


def _notes(node: dict) -> str:
    edges = ((node.get("noteTargets") or {}).get("edges")) or []
    parts: list[str] = []
    for edge in edges:
        note = (edge.get("node") or {}).get("note") or {}
        body = (note.get("bodyV2") or {}).get("markdown") or ""
        text = str(body).strip()
        if text:
            parts.append(text)
    return "\n".join(parts)


def _timeline_count(node: dict) -> int:
    edges = ((node.get("timelineActivities") or {}).get("edges")) or []
    return len(edges)
