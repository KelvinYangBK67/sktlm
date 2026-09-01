from __future__ import annotations

from pathlib import Path

import pytest

from sktlm.experiments.training.latent_lexicon import build_arg_parser
from sktlm.latent.frontend import (
    CueKind,
    iter_observed_segments,
    parse_devanagari_surface,
    parse_iast_surface,
    parse_surface,
)
from sktlm.latent.phonology import parse_iast_form
from sktlm.latent.training import TrainingConfig, load_documents
from sktlm.representations.devanagari import transliterate_iast_to_devanagari
from sktlm.representations.spacing import apply_spacing


def test_default_iast_frontend_path_is_unchanged() -> None:
    text = "devo'pi api ca |"
    assert parse_surface(text) == parse_iast_surface(text)
    assert tuple(iter_observed_segments(text)) == tuple(
        iter_observed_segments(text, script="iast")
    )


@pytest.mark.parametrize(
    ("written", "iast"),
    (
        ("अ", "a"),
        ("क", "ka"),
        ("का", "kā"),
        ("क्", "k"),
        ("क्त", "kta"),
        ("कं", "kaṃ"),
        ("कः", "kaḥ"),
        ("कँ", "kam̐"),
        ("ॐ", "oṃ"),
    ),
)
def test_devanagari_frontend_emits_script_neutral_phonemes(
    written: str,
    iast: str,
) -> None:
    parsed = parse_devanagari_surface(written)
    assert parsed.phonemes == parse_iast_form(iast).symbols
    assert all(0 <= start < end <= len(written) for start, end in parsed.phoneme_spans)


def test_devanagari_cues_and_offsets_are_deterministic() -> None:
    text = "रामो ऽस्ति । ॥"
    first = parse_devanagari_surface(text)
    second = parse_devanagari_surface(text)
    assert first == second
    assert tuple(cue.kind for cue in first.cues) == (
        CueKind.SPACE,
        CueKind.AVAGRAHA,
        CueKind.SPACE,
        CueKind.PUNCTUATION,
        CueKind.SPACE,
        CueKind.PUNCTUATION,
    )


def test_generated_iast_and_devanagari_have_identical_phonology() -> None:
    iast = "rāmo 'sti | tat tvam asi || oṃ"
    devanagari = transliterate_iast_to_devanagari(iast)
    assert parse_iast_surface(iast).phonemes == parse_devanagari_surface(
        devanagari
    ).phonemes


@pytest.mark.parametrize(
    "condition",
    ("surface_word", "legacy_joined", "continuous"),
)
def test_spacing_conditions_preserve_cross_script_phonology(condition: str) -> None:
    iast = "tat tvam asi || rāmo 'sti |"
    devanagari = transliterate_iast_to_devanagari(iast)
    observed_iast = apply_spacing(iast, condition, "iast")
    observed_devanagari = apply_spacing(devanagari, condition, "devanagari")
    assert parse_iast_surface(observed_iast).phonemes == parse_devanagari_surface(
        observed_devanagari
    ).phonemes


def test_all_formal_manifest_cells_select_exactly_240_documents() -> None:
    manifest = Path("data/manifests/representations.csv")
    for script in ("iast", "devanagari"):
        for condition in ("surface_word", "legacy_joined", "continuous"):
            documents = load_documents(
                manifest,
                repo_root=Path("."),
                max_documents=None,
                script=script,
                condition=condition,
            )
            assert len(documents) == 240
            assert len({document.relative_path for document in documents}) == 240


def test_selectors_reject_unsupported_values_and_cli_defaults_remain_iast_surface() -> None:
    with pytest.raises(ValueError, match="unsupported formal script"):
        TrainingConfig(script="unknown")
    with pytest.raises(ValueError, match="unsupported formal condition"):
        TrainingConfig(condition="unknown")
    args = build_arg_parser().parse_args([])
    assert (args.script, args.condition) == ("iast", "surface_word")
