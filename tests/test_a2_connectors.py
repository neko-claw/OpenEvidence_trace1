from __future__ import annotations

import json

import httpx
import pymupdf
import pytest

from a2.config import HTTPConfig
from a2.connectors.base import A2HTTPClient
from a2.connectors.clinical_trials import ClinicalTrialsConnector
from a2.connectors.europe_pmc import EuropePMCConnector
from a2.connectors.guidelines import GuidelinesConnector
from a2.connectors.pubmed import PubMedConnector
from a2.models.errors import A2ErrorCode, A2Exception
from a2.storage.sqlite_store import SQLiteStore


PUBMED_XML = b"""<?xml version='1.0'?><PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>31452104</PMID><Article><Journal><JournalIssue><PubDate><Year>2019</Year></PubDate></JournalIssue><Title>Methods in molecular biology (Clifton, N.J.)</Title></Journal><ArticleTitle>Molegro Virtual Docker for Docking.</ArticleTitle><Abstract><AbstractText Label='BACKGROUND'>Molegro Virtual Docker is a protein-ligand docking simulation program.</AbstractText><AbstractText>It supports integrated docking simulations.</AbstractText></Abstract><AuthorList><Author><ForeName>Gabriela</ForeName><LastName>Bitencourt-Ferreira</LastName></Author><Author><ForeName>Walter Filgueira</ForeName><LastName>de Azevedo</LastName></Author></AuthorList></Article></MedlineCitation><PubmedData><ArticleIdList><ArticleId IdType='pubmed'>31452104</ArticleId><ArticleId IdType='doi'>10.1007/978-1-4939-9752-7_10</ArticleId></ArticleIdList></PubmedData></PubmedArticle></PubmedArticleSet>"""
PUBMED_NO_ABSTRACT_OR_DOI_XML = b"""<?xml version='1.0'?><PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>30491001</PMID><Article><Journal><JournalIssue><PubDate><Year>1800</Year><Month>Dec</Month></PubDate></JournalIssue><Title>The Medical and physical journal</Title></Journal><ArticleTitle>Mr. Oliphant's Cases.</ArticleTitle><AuthorList><Author><ForeName>Isaac</ForeName><LastName>Oliphant</LastName></Author></AuthorList></Article></MedlineCitation><PubmedData><ArticleIdList><ArticleId IdType='pubmed'>30491001</ArticleId><ArticleId IdType='pmc'>PMC5670692</ArticleId></ArticleIdList></PubmedData></PubmedArticle></PubmedArticleSet>"""

EPMC_RESULT = {
    "resultList": {"result": [{
        "id": "31452104", "source": "MED", "pmid": "31452104",
        "doi": "10.1007/978-1-4939-9752-7_10", "title": "Molegro Virtual Docker for Docking.",
        "abstractText": "Molegro Virtual Docker is a protein-ligand docking simulation program.",
        "firstPublicationDate": "2019-01-01", "isOpenAccess": "N",
        "authorList": {"author": [{"fullName": "Bitencourt-Ferreira G"}, {"fullName": "de Azevedo WF Jr"}]},
    }]}
}

TRIAL_RESULT = {
    "protocolSection": {
        "identificationModule": {"nctId": "NCT03036124", "briefTitle": "Study to Evaluate the Effect of Dapagliflozin on the Incidence of Worsening Heart Failure or Cardiovascular Death", "officialTitle": "Study to Evaluate the Effect of Dapagliflozin on Chronic Heart Failure With Reduced Ejection Fraction"},
        "statusModule": {"overallStatus": "COMPLETED", "startDateStruct": {"date": "2017-02-08"}, "completionDateStruct": {"date": "2019-07-17"}, "studyFirstSubmitDate": "2017-01-26"},
        "descriptionModule": {"briefSummary": "The purpose is to evaluate dapagliflozin in chronic heart failure."},
        "conditionsModule": {"conditions": ["Chronic Heart Failure With Reduced Ejection Fraction (HFrEF)"]},
        "armsInterventionsModule": {"interventions": [{"type": "DRUG", "name": "Dapagliflozin"}]},
        "outcomesModule": {"primaryOutcomes": [{"measure": "Cardiovascular death or worsening heart failure"}]},
        "eligibilityModule": {"eligibilityCriteria": "Adults with documented symptomatic HFrEF."},
        "sponsorCollaboratorsModule": {"leadSponsor": {"name": "AstraZeneca", "class": "INDUSTRY"}},
    }
}


