"""Generate expanded synthetic classification starter dataset (run once)."""

from __future__ import annotations

import json
from pathlib import Path

invoice = [
    "TAX INVOICE Invoice Number INV-4401 Bill To Demo Client Subtotal 1200.00 Tax 120.00 Total Amount 1320.00 Amount Due 1320.00 Due Date 15 April 2026 Currency USD",
    "Invoice No. 8821 Vendor Supplies Co Bill To Accounts Payable Subtotal 450.50 Sales Tax 45.05 Grand Total 495.55 Payment Terms Net 30 Amount Due",
    "Commercial Invoice Invoice Number ABC-19 Bill To North Office Subtotal 980 Tax Amount 98 Total Amount Due 1078 Currency EUR Vendor Demo Traders",
    "Invoice Invoice # 3002 Billed To Local Services Sub Total 75.00 VAT 7.50 Amount Due 82.50 Due Date next month Invoice Date 02 March 2026",
    "Invoice Number INV-77 Bill To Training Desk Subtotal 210 Tax 21 Total Amount 231 Amount Due now Currency PKR",
    "Customer Invoice INV-9012 Bill To Facilities Team Subtotal 1550.00 Tax 155.00 Total 1705.00 Due Date 30 days Currency GBP",
    "Invoice Number SI-204 Bill To Purchasing Desk Subtotal 88.40 Tax 8.84 Total Amount 97.24 Amount Due Vendor Demo Print Shop",
    "Tax Invoice INV-5560 Bill To Warehouse Admin Subtotal 3200 Sales Tax 320 Grand Total 3520 Due Date 10 May 2026 Currency USD",
    "Invoice No INV-1188 Vendor Office Essentials Bill To Finance Subtotal 64.00 VAT 6.40 Total Amount Due 70.40 Payment Terms COD",
    "Service Invoice Invoice Number INV-334 Bill To Marketing Ops Subtotal 499.00 Tax 49.90 Amount Due 548.90 Due Date end of month",
    "Invoice Invoice Number INV-6701 Bill To Legal Review Subtotal 140 Tax 14 Total 154 Currency USD Amount Due",
    "Billing Invoice INV-2210 Bill To Project Alpha Subtotal 2100.75 Tax Amount 210.08 Total Amount 2310.83 Due Date 22 June 2026",
    "Invoice Number INV-808 Bill To Support Desk Subtotal 36 Tax 3.60 Total Amount Due 39.60 Vendor Demo Cloud Notes",
    "Invoice INV-9912 Bill To Research Lab Subtotal 875.00 VAT 87.50 Grand Total 962.50 Currency EUR Due Date Net 15",
    "Tax Invoice Number INV-450 Bill To Operations Hub Subtotal 1800 Tax 180 Total Amount 1980 Amount Due Currency PKR",
    "Invoice No. INV-6060 Bill To Design Studio Subtotal 250.00 Tax 25.00 Total Amount Due 275.00 Due Date 05 July 2026",
    "Commercial Invoice INV-777 Bill To Logistics Desk Subtotal 945 Tax 94.50 Amount Due 1039.50 Vendor Demo Freight Demo",
    "Invoice Number INV-3120 Bill To Admin Pool Subtotal 120 Tax 12 Total 132 Currency USD Payment Terms Net 45 Amount Due",
]

