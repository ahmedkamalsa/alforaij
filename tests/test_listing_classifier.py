from backend.services.listing_classifier import ListingClassifier


def test_classifier_tolerates_missing_numeric_fields():
    classifier = ListingClassifier()

    result = classifier.classify_listing({
        "id": "missing-numbers",
        "title": "house for sale",
        "description": "",
        "price": None,
        "space": None,
        "opportunityScore": None,
        "movement": None,
        "evidenceCount": None,
        "transaction": "sell",
        "source": "market",
    })

    assert result.listing_id == "missing-numbers"
    assert result.classifications["priority"]
    assert result.classifications["trust_level"]
