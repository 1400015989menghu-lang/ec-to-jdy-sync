#!/usr/bin/env python3
"""
EC → 金蝶云星辰 数据同步脚本
- 从 EC 获取客户/订单，同步到金蝶云星辰
- 增量同步（基于时间范围过滤）
- 每隔 1 小时自动执行（通过 WorkBuddy Automation 触发）

用法：
    python sync.py              # 执行增量同步
    python sync.py --full       # 全量同步（忽略时间过滤）
"""
import sys
import argparse
from datetime import datetime
from typing import Dict, Any, Optional, List

from config import SYNC_ORDER_STATUS, PAGE_SIZE
from state import SyncState
from ec_client import ECClient
from jdy_client import JDYClient


# 同步统计
class SyncStats:
    def __init__(self):
        self.customers_total = 0
        self.customers_new = 0
        self.customers_updated = 0
        self.customers_skipped = 0
        self.customers_failed = 0
        self.orders_total = 0
        self.orders_new = 0
        self.orders_skipped = 0
        self.orders_failed = 0
        self.errors: List[str] = []

    def log(self):
        """输出同步结果摘要"""
        lines = [
            "",
            "=" * 50,
            "  同步结果摘要",
            "=" * 50,
            f"【客户同步】",
            f"  EC 拉取总数: {self.customers_total}",
            f"  金蝶新增:    {self.customers_new}",
            f"  金蝶更新:    {self.customers_updated}",
            f"  跳过(已存在): {self.customers_skipped}",
            f"  失败:        {self.customers_failed}",
            "",
            f"【订单同步】",
            f"  EC 拉取总数: {self.orders_total}",
            f"  金蝶新增:    {self.orders_new}",
            f"  跳过(已存在): {self.orders_skipped}",
            f"  失败:        {self.orders_failed}",
            "=" * 50,
        ]
        if self.errors:
            lines.append("")
            lines.append("【错误列表】")
            for err in self.errors:
                lines.append(f"  ❌ {err}")

        print("\n".join(lines))


# ========== 字段映射函数 ==========

def map_ec_customer_to_jdy(ec_customer: Dict[str, Any]) -> Dict[str, Any]:
    """
    将 EC 客户数据映射为金蝶客户保存格式
    """
    crm_id = str(ec_customer.get("crmId", ""))
    crm_type = ec_customer.get("crmType", 0)  # 0=个人, 1=企业
    name = ec_customer.get("name", "")
    company = ec_customer.get("company", "")

    # 客户名称：企业客户用公司名，个人客户用姓名
    customer_name = company if (crm_type == 1 and company) else name
    if not customer_name:
        customer_name = f"EC客户-{crm_id}"

    jdy_customer = {
        "number": crm_id,              # EC crmId → 金蝶客户编码（唯一键）
        "name": customer_name,         # 客户名称
    }

    # 可选字段
    mobile = ec_customer.get("mobile", "")
    if mobile:
        jdy_customer["mobile"] = mobile

    phone = ec_customer.get("phone", "")
    if phone:
        jdy_customer["telephone"] = phone

    email = ec_customer.get("email", "")
    if email:
        jdy_customer["email"] = email

    # 地区和地址
    region = ec_customer.get("prefecture", "")  # 格式: "中国/广东/深圳/南山"
    if region:
        parts = region.split("/")
        if len(parts) >= 2:
            jdy_customer["region_name"] = "/".join(parts[1:])
        else:
            jdy_customer["region_name"] = region

    company_addr = ec_customer.get("companyAddress", "")
    if company_addr:
        jdy_customer["address"] = company_addr

    # 备注
    memo = ec_customer.get("memo", "")
    if memo:
        jdy_customer["remark"] = memo

    # 客户类型
    if crm_type == 1:
        jdy_customer["customer_type"] = "company"
    else:
        jdy_customer["customer_type"] = "person"

    return jdy_customer