purchase_order = [
    "PURCHASE ORDER PO Number PO-9001 Order Date 01 March 2026 Quantity 20 Unit Price 15.00 Ship To Warehouse A Ordered By Procurement Total 300.00",
    "Purchase Order PO No. PO-4412 Order Number ORD-88 Quantity 5 Unit Price 99.00 Ship To Dock 2 Order Date 12 Feb 2026 Supplier Demo Parts",
    "P.O. Number PO-12 Purchase Order for office chairs Quantity 8 Unit Price 120 Ship To Facilities Order Date today Delivery Terms FOB",
    "Purchase Order Form PO Number PO-7788 Quantity 100 Unit Price 2.50 Ship To Store Room Order Number 55 Supplier Catalog Demo",
    "Authorized Purchase Order PO Number PO-331 Quantity 3 Unit Price 400.00 Ship To Lab B Order Date 2026-01-09 Delivery Terms prepaid",
    "Purchase Order PO-2201 Vendor Demo Hardware Quantity 12 Unit Price 45.00 Ship To Receiving Bay Order Date 18 April 2026 Total 540",
    "PO Number PO-8840 Purchase Order Quantity 2 Unit Price 1250 Ship To Data Center Delivery Terms Net 30 Order Date 03 May 2026",
    "Purchase Order PO Number PO-1009 Supplier Demo Paper Co Quantity 500 Unit Price 0.20 Ship To Print Room Ordered By Admin",
    "PO No PO-5566 Purchase Order Order Number REQ-44 Quantity 15 Unit Price 18.75 Ship To North Campus Delivery Terms collect",
    "Purchase Order Form PO-670 Quantity 7 Unit Price 60.00 Ship To Workshop Supplier Demo Tools Order Date 11 June 2026",
    "Purchase Order PO Number PO-909 Quantity 40 Unit Price 9.50 Ship To Cafeteria Store Delivery Terms door delivery",
    "PO Number PO-4141 Purchase Order Quantity 1 Unit Price 899.00 Ship To IT Closet Order Date 28 Feb 2026 Supplier Demo Soft",
    "Purchase Order PO-3030 Order Number ORD-19 Quantity 25 Unit Price 4.00 Ship To Classroom A Delivery Terms same day",
    "Authorized PO Number PO-1717 Purchase Order Quantity 9 Unit Price 33.00 Ship To Clinic Store Vendor Demo Med Supply",
    "Purchase Order PO Number PO-2626 Quantity 60 Unit Price 1.15 Ship To Mail Room Order Date 09 July 2026 Delivery Terms Net 10",
    "PO No. PO-8181 Purchase Order Supplier Demo Apparel Quantity 30 Unit Price 12.00 Ship To Event Desk Ordered By Ops",
    "Purchase Order Form PO-505 Quantity 4 Unit Price 210.00 Ship To Studio B Delivery Terms install included Order Date 14 Aug 2026",
    "Purchase Order PO Number PO-9393 Quantity 18 Unit Price 7.25 Ship To Field Depot Order Number REQ-90 Delivery Terms collect",
]

contract = [
    "SERVICE AGREEMENT This Contract is entered into by the Parties. Terms and Conditions apply. Effective Date January 1 2026 Termination clause Governing Law California Whereas the parties agree",
    "Master Services Agreement between the Parties Terms and Conditions Effective Date next quarter Termination for convenience Governing Law and venue Whereas obligations",
    "Contract of Engagement Parties agree to Terms and Conditions Effective Date recorded Termination notice thirty days Governing Law applies Signature blocks",
    "Software License Agreement Parties Terms and Conditions Effective Date Termination rights Governing Law nondisclosure Whereas signatures required",
    "Consulting Contract Agreement Parties bound by Terms and Conditions Effective Date Termination may occur Governing Law state rules Obligations of each party",
    "Employment Contract Agreement between the Parties Effective Date Terms and Conditions Termination notice Governing Law Signatures of employer and employee",
    "Lease Agreement Parties Terms and Conditions Effective Date rent obligations Termination clause Governing Law signatures Witness",
    "Partnership Agreement Whereas the Parties enter Terms and Conditions Effective Date Termination events Governing Law obligations Signature page",
    "Non Disclosure Agreement Parties Terms and Conditions Effective Date confidentiality obligations Termination Governing Law signatures",
    "Vendor Services Contract Parties agree Terms and Conditions Effective Date service obligations Termination for breach Governing Law Signature",
    "Framework Agreement between Parties Terms and Conditions Effective Date Termination rights Governing Law obligations Annex signatures",
    "Maintenance Contract Agreement Parties Terms and Conditions Effective Date support obligations Termination notice Governing Law signed",
    "Supply Contract Parties Terms and Conditions Effective Date delivery obligations Termination Governing Law Signature blocks",
    "Agency Agreement Whereas Parties Terms and Conditions Effective Date agent obligations Termination Governing Law signatures",
    "Research Collaboration Agreement Parties Terms and Conditions Effective Date IP obligations Termination Governing Law signed by authorized",
    "Hosting Services Contract Parties Terms and Conditions Effective Date uptime obligations Termination for convenience Governing Law",
    "Training Agreement Contract Parties Terms and Conditions Effective Date trainer obligations Termination Governing Law signatures",
    "Memorandum of Agreement Parties Terms and Conditions Effective Date mutual obligations Termination Governing Law Signature page",
]

