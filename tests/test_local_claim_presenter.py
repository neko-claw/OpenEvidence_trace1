from __future__ import annotations

from backend.local_claim_presenter import LocalVerifiedClaimPresenter


def _presenter(tmp_path):
    prompt = tmp_path / "prompt.md"
    prompt.write_text("test", encoding="utf-8")
    return LocalVerifiedClaimPresenter(tmp_path / "model", prompt)


def test_local_claim_presentation_rejects_medical_abbreviation_mistranslation(tmp_path) -> None:
    presenter = _presenter(tmp_path)
    source = (
        "DOAC use was associated with a lower risk compared with VKAs "
        "(RR 0.83, 95% CI 0.78-0.88)."
    )
    unsafe = "阿德福韦酯较维生素K拮抗剂风险更低（RR 0.83，95% CI 0.78-0.88）。"
    assert presenter._validate(source, unsafe) is False


def test_local_claim_presentation_requires_numbers_terms_and_direction(tmp_path) -> None:
    presenter = _presenter(tmp_path)
    source = (
        "DOAC use was associated with a lower risk compared with VKAs "
        "(RR 0.83, 95% CI 0.78-0.88)."
    )
    safe = (
        "与维生素K拮抗剂（VKA）相比，直接口服抗凝药（DOAC）与较低风险相关"
        "（RR 0.83，95% CI 0.78-0.88）。"
    )
    changed_number = safe.replace("0.83", "0.73")
    wrong_direction = safe.replace("较低", "较高")
    assert presenter._validate(source, safe) is True
    assert presenter._validate(source, changed_number) is False
    assert presenter._validate(source, wrong_direction) is False


def test_unavailable_local_presenter_falls_back_without_loading(tmp_path) -> None:
    presenter = _presenter(tmp_path)
    assert presenter.available is False
    assert presenter.present("Verified statement.") is None
