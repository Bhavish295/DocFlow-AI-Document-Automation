from pathlib import Path



from app.models.document_review import ReviewReason

from app.services.classification import ClassificationResult, RuleBasedDocumentClassifier

from app.services.hybrid_classification import HybridDocumentClassifier, combine_rule_and_ml

from app.services.ml_classification import (

    DEFAULT_TEST_SIZE,

    SUPPORTED_LABELS,

    TfidfLogisticDocumentClassifier,

    dataset_label_counts,

    load_starter_training_examples,

    reset_default_ml_classifier,

    split_examples,

)

from tests.test_classification import (

    BANK_STATEMENT_TEXT,

    CONTRACT_TEXT,

    GOODS_RECEIPT_WITH_PO_TEXT,

    INVOICE_TEXT,

    PURCHASE_ORDER_TEXT,

    RECEIPT_TEXT,

    UNKNOWN_TEXT,

)





def _train_temp_classifier(tmp_path: Path) -> TfidfLogisticDocumentClassifier:

    reset_default_ml_classifier()

    classifier = TfidfLogisticDocumentClassifier(model_dir=tmp_path / "models")

    classifier.train(load_starter_training_examples())

    return classifier





def test_training_dataset_contains_all_seven_labels():

    examples = load_starter_training_examples()

    labels = {item.label for item in examples}

    assert labels == set(SUPPORTED_LABELS)

    assert len(SUPPORTED_LABELS) == 7





def test_training_dataset_is_reasonably_balanced():

    examples = load_starter_training_examples()

    counts = dataset_label_counts(examples)

    values = list(counts.values())

    assert min(values) >= 12

    assert max(values) <= 20

    assert max(values) - min(values) <= 5

    assert 90 <= len(examples) <= 130





def test_training_dataset_loads_with_valid_labels():

    examples = load_starter_training_examples()

    assert len(examples) >= len(SUPPORTED_LABELS)

    labels = {item.label for item in examples}

    assert labels == set(SUPPORTED_LABELS)

    assert all(item.text.strip() for item in examples)





def test_deterministic_train_test_split():

    examples = load_starter_training_examples()

    train_a, test_a = split_examples(examples, test_size=DEFAULT_TEST_SIZE, random_state=42)

    train_b, test_b = split_examples(examples, test_size=DEFAULT_TEST_SIZE, random_state=42)

    assert [item.text for item in train_a] == [item.text for item in train_b]

    assert [item.label for item in test_a] == [item.label for item in test_b]

    train_texts = {item.text for item in train_a}

    test_texts = {item.text for item in test_a}

    assert train_texts.isdisjoint(test_texts)

    assert len(test_a) >= len(SUPPORTED_LABELS)

    assert len(train_a) + len(test_a) == len(examples)





def test_model_trains_saves_and_loads(tmp_path):

    classifier = _train_temp_classifier(tmp_path)

    assert classifier.is_available()

    assert classifier.model_path.exists()



    reloaded = TfidfLogisticDocumentClassifier(model_dir=tmp_path / "models")

    assert reloaded.is_available()

    status = reloaded.get_status()

    assert status.model_available is True

    assert status.training_example_count == len(load_starter_training_examples())

    assert status.supported_labels == list(SUPPORTED_LABELS)

    assert status.evaluation_accuracy is not None

    assert status.evaluation_macro_f1 is not None

    assert status.evaluation_timestamp is not None





def test_evaluation_metrics_are_valid(tmp_path):

    classifier = TfidfLogisticDocumentClassifier(model_dir=tmp_path / "models")

    result = classifier.train(load_starter_training_examples())

    evaluation = result.evaluation

    assert evaluation is not None

    assert 0.0 <= evaluation.accuracy <= 1.0

    assert 0.0 <= evaluation.macro_precision <= 1.0

    assert 0.0 <= evaluation.macro_recall <= 1.0

    assert 0.0 <= evaluation.macro_f1 <= 1.0

    assert set(evaluation.per_class.keys()) == set(SUPPORTED_LABELS)

    for metrics in evaluation.per_class.values():

        assert 0.0 <= metrics["precision"] <= 1.0

        assert 0.0 <= metrics["recall"] <= 1.0

        assert 0.0 <= metrics["f1"] <= 1.0

        assert metrics["support"] >= 0

    matrix = evaluation.confusion_matrix

    assert len(matrix) == len(SUPPORTED_LABELS)

    assert all(len(row) == len(SUPPORTED_LABELS) for row in matrix)

    assert evaluation.train_size + evaluation.test_size == result.example_count

    assert "synthetic" in evaluation.note.lower() or "not production" in evaluation.note.lower()





def test_ml_predicts_supported_document_types(tmp_path):

    classifier = _train_temp_classifier(tmp_path)

    samples = [

        (INVOICE_TEXT, "invoice"),

        (PURCHASE_ORDER_TEXT, "purchase_order"),

        (CONTRACT_TEXT, "contract"),

        (RECEIPT_TEXT, "receipt"),

        (BANK_STATEMENT_TEXT, "bank_statement"),

    ]

    for text, expected in samples:

        result = classifier.predict(text)

        assert result is not None

        assert result.document_type == expected

        assert 0.0 <= result.confidence <= 1.0