receipt = [
    "STORE RECEIPT Payment Received Cash tendered Change given Transaction 99821 Thank you for your purchase Merchant Corner Market Paid in full",
    "Customer Receipt Payment Received Merchant Downtown Cafe Cash Change Transaction reference Thank you for your payment Paid",
    "Sales Receipt Payment Received Paid by card Merchant Kiosk Thank you for your purchase Transaction complete Change 0.00",
    "Retail Receipt Merchant Shoppe Payment Received Cash Change Transaction ID Thank you for your purchase Paid",
    "Payment Receipt Merchant Services Desk Payment Received Thank you for your payment Transaction logged Cash Change",
    "POS Receipt Cashier Lane 3 Payment Received Items purchased Amount Paid Change Transaction 44102 Merchant Demo Mart",
    "Store Receipt Merchant Bakery Payment Received Card approved Amount Paid Transaction Thank you for your purchase",
    "Customer Sales Receipt Cashier Payment Received Purchased items Amount Paid Change due Merchant Demo Books",
    "Receipt Payment Received Merchant Pharmacy Transaction Cashier Amount Paid Thank you for your purchase Paid",
    "Retail Payment Receipt Merchant Electronics Payment Received Card Payment Amount Paid Transaction Thank you",
    "Store Receipt Cashier 2 Payment Received Items Purchased Amount Paid Change Merchant Demo Grocer Transaction",
    "Sales Receipt Merchant Cafe Counter Payment Received Cash Amount Paid Change Thank you for your purchase",
    "Payment Receipt Transaction 22011 Merchant Demo Salon Payment Received Amount Paid Card Cashier Thank you",
    "Customer Receipt Merchant Fuel Stop Payment Received Amount Paid Cash Change Transaction Thank you for your payment",
    "POS Receipt Merchant Demo Hardware Payment Received Purchased items Amount Paid Transaction Cashier Paid",
    "Store Receipt Payment Received Merchant Demo Florist Amount Paid Change Transaction Thank you for your purchase",
    "Sales Receipt Cashier Payment Received Merchant Demo Optics Amount Paid Card Transaction Thank you Paid",
    "Retail Receipt Merchant Demo Toys Payment Received Amount Paid Cash Change Transaction Thank you for your purchase",
]

