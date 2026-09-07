"""Streaming compressed archives for immutable S1M2 piece topology."""

from __future__ import annotations

import json
import marshal
import os
import struct
import sys
import zlib
from array import array
from pathlib import Path
from typing import Any, BinaryIO

from sktlm.latent.phonology import Phoneme
from sktlm.pieces.composed import (
    CompiledSegmentTopology,
    CompiledSharedFormTopology,
)


_MAGIC = b"SKTLM-S1M2-TOPOLOGY\x01"
_UINT32 = struct.Struct("<I")
_PHONEMES = tuple(Phoneme)
_PHONEME_IDS = {phoneme: index for index, phoneme in enumerate(_PHONEMES)}


def _array_from_bytes(typecode: str, payload: bytes) -> array:
    result = array(typecode)
    result.frombytes(payload)
    return result


def _topology_payload(topology: CompiledSharedFormTopology) -> tuple[Any, ...]:
    return (
        topology.max_piece_length,
        topology.parent.tobytes(),
        topology.depth.tobytes(),
        topology.transition_offsets.tobytes(),
        topology.transition_sources.tobytes(),
        topology.transition_piece_ids.tobytes(),
        tuple(
            bytes(_PHONEME_IDS[symbol] for symbol in piece)
            for piece in topology.pieces
        ),
        topology.form_keys,
        topology.endpoint_nodes.tobytes(),
        topology.whole_piece_ids.tobytes(),
    )


def _topology_from_payload(payload: tuple[Any, ...]) -> CompiledSharedFormTopology:
    (
        max_piece_length,
        parent,
        depth,
        transition_offsets,
        transition_sources,
        transition_piece_ids,
        pieces,
        form_keys,
        endpoint_nodes,
        whole_piece_ids,
    ) = payload
    return CompiledSharedFormTopology(
        max_piece_length=int(max_piece_length),
        parent=_array_from_bytes("i", parent),
        depth=_array_from_bytes("I", depth),
        transition_offsets=_array_from_bytes("I", transition_offsets),
        transition_sources=_array_from_bytes("I", transition_sources),
        transition_piece_ids=_array_from_bytes("I", transition_piece_ids),
        pieces=tuple(
            tuple(_PHONEMES[index] for index in item)
            for item in pieces
        ),
        form_keys=tuple(str(item) for item in form_keys),
        endpoint_nodes=_array_from_bytes("I", endpoint_nodes),
        whole_piece_ids=_array_from_bytes("I", whole_piece_ids),
    )


def archive_header(
    *,
    config_signature: str,
    document_index: int,
    relative_path: str,
    freeze_id: str,
) -> dict[str, Any]:
    return {
        "schema_version": "sktlm-s1m2-topology-archive/v1",
        "config_signature": config_signature,
        "document_index": document_index,
        "relative_path": relative_path,
        "freeze_id": freeze_id,
        "byteorder": sys.byteorder,
        "array_item_sizes": {
            code: array(code).itemsize for code in ("i", "I")
        },
        "phoneme_ids": [phoneme.value for phoneme in _PHONEMES],
        "compression": "zlib_level_1_per_segment",
        "mutable_state_stored": False,
    }


class TopologyArchiveWriter:
    """Write one temporary document archive in bounded segment records."""

    def __init__(self, path: Path, header: dict[str, Any]) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle: BinaryIO = path.open("wb")
        header_bytes = json.dumps(
            header,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        self._handle.write(_MAGIC)
        self._handle.write(_UINT32.pack(len(header_bytes)))
        self._handle.write(header_bytes)
        self.records = 0
        self.uncompressed_bytes = 0

    def write(
        self,
        line_number: int,
        segment_index: int,
        topology: CompiledSegmentTopology,
    ) -> None:
        primitive = (
            line_number,
            segment_index,
            topology.factor_ids,
            tuple(
                None if factor is None else _topology_payload(factor)
                for factor in topology.factors
            ),
        )
        raw = marshal.dumps(primitive, 4)
        compressed = zlib.compress(raw, level=1)
        self._handle.write(_UINT32.pack(len(compressed)))
        self._handle.write(compressed)
        self.records += 1
        self.uncompressed_bytes += len(raw)

    def close(self) -> None:
        if self._handle.closed:
            return
        self._handle.flush()
        os.fsync(self._handle.fileno())
        self._handle.close()

    def __enter__(self) -> TopologyArchiveWriter:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if exc_type is not None:
            self._handle.close()
        else:
            self.close()


class TopologyArchiveReader:
    """Read and validate one document archive one segment at a time."""

    def __init__(self, path: Path, expected_header: dict[str, Any]) -> None:
        self.path = path
        self._handle: BinaryIO = path.open("rb")
        try:
            if self._handle.read(len(_MAGIC)) != _MAGIC:
                raise ValueError(f"Invalid topology archive magic: {path}")
            header_size = self._read_size()
            header_payload = self._handle.read(header_size)
            if len(header_payload) != header_size:
                raise ValueError(f"Truncated topology archive header: {path}")
            actual_header = json.loads(header_payload.decode("utf-8"))
            if actual_header != expected_header:
                raise ValueError(f"Topology archive header mismatch: {path}")
        except BaseException:
            self._handle.close()
            raise
        self.records = 0

    def _read_size(self) -> int:
        payload = self._handle.read(_UINT32.size)
        if len(payload) != _UINT32.size:
            raise ValueError(f"Truncated topology archive: {self.path}")
        return _UINT32.unpack(payload)[0]

    def read(
        self,
        line_number: int,
        segment_index: int,
    ) -> CompiledSegmentTopology:
        compressed_size = self._read_size()
        compressed = self._handle.read(compressed_size)
        if len(compressed) != compressed_size:
            raise ValueError(f"Truncated topology record: {self.path}")
        try:
            payload = marshal.loads(zlib.decompress(compressed))
        except (EOFError, TypeError, ValueError, zlib.error) as error:
            raise ValueError(f"Invalid topology record: {self.path}") from error
        stored_line, stored_segment, factor_ids, factors = payload
        if (stored_line, stored_segment) != (line_number, segment_index):
            raise ValueError(
                f"Topology archive traversal mismatch in {self.path}: "
                f"expected {(line_number, segment_index)}, "
                f"found {(stored_line, stored_segment)}"
            )
        self.records += 1
        return CompiledSegmentTopology(
            factor_ids=tuple(str(item) for item in factor_ids),
            factors=tuple(
                None if factor is None else _topology_from_payload(factor)
                for factor in factors
            ),
            reused=True,
        )

    def close(self, *, require_eof: bool = True) -> None:
        if self._handle.closed:
            return
        unused = self._handle.read(1) if require_eof else b""
        self._handle.close()
        if unused:
            raise ValueError(f"Unused topology records remain: {self.path}")

    def __enter__(self) -> TopologyArchiveReader:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close(require_eof=exc_type is None)
