from pathlib import Path

import duckdb

from dossier.sources.linkedin import LinkedInSource
from dossier.store import Corpus


def _warehouse(path: Path) -> Path:
    db = path / "catalog.duckdb"
    conn = duckdb.connect(str(db))
    conn.execute("CREATE SCHEMA linkedin")
    conn.execute(
        """
        CREATE TABLE linkedin.positions (
            company_name VARCHAR,
            title VARCHAR,
            description VARCHAR,
            location VARCHAR,
            started_on VARCHAR,
            finished_on VARCHAR
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE linkedin.education (
            school_name VARCHAR,
            degree_name VARCHAR,
            notes VARCHAR,
            start_date VARCHAR,
            end_date VARCHAR
        )
        """
    )
    conn.execute("CREATE TABLE linkedin.skills (name VARCHAR)")
    conn.execute(
        """
        CREATE TABLE linkedin.publications (
            name VARCHAR,
            published_on VARCHAR,
            description VARCHAR,
            publisher VARCHAR,
            url VARCHAR
        )
        """
    )
    conn.execute(
        """
        INSERT INTO linkedin.positions VALUES
        ('Oceana', 'Policy fellow',
         'Led the Oceana BBNJ working group.',
         'Paris', '2022', '2023')
        """
    )
    conn.execute(
        """
        INSERT INTO linkedin.education VALUES
        ('Sciences Po', 'PhD', 'Ocean governance', '2018', '2022')
        """
    )
    conn.execute("INSERT INTO linkedin.skills VALUES ('BBNJ'), ('science policy')")
    conn.execute(
        """
        INSERT INTO linkedin.publications VALUES
        ('Synthetic reef paper', '2021', 'A synthetic paper.', 'Journal',
         'https://example.test/pub')
        """
    )
    conn.close()
    return db


def test_linkedin_reads_four_tables(tmp_path: Path, corpus: Corpus) -> None:
    db = _warehouse(tmp_path)
    src = LinkedInSource()
    assert src.detect(db)
    src.load(db, corpus)
    recs = corpus.records("linkedin")
    uris = {r.uri for r in recs}
    assert "linkedin://positions/0" in uris
    assert "linkedin://education/0" in uris
    assert "linkedin://skills" in uris
    assert "https://example.test/pub" in uris
    pos = next(r for r in recs if r.uri.endswith("positions/0"))
    assert "Oceana" in pos.text
    assert "BBNJ" in pos.text
