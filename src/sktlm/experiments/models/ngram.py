from __future__ import annotations

import math
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field


BOS = "<BOS>"
EOS = "<EOS>"
UNK = "<UNK>"


@dataclass(slots=True)
class CharNGramLM:
    """
    Tiny add-alpha character n-gram language model.

    Counts may be integer counts from observed strings or fractional expected
    counts from a latent-lattice E-step.
    """

    order: int = 3
    alpha: float = 0.1

    _ngram_counts: Counter[tuple[str, ...]] = field(
        init=False,
        default_factory=Counter,
    )
    _context_counts: Counter[tuple[str, ...]] = field(
        init=False,
        default_factory=Counter,
    )
    _vocab: set[str] = field(
        init=False,
        default_factory=set,
    )
    _fitted: bool = field(
        init=False,
        default=False,
    )

    def __post_init__(self) -> None:
        if self.order < 1:
            raise ValueError("order must be >= 1.")
        if self.alpha <= 0.0:
            raise ValueError("alpha must be > 0.")

    @property
    def context_size(self) -> int:
        return self.order - 1

    @property
    def vocabulary(self) -> frozenset[str]:
        self._require_fitted()
        return frozenset(self._vocab)

    @property
    def ngram_counts(self) -> dict[tuple[str, ...], float]:
        self._require_fitted()
        return dict(self._ngram_counts)

    @property
    def context_counts(self) -> dict[tuple[str, ...], float]:
        self._require_fitted()
        return dict(self._context_counts)

    def start_context(self) -> tuple[str, ...]:
        return (BOS,) * self.context_size

    @staticmethod
    def _validate_extra_symbols(
        extra_symbols: Iterable[str],
    ) -> tuple[str, ...]:
        symbols = tuple(extra_symbols)

        for symbol in symbols:
            if not isinstance(symbol, str):
                raise TypeError(
                    "extra_symbols must contain strings."
                )
            if len(symbol) != 1:
                raise ValueError(
                    "extra_symbols must contain single Unicode "
                    "characters."
                )

        return symbols

    def fit(
        self,
        texts: Iterable[str],
        *,
        extra_symbols: Iterable[str] = (),
    ) -> "CharNGramLM":
        materialized = tuple(texts)

        if not materialized:
            raise ValueError(
                "Cannot fit CharNGramLM on an empty corpus."
            )

        extra = self._validate_extra_symbols(
            extra_symbols,
        )

        self._ngram_counts.clear()
        self._context_counts.clear()
        self._vocab.clear()
        self._fitted = False

        for text in materialized:
            if not isinstance(text, str):
                raise TypeError(
                    "CharNGramLM.fit() expects an iterable of strings."
                )
            self._vocab.update(text)

        self._vocab.update(extra)
        self._vocab.add(EOS)
        self._vocab.add(UNK)

        for text in materialized:
            context = self.start_context()

            for char in text:
                self._observe(
                    context,
                    char,
                )
                context = self.advance_context(
                    context,
                    char,
                )

            self._observe(
                context,
                EOS,
            )

        self._fitted = True
        return self

    @classmethod
    def fit_corpus(
        cls,
        texts: Iterable[str],
        *,
        order: int = 3,
        alpha: float = 0.1,
        extra_symbols: Iterable[str] = (),
    ) -> "CharNGramLM":
        return cls(
            order=order,
            alpha=alpha,
        ).fit(
            texts,
            extra_symbols=extra_symbols,
        )

    def replace_counts(
        self,
        *,
        ngram_counts: Mapping[
            tuple[str, ...],
            float,
        ],
        context_counts: Mapping[
            tuple[str, ...],
            float,
        ],
        vocabulary: Iterable[str],
    ) -> "CharNGramLM":
        """
        Replace model statistics with non-negative fractional counts.

        This is used by expected-count latent training. Smoothing remains
        controlled by `alpha` in log_prob().
        """
        new_ngram: Counter[tuple[str, ...]] = Counter()
        new_context: Counter[tuple[str, ...]] = Counter()

        for key, value in ngram_counts.items():
            if len(key) != self.order:
                raise ValueError(
                    "ngram count key has wrong order."
                )
            value = float(value)
            if not math.isfinite(value) or value < 0.0:
                raise ValueError(
                    "ngram counts must be finite and non-negative."
                )
            if value:
                new_ngram[key] = value

        for key, value in context_counts.items():
            if len(key) != self.context_size:
                raise ValueError(
                    "context count key has wrong length."
                )
            value = float(value)
            if not math.isfinite(value) or value < 0.0:
                raise ValueError(
                    "context counts must be finite and non-negative."
                )
            if value:
                new_context[key] = value

        vocab = set(vocabulary)
        vocab.add(EOS)
        vocab.add(UNK)

        if not vocab:
            raise ValueError(
                "vocabulary must be non-empty."
            )

        self._ngram_counts = new_ngram
        self._context_counts = new_context
        self._vocab = vocab
        self._fitted = True

        return self

    def _observe(
        self,
        context: tuple[str, ...],
        symbol: str,
    ) -> None:
        self._context_counts[context] += 1.0
        self._ngram_counts[
            context + (symbol,)
        ] += 1.0

    def _require_fitted(self) -> None:
        if not self._fitted:
            raise RuntimeError(
                "CharNGramLM must be fitted before scoring."
            )

    def normalize_symbol(
        self,
        symbol: str,
    ) -> str:
        self._require_fitted()

        if symbol in self._vocab:
            return symbol

        return UNK

    def log_prob(
        self,
        symbol: str,
        context: tuple[str, ...],
    ) -> float:
        """
        Return log P(symbol | context) with add-alpha smoothing.
        """
        self._require_fitted()

        if len(context) != self.context_size:
            raise ValueError(
                f"Expected context of length {self.context_size}, "
                f"got {len(context)}."
            )

        symbol = self.normalize_symbol(symbol)

        numerator = (
            self._ngram_counts[
                context + (symbol,)
            ]
            + self.alpha
        )
        denominator = (
            self._context_counts[context]
            + self.alpha * len(self._vocab)
        )

        return math.log(
            numerator / denominator
        )

    def advance_context(
        self,
        context: tuple[str, ...],
        symbol: str,
    ) -> tuple[str, ...]:
        if len(context) != self.context_size:
            raise ValueError(
                f"Expected context of length {self.context_size}, "
                f"got {len(context)}."
            )

        if self.context_size == 0:
            return ()

        return (
            context
            + (symbol,)
        )[-self.context_size:]

    def score_sequence(
        self,
        text: str,
        *,
        include_eos: bool = True,
    ) -> float:
        """
        Score one complete character sequence from BOS context.
        """
        self._require_fitted()

        context = self.start_context()
        total = 0.0

        for char in text:
            normalized = self.normalize_symbol(
                char,
            )
            total += self.log_prob(
                normalized,
                context,
            )
            context = self.advance_context(
                context,
                normalized,
            )

        if include_eos:
            total += self.log_prob(
                EOS,
                context,
            )

        return total
