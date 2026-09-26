"""Deterministic hybrid classification: rule-based + optional local ML."""

from __future__ import annotations

from dataclasses import dataclass

from app.models.document import DocumentType
from app.services.classification import ClassificationResult, DocumentClassifier, RuleBasedDocumentClassifier
from app.services.ml_classification import TfidfLogisticDocumentClassifier, get_default_ml_classifier


# Decision thresholds for combining rule-based and ML predictions.
AGREE_CONFIDENCE_BOOST = 0.05
DISAGREE_CONFIDENCE_FACTOR = 0.85
STRONG_CONFIDENCE_MIN = 0.70
STRONG_MARGIN_MIN = 0.15
UNCERTAIN_CONFIDENCE_CAP = 0.49


@dataclass(frozen=True)
class HybridClassificationResult:
    """Final classification plus transparent rule/ML evidence."""

    document_type: str
    confidence: float
    classification_method: str
    rule_based_type: str
    rule_based_confidence: float
    ml_type: str | None
    ml_confidence: float | None
    models_disagreed: bool

    def as_legacy(self) -> ClassificationResult:
        return ClassificationResult(
            document_type=self.document_type,
            confidence=self.confidence,
        )


def combine_rule_and_ml(
    rule: ClassificationResult,
    ml: ClassificationResult | None,
) -> HybridClassificationResult:
    """Combine rule-based and ML predictions with an explicit deterministic policy.

    Policy:
    1. Empty/missing ML -> use rule-based only (`rule_based`).
    2. Same label -> average confidences and add a small agreement boost (`hybrid_agree`).
    3. Different labels:
       - If the stronger side has confidence >= 0.70 and leads by >= 0.15,
         prefer that label and multiply confidence by 0.85 (`hybrid_prefer_stronger`).
       - Otherwise classify as `other` with capped low confidence (`hybrid_uncertain`).
    """
    if ml is None:
        return HybridClassificationResult(
            document_type=rule.document_type,
            confidence=_clamp(rule.confidence),
            classification_method="rule_based",
            rule_based_type=rule.document_type,
            rule_based_confidence=_clamp(rule.confidence),
            ml_type=None,
            ml_confidence=None,
            models_disagreed=False,
        )

    rule_type = rule.document_type
    rule_conf = _clamp(rule.confidence)
    ml_type = ml.document_type
    ml_conf = _clamp(ml.confidence)

    if rule_type == ml_type:
        combined = min(0.99, ((rule_conf + ml_conf) / 2.0) + AGREE_CONFIDENCE_BOOST)
        return HybridClassificationResult(
            document_type=rule_type,
            confidence=_clamp(combined),
            classification_method="hybrid_agree",
            rule_based_type=rule_type,
            rule_based_confidence=rule_conf,
            ml_type=ml_type,
            ml_confidence=ml_conf,
            models_disagreed=False,
        )

    if rule_conf >= ml_conf:
        stronger_type, stronger_conf = rule_type, rule_conf
        weaker_conf = ml_conf
    else:
        stronger_type, stronger_conf = ml_type, ml_conf
        weaker_conf = rule_conf

    margin = stronger_conf - weaker_conf
    if stronger_conf >= STRONG_CONFIDENCE_MIN and margin >= STRONG_MARGIN_MIN:
        preferred = min(0.99, stronger_conf * DISAGREE_CONFIDENCE_FACTOR)
        return HybridClassificationResult(
            document_type=stronger_type,
            confidence=_clamp(preferred),
            classification_method="hybrid_prefer_stronger",
            rule_based_type=rule_type,
            rule_based_confidence=rule_conf,
            ml_type=ml_type,
            ml_confidence=ml_conf,
            models_disagreed=True,
        )

    uncertain = min(UNCERTAIN_CONFIDENCE_CAP, max(rule_conf, ml_conf) * 0.5)
    return HybridClassificationResult(
        document_type=DocumentType.OTHER.value,
        confidence=_clamp(uncertain),
        classification_method="hybrid_uncertain",
        rule_based_type=rule_type,
        rule_based_confidence=rule_conf,
        ml_type=ml_type,
        ml_confidence=ml_conf,
        models_disagreed=True,
    )


class HybridDocumentClassifier:
    """Runs rule-based classification and optionally blends a local ML prediction."""

    def __init__(
        self,
        rule_classifier: DocumentClassifier | None = None,
        ml_classifier: TfidfLogisticDocumentClassifier | None = None,
    ) -> None:
        self.rule_classifier = rule_classifier or RuleBasedDocumentClassifier()
        self.ml_classifier = ml_classifier if ml_classifier is not None else get_default_ml_classifier()

    def classify_detailed(self, text: str) -> HybridClassificationResult:
        rule = self.rule_classifier.classify(text or "")
        ml_result: ClassificationResult | None = None
        if self.ml_classifier.is_available():
            try:
                ml_result = self.ml_classifier.predict(text or "")
            except Exception:
                ml_result = None
        return combine_rule_and_ml(rule, ml_result)

    def classify(self, text: str) -> ClassificationResult:
        return self.classify_detailed(text).as_legacy()


def _clamp(value: float) -> float:
    return round(min(1.0, max(0.0, float(value))), 4)