def cfg(retries: int = 0) -> HTTPConfig:
    return HTTPConfig(connect_timeout_seconds=1, read_timeout_seconds=1, total_timeout_seconds=2, retry_count=retries, backoff_seconds=0, user_agent="A2-test")


def client(tmp_path, source: str, handler, retries: int = 0) -> A2HTTPClient:
    return A2HTTPClient(source, cfg(retries), SQLiteStore(tmp_path / f"{source}.sqlite3"), transport=httpx.MockTransport(handler), sleeper=lambda _: None)


def pubmed_handler(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("esearch.fcgi"):
        return httpx.Response(200, json={"esearchresult": {"idlist": ["31452104"]}})
    return httpx.Response(200, content=PUBMED_XML, headers={"content-type": "application/xml"})


def test_pubmed_search_get_multisection_authors_date_and_cache(tmp_path) -> None:
    http = client(tmp_path, "pubmed", pubmed_handler)
    connector = PubMedConnector(http, "https://eutils.ncbi.nlm.nih.gov/entrez/eutils")
    record = connector.search("Molegro Virtual Docker", 1)[0]
    assert record.id == "PMID:31452104" and record.doi == "10.1007/978-1-4939-9752-7_10"
    assert record.authors == ["Gabriela Bitencourt-Ferreira", "Walter Filgueira de Azevedo"]
    assert "BACKGROUND:" in record.abstract_or_chunk and record.published_at.year == 2019
    assert connector.get("31452104").url == "https://pubmed.ncbi.nlm.nih.gov/31452104/"
    before = http.request_count
    connector.search("Molegro Virtual Docker", 1)
    assert http.request_count == before and http.cache_hits >= 2


def test_pubmed_empty_and_error_bodies(tmp_path) -> None:
    empty = PubMedConnector(client(tmp_path, "empty", lambda _: httpx.Response(200, json={"esearchresult": {"idlist": []}})), "https://example.test")
    assert empty.search("no result") == []
    bad = PubMedConnector(client(tmp_path, "bad", lambda _: httpx.Response(200, content=b"<ERROR>bad</ERROR>")), "https://example.test")
    with pytest.raises(A2Exception) as caught:
        bad.get("31452104")
    assert caught.value.error.code is A2ErrorCode.UPSTREAM_PARSE_ERROR


def test_pubmed_public_record_without_abstract_or_doi(tmp_path) -> None:
    connector = PubMedConnector(client(tmp_path, "pubmed-missing", lambda _: httpx.Response(200, content=PUBMED_NO_ABSTRACT_OR_DOI_XML)), "https://example.test")
    record = connector.get("30491001")
    assert record.abstract_or_chunk == "Mr. Oliphant's Cases."
    assert record.doi is None and record.published_at.year == 1800


@pytest.mark.parametrize("body", [b"not xml", b"<Unexpected/>"])
def test_pubmed_malformed_xml(tmp_path, body) -> None:
    connector = PubMedConnector(client(tmp_path, body.hex(), lambda _: httpx.Response(200, content=body)), "https://example.test")
    with pytest.raises(A2Exception): connector.get("31452104")


def test_europe_pmc_normal_missing_optional_pagination_and_cache(tmp_path) -> None:
    http = client(tmp_path, "europe", lambda _: httpx.Response(200, json=EPMC_RESULT))
    connector = EuropePMCConnector(http, "https://www.ebi.ac.uk/europepmc/webservices/rest")
    record = connector.search("EXT_ID:31452104", limit=1, cursor_mark="*")[0]
    assert record.id == "EPMC:MED:31452104" and record.pmid == "31452104"
    connector.search("EXT_ID:31452104", limit=1, cursor_mark="*")
    assert http.cache_hits == 1
    missing = json.loads(json.dumps(EPMC_RESULT))
    missing["resultList"]["result"][0].pop("pmid")
    missing["resultList"]["result"][0].pop("abstractText")
    result = EuropePMCConnector(client(tmp_path, "epmissing", lambda _: httpx.Response(200, json=missing)), "https://example.test").search("x", 1)[0]
    assert result.pmid is None and result.abstract_or_chunk == result.title


def test_europe_pmc_http_and_malformed_json(tmp_path) -> None:
    with pytest.raises(A2Exception): EuropePMCConnector(client(tmp_path, "e404", lambda _: httpx.Response(404)), "https://x.test").search("x")
    with pytest.raises(A2Exception): EuropePMCConnector(client(tmp_path, "ejson", lambda _: httpx.Response(200, content=b"{")), "https://x.test").search("x")


def test_clinical_trials_search_get_optional_status_and_cache(tmp_path) -> None:
    def handler(request):
        return httpx.Response(200, json={"studies": [TRIAL_RESULT], "dataTimestamp": "2026-08-11"}) if request.url.path.endswith("/studies") else httpx.Response(200, json=TRIAL_RESULT)
    http = client(tmp_path, "trials", handler)
    connector = ClinicalTrialsConnector(http, "https://clinicaltrials.gov/api/v2")
    record = connector.search("DAPA-HF", 1, "token")[0]
    assert record.id == "NCT:NCT03036124"
    assert record.source_metadata["overall_status"] == "COMPLETED"
    assert record.source_metadata["interventions"][0]["name"] == "Dapagliflozin"
    assert connector.get("NCT03036124").nct_id == "NCT03036124"
    connector.get("NCT03036124")
    assert http.cache_hits == 1


def test_clinical_trials_missing_optional_malformed_404_timeout(tmp_path) -> None:
    minimal = {"protocolSection": {"identificationModule": {"nctId": "NCT03036124", "briefTitle": "DAPA-HF"}}}
    assert ClinicalTrialsConnector(client(tmp_path, "ctmin", lambda _: httpx.Response(200, json=minimal)), "https://x.test").get("NCT03036124").published_at is None
    with pytest.raises(A2Exception): ClinicalTrialsConnector(client(tmp_path, "ct404", lambda _: httpx.Response(404)), "https://x.test").get("NCT03036124")
    with pytest.raises(A2Exception): ClinicalTrialsConnector(client(tmp_path, "ctbad", lambda _: httpx.Response(200, content=b"x")), "https://x.test").get("NCT03036124")
    def timeout(_: httpx.Request): raise httpx.ReadTimeout("timeout")
    with pytest.raises(A2Exception) as caught: ClinicalTrialsConnector(client(tmp_path, "cttimeout", timeout), "https://x.test").get("NCT03036124")
    assert caught.value.error.code is A2ErrorCode.TIMEOUT


@pytest.mark.parametrize("statuses,expected", [([429, 200], 1), ([500, 200], 1)])
def test_http_retry_for_retryable_status(tmp_path, statuses, expected) -> None:
    calls = iter(statuses)
    http = client(tmp_path, f"retry{statuses[0]}", lambda _: httpx.Response(next(calls), json={"ok": True}), retries=1)
    assert http.get_json("https://example.test")["ok"] is True
    assert http.retry_count == expected


def test_guideline_manifest_pdf_page_missing_unlisted_and_parser(tmp_path) -> None:
    pdf = tmp_path / "fixture.pdf"
    document = pymupdf.open(); page = document.new_page(); page.insert_text((72, 72), "Synthetic parser fixture; not medical evidence."); document.save(pdf); document.close()
    manifest = tmp_path / "a2_guidelines.json"
    manifest.write_text(json.dumps({"manifest_version": "1", "guidelines": [{
        "manifest_id": "fixture-only-not-medical-evidence", "guideline_name": "Synthetic parser fixture",
        "organization": "Test suite", "version": "1", "published_at": None,
        "source_url": None, "local_path": str(pdf), "license_or_usage_note": "Self-generated test fixture",
    }]}), encoding="utf-8")
    connector = GuidelinesConnector(manifest)
    result = connector.search("Synthetic", 1)[0]
    assert result.page == 1 and result.source_metadata["license_or_usage_note"].startswith("Self-generated")
    with pytest.raises(A2Exception): connector.get_page("not-whitelisted", "1", 1)
    pdf.unlink()
    with pytest.raises(A2Exception): connector.search("Synthetic")
    manifest.write_text("not json", encoding="utf-8")
    with pytest.raises(A2Exception): GuidelinesConnector(manifest)
