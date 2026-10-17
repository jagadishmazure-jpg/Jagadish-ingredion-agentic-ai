"""Graph-based 3-way invoice matching flow (agentic ERP: finance & operations).

Business scenario: an invoice arrives for a delivered ingredient order.
The flow performs deterministic 3-way matching — purchase order vs goods
receipt vs invoice — within a tolerance. A clean match schedules payment
and records it; a mismatch is investigated (line items with variances are
flagged) and escalated to a human reviewer.

Topology::

    intake_invoice --> three_way_match --(match)--> schedule_payment --> record_payment --> done
                              |
                              +--(mismatch)--> investigate --> escalate --> done

All numbers are synthetic demo data. Every node is deterministic; the
graph runtime is the small stdlib-only implementation in
``food_ingredients_ai/graph/graph.py``.
"""

from __future__ import annotations

from typing import Any, Dict, List

from food_ingredients_ai.graph.graph import Graph

DEFAULT_INVOICE_ID = "INV-2041"
#: Match tolerance: totals within this fraction of the PO total match.
MATCH_TOLERANCE_FRACTION = 0.01
#: Fixed demo "today" so payment dates stay deterministic across runs.
DEMO_TODAY = "2026-10-11"
PAYMENT_TERMS_DAYS = 30


def _demo_documents(inject_mismatch: bool) -> Dict[str, Any]:
    """Synthetic PO / goods-receipt / invoice triple for citric acid."""
    unit_price = 2.10
    qty_kg = 5000.0
    po_total = round(qty_kg * unit_price, 2)
    gr_total = round(qty_kg * unit_price, 2)  # received in full
    # A mismatching invoice bills 2% over the PO unit price.
    inv_unit = round(unit_price * 1.02, 4) if inject_mismatch else unit_price
    inv_total = round(qty_kg * inv_unit, 2)
    return {
        "purchase_order": {
            "po_id": "PO-CITRIC-ACID-5000",
            "item": "citric acid",
            "qty_kg": qty_kg,
            "unit_price_usd_per_kg": unit_price,
            "total_usd": po_total,
        },
        "goods_receipt": {
            "gr_id": "GR-8817",
            "po_id": "PO-CITRIC-ACID-5000",
            "qty_kg": qty_kg,
            "total_usd": gr_total,
        },
        "invoice": {
            "invoice_id": DEFAULT_INVOICE_ID,
            "po_id": "PO-CITRIC-ACID-5000",
            "lines": [
                {
                    "item": "citric acid",
                    "qty_kg": qty_kg,
                    "unit_price_usd_per_kg": inv_unit,
                    "line_total_usd": inv_total,
                }
            ],
            "total_usd": inv_total,
        },
    }


def _add_days(date_iso: str, days: int) -> str:
    from datetime import date, timedelta

    return (date.fromisoformat(date_iso) + timedelta(days=days)).isoformat()


def run_invoice_graph(
    invoice_id: str = DEFAULT_INVOICE_ID,
    inject_mismatch: bool = True,
) -> Dict[str, Any]:
    """Run the invoice matching flow end-to-end, offline and deterministic.

    ``inject_mismatch`` controls the scenario: ``True`` (default) bills
    the invoice 2% over the PO total so the mismatch branch runs;
    ``False`` produces a clean 3-way match and the payment branch runs.

    Returns the final state: ``matched`` (bool), ``outcome`` (one of
    ``"payment_scheduled"`` or ``"escalated"``), and per-node results.
    """
    docs = _demo_documents(inject_mismatch)
    docs["invoice"]["invoice_id"] = invoice_id

    def intake_invoice(state: Dict[str, Any]) -> Dict[str, Any]:
        return {"documents": docs, "invoice_id": invoice_id}

    def three_way_match(state: Dict[str, Any]) -> Dict[str, Any]:
        po_total = docs["purchase_order"]["total_usd"]
        gr_total = docs["goods_receipt"]["total_usd"]
        inv_total = docs["invoice"]["total_usd"]
        tolerance = round(po_total * MATCH_TOLERANCE_FRACTION, 2)
        variances = {
            "po_vs_gr_usd": round(abs(po_total - gr_total), 2),
            "po_vs_invoice_usd": round(abs(po_total - inv_total), 2),
        }
        matched = all(v <= tolerance for v in variances.values())
        return {
            "match": {
                "po_total_usd": po_total,
                "gr_total_usd": gr_total,
                "invoice_total_usd": inv_total,
                "tolerance_usd": tolerance,
                "variances_usd": variances,
                "matched": matched,
            },
            "matched": matched,
        }

    def schedule_payment(state: Dict[str, Any]) -> Dict[str, Any]:
        inv_total = docs["invoice"]["total_usd"]
        return {
            "payment": {
                "invoice_id": invoice_id,
                "amount_usd": inv_total,
                "scheduled_date": _add_days(DEMO_TODAY, PAYMENT_TERMS_DAYS),
                "terms": f"NET_{PAYMENT_TERMS_DAYS}",
                "status": "scheduled",
            }
        }

    def record_payment(state: Dict[str, Any]) -> Dict[str, Any]:
        payment = state["payment"]
        return {
            "ledger_entry": {
                "entry_id": f"JE-{invoice_id}",
                "debit": "inventory",
                "credit": "accounts_payable",
                "amount_usd": payment["amount_usd"],
                "reference": invoice_id,
            },
            "outcome": "payment_scheduled",
        }

    def investigate(state: Dict[str, Any]) -> Dict[str, Any]:
        match = state["match"]
        flagged: List[Dict[str, Any]] = []
        for line in docs["invoice"]["lines"]:
            po_unit = docs["purchase_order"]["unit_price_usd_per_kg"]
            variance_pct = round(
                abs(line["unit_price_usd_per_kg"] - po_unit) / po_unit * 100, 2
            )
            if variance_pct > MATCH_TOLERANCE_FRACTION * 100:
                flagged.append(
                    {
                        "item": line["item"],
                        "po_unit_price_usd_per_kg": po_unit,
                        "invoice_unit_price_usd_per_kg": line["unit_price_usd_per_kg"],
                        "variance_pct": variance_pct,
                    }
                )
        return {
            "investigation": {
                "flagged_lines": flagged,
                "variances_usd": match["variances_usd"],
                "finding": (
                    f"{len(flagged)} line(s) exceed the "
                    f"{MATCH_TOLERANCE_FRACTION * 100:.0f}% match tolerance"
                ),
            }
        }

    def escalate(state: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "escalation": {
                "to": "accounts_payable_lead (demo)",
                "invoice_id": invoice_id,
                "reason": state["investigation"]["finding"],
                "flagged_lines": state["investigation"]["flagged_lines"],
                "sla": "resolve within 2 business days",
            },
            "outcome": "escalated",
        }

    def _matched(state: Dict[str, Any]) -> bool:
        return bool(state.get("matched"))

    graph = Graph()
    graph.add_node("intake_invoice", intake_invoice)
    graph.add_node("three_way_match", three_way_match)
    graph.add_node("schedule_payment", schedule_payment)
    graph.add_node("record_payment", record_payment)
    graph.add_node("investigate", investigate)
    graph.add_node("escalate", escalate)
    graph.add_edge("intake_invoice", "three_way_match")
    graph.add_edge("schedule_payment", "record_payment")
    graph.add_edge("investigate", "escalate")
    graph.add_conditional("three_way_match", _matched, "schedule_payment", "investigate")
    # "record_payment" and "escalate" have no outgoing edge: terminal nodes.

    return graph.run({"invoice_id": invoice_id, "matched": False})
