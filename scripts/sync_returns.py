#!/usr/bin/env python3
"""
金蝶云星辰 销售退货单 → EC 退货单 同步脚本

每10分钟自动执行，或手动运行：
  python3 scripts/sync_returns.py             # 增量同步
  python3 scripts/sync_returns.py --full      # 全量同步

流程：
① 获取金蝶 Token
② 拉取金蝶销售退货单列表（bill_status=C 已审核，增量）
③ 对每条退货单：
   - 解析客户ID → EC crmId（金蝶客户number字段）
   - 解析商品分录 → EC 退货商品列表（material_id→productId映射）
   - 调用 EC 新建退货单接口
④ 记录映射表，防重复同步
⑤ 更新同步时间
"""
import sys
import os
import time
import argparse
from datetime import datetime
from typing import Optional, List, Dict, Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import (
    RETURN_SYNC_USER_ID, RETURN_GROUP_ID,
    RETURN_REASON_DEFAULT, RETURN_PAGE_SIZE,
)
from ec_client import ECClient
from jdy_client import JDYClient
from state import SyncState


# 退货原因枚举映射
RETURN_REASON_MAP = {
    1: "产品损坏",
    2: "质量问题",
    3: "订单下错产品",
    4: "产品尺寸/参数不符",
    5: "发票问题",
    6: "客户原因",
    7: "其他原因",
}


