from __future__ import annotations

from sktlm.latent.phonology import Phoneme, PhonologicalForm


def test_cached_form_key_preserves_canonical_identity() -> None:
    form = PhonologicalForm((Phoneme.O, Phoneme.M))
    same = PhonologicalForm((Phoneme.O, Phoneme.M))

    assert form.key == "V_O.C_M"
    assert form == same
    assert hash(form) == hash(same)
    assert PhonologicalForm.from_key(form.key) == form
