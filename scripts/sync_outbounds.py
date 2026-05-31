#!/usr/bin/env python3
"""
金蝶云星辰 销售出库单 → EC 销售订单 同步脚本

每10分钟自动执行，或手动运行：
  python3 scripts/sync_outbounds.py             # 增量同步
  python3 scripts/sync_outbounds.py --full      # 全量同步

流程：
① 获取金蝶 Token
② 拉取金蝶已审核销售出库单列表（bill_status=C，增量）
③ 对每条出库单：
   - 解析客户ID → EC crmId（金蝶客户number字段）
   - 解析商品分录 → EC 订单商品列表（material_id→productId映射）
   - 调用 EC 创建订单接口
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
    OUTBOUND_SYNC_USER_ID, OUTBOUND_ORDER_STATUS,
    OUTBOUND_PAGE_SIZE,
)
from ec_client import ECClient
from jdy_client import JDYClient
from state import SyncState


class OutboundSyncRunner:
    """金蝶销售出库单 → EC 销售订单 同步器"""

    def __init__(self):
        self.ec = ECClient()
        self.jdy = JDYClient()
        self.state = SyncState()

        # 统计
        self.total_pulled = 0
        self.synced = 0
        self.skipped_synced = 0
        self.skipped_no_customer = 0
        self.failed = 0
        self.errors: List[str] = []

        # 缓存
        self._customer_cache: Dict[str, Optional[str]] = {}
        self._ec_products_cache: Optional[list] = None

    def _log(self, msg: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {msg}")

    # ===== 客户ID解析 =====

    def resolve_crm_id(self, jdy_customer_id: str) -> Optional[str]:
        """将金蝶客户ID解析为EC crmId（通过金蝶客户 number 字段）"""
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
        """将金蝶商品ID解析为EC产品ID"""
        # 1. 查本地映射表
        mapped_id = self.state.get_mapped_ec_product_id_for_material(material_id)
        if mapped_id:
            return mapped_id

        # 2. 按名称在EC产品中匹配
        if not material_name:
            return None

        if self._ec_products_cache is None:
            try:
                self._ec_products_cache = self.ec.get_all_products(OUTBOUND_SYNC_USER_ID)
                self._log(f"    加载 EC 产品列表: {len(self._ec_products_cache)} 个")
            except Exception as e:
                self._log(f"    ⚠ 加载EC产品列表失败: {e}")
                self._ec_products_cache = []

        for prod in self._ec_products_cache:
            if prod.get("productName", "").strip() == material_name.strip():
                ec_product_id = prod.get("id")
                if ec_product_id:
                    self.state.add_material_product_mapping(
                        material_id, ec_product_id, material_name
                    )
                    return ec_product_id

        return None

    # ===== 金额单位检测 =====

    @staticmethod
    def detect_amount_unit(price: float) -> float:
        """
        自动检测金蝶金额是否为分单位
        规则：单价 > 100000 触发分→元转换
        """
        if price > 100000:
            return round(price / 100, 2)
        return round(price, 2)

    # ===== 主流程 =====

    def run(self, full_sync: bool = False):
        start_time = datetime.now()
        self._log("=" * 60)
        mode_text = "全量" if full_sync else "增量"
        self._log(f"金蝶出库单 → EC订单 同步开始（模式: {mode_text}）")
        self._log("=" * 60)

        try:
            # Step 1: 获取金蝶 Token
            self._log("① 获取金蝶 access_token ...")
            token = self.jdy.get_access_token()
            self._log(f"    Token 获取成功: {token[:20]}...")

            # Step 2: 拉取出库单
            self._log("② 拉取金蝶已审核销售出库单 ...")
            if full_sync:
                modify_since_ms = None
            else:
                last_sync = self.state.last_outbound_sync
                if last_sync:
                    modify_since_ms = str(self.state.get_timestamp_ms(last_sync))
                    self._log(f"    增量模式: 从 {last_sync} 开始")
                else:
                    modify_since_ms = None
                    self._log("    首次同步，拉取所有已审核出库单")

            outbound_orders = self.jdy.get_all_outbound_orders(
                bill_status="C",
                modify_since_ms=modify_since_ms,
            )
            self.total_pulled = len(outbound_orders)
            self._log(f"    拉取到 {self.total_pulled} 条已审核出库单")

            if not outbound_orders:
                self._log("    无新数据，同步结束")
                self.state.update_outbound_sync()
                self._print_summary(start_time)
                return

            # Step 3: 逐条同步
            self._log(f"③ 开始逐条同步 {self.total_pulled} 条出库单 ...")

            for i, jdy_outbound in enumerate(outbound_orders, 1):
                outbound_id = str(jdy_outbound.get("id", ""))
                bill_no = jdy_outbound.get("bill_no", "")
                total_amount_raw = float(jdy_outbound.get("total_amount", 0) or 0)

                try:
                    # 3a. 去重检查
                    if self.state.is_outbound_order_synced(outbound_id):
                        self.skipped_synced += 1
                        self._log(
                            f"    [{i}/{self.total_pulled}] ⏭ 已同步: {bill_no} "
                            f"(总金额={total_amount_raw})"
                        )
                        continue

                    # 3b. 解析客户
                    jdy_customer_id = str(jdy_outbound.get("customer_id", ""))
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

                    # 3c. 映射商品分录
                    material_entity = jdy_outbound.get("material_entity", [])
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
                        qty = int(float(mat.get("qty", 0) or 0))
                        price_raw = float(mat.get("price", 0) or 0)
                        cost_raw = float(mat.get("cost", mat.get("unit_cost", 0)) or 0)
                        mat_model = mat.get("material_model", "")
                        comment = mat.get("comment", "")

                        if qty <= 0:
                            continue

                        # 解析产品ID
                        product_id = self.resolve_product_id(mat_id, mat_name)
                        if not product_id:
                            self._log(
                                f"    [{i}/{self.total_pulled}] ⚠ {bill_no}: "
                                f"商品 {mat_name}(material_id={mat_id}) 无EC产品映射，跳过该行"
                            )
                            continue

                        # 金额转换（分→元自动检测）
                        sale_money = self.detect_amount_unit(price_raw)
                        cost_money = self.detect_amount_unit(cost_raw)

                        ec_products.append({
                            "productId": product_id,
                            "specsId": 0,
                            "saleMoney": sale_money,
                            "costMoney": cost_money,
                            "productNum": qty,
                            "saleDiscount": 100,  # 默认不折扣
                            "productMemo": comment[:100] if comment else "",
                        })

                    if not ec_products:
                        self.failed += 1
                        err = f"{bill_no}: 所有商品行均无EC产品映射"
                        self.errors.append(err)
                        self._log(f"    [{i}/{self.total_pulled}] ❌ {err}")
                        continue

                    # 3d. 构建EC订单
                    title = f"金蝶出库-{bill_no}"[:100]
                    order_amount = self.detect_amount_unit(total_amount_raw) if total_amount_raw else None

                    # 3e. 调用EC创建订单
                    result = self.ec.create_sales_order(
                        opt_user_id=OUTBOUND_SYNC_USER_ID,
                        crm_id=crm_id,
                        title=title,
                        products=ec_products,
                        order_amount=order_amount,
                        order_status=OUTBOUND_ORDER_STATUS,
                        code=bill_no,
                    )

                    if result.get("code") == 200:
                        ec_order_id = result.get("data")
                        self.state.add_outbound_order_mapping(outbound_id, ec_order_id)
                        self.synced += 1
                        self._log(
                            f"    [{i}/{self.total_pulled}] ✅ 同步: {bill_no} "
                            f"→ EC订单ID={ec_order_id} (¥{order_amount}, "
                            f"{len(ec_products)}行商品)"
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
            self.state.update_outbound_sync()

        self._print_summary(start_time)

    def _print_summary(self, start_time: datetime):
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
    parser = argparse.ArgumentParser(description="金蝶销售出库单 → EC 订单 同步")
    parser.add_argument("--full", action="store_true", help="全量同步（忽略上次同步时间）")
    args = parser.parse_args()

    runner = OutboundSyncRunner()
    runner.run(full_sync=args.full)


if __name__ == "__main__":
    main()
