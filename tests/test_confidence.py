from account_intel.run import normalize_confidence, normalized_avg_confidence


def test_normalize_confidence_labels_and_numbers():
    assert normalize_confidence("High") == 0.85
    assert normalize_confidence("Medium") == 0.65
    assert normalize_confidence("Low") == 0.35
    assert normalize_confidence("85%") == 0.85
    assert normalize_confidence("0.9") == 0.9
    assert normalize_confidence(85) == 0.85
    assert normalize_confidence(None, 0.7) == 0.7


def test_normalized_avg_confidence():
    items = [{"confidence": "High"}, {"confidence": 0.5}]
    assert round(normalized_avg_confidence(items), 2) == 0.68
