from __future__ import annotations

import pytest

from sktlm.latent.phonology import (
    HOST_BLOB_CODEC_VERSION,
    Phoneme,
    PhonologicalForm,
    canonical_host_key_utf8_length,
    host_blob_to_key,
    pack_host_key,
    pack_phonological_form,
    unpack_host_blob,
)


def test_cached_form_key_preserves_canonical_identity() -> None:
    form = PhonologicalForm((Phoneme.O, Phoneme.M))
    same = PhonologicalForm((Phoneme.O, Phoneme.M))

    assert form.key == "V_O.C_M"
    assert form == same
    assert hash(form) == hash(same)
    assert PhonologicalForm.from_key(form.key) == form


def test_versioned_host_blob_codec_is_exact_deterministic_and_order_preserving() -> None:
    forms = [PhonologicalForm((phoneme,)) for phoneme in Phoneme]
    forms.extend(
        [
            PhonologicalForm((Phoneme.A, Phoneme.I)),
            PhonologicalForm((Phoneme.K, Phoneme.H, Phoneme.A)),
            PhonologicalForm((Phoneme.O, Phoneme.M)),
            PhonologicalForm((Phoneme.O, Phoneme.ANUSVARA)),
            PhonologicalForm((Phoneme.VOCALIC_R, Phoneme.TTH, Phoneme.AA)),
        ]
    )
    encoded = [pack_phonological_form(form) for form in forms]

    assert HOST_BLOB_CODEC_VERSION == 1
    assert all(payload[0] == HOST_BLOB_CODEC_VERSION for payload in encoded)
    assert len(set(encoded)) == len(forms)
    assert [unpack_host_blob(payload) for payload in encoded] == forms
    assert [host_blob_to_key(payload) for payload in encoded] == [
        form.key for form in forms
    ]
    assert [pack_host_key(form.key) for form in forms] == encoded
    assert [canonical_host_key_utf8_length(payload) for payload in encoded] == [
        len(form.key.encode("utf-8")) for form in forms
    ]
    assert sorted(forms, key=lambda form: form.key) == [
        form for _payload, form in sorted(zip(encoded, forms))
    ]


@pytest.mark.parametrize("payload", [b"", b"\x01", b"\x02\x01", b"\x01\x00", b"\x01\xff"])
def test_host_blob_codec_rejects_corruption(payload: bytes) -> None:
    with pytest.raises(ValueError, match="Packed host|Unsupported packed"):
        unpack_host_blob(payload)
