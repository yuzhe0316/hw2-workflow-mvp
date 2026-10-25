"""计费示例模块。

用于演示 docflow 的"代码 → 文档"流程。模块里刻意保留了少量没有 docstring
的函数，方便观察审校与覆盖率统计的效果。
"""

from __future__ import annotations

import uuid

TAX_RATE = 0.06


def create_invoice(customer: str, items: list, tax_rate: float = TAX_RATE) -> dict:
    """根据订单明细生成一张发票。

    发票号随机生成，金额按 ``tax_rate`` 计算增值税；
    明细中每一项需包含 ``name``、``qty`` 与 ``unit_price`` 三个字段。
    """
    if not customer:
        raise ValueError("customer 不能为空")
    lines = []
    subtotal = 0.0
    for item in items:
        line_total = round(float(item["qty"]) * float(item["unit_price"]), 2)
        subtotal += line_total
        lines.append({"name": item["name"], "qty": item["qty"], "line_total": line_total})
    tax = round(subtotal * tax_rate, 2)
    return {
        "id": f"INV-{uuid.uuid4().hex[:8].upper()}",
        "customer": customer,
        "items": lines,
        "subtotal": round(subtotal, 2),
        "tax": tax,
        "total": round(subtotal + tax, 2),
    }


def apply_discount(amount: float, rate: float) -> float:
    if not 0 <= rate < 1:
        raise ValueError("rate 必须落在 [0, 1) 区间")
    return round(amount * (1 - rate), 2)


def total_revenue(invoices: list) -> float:
    """汇总一批发票的含税总额。

    对空列表返回 ``0.0``，不抛异常，便于统计脚本直接使用。
    """
    return round(sum(float(invoice["total"]) for invoice in invoices), 2)


class InvoiceBook:
    """发票台账：按客户归集发票，并支持简单汇总。"""

    def __init__(self) -> None:
        self._by_customer: dict = {}

    def add(self, invoice: dict) -> None:
        """登记一张发票；同一发票号重复登记会被忽略。"""
        customer = invoice["customer"]
        bucket = self._by_customer.setdefault(customer, {})
        bucket.setdefault(invoice["id"], invoice)

    def by_customer(self, customer: str) -> list:
        """返回指定客户的全部发票（按登记顺序）。"""
        return list(self._by_customer.get(customer, {}).values())

    def summary(self) -> dict:
        """按客户统计发票张数与含税总额。"""
        return {
            customer: {
                "count": len(invoices),
                "total": round(sum(inv["total"] for inv in invoices.values()), 2),
            }
            for customer, invoices in self._by_customer.items()
        }
