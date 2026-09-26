"""Controlled predefined workflow definitions (no arbitrary user code)."""

from __future__ import annotations

from typing import Any


ALLOWED_TRIGGER_TYPES = frozenset(
    {
        "document_processed",
        "invoice_extracted",
        "purchase_order_extracted",
        "goods_receipt_extracted",
        "validation_completed",
        "review_completed",
    }
)

ALLOWED_ACTION_TYPES = frozenset(
    {
        "run_validation",
        "create_review",
        "record_result",
        "mark_workflow_completed",
    }
)

ALLOWED_CONDITION_TYPES = frozenset(
    {
        "classification_confidence_below",
        "extraction_confidence_below",
        "document_type_is",
        "validation_status_is",
        "review_status_is",
        "has_invoice",
        "has_purchase_order",
        "has_related_purchase_order",
        "has_required_invoice_fields",
        "has_required_po_fields",
        "any_of",
        "all_of",
    }
)


PREDEFINED_WORKFLOWS: tuple[dict[str, Any], ...] = (
    {
        "code": "invoice_validation",
        "name": "Invoice Validation Workflow",
        "description": (
            "After an invoice is extracted, validate it against a related purchase order. "
            "Create or reuse a review item on mismatch; record success when matched."
        ),
        "trigger_type": "invoice_extracted",
        "condition_mode": "all",
        "conditions": [
            {"type": "has_invoice"},
            {"type": "has_related_purchase_order"},
        ],
        "actions": [
            {"type": "run_validation", "name": "run_validation"},
            {
                "type": "create_review",
                "name": "create_review_on_mismatch",
                "when": {"validation_status": "mismatch"},
                "params": {
                    "reason": "validation_mismatch",
                    "priority": "high",
                    "details": "Workflow detected an invoice/PO validation mismatch.",
                },
            },
            {"type": "record_result", "name": "record_validation_result"},
            {"type": "mark_workflow_completed", "name": "mark_completed"},
        ],
    },
    {
        "code": "low_confidence_review",
        "name": "Low Confidence Review Workflow",
        "description": (
            "After a document is processed, create a review item when classification "
            "or extraction confidence is below the configured threshold."
        ),
        "trigger_type": "document_processed",
        "condition_mode": "any",
        "conditions": [
            {"type": "classification_confidence_below", "threshold": 0.7},
            {"type": "extraction_confidence_below", "threshold": 0.7},
        ],
        "actions": [
            {
                "type": "create_review",
                "name": "create_low_confidence_review",
                "params": {
                    "reason": "low_classification_confidence",
                    "priority": "medium",
                    "details": (
                        "Workflow detected low classification or extraction confidence "
                        "and queued the document for review."
                    ),
                },
            },
            {"type": "record_result", "name": "record_low_confidence_result"},
            {"type": "mark_workflow_completed", "name": "mark_completed"},
        ],
    },
    {
        "code": "document_review_completion",
        "name": "Document Review Workflow",
        "description": (
            "When a review is approved or rejected, record audit information and "
            "mark the workflow execution complete."
        ),
        "trigger_type": "review_completed",
        "condition_mode": "all",
        "conditions": [
            {"type": "review_status_is", "values": ["approved", "rejected"]},
        ],
        "actions": [
            {"type": "record_result", "name": "record_review_completion"},
            {"type": "mark_workflow_completed", "name": "mark_completed"},
        ],
    },
)


def get_definition_by_code(code: str) -> dict[str, Any] | None:
    for item in PREDEFINED_WORKFLOWS:
        if item["code"] == code:
            return item
    return None


def validate_definition(definition: dict[str, Any]) -> None:
    """Raise ValueError if a definition uses disallowed triggers/actions/conditions."""
    trigger = definition.get("trigger_type")
    if trigger not in ALLOWED_TRIGGER_TYPES:
        raise ValueError(f"Unsupported trigger type: {trigger}")

    for action in definition.get("actions") or []:
        action_type = action.get("type")
        if action_type not in ALLOWED_ACTION_TYPES:
            raise ValueError(f"Unsupported action type: {action_type}")

    def _check_conditions(conditions: list[dict[str, Any]]) -> None:
        for condition in conditions:
            ctype = condition.get("type")
            if ctype not in ALLOWED_CONDITION_TYPES:
                raise ValueError(f"Unsupported condition type: {ctype}")
            if ctype in {"any_of", "all_of"}:
                _check_conditions(condition.get("conditions") or [])

    _check_conditions(list(definition.get("conditions") or []))


for _definition in PREDEFINED_WORKFLOWS:
    validate_definition(_definition)
