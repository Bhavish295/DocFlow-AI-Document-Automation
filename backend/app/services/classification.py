from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

from app.models.document import DocumentType


@dataclass(frozen=True)
class ClassificationResult:
    document_type: str
    confidence: float


class DocumentClassifier(Protocol):
    def classify(self, text: str) -> ClassificationResult:
        """Classify document text. Replaceable by an ML model later."""


PATTERN_WEIGHTS: dict[str, list[tuple[str, float]]] = {
    DocumentType.INVOICE.value: [
        (r"\binvoice\s+number\b", 3.5),
        (r"\binvoice\s+no\.?\b", 3.0),
        (r"\binvoice\b", 2.0),
        (r"\bsubtotal\b", 2.0),
        (r"\btax\b", 1.5),
        (r"\btotal\s+amount\b", 3.0),
        (r"\bamount\s+due\b", 2.5),
        (r"\bdue\s+date\b", 2.5),
        (r"\bbill\s+to\b", 2.0),
    ],
    DocumentType.PURCHASE_ORDER.value: [
        (r"\bpurchase\s+order\b", 3.5),
        (r"\bpo\s+number\b", 3.5),
        (r"\bp\.?o\.?\s*#?\s*\d+", 3.0),
        (r"\border\s+number\b", 2.5),
        (r"\bordered\s+quantity\b", 2.5),
        (r"\bquantity\b", 1.0),
        (r"\bunit\s+price\b", 3.0),
        (r"\border\s+date\b", 2.0),
        (r"\bship\s+to\b", 1.5),
    ],
    DocumentType.GOODS_RECEIPT.value: [
        (r"\bgoods\s+receipt\s+note\b", 5.0),
        (r"\bgoods\s+receipt\b", 4.0),
        (r"\bgoods\s+received\b", 3.5),
        (r"\bgrn\s*(?:number|no\.?|#)\b", 4.5),
        (r"\bgrn\b", 3.0),
        (r"\breceived\s+quantity\b", 4.0),
        (r"\bquantity\s+received\b", 4.0),
        (r"\bqty\s+received\b", 3.0),
        (r"\breceived\s+by\b", 3.0),
        (r"\breceipt\s+status\b", 3.0),
        (r"\breceived\s+items?\b", 3.0),
        (r"\breceived\s+date\b", 2.5),
        (r"\bdate\s+received\b", 2.5),
        (r"\bgrn\s+date\b", 2.5),
        (r"\bdelivery\s+note\b", 2.5),
        (r"\bpurchase\s+order\s+reference\b", 2.0),
        (r"\bsupplier\b", 1.5),
    ],
    DocumentType.CONTRACT.value: [
        (r"\bterms\s+and\s+conditions\b", 3.5),
        (r"\beffective\s+date\b", 3.0),
        (r"\bagreement\b", 2.5),
        (r"\bcontract\b", 2.5),
        (r"\bparties\b", 2.0),
        (r"\btermination\b", 2.5),
        (r"\bwhereas\b", 2.0),
        (r"\bgoverning\s+law\b", 2.5),
    ],
    DocumentType.RECEIPT.value: [
        (r"\breceipt\b", 3.0),
        (r"\bpayment\s+received\b", 3.5),
        (r"\bcash\b", 1.5),
        (r"\bchange\b", 1.5),
        (r"\btransaction\b", 1.5),
        (r"\bthank\s+you\s+for\s+your\s+(purchase|payment)\b", 2.5),
        (r"\bpaid\b", 1.5),
        (r"\bmerchant\b", 1.5),
    ],
    DocumentType.BANK_STATEMENT.value: [
        (r"\baccount\s+statement\b", 3.5),
        (r"\bopening\s+balance\b", 3.5),
        (r"\bclosing\s+balance\b", 3.5),
        (r"\btransaction\s+date\b", 3.0),
        (r"\bdebit\b", 2.0),
        (r"\bcredit\b", 2.0),
        (r"\bbalance\b", 1.5),
        (r"\bstatement\s+period\b", 3.0),
        (r"\baccount\s+number\b", 2.0),
    ],
}

MIN_SCORE = 4.0
MIN_MATCHES = 2


def normalize_text(text: str) -> str:
    normalized = text.lower().replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"[^\w\s.#$/:-]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


class RuleBasedDocumentClassifier:
    """Transparent keyword/pattern classifier. Swap via DocumentClassifier protocol."""

    def classify(self, text: str) -> ClassificationResult:
        normalized = normalize_text(text or "")
        if not normalized:
            return ClassificationResult(document_type=DocumentType.OTHER.value, confidence=0.2)

        scores: dict[str, float] = {}
        matches: dict[str, int] = {}

        for doc_type, patterns in PATTERN_WEIGHTS.items():
            score = 0.0
            hit_count = 0
            for pattern, weight in patterns:
                if re.search(pattern, normalized, flags=re.IGNORECASE):
                    score += weight
                    hit_count += 1
            scores[doc_type] = score
            matches[doc_type] = hit_count

        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        best_type, best_score = ranked[0]
        second_score = ranked[1][1] if len(ranked) > 1 else 0.0
        best_matches = matches[best_type]

        if best_score < MIN_SCORE or best_matches < MIN_MATCHES:
            weak_confidence = round(min(0.49, max(0.2, best_score / 12.0)), 2)
            return ClassificationResult(
                document_type=DocumentType.OTHER.value,
                confidence=weak_confidence,
            )

        confidence = best_score / (best_score + second_score + 1.0)
        confidence = round(min(0.99, max(0.55, confidence)), 2)
        return ClassificationResult(document_type=best_type, confidence=confidence)


def get_default_classifier() -> DocumentClassifier:
    return RuleBasedDocumentClassifier()
