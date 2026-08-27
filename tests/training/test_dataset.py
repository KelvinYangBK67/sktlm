"""Regression tests for the existing token-stream dataset behavior."""

import torch

from sktlm.data.representations.canonical import RepresentedSegment
from sktlm.tokenizers.character import CharacterTokenizer
from sktlm.training.dataset import BlockDataset, SegmentBlockDataset, encode_segments, split_train_val


def test_token_level_train_val_split_is_unchanged() -> None:
    tokens = torch.arange(10)
    train, val = split_train_val(tokens, 0.9)
    assert train.tolist() == list(range(9))
    assert val.tolist() == [9]


def test_block_dataset_is_next_token_shifted() -> None:
    dataset = BlockDataset(torch.arange(6), context_length=3)
    inputs, targets = dataset[1]
    assert inputs.tolist() == [1, 2, 3]
    assert targets.tolist() == [2, 3, 4]


def test_controlled_dataset_never_crosses_segment_boundaries() -> None:
    represented = [
        RepresentedSegment("doc", "seg-a", "train", "abcd", "test", "test", "iast", "observed"),
        RepresentedSegment("doc", "seg-b", "train", "wxyz", "test", "test", "iast", "observed"),
    ]
    tokenizer = CharacterTokenizer.train(item.text for item in represented)
    encoded = encode_segments(represented, tokenizer, prepend_bos=False, append_eos=False)
    dataset = SegmentBlockDataset(encoded, context_length=2)
    decoded_pairs = [
        (tokenizer.decode(inputs.tolist()), tokenizer.decode(targets.tolist()))
        for inputs, targets in (dataset[index] for index in range(len(dataset)))
    ]
    assert decoded_pairs == [("ab", "bc"), ("bc", "cd"), ("wx", "xy"), ("xy", "yz")]