def test_ml_handles_unrelated_and_empty_text(tmp_path):

    classifier = _train_temp_classifier(tmp_path)

    other = classifier.predict(UNKNOWN_TEXT)

    assert other is not None

    assert other.document_type == "other"

    assert 0.0 <= other.confidence <= 1.0



    empty = classifier.predict("   ")

    assert empty is not None

    assert empty.document_type == "other"

    assert empty.confidence == 0.2





def test_unavailable_model_falls_back_to_rule_based(tmp_path):

    reset_default_ml_classifier()

    hybrid = HybridDocumentClassifier(

        rule_classifier=RuleBasedDocumentClassifier(),

        ml_classifier=TfidfLogisticDocumentClassifier(model_dir=tmp_path / "empty"),

    )

    result = hybrid.classify_detailed(INVOICE_TEXT)

    assert result.classification_method == "rule_based"

    assert result.document_type == "invoice"

    assert result.ml_type is None

    assert result.ml_confidence is None

    assert result.models_disagreed is False





def test_rule_and_ml_agreement_boosts_confidence():

    rule = ClassificationResult(document_type="invoice", confidence=0.80)

    ml = ClassificationResult(document_type="invoice", confidence=0.90)

    result = combine_rule_and_ml(rule, ml)

    assert result.classification_method == "hybrid_agree"

    assert result.document_type == "invoice"

    assert result.confidence == 0.9  # ((0.8+0.9)/2)+0.05

    assert result.models_disagreed is False





def test_rule_and_ml_disagreement_prefers_stronger_or_other():

    strong = combine_rule_and_ml(

        ClassificationResult(document_type="invoice", confidence=0.90),

        ClassificationResult(document_type="receipt", confidence=0.55),

    )

    assert strong.models_disagreed is True

    assert strong.classification_method == "hybrid_prefer_stronger"

    assert strong.document_type == "invoice"

    assert strong.confidence == 0.765  # 0.90 * 0.85



    uncertain = combine_rule_and_ml(

        ClassificationResult(document_type="invoice", confidence=0.60),

        ClassificationResult(document_type="receipt", confidence=0.58),

    )

    assert uncertain.models_disagreed is True

    assert uncertain.classification_method == "hybrid_uncertain"

    assert uncertain.document_type == "other"

    assert uncertain.confidence <= 0.49



def test_hybrid_prefers_strong_goods_receipt_rule_over_weak_po_ml():
    """Live GRN-vs-PO confusion: clear rule GRN must not become hybrid_uncertain/other."""
    result = combine_rule_and_ml(
        ClassificationResult(document_type="goods_receipt", confidence=0.61),
        ClassificationResult(document_type="purchase_order", confidence=0.32),
    )
    assert result.models_disagreed is True
    assert result.classification_method == "hybrid_prefer_stronger"
    assert result.document_type == "goods_receipt"
    assert result.rule_based_type == "goods_receipt"
    assert result.ml_type == "purchase_order"
    assert result.confidence == 0.5185  # 0.61 * 0.85


def test_hybrid_keeps_uncertain_for_close_non_grn_disagreement():
    result = combine_rule_and_ml(
        ClassificationResult(document_type="contract", confidence=0.62),
        ClassificationResult(document_type="other", confidence=0.55),
    )
    assert result.classification_method == "hybrid_uncertain"
    assert result.document_type == "other"


def test_hybrid_classifies_grn_with_po_reference_as_goods_receipt(tmp_path):
    """End-to-end: rule GRN evidence wins even if ML weakly predicts purchase_order."""

    class StubMl:
        def is_available(self) -> bool:
            return True

        def predict(self, text: str) -> ClassificationResult:
            return ClassificationResult(document_type="purchase_order", confidence=0.32)

    hybrid = HybridDocumentClassifier(
        rule_classifier=RuleBasedDocumentClassifier(),
        ml_classifier=StubMl(),  # type: ignore[arg-type]
    )
    result = hybrid.classify_detailed(GOODS_RECEIPT_WITH_PO_TEXT)
    assert result.document_type == "goods_receipt"
    assert result.rule_based_type == "goods_receipt"
    assert result.ml_type == "purchase_order"
    assert result.classification_method == "hybrid_prefer_stronger"
    assert result.confidence >= 0.50