class ReturnSyncRunner:
    """金蝶销售退货单 → EC 退货单 同步器"""

    def __init__(self):
        self.ec = ECClient()
        self.jdy = JDYClient()
        self.state = SyncState()

        # 统计
        self.total_pulled = 0       # 金蝶拉取总数
        self.synced = 0             # 成功同步数
        self.skipped_synced = 0     # 已同步跳过数
        self.skipped_no_customer = 0  # 无客户映射跳过数
        self.failed = 0             # 失败数
        self.errors: List[str] = [] # 错误记录

        # 缓存：避免重复查询
        self._customer_cache: Dict[str, Optional[str]] = {}  # JDY customer_id → EC crmId
        self._ec_products_cache: Optional[list] = None

    def _log(self, msg: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {msg}")

    # ===== 客户ID解析 =====

    def resolve_crm_id(self, jdy_customer_id: str) -> Optional[str]:
        """
        将金蝶客户ID解析为EC crmId
        逻辑：查询金蝶客户详情 → 获取 number 字段（即EC crmId）
        """
        if jdy_customer_id in self._customer_cache:
            return self._customer_cache[jdy_customer_id]

        try:
            customer = self.jdy.query_customer_by_id(jdy_customer_id)
            if customer:
                crm_id = customer.get("number", "")
                self._customer_cache[jdy_customer_id] = crm_id
                return crm_id
        except Exception as e:
            self._log(f"    ⚠ 查询金蝶客户 {jdy_customer_id} 失败: {e}")

        self._customer_cache[jdy_customer_id] = None
        return None

    # ===== 产品ID解析 =====

    def resolve_product_id(self, material_id: str, material_name: str) -> Optional[int]:
        """
        将金蝶商品ID解析为EC产品ID
        优先查本地映射表 → 按名称在EC产品列表中匹配
        """
        # 1. 检查本地映射表
        mapped_id = self.state.get_mapped_ec_product_id_for_material(material_id)
        if mapped_id:
            return mapped_id

        # 2. 按名称在EC产品中匹配
        if not material_name:
            return None

        if self._ec_products_cache is None:
            try:
                self._ec_products_cache = self.ec.get_all_products(RETURN_SYNC_USER_ID)
                self._log(f"    加载 EC 产品列表: {len(self._ec_products_cache)} 个")
            except Exception as e:
                self._log(f"    ⚠ 加载EC产品列表失败: {e}")
                self._ec_products_cache = []

        for prod in self._ec_products_cache:
            if prod.get("productName", "").strip() == material_name.strip():
                ec_product_id = prod.get("id")
                if ec_product_id:
                    # 记录映射
                    self.state.add_material_product_mapping(
                        material_id, ec_product_id, material_name
                    )
                    return ec_product_id

        return None

    # ===== saleId 解析 =====

    def resolve_sale_id(self, src_inter_id: str = None, bill_no: str = None) -> int:
        """
        尝试解析金蝶退货单对应的EC销售订单ID

        策略：
        1. 如果金蝶源单的 bill_no 以 "EC-" 开头，提取EC订单编码查询
        2. 否则返回 0（EC允许saleId=0不关联源单）
        """
        # 尝试从源单解析
        if src_inter_id:
            try:
                src_order = self.jdy.get_return_order_detail(src_inter_id)
                if src_order:
                    src_bill_no = src_order.get("bill_no", "")
                    if src_bill_no.startswith("EC-"):
                        ec_code = src_bill_no[3:]  # 去掉 "EC-" 前缀
                        ec_order = self.ec.query_order_by_code(ec_code)
                        if ec_order:
                            sale_id = ec_order.get("id")
                            if sale_id:
                                return int(sale_id)
            except Exception:
                pass

        # 尝试从退货单自身的 bill_no 解析（某些场景下 bill_no 含EC编码）
        if bill_no and bill_no.startswith("EC-"):
            try:
                ec_code = bill_no[3:]
                ec_order = self.ec.query_order_by_code(ec_code)
                if ec_order:
                    sale_id = ec_order.get("id")
                    if sale_id:
                        return int(sale_id)
            except Exception:
                pass

        return 0  # 无法解析时返回0

    # ===== 主流程 =====

    def run(self, full_sync: bool = False):
        """执行同步"""
        start_time = datetime.now()
        self._log("=" * 60)
        self._log(f"金蝶退货单 → EC退货单 同步开始（模式: {'全量' if full_sync else '增量'}）")
        self._log("=" * 60)

        try:
            # Step 1: 获取金蝶 Token
            self._log("① 获取金蝶 access_token ...")
            token = self.jdy.get_access_token()
            self._log(f"    Token 获取成功: {token[:20]}...")

            # Step 2: 读取上次同步时间（增量模式）
            self._log("② 拉取金蝶已审核退货单 ...")
            if full_sync:
                modify_since_ms = None
            else:
                last_sync = self.state.last_return_sync
                if last_sync:
                    modify_since_ms = str(self.state.get_timestamp_ms(last_sync))
                    self._log(f"    增量模式: 从 {last_sync} 开始")
                else:
                    modify_since_ms = None
                    self._log("    首次同步，拉取所有已审核退货单")

            return_orders = self.jdy.get_all_return_orders(
                bill_status="C",
                modify_since_ms=modify_since_ms,
            )
            self.total_pulled = len(return_orders)
            self._log(f"    拉取到 {self.total_pulled} 条已审核退货单")

            if not return_orders:
                self._log("    无新数据，同步结束")
                self.state.update_return_sync()
                self._print_summary(start_time)
                return

            # Step 3: 逐条同步
            self._log(f"③ 开始逐条同步 {self.total_pulled} 条退货单 ...")

            for i, jdy_return in enumerate(return_orders, 1):
                return_id = str(jdy_return.get("id", ""))
                bill_no = jdy_return.get("bill_no", "")
                total_amount = jdy_return.get("total_amount", 0)

                try:
                    # 3a. 去重检查
                    if self.state.is_return_order_synced(return_id):
                        self.skipped_synced += 1
                        self._log(f"    [{i}/{self.total_pulled}] ⏭ 已同步: {bill_no} (总金额={total_amount})")
                        continue

                    # 3b. 解析客户
                    jdy_customer_id = str(jdy_return.get("customer_id", ""))
                    crm_id_str = self.resolve_crm_id(jdy_customer_id)
                    if not crm_id_str:
                        self.skipped_no_customer += 1
                        self._log(
                            f"    [{i}/{self.total_pulled}] ⏭ 跳过: {bill_no} "
                            f"(无法解析金蝶客户 {jdy_customer_id} → EC crmId)"
                        )
                        continue

                    try:
                        crm_id = int(crm_id_str)
                    except (ValueError, TypeError):
                        self.skipped_no_customer += 1
                        self._log(
                            f"    [{i}/{self.total_pulled}] ⏭ 跳过: {bill_no} "
                            f"(客户编码 {crm_id_str} 不是有效数字)"
                        )
                        continue

                    # 3c. 解析 saleId
                    src_inter_id = str(jdy_return.get("src_inter_id", "")) if jdy_return.get("src_inter_id") else None
                    sale_id = self.resolve_sale_id(src_inter_id=src_inter_id, bill_no=bill_no)

                    # 3d. 映射商品分录
                    material_entity = jdy_return.get("material_entity", [])
                    if not material_entity:
                        self.failed += 1
                        err = f"{bill_no}: 无商品分录数据"
                        self.errors.append(err)
                        self._log(f"    [{i}/{self.total_pulled}] ❌ {err}")
                        continue

                    ec_products = []
                    for mat in material_entity:
                        mat_id = str(mat.get("material_id", ""))
                        mat_name = mat.get("material_name", "")
                        qty = float(mat.get("return_qty_unit", mat.get("qty", 0)) or 0)
                        price = float(mat.get("price", 0) or 0)
                        all_amount = float(mat.get("all_amount", 0) or 0)
                        mat_model = mat.get("material_model", "")

                        if qty <= 0:
                            continue  # 跳过数量为0的行

                        # 解析产品ID
                        product_id = self.resolve_product_id(mat_id, mat_name)
                        if not product_id:
                            self._log(
                                f"    [{i}/{self.total_pulled}] ⚠ {bill_no}: "
                                f"商品 {mat_name}(material_id={mat_id}) 无EC产品映射，跳过该行"
                            )
                            continue

                        # 金额处理：JDY返回的金额可能是分(cents)单位，检测并转换
                        # 如果单价 > 100000，很可能是分单位
                        if price > 100000:
                            price = price / 100
                        if all_amount > 100000:
                            all_amount = all_amount / 100

                        ec_products.append({
                            "productId": product_id,
                            "productName": mat_name,
                            "returnMoney": round(price, 2),
                            "returnQuantity": round(qty, 2),
                            "returnTotal": round(all_amount, 2),
                            "specsId": 0,
                            "specsName": mat_model if mat_model else "",
                        })

                    if not ec_products:
                        self.failed += 1
                        err = f"{bill_no}: 所有商品行均无EC产品映射"
                        self.errors.append(err)
                        self._log(f"    [{i}/{self.total_pulled}] ❌ {err}")
                        continue

                    # 3e. 构建EC退货单
                    title = f"金蝶退货-{bill_no}"[:35]
                    memo = jdy_return.get("remark", "")

                    # 3f. 调用EC创建退货单
                    result = self.ec.create_return_order(
                        user_id=RETURN_SYNC_USER_ID,
                        title=title,
                        group_id=RETURN_GROUP_ID,
                        crm_id=crm_id,
                        sale_id=sale_id,
                        return_reason=RETURN_REASON_DEFAULT,
                        products=ec_products,
                        code=bill_no,
                        memo=memo,
                    )

                    if result.get("code") == 200:
                        ec_return_id = result.get("data")
                        self.state.add_return_order_mapping(return_id, ec_return_id)
                        self.synced += 1
                        self._log(
                            f"    [{i}/{self.total_pulled}] ✅ 同步: {bill_no} "
                            f"→ EC退货单ID={ec_return_id} (¥{total_amount}, "
                            f"{len(ec_products)}行商品, saleId={sale_id})"
                        )
                    else:
                        self.failed += 1
                        err = f"{bill_no}: {result.get('msg', '未知错误')}"
                        self.errors.append(err)
                        self._log(f"    [{i}/{self.total_pulled}] ❌ {err}")

                except Exception as e:
                    self.failed += 1
                    err = f"{bill_no}: {str(e)}"
                    self.errors.append(err)
                    self._log(f"    [{i}/{self.total_pulled}] ❌ 异常: {err}")

                # 避免请求过快
                time.sleep(0.5)

        except Exception as e:
            self._log(f"❌ 同步过程出错: {e}")
            import traceback
            traceback.print_exc()
            return

        finally:
            # Step 4: 更新同步时间
            self.state.update_return_sync()

        self._print_summary(start_time)

    def _print_summary(self, start_time: datetime):
        """打印汇总报告"""
        elapsed = (datetime.now() - start_time).total_seconds()
        self._log("=" * 60)
        self._log(f"同步完成！耗时 {elapsed:.1f} 秒")
        self._log(f"  金蝶拉取: {self.total_pulled} 条")
        self._log(f"  成功同步: {self.synced}")
        self._log(f"  已同步跳过: {self.skipped_synced}")
        self._log(f"  无客户映射跳过: {self.skipped_no_customer}")
        self._log(f"  失败: {self.failed}")
        if self.errors:
            self._log(f"  错误详情:")
            for e in self.errors:
                self._log(f"    ❌ {e}")
        self._log("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="金蝶销售退货单 → EC 退货单 同步")
    parser.add_argument("--full", action="store_true", help="全量同步（忽略上次同步时间）")
    args = parser.parse_args()

    runner = ReturnSyncRunner()
    runner.run(full_sync=args.full)


if __name__ == "__main__":
    main()