bank_statement = [
    "Account Statement Account Number 123456789 Statement Period Feb 1 to Feb 28 Opening Balance 1200.00 Closing Balance 1450.00 Debit Credit Transaction Date Balance",
    "Bank Account Statement Opening Balance Closing Balance Statement Period March Debit entries Credit entries Transaction Date Account Number Balance summary",
    "Monthly Account Statement Account Number ending 7788 Opening Balance Closing Balance Statement Period Debit Credit Transaction Date",
    "Personal Account Statement Statement Period Opening Balance Closing Balance Account Number Debit Credit Transaction Date Balance",
    "Business Account Statement Opening Balance Closing Balance Debit Credit Transaction Date Statement Period Account Number",
    "Checking Account Statement Account Number 556677 Statement Period April Opening Balance Closing Balance Debit Credit Transaction Date",
    "Savings Account Statement Opening Balance Closing Balance Statement Period May Debit Credit Transaction Date Account Number Balance",
    "Bank Statement Account Number 990011 Statement Period June Opening Balance Closing Balance Credits Debits Transaction Date",
    "Account Statement Statement Period July Opening Balance Closing Balance Account Number Debit Credit Transaction Date Balance brought forward",
    "Monthly Bank Statement Account Number ending 3344 Opening Balance Closing Balance Debit Credit Transaction Date Statement Period",
    "Current Account Statement Opening Balance Closing Balance Statement Period August Debit Credit Transaction Date Account Number",
    "Account Statement Account Number 221133 Statement Period September Opening Balance Closing Balance Transaction Date Debit Credit",
    "Bank Account Statement Statement Period October Opening Balance Closing Balance Debit Credit Transaction Date Account Number Balance",
    "Statement of Account Account Number 667788 Opening Balance Closing Balance Statement Period November Debit Credit Transaction Date",
    "Personal Bank Statement Opening Balance Closing Balance Account Number Statement Period December Debit Credit Transaction Date",
    "Business Bank Statement Account Number ending 1212 Opening Balance Closing Balance Debit Credit Transaction Date Statement Period",
    "Account Statement Statement Period Q1 Opening Balance Closing Balance Debit Credit Transaction Date Account Number Balance",
    "Bank Statement Account Number 445566 Opening Balance Closing Balance Statement Period January Debit Credit Transaction Date",
]

other = [
    "Weekly team notes Discussed roadmap priorities and staffing Follow up on office supplies next Monday Agenda items only",
    "Meeting minutes Attendees discussed project timeline Action items assigned No financial totals No invoice language",
    "Internal memo Reminder about building access badges Please renew visitor passes Contact facilities for questions",
    "Product brainstorming notes Ideas for onboarding checklist UX copy drafts Sprint planning leftovers",
    "Holiday schedule notice Offices closed on public holidays Remote work optional Reply to this message if travel planned",
    "Resume Summary Experienced coordinator Skills communication scheduling Education diploma References available upon request",
    "Cover letter Applying for the coordinator role Interested in supporting operations Available for interview next week",
    "Neighborhood notice Street cleaning tomorrow Please move vehicles Community board update Thank you residents",
    "Library overdue notice Please return borrowed books Desk hours listed Contact the librarian for renewals",
    "Team retrospective notes What went well What to improve Action owners Parking lot topics for next sprint",
    "School newsletter Sports day next Friday Volunteer signup Parent teacher conference schedule Cafeteria menu",
    "Travel itinerary notes Flight numbers hotel check in reminders Packing checklist Local transit tips",
    "Volunteer signup sheet Event roles needed Shift times Contact organizer Bring water and ID badge",
    "Club meeting agenda Welcome updates budget discussion event planning open floor closing remarks",
    "Lost and found notice Blue backpack found near lobby Claim at reception with description",
]

