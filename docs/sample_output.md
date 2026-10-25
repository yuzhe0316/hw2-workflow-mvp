# API 文档：billing

> 由 docflow 自动生成 · 2026-10-25 14:02 · revision 1

## 模块概览

| 指标 | 数值 |
|------|------|
| 源文件 | `billing.py` |
| 代码行数 | 77 |
| 公共函数 | 3 |
| 公共类 | 1 |
| 文档覆盖率 | 6/7（86%） |

## 模块说明

计费示例模块。

用于演示 docflow 的"代码 → 文档"流程。模块里刻意保留了少量没有 docstring
的函数，方便观察审校与覆盖率统计的效果。

依赖：`__future__`, `uuid`

## 公共 API

### `create_invoice`

`def create_invoice(customer: str, items: list, tax_rate: float = TAX_RATE) -> dict`

根据订单明细生成一张发票

**参数**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `customer` | `str` | — | 客户名称或客户编号 |
| `items` | `list` | — | 明细列表，每项包含商品、数量与单价 |
| `tax_rate` | `float` | `TAX_RATE` | 税率，按小数传入（0.06 表示 6%） |

**返回值**：`dict`

**圈复杂度**：3（简单）

**补充说明**

发票号自动生成，金额按 ``tax_rate`` 计算增值税；
明细中每一项需包含 ``name``、``qty`` 与 ``unit_price`` 三个字段。

### `apply_discount`

`def apply_discount(amount: float, rate: float) -> float`

（未提供 docstring，说明待补充）

**参数**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `amount` | `float` | — | 金额（单位：元） |
| `rate` | `float` | — | 浮点数类型的输入 |

**返回值**：`float`

**圈复杂度**：2（简单）

### `total_revenue`

`def total_revenue(invoices: list) -> float`

汇总一批发票的含税总额

**参数**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `invoices` | `list` | — | 列表类型的输入 |

**返回值**：`float`

**圈复杂度**：2（简单）

**补充说明**

对空列表返回 ``0.0``，不抛异常，便于统计脚本直接使用。

### `InvoiceBook`

发票台账：按客户归集发票，并支持简单汇总

**公开方法**

| 方法 | 签名 | 说明 |
|------|------|------|
| `add` | `def add(invoice: dict) -> None` | 登记一张发票；同一发票号重复登记会被忽略 |
| `by_customer` | `def by_customer(customer: str) -> list` | 返回指定客户的全部发票（按登记顺序） |
| `summary` | `def summary() -> dict` | 按客户统计发票张数与含税总额 |

## 使用示例

```python
from billing import total_revenue

result = total_revenue(invoices=[])
print(result)
```

## 文档覆盖情况

以下 1 个符号缺少 docstring，正文中的说明由签名与类型推断，建议补充源码注释后重新生成：

- `apply_discount`

## 审校意见处理

本版针对上一轮审校提出的问题做了补充：

- `create_invoice` 缺少参数表
- `apply_discount` 缺少参数表
- `total_revenue` 缺少参数表
- 缺少可运行的「## 使用示例」代码块
