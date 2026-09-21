from dossier.lenses import infer_kind, infer_lenses, infer_skills
from dossier.seekers.hits import Hit, merge_hits
from dossier.seekers.quota import apply_quotas


def _hit(uri: str, *, kind: str = "brief", year: int = 2024, score: float = 10) -> Hit:
    return Hit(
        source="mbox",
        uri=uri,
        title=uri,
        preview=uri,
        year=year,
        org="IDDRI",
        kind=kind,
        lenses=("delivered",),
        primary_lens="delivered",
        artifacts=(),
        people=(),
        skills=(),
        score=score,
        hunts=("t",),
        fetch_body=False,
    )


def test_infer_kind_from_folder_and_files() -> None:
    assert infer_kind(folder="Teaching") == "teaching"
    assert infer_kind(channel="gsr_section_ocean", artifacts=("ch.docx",)) == "chapter"
    assert infer_kind(artifacts=("tables.xlsx",)) == "tables"
    assert infer_kind(folder="MCS workshop 1") == "workshop"


def test_skills_and_lenses() -> None:
    skills = infer_skills("BBNJ fisheries brief", "legal analysis.docx")
    assert "science-policy" in skills
    assert "legal-analysis" in skills
    lenses = infer_lenses(
        kind="brief",
        artifacts=("brief.pdf",),
        authored=True,
        skills=skills,
    )
    assert "delivered" in lenses
    assert "contributions" in lenses
    assert "skills" in lenses


def test_quotas_keep_one_per_stratum_then_cap() -> None:
    hits = [_hit(f"a-{i}", kind="brief", year=2024, score=100 - i) for i in range(30)]
    hits += [_hit(f"b-{i}", kind="workshop", year=2019, score=50 - i) for i in range(5)]
    chosen = apply_quotas(hits, per_stratum=3, overall=10)
    kinds = {h.kind for h in chosen}
    assert "brief" in kinds
    assert "workshop" in kinds
    assert sum(1 for h in chosen if h.kind == "brief") == 3
    assert sum(1 for h in chosen if h.kind == "workshop") == 3
    assert len(chosen) == 6


def test_merge_hits_unions_hunts_and_keeps_max_score() -> None:
    a = _hit("u1", score=10)
    b = Hit(
        source="mbox",
        uri="u1",
        title="later",
        preview="longer preview text",
        year=2024,
        org="IDDRI",
        kind="workshop",
        lenses=("contributions",),
        primary_lens="contributions",
        artifacts=("a.pdf",),
        people=(),
        skills=(),
        score=40,
        hunts=("other",),
        fetch_body=True,
    )
    merged = merge_hits([a, b])
    assert len(merged) == 1
    hit = merged[0]
    assert hit.score == 40
    assert "t" in hit.hunts and "other" in hit.hunts
    assert "delivered" in hit.lenses
    assert "contributions" in hit.lenses
    assert hit.fetch_body is False
