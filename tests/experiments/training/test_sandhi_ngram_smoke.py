from __future__ import annotations

import math

from sktlm.experiments.training.sandhi_ngram_smoke import (
    run_sandhi_ngram_smoke,
)


def test_smoke_pipeline_runs_end_to_end() -> None:
    result = run_sandhi_ngram_smoke()

    assert result.surface == "devo'pi"
    assert result.num_nodes == len("devo'pi") + 1
    assert result.num_edges >= len("devo'pi")
    assert result.num_paths >= 1
    assert math.isfinite(result.marginal_log_likelihood)
    assert math.isfinite(result.viterbi_log_likelihood)


def test_marginal_is_not_below_best_path() -> None:
    result = run_sandhi_ngram_smoke()

    assert (
        result.marginal_log_likelihood
        >= result.viterbi_log_likelihood
    )


def test_default_toy_training_prefers_latent_deva_visarga_api() -> None:
    result = run_sandhi_ngram_smoke()

    assert result.viterbi_uses_sandhi
    assert result.viterbi_latent_text == "devaḥ#api"
    assert result.viterbi_rule_ids


def test_identity_only_unknown_surface_still_has_complete_path() -> None:
    result = run_sandhi_ngram_smoke(
        surface="☃",
    )

    assert result.num_paths == 1
    assert not result.viterbi_uses_sandhi
    assert result.viterbi_latent_text == "☃"


def test_custom_toy_training_can_prefer_identity_path() -> None:
    result = run_sandhi_ngram_smoke(
        surface="devo'pi",
        training_texts=("devo'pi",) * 100,
        order=3,
        alpha=0.01,
    )

    assert result.viterbi_latent_text == "devo'pi"
    assert not result.viterbi_uses_sandhi
