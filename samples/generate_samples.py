from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


OUT = Path(__file__).resolve().parent


def build_pdf(path: Path, lines: list[str]) -> None:
    text_ops = ["BT", "/F1 12 Tf", "50 740 Td"]
    for index, line in enumerate(lines):
        safe = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        if index == 0:
            text_ops.append(f"({safe}) Tj")
        else:
            text_ops.append("0 -18 Td")
            text_ops.append(f"({safe}) Tj")
    text_ops.append("ET")
    stream = "\n".join(text_ops).encode("latin-1", errors="replace")

    objs = [
        b"1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj\n",
        b"2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj\n",
        (
            b"3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Contents 4 0 R /Resources<< /Font<< /F1 5 0 R >> >> >>endobj\n"
        ),
        f"4 0 obj<< /Length {len(stream)} >>stream\n".encode()
        + stream
        + b"\nendstream\nendobj\n",
        b"5 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>endobj\n",
    ]

    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objs:
        offsets.append(len(pdf))
        pdf.extend(obj)

    xref_at = len(pdf)
    pdf.extend(f"xref\n0 {len(offsets)}\n".encode())
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode())
    pdf.extend(
        f"trailer<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n".encode()
    )
    path.write_bytes(pdf)


def build_png(path: Path, lines: list[str]) -> None:
    image = Image.new("RGB", (900, 80 + 30 * len(lines)), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    y = 40
    for line in lines:
        draw.text((40, y), line, fill=(0, 0, 0), font=font)
        y += 30
    image.save(path)


def main() -> None:
    OUT.mkdir(exist_ok=True)

    # One consistent Invoice / PO / GRN set so 3-way matching can fully match:
    # same vendor, PO-7788 referenced everywhere, GRN-1001 referenced on the invoice,
    # and one line item (DEV-001) with matching quantity and amounts.
    item_lines = [
        "Description: Software Development Services",
        "Item Code: DEV-001",
    ]
    money_lines = [
        "Unit: Service",
        "Unit Price: 450000",
        "Line Total: 450000",
        "Subtotal: 450,000",
        "Tax: 81,000",
        "Total: 531,000",
        "Currency: PKR",
    ]
    invoice_lines = [
        "ABC Pvt Ltd",
        "Invoice No: INV-1827",
        "Date: 10-09-2026",
        "Bill To: Customer Co",
        "PO Number: PO-7788",
        "GRN Number: GRN-1001",
        *item_lines,
        "Quantity: 1",
        *money_lines,
    ]
    po_lines = [
        "ABC Pvt Ltd",
        "Purchase Order",
        "PO Number: PO-7788",
        "PO Date: 01-09-2026",
        *item_lines,
        "Ordered Quantity: 1",
        *money_lines,
    ]
    grn_lines = [
        "GOODS RECEIPT NOTE",
        "GRN Number: GRN-1001",
        "GRN Date: September 5, 2026",
        "Vendor: ABC Pvt Ltd",
        "PO Number: PO-7788",
        *item_lines,
        "Ordered Quantity: 1",
        "Received Quantity: 1",
        *money_lines,
        "Received By: Store Department",
        "Receipt Status: Received",
    ]

    build_pdf(OUT / "sample_invoice.pdf", invoice_lines)
    build_pdf(OUT / "sample_purchase_order.pdf", po_lines)
    build_pdf(OUT / "sample_goods_receipt.pdf", grn_lines)
    build_png(OUT / "sample_invoice.png", invoice_lines)
    build_png(OUT / "sample_purchase_order.png", po_lines)

    for path in sorted(OUT.glob("sample_*")):
        print(path)


if __name__ == "__main__":
    main()
