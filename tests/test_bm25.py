from retrieval.bm25_index import (
    BM25Index,
    tokenize,
)


def make_documents():
    return [
        {
            "chunk_id": "C001",
            "evidence_id": "E001",
            "title": "Hypertension clinical trial",
            "text": (
                "Clinical trial about "
                "blood pressure."
            ),
            "source_type": "clinicaltrials",
            "stable_id": "nct:NCT00000001",
            "evidence_level": "clinical_trial",
            "population": "Adults with hypertension",
            "intervention": None,
            "comparator": None,
            "outcome": "Blood pressure",
        },
        {
            "chunk_id": "C002",
            "evidence_id": "E002",
            "title": "Dyslipidemia review",
            "text": (
                "Review of lipid outcomes "
                "and dyslipidemia."
            ),
            "source_type": "pubmed",
            "stable_id": "pmid:12345678",
            "evidence_level": "review",
            "population": "Adults with dyslipidemia",
            "intervention": None,
            "comparator": None,
            "outcome": "Lipid outcomes",
        },
        {
            "chunk_id": "C003",
            "evidence_id": "E003",
            "title": "Diabetes observational study",
            "text": (
                "Observational evidence about "
                "glucose and diabetes."
            ),
            "source_type": "pubmed",
            "stable_id": "pmid:87654321",
            "evidence_level": "observational",
            "population": "Adults with diabetes",
            "intervention": None,
            "comparator": None,
            "outcome": "Glucose",
        },
    ]


def test_tokenize_english():
    tokens = tokenize(
        "Hypertension Clinical Trial"
    )

    assert "hypertension" in tokens
    assert "clinical" in tokens
    assert "trial" in tokens


def test_tokenize_stable_id_adds_bare_identifier():
    tokens = tokenize(
        "nct:NCT00000001"
    )

    assert "nct:nct00000001" in tokens
    assert "nct00000001" in tokens


def test_bm25_ranks_dyslipidemia_first():
    index = BM25Index(
        make_documents()
    )

    results = index.search(
        "dyslipidemia lipid outcomes",
        top_k=2,
    )

    assert results
    assert results[0]["evidence_id"] == "E002"


def test_bm25_can_find_exact_nct_id():
    index = BM25Index(
        make_documents()
    )

    results = index.search(
        "NCT00000001",
        top_k=2,
    )

    assert results
    assert results[0]["evidence_id"] == "E001"


def test_bm25_save_and_load(tmp_path):
    index = BM25Index(
        make_documents()
    )

    index.save(tmp_path)

    loaded = BM25Index.load(
        tmp_path
    )

    results = loaded.search(
        "dyslipidemia lipid",
        top_k=1,
    )

    assert results
    assert results[0]["evidence_id"] == "E002"