goods_receipt = [
    "GOODS RECEIPT NOTE GRN Number GRN-501 Received Date 12 March 2026 Supplier Demo Parts PO Number PO-1007 Quantity Received 20 Received By Store Department Receipt Status Received",
    "Goods Receipt GRN No GRN-880 Vendor Office Essentials Purchase Order PO-4412 Received Quantity 5 Received Date 01 April 2026 Received By Warehouse Receipt Status Complete",
    "GRN Number GRN-2201 Goods Receipt Note Supplier Demo Hardware PO Number PO-9001 Qty Received 12 Date Received 18 Feb 2026 Received By Receiving Dock",
    "Goods Receipt Note Receipt No GRN-334 PO Number PO-7788 Supplier Warehouse Demo Quantity Received 100 Received Date 05 May 2026 Received By Store Department Receipt Status Received",
    "GRN GRN-9912 Goods Receipt Vendor Demo Soft Purchase Order Number PO-331 Received Quantity 3 Received Date 09 June 2026 Goods Received Received By Ops",
    "Goods Receipt Note GRN Number GRN-1414 Supplier Demo Paper Co PO Number PO-2201 Quantity Received 500 Date Received 22 July 2026 Receipt Status Received Received By Mail Room",
    "GRN No. GRN-6060 Goods Receipt Purchase Order PO-8840 Vendor Demo Tools Received Quantity 7 Received Date 11 Aug 2026 Received Items verified Received By Workshop",
    "Goods Receipt GRN-7171 Supplier Demo Med Supply PO Number PO-1009 Quantity Received 15 Received Date 30 Jan 2026 Received By Clinic Store Receipt Status Received",
    "GRN Number GRN-3030 Goods Receipt Note Vendor Demo Apparel Purchase Order PO-5566 Qty Received 30 Date Received 14 Sep 2026 Received By Event Desk",
    "Goods Receipt Note GRN No GRN-4545 PO Number PO-670 Supplier Demo Freight Quantity Received 40 Received Date 03 Oct 2026 Goods Received Receipt Status Complete",
    "GRN GRN-1212 Goods Receipt Supplier North Supplies PO Number PO-909 Received Quantity 9 Received Date 19 Nov 2026 Received By Store Department",
    "Goods Receipt Note Receipt Number GRN-8383 Vendor Demo Parts PO Number PO-4141 Quantity Received 1 Date Received 08 Dec 2026 Received By Warehouse Receipt Status Received",
    "GRN Number GRN-5757 Goods Receipt Purchase Order Reference PO-3030 Supplier Demo Catalog Received Quantity 25 Received Date 27 Mar 2026 Received Items counted",
    "Goods Receipt GRN-2929 Vendor Lab Demo PO Number PO-1717 Quantity Received 60 Received Date 16 Apr 2026 Received By Lab Store Receipt Status Received",
    "GRN No GRN-8686 Goods Receipt Note Supplier Depot Demo Purchase Order PO-2626 Received Quantity 18 Received Date 21 May 2026 Received By Depot Clerk",
    "GOODS RECEIPT NOTE GRN Number GRN-1001 GRN Date 05 September 2026 Vendor ABC Pvt Ltd PO Number PO-7788 Received Quantity 1 Ordered Quantity 1 Received By Store Department Receipt Status Received Unit Service",
    "Goods Receipt Note GRN Number GRN-4420 Goods Received Vendor Metro Supplies Purchase Order Reference PO-2109 Received Quantity 14 Receipt Status Received Received By Receiving Bay",
    "GRN Number GRN-7711 Goods Receipt Note PO Number PO-5530 Supplier Harbor Parts Qty Received 22 Received By Dock Team Receipt Status Complete Date Received 02 Aug 2026",
]


def main() -> None:
    examples = []
    for label, texts in [
        ("invoice", invoice[:15]),
        ("purchase_order", purchase_order[:15]),
        ("goods_receipt", goods_receipt[:18]),
        ("contract", contract[:15]),
        ("receipt", receipt[:15]),
        ("bank_statement", bank_statement[:15]),
        ("other", other[:15]),
    ]:
        if label == "goods_receipt":
            if not 15 <= len(texts) <= 20:
                raise SystemExit(f"{label} has {len(texts)} examples; expected 15-20")
        elif len(texts) != 15:
            raise SystemExit(f"{label} has {len(texts)} examples")
        for text in texts:
            examples.append({"label": label, "text": text})

    payload = {
        "version": "1.3.0",
        "description": (
            "Expanded starter/demo labeled examples for local ML document classification "
            "including stronger goods_receipt coverage. Synthetic text only; not production "
            "business data. Evaluation metrics are measured on a local synthetic holdout "
            "split and are not production accuracy."
        ),
        "labels": [
            "invoice",
            "purchase_order",
            "goods_receipt",
            "contract",
            "receipt",
            "bank_statement",
            "other",
        ],
        "examples": examples,
    }
    path = Path(__file__).resolve().parent / "starter_training_set.json"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    counts = {label: sum(1 for item in examples if item["label"] == label) for label in payload["labels"]}
    print(path)
    print(len(examples), counts)


if __name__ == "__main__":
    main()
