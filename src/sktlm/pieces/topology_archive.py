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
from typing import Any, BinaryIO, Callable

from sktlm.latent.phonology import Phoneme, PhonologicalForm
from sktlm.pieces.composed import (
    CompiledSegmentTopology,
    CompiledSharedFormTopology,
)


_MAGIC = b"SKTLM-S1M2-TOPOLOGY\x01"
_UINT32 = struct.Struct("<I")
_PHONEMES = tuple(Phoneme)
_PHONEME_IDS = {phoneme: index for index, phoneme in enumerate(_PHONEMES)}


class TopologyArchiveError(ValueError):
    """Expected validation failure for a reconstructible topology archive."""


def _array_from_bytes(typecode: str, payload: bytes) -> array:
    if not isinstance(payload, bytes):
        raise TopologyArchiveError("Topology array payload is not bytes.")
    result = array(typecode)
    try:
        result.frombytes(payload)
    except ValueError as error:
        raise TopologyArchiveError("Invalid topology array byte length.") from error
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
    if not isinstance(payload, tuple) or len(payload) != 10:
        raise TopologyArchiveError("Invalid shared topology payload shape.")
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
    try:
        maximum = int(max_piece_length)
        parents = _array_from_bytes("i", parent)
        depths = _array_from_bytes("I", depth)
        offsets = _array_from_bytes("I", transition_offsets)
        sources = _array_from_bytes("I", transition_sources)
        transition_ids = _array_from_bytes("I", transition_piece_ids)
        decoded_pieces = tuple(
            tuple(_PHONEMES[index] for index in item)
            for item in pieces
        )
        if not all(isinstance(item, str) for item in form_keys):
            raise TopologyArchiveError("Invalid topology form-key type.")
        keys = tuple(form_keys)
        endpoints = _array_from_bytes("I", endpoint_nodes)
        whole_ids = _array_from_bytes("I", whole_piece_ids)
    except (IndexError, TypeError, ValueError) as error:
        if isinstance(error, TopologyArchiveError):
            raise
        raise TopologyArchiveError("Invalid shared topology values.") from error

    node_count = len(parents)
    transition_count = len(sources)
    if maximum < 1 or node_count < 1:
        raise TopologyArchiveError("Invalid topology size or piece bound.")
    if len(depths) != node_count or len(offsets) != node_count:
        raise TopologyArchiveError("Inconsistent topology node arrays.")
    if parents[0] != -1 or depths[0] != 0 or offsets[0] != 0:
        raise TopologyArchiveError("Invalid topology root node.")
    if len(transition_ids) != transition_count or offsets[-1] != transition_count:
        raise TopologyArchiveError("Inconsistent topology transition arrays.")
    if any(offsets[index] > offsets[index + 1] for index in range(node_count - 1)):
        raise TopologyArchiveError("Topology transition offsets are not monotone.")
    if any(parent < 0 or parent >= index for index, parent in enumerate(parents[1:], 1)):
        raise TopologyArchiveError("Invalid topology parent index.")
    if any(
        depths[index] != depths[parents[index]] + 1
        for index in range(1, node_count)
    ):
        raise TopologyArchiveError("Invalid topology node depth.")
    if any(source >= node_count for source in sources):
        raise TopologyArchiveError("Invalid topology transition source.")
    if any(piece_id >= len(decoded_pieces) for piece_id in transition_ids):
        raise TopologyArchiveError("Invalid topology transition piece ID.")
    if any(not piece for piece in decoded_pieces):
        raise TopologyArchiveError("Empty topology piece.")
    node_symbols: list[tuple[Phoneme, ...]] = [()]
    for node_index in range(1, node_count):
        start = offsets[node_index - 1]
        end = offsets[node_index]
        if end - start != min(depths[node_index], maximum):
            raise TopologyArchiveError("Invalid topology transition count.")
        singleton_symbols = [
            decoded_pieces[transition_ids[transition_index]]
            for transition_index in range(start, end)
            if sources[transition_index] == parents[node_index]
        ]
        if len(singleton_symbols) != 1 or len(singleton_symbols[0]) != 1:
            raise TopologyArchiveError("Invalid topology parent transition.")
        node_symbols.append(
            node_symbols[parents[node_index]] + singleton_symbols[0]
        )
        for transition_index in range(start, end):
            source = sources[transition_index]
            piece_id = transition_ids[transition_index]
            piece_length = depths[node_index] - depths[source]
            if (
                source >= node_index
                or piece_length < 1
                or piece_length > maximum
                or piece_length != len(decoded_pieces[piece_id])
            ):
                raise TopologyArchiveError("Invalid topology transition structure.")
            if node_symbols[source] + decoded_pieces[piece_id] != node_symbols[node_index]:
                raise TopologyArchiveError("Inconsistent topology transition symbols.")
    if len(keys) != len(endpoints) or len(keys) != len(whole_ids):
        raise TopologyArchiveError("Inconsistent topology endpoint arrays.")
    if any(endpoint >= node_count for endpoint in endpoints):
        raise TopologyArchiveError("Invalid topology endpoint node.")
    if any(piece_id >= len(decoded_pieces) for piece_id in whole_ids):
        raise TopologyArchiveError("Invalid topology whole-piece ID.")
    for key, endpoint, whole_id in zip(keys, endpoints, whole_ids, strict=True):
        endpoint_symbols = node_symbols[endpoint]
        if (
            not endpoint_symbols
            or PhonologicalForm(endpoint_symbols).key != key
            or decoded_pieces[whole_id] != endpoint_symbols
        ):
            raise TopologyArchiveError("Invalid topology form endpoint.")

    return CompiledSharedFormTopology(
        max_piece_length=maximum,
        parent=parents,
        depth=depths,
        transition_offsets=offsets,
        transition_sources=sources,
        transition_piece_ids=transition_ids,
        pieces=decoded_pieces,
        form_keys=keys,
        endpoint_nodes=endpoints,
        whole_piece_ids=whole_ids,
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
                raise TopologyArchiveError(f"Invalid topology archive magic: {path}")
            header_size = self._read_size()
            header_payload = self._handle.read(header_size)
            if len(header_payload) != header_size:
                raise TopologyArchiveError(f"Truncated topology archive header: {path}")
            try:
                actual_header = json.loads(header_payload.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise TopologyArchiveError(
                    f"Invalid topology archive header: {path}"
                ) from error
            if actual_header != expected_header:
                raise TopologyArchiveError(
                    f"Topology archive header mismatch: {path}"
                )
        except BaseException:
            self._handle.close()
            raise
        self.records = 0

    def _read_size(self) -> int:
        payload = self._handle.read(_UINT32.size)
        if len(payload) != _UINT32.size:
            raise TopologyArchiveError(f"Truncated topology archive: {self.path}")
        return _UINT32.unpack(payload)[0]

    def skip_records(self, count: int) -> None:
        """Seek over complete framed records without decoding their payloads."""

        if count < 0:
            raise ValueError("Topology record skip count must be nonnegative.")
        file_size = os.fstat(self._handle.fileno()).st_size
        for _ in range(count):
            compressed_size = self._read_size()
            next_offset = self._handle.tell() + compressed_size
            if next_offset > file_size:
                raise TopologyArchiveError(
                    f"Truncated topology record: {self.path}"
                )
            self._handle.seek(compressed_size, os.SEEK_CUR)

    def read(
        self,
        line_number: int,
        segment_index: int,
    ) -> CompiledSegmentTopology:
        compressed_size = self._read_size()
        compressed = self._handle.read(compressed_size)
        if len(compressed) != compressed_size:
            raise TopologyArchiveError(f"Truncated topology record: {self.path}")
        try:
            payload = marshal.loads(zlib.decompress(compressed))
        except (EOFError, TypeError, ValueError, zlib.error) as error:
            raise TopologyArchiveError(
                f"Invalid topology record: {self.path}"
            ) from error
        if not isinstance(payload, tuple) or len(payload) != 4:
            raise TopologyArchiveError(f"Invalid topology record shape: {self.path}")
        stored_line, stored_segment, factor_ids, factors = payload
        if (
            not isinstance(stored_line, int)
            or not isinstance(stored_segment, int)
            or not isinstance(factor_ids, tuple)
            or not isinstance(factors, tuple)
            or len(factor_ids) != len(factors)
            or not all(isinstance(item, str) for item in factor_ids)
        ):
            raise TopologyArchiveError(f"Invalid topology record values: {self.path}")
        if (stored_line, stored_segment) != (line_number, segment_index):
            raise TopologyArchiveError(
                f"Topology archive traversal mismatch in {self.path}: "
                f"expected {(line_number, segment_index)}, "
                f"found {(stored_line, stored_segment)}"
            )
        self.records += 1
        try:
            return CompiledSegmentTopology(
                factor_ids=factor_ids,
                factors=tuple(
                    None if factor is None else _topology_from_payload(factor)
                    for factor in factors
                ),
                reused=True,
            )
        except (TypeError, ValueError) as error:
            if isinstance(error, TopologyArchiveError):
                raise
            raise TopologyArchiveError(
                f"Invalid topology record structure: {self.path}"
            ) from error

    def close(self, *, require_eof: bool = True) -> None:
        if self._handle.closed:
            return
        unused = self._handle.read(1) if require_eof else b""
        self._handle.close()
        if unused:
            raise TopologyArchiveError(
                f"Unused topology records remain: {self.path}"
            )

    def __enter__(self) -> TopologyArchiveReader:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close(require_eof=exc_type is None)


class ReconstructibleTopologyArchiveReader:
    """Repair only expected cache failures, then resume the current document.

    The caller supplies deterministic reconstruction from frozen input and fixed
    structural configuration.  Previously consumed record identities are kept
    only for the current document so a mid-stream repair can replay to the exact
    position without retaining any topology or mutable scientific state.
    """

    def __init__(
        self,
        path: Path,
        expected_header: dict[str, Any],
        rebuild: Callable[[BaseException], None],
    ) -> None:
        self.path = path
        self.expected_header = expected_header
        self._rebuild = rebuild
        self._history: list[tuple[int, int]] = []
        self._repairs = 0
        self._reader = self._open_with_repair()

    @property
    def records(self) -> int:
        return len(self._history)

    @property
    def repairs(self) -> int:
        return self._repairs

    def _open_with_repair(self) -> TopologyArchiveReader:
        try:
            return TopologyArchiveReader(self.path, self.expected_header)
        except (FileNotFoundError, TopologyArchiveError) as error:
            self._repair(error)
            return TopologyArchiveReader(self.path, self.expected_header)

    def _repair(self, error: BaseException) -> None:
        if self._repairs:
            raise TopologyArchiveError(
                f"Rebuilt topology archive is invalid: {self.path}"
            ) from error
        self._repairs += 1
        self._rebuild(error)

    def _reopen_and_replay(self, error: BaseException) -> None:
        self._reader.close(require_eof=False)
        self._repair(error)
        self._reader = TopologyArchiveReader(self.path, self.expected_header)
        for line_number, segment_index in self._history:
            self._reader.read(line_number, segment_index)

    def read(self, line_number: int, segment_index: int) -> CompiledSegmentTopology:
        try:
            topology = self._reader.read(line_number, segment_index)
        except TopologyArchiveError as error:
            self._reopen_and_replay(error)
            topology = self._reader.read(line_number, segment_index)
        self._history.append((line_number, segment_index))
        return topology

    def close(self, *, require_eof: bool = True) -> None:
        if not require_eof:
            self._reader.close(require_eof=False)
            return
        try:
            self._reader.close()
        except TopologyArchiveError as error:
            self._reopen_and_replay(error)
            self._reader.close()

    def __enter__(self) -> ReconstructibleTopologyArchiveReader:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close(require_eof=exc_type is None)