def test_classification_train_and_status_api(client, tmp_path, monkeypatch):

    from app.core.config import settings

    from app.services.ml_classification import reset_default_ml_classifier



    monkeypatch.setattr(settings, "CLASSIFICATION_MODEL_DIR", str(tmp_path / "api-models"))

    reset_default_ml_classifier()



    status_before = client.get("/api/v1/classification/model-status")

    assert status_before.status_code == 200

    body_before = status_before.json()

    assert body_before["model_available"] is False

    assert body_before["supported_labels"] == list(SUPPORTED_LABELS)

    assert body_before["evaluation_accuracy"] is None

    assert body_before["evaluation_macro_f1"] is None



    trained = client.post("/api/v1/classification/train")

    assert trained.status_code == 200

    body = trained.json()

    assert body["status"] == "trained"

    assert body["example_count"] == len(load_starter_training_examples())

    assert body["model_available"] is True

    assert "invoice" in body["labels"]

    assert body["evaluation"] is not None

    assert 0.0 <= body["evaluation"]["accuracy"] <= 1.0

    assert 0.0 <= body["evaluation"]["macro_f1"] <= 1.0

    assert set(body["evaluation"]["per_class"].keys()) == set(SUPPORTED_LABELS)

    assert len(body["evaluation"]["confusion_matrix"]) == len(SUPPORTED_LABELS)



    status_after = client.get("/api/v1/classification/model-status").json()

    assert status_after["model_available"] is True

    assert status_after["training_example_count"] == body["example_count"]

    assert status_after["evaluation_accuracy"] == body["evaluation"]["accuracy"]

    assert status_after["evaluation_macro_f1"] == body["evaluation"]["macro_f1"]

    assert status_after["evaluation_timestamp"] is not None





def test_classification_api_includes_hybrid_fields(client, monkeypatch, tmp_path):

    import io



    from app.core.config import settings

    from app.services.ml_classification import reset_default_ml_classifier



    monkeypatch.setattr(settings, "CLASSIFICATION_MODEL_DIR", str(tmp_path / "api-models"))

    reset_default_ml_classifier()

    assert client.post("/api/v1/classification/train").status_code == 200



    created = client.post(

        "/api/v1/documents",

        files={"file": ("inv.pdf", io.BytesIO(b"%PDF-1.4 sample"), "application/pdf")},

    ).json()

    monkeypatch.setattr(

        "app.services.text_extraction.extract_selectable_pdf_text",

        lambda _path: INVOICE_TEXT,

    )

    processed = client.post(f"/api/v1/documents/{created['id']}/process")

    assert processed.status_code == 200

    assert processed.json()["document_type"] == "invoice"

    assert processed.json()["classification_method"] in {

        "hybrid_agree",

        "hybrid_prefer_stronger",

        "rule_based",

    }



    classification = client.get(f"/api/v1/documents/{created['id']}/classification")

    assert classification.status_code == 200

    payload = classification.json()

    assert payload["document_type"] == "invoice"

    assert payload["final_type"] == "invoice"

    assert payload["rule_based_type"] == "invoice"

    assert payload["ml_type"] == "invoice"

    assert 0.0 <= payload["ml_confidence"] <= 1.0

    assert payload["classification_method"] == "hybrid_agree"





def test_low_confidence_review_behavior_remains(client):

    import io

    import uuid



    from sqlalchemy import update



    from app.models.document import Document, DocumentStatus, DocumentType

    from app.services.document_review import DocumentReviewService



    created = client.post(

        "/api/v1/documents",

        files={"file": ("low.pdf", io.BytesIO(b"%PDF-1.4 sample"), "application/pdf")},

    ).json()

    db = client.testing_session_local()

    try:

        db.execute(

            update(Document)

            .where(Document.id == uuid.UUID(created["id"]))

            .values(

                status=DocumentStatus.PROCESSED.value,

                document_type=DocumentType.INVOICE.value,

                classification_confidence=0.55,

                extracted_text="invoice content",

                classification_method="rule_based",

            )

        )

        db.commit()

        document = db.get(Document, uuid.UUID(created["id"]))

        DocumentReviewService(db).evaluate_after_processing(document)

        db.commit()

    finally:

        db.close()



    reviews = client.get(

        "/api/v1/reviews",

        params={"reason": ReviewReason.LOW_CLASSIFICATION_CONFIDENCE.value},

    ).json()

    assert reviews["total"] == 1





def test_disagreement_review_reason_is_allowed(client):

    import io

    import uuid



    from app.services.document_review import DocumentReviewService



    created = client.post(

        "/api/v1/documents",

        files={"file": ("disagree.pdf", io.BytesIO(b"%PDF-1.4 sample"), "application/pdf")},

    ).json()

    db = client.testing_session_local()

    try:

        review = DocumentReviewService(db).create_review_if_needed(

            document_id=uuid.UUID(created["id"]),

            reason=ReviewReason.CLASSIFICATION_MODEL_DISAGREEMENT.value,

            priority="medium",

            details="Rule and ML disagreed.",

        )

        db.commit()

        assert review is not None

        assert review.reason == ReviewReason.CLASSIFICATION_MODEL_DISAGREEMENT.value

    finally:

        db.close()




def test_stale_model_is_retrained_on_load(tmp_path):
    import joblib

    from app.core.config import settings

    classifier = _train_temp_classifier(tmp_path)
    payload = joblib.load(classifier.model_path)
    payload["metadata"]["model_version"] = "0.0.1-old"
    joblib.dump(payload, classifier.model_path)

    reloaded = TfidfLogisticDocumentClassifier(model_dir=tmp_path / "models")
    assert reloaded.predict("Invoice No: INV-1 Total due 100") is not None
    assert joblib.load(reloaded.model_path)["metadata"]["model_version"] == (
        settings.CLASSIFICATION_MODEL_VERSION
    )