def map_ec_order_to_jdy(ec_order: Dict[str, Any], customer_number: str) -> Dict[str, Any]:
    """
    将 EC 订单数据映射为金蝶销售订单格式
    """
    order_code = ec_order.get("code", "")
    money = float(ec_order.get("money", 0) or 0)
    product_id = ec_order.get("productId", "")
    product_des = ec_order.get("productDes", "")

    # 订单日期：优先用成交日期，其次建单时间
    deal_date = ec_order.get("dealDate", "") or ec_order.get("createTime", "")
    if deal_date and " " in deal_date:
        deal_date = deal_date.split(" ")[0]  # 只取日期部分 2024-01-01

    # 订单备注
    remark = ec_order.get("remark", "")
    if product_des and product_des not in (remark or ""):
        remark = f"[产品] {product_des}" + (f"; {remark}" if remark else "")

    jdy_order = {
        "billno": f"EC-{order_code}",    # 订单编码（加 EC- 前缀防冲突）
        "customerid_id": customer_number, # 关联金蝶客户编码
        "billdate": deal_date,
        "remark": remark,
        "material_entity": [
            {
                "materialid_id": product_id,   # 物料编码（EC productId）
                "qty": "1",
                "price": str(money),           # 总金额作为单价（数量=1）
            }
        ],
    }

    return jdy_order


# ========== 同步逻辑 ==========

def sync_customers(
    ec: ECClient, jdy: JDYClient, state: SyncState, stats: SyncStats, full_sync: bool = False
):
    """同步客户：EC → 金蝶"""
    print("[客户同步] 开始...")

    modify_since = None if full_sync else state.last_customer_sync
    if modify_since:
        print(f"  └ 增量同步，起始时间: {modify_since}")
    else:
        print(f"  └ 全量同步")

    try:
        ec_customers = ec.get_all_customers(modify_since=modify_since)
    except Exception as e:
        stats.errors.append(f"EC 查询客户失败: {e}")
        print(f"  ❌ EC 查询客户失败: {e}")
        return

    stats.customers_total = len(ec_customers)
    print(f"  └ EC 拉取到 {stats.customers_total} 位客户")

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for i, ec_cust in enumerate(ec_customers):
        crm_id = str(ec_cust.get("crmId", ""))
        customer_name = ec_cust.get("name", "") or ec_cust.get("company", "")

        try:
            # 1. 检查金蝶中是否已存在
            existing = jdy.find_customer_by_number(crm_id)

            # 2. 映射字段
            jdy_cust = map_ec_customer_to_jdy(ec_cust)

            if existing:
                # 已存在 → 更新
                jdy_cust["id"] = existing.get("id", "")
                result = jdy.save_customer(jdy_cust)
                if result.get("errcode") == 0:
                    stats.customers_updated += 1
                    print(f"  [{i+1}/{stats.customers_total}] 🔄 更新: {customer_name} (crmId={crm_id})")
                else:
                    raise Exception(result.get("description", "未知错误"))
            else:
                # 不存在 → 新增
                result = jdy.save_customer(jdy_cust)
                if result.get("errcode") == 0:
                    stats.customers_new += 1
                    print(f"  [{i+1}/{stats.customers_total}] ✅ 新增: {customer_name} (crmId={crm_id})")
                else:
                    raise Exception(result.get("description", "未知错误"))

        except Exception as e:
            stats.customers_failed += 1
            err_msg = f"客户 {customer_name}(crmId={crm_id}) 同步失败: {e}"
            stats.errors.append(err_msg)
            print(f"  [{i+1}/{stats.customers_total}] ❌ {err_msg}")

    # 更新同步时间
    state.update_customer_sync(now_str)
    print(f"[客户同步] 完成，新增 {stats.customers_new}, 更新 {stats.customers_updated}, 失败 {stats.customers_failed}")


