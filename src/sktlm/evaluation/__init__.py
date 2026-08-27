"""Shared tokenizer, orthography, and normalized-likelihood evaluation."""

from typing import Any


__all__ = ["LikelihoodMetrics", "normalize_likelihood", "evaluate_tokenizer"]


def __getattr__(name: str) -> Any:
    """Keep diagnostics-only commands from importing the Torch backend."""
    if name in {"LikelihoodMetrics", "normalize_likelihood"}:
        from sktlm.evaluation.likelihood import LikelihoodMetrics, normalize_likelihood

        return {"LikelihoodMetrics": LikelihoodMetrics, "normalize_likelihood": normalize_likelihood}[name]
    if name == "evaluate_tokenizer":
        from sktlm.evaluation.tokenizer import evaluate_tokenizer

        return evaluate_tokenizer
    raise AttributeError(name)