def sync_orders(
    ec: ECClient, jdy: JDYClient, state: SyncState, stats: SyncStats, full_sync: bool = False
):
    """同步订单：EC → 金蝶"""
    print("[订单同步] 开始...")

    creat_since = None if full_sync else state.last_order_sync
    if creat_since:
        print(f"  └ 增量同步，起始时间: {creat_since}")
    else:
        print(f"  └ 全量同步")

    try:
        status = int(SYNC_ORDER_STATUS)  # 默认 3 = 已结单
        ec_orders = ec.get_all_orders(status=status, creat_since=creat_since)
    except Exception as e:
        stats.errors.append(f"EC 查询订单失败: {e}")
        print(f"  ❌ EC 查询订单失败: {e}")
        return

    stats.orders_total = len(ec_orders)
    print(f"  └ EC 拉取到 {stats.orders_total} 条结单订单")

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for i, ec_order in enumerate(ec_orders):
        order_code = ec_order.get("code", "")
        crm_id = str(ec_order.get("crmId", ""))
        order_money = ec_order.get("money", 0)

        try:
            # 1. 先确保客户已同步到金蝶（获取客户编码）
            jdy_customer = jdy.find_customer_by_number(crm_id)
            if not jdy_customer:
                # 客户尚未同步，尝试从 EC 获取客户信息并同步
                print(f"  [{i+1}/{stats.orders_total}] ⚠️ 客户 crmId={crm_id} 尚未同步，跳过订单 {order_code}")
                stats.orders_skipped += 1
                continue

            customer_number = jdy_customer.get("number", crm_id)

            # 2. 检查订单是否已存在
            billno = f"EC-{order_code}"
            existing_order = jdy.find_order_by_billno(billno)
            if existing_order:
                stats.orders_skipped += 1
                print(f"  [{i+1}/{stats.orders_total}] ⏭️ 跳过(已存在): {order_code} (¥{order_money})")
                continue

            # 3. 映射并保存
            jdy_order = map_ec_order_to_jdy(ec_order, customer_number)
            result = jdy.save_sales_order(jdy_order)

            if result.get("errcode") == 0:
                stats.orders_new += 1
                print(f"  [{i+1}/{stats.orders_total}] ✅ 新增: {order_code} (¥{order_money})")
            else:
                raise Exception(result.get("description", "未知错误"))

        except Exception as e:
            stats.orders_failed += 1
            err_msg = f"订单 {order_code}(¥{order_money}) 同步失败: {e}"
            stats.errors.append(err_msg)
            print(f"  [{i+1}/{stats.orders_total}] ❌ {err_msg}")

    # 更新同步时间
    state.update_order_sync(now_str)
    print(f"[订单同步] 完成，新增 {stats.orders_new}, 跳过 {stats.orders_skipped}, 失败 {stats.orders_failed}")


# ========== 主函数 ==========

def main():
    parser = argparse.ArgumentParser(description="EC → 金蝶云星辰 数据同步")
    parser.add_argument("--full", action="store_true", help="全量同步（忽略时间过滤）")
    parser.add_argument("--customers-only", action="store_true", help="仅同步客户")
    parser.add_argument("--orders-only", action="store_true", help="仅同步订单")
    args = parser.parse_args()

    print("=" * 50)
    print("  EC → 金蝶云星辰 数据同步")
    print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  模式: {'全量同步' if args.full else '增量同步'}")
    print(f"  订单状态过滤: status={SYNC_ORDER_STATUS}")
    print("=" * 50)

    # 初始化
    state = SyncState()
    ec = ECClient()
    jdy = JDYClient()
    stats = SyncStats()

    # 1. 获取金蝶 Token
    try:
        token = jdy.get_access_token()
        print(f"\n[认证] 金蝶 Token 获取成功: {token[:20]}...")
    except Exception as e:
        print(f"\n❌ 金蝶 Token 获取失败: {e}")
        stats.errors.append(f"金蝶 Token 获取失败: {e}")
        stats.log()
        sys.exit(1)

    # 2. 同步客户
    if not args.orders_only:
        sync_customers(ec, jdy, state, stats, full_sync=args.full)
    else:
        print("\n[客户同步] ⏭️ 跳过（仅同步订单模式）")

    # 3. 同步订单
    if not args.customers_only:
        sync_orders(ec, jdy, state, stats, full_sync=args.full)
    else:
        print("\n[订单同步] ⏭️ 跳过（仅同步客户模式）")

    # 4. 输出结果
    stats.log()


if __name__ == "__main__":
    main()
