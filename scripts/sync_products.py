#!/usr/bin/env python3
"""
金蝶云星辰 商品分类 → EC 产品 同步脚本

每日凌晨 1:00 自动执行，或手动运行：
  python3 scripts/sync_products.py             # 增量同步
  python3 scripts/sync_products.py --full      # 全量同步
"""
import sys
import os
import time
import argparse
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import (
    EC_OPT_USER_ID, PRODUCT_DEFAULT_UNIT,
    PRODUCT_DEFAULT_PRICE, PRODUCT_GROUP_ID,
)
from ec_client import ECClient
from jdy_client import JDYClient
from state import SyncState


class ProductSyncRunner:
    """金蝶商品分类 → EC 产品 同步器"""

    def __init__(self):
        self.ec = ECClient()
        self.jdy = JDYClient()
        self.state = SyncState()

        self.created = 0       # 新增产品数
        self.skipped = 0       # 已存在跳过数
        self.errors = []       # 错误记录

    def _log(self, msg: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {msg}")

    # ===== 主流程 =====

    def run(self, full_sync: bool = False):
        """执行同步"""
        start_time = datetime.now()
        self._log("=" * 60)
        self._log(f"金蝶商品分类 → EC产品 同步开始（模式: {'全量' if full_sync else '增量'}）")
        self._log("=" * 60)

        try:
            # Step 1: 获取金蝶 Token
            self._log("① 获取金蝶 access_token ...")
            token = self.jdy.get_access_token()
            self._log(f"    Token 获取成功: {token[:20]}...")

            # Step 2: 拉取金蝶商品分类
            self._log("② 拉取金蝶商品分类数据 ...")
            if full_sync:
                categories = self.jdy.get_all_material_groups()
            else:
                last_sync = self.state.last_product_sync
                if last_sync:
                    modify_since_ms = str(self.state.get_timestamp_ms(last_sync))
                    self._log(f"    增量模式: 从 {last_sync} 开始")
                else:
                    modify_since_ms = None
                    self._log("    首次同步，转为全量模式")
                categories = self.jdy.get_all_material_groups(modify_since_ms=modify_since_ms)

            self._log(f"    拉取到 {len(categories)} 个商品分类")

            if not categories:
                self._log("    无新数据，同步结束")
                self.state.update_product_sync()
                return

            # Step 3: 拉取 EC 已有产品（用于去重）
            self._log("③ 拉取 EC 已有产品列表（用于去重）...")
            ec_products = self.ec.get_all_products(EC_OPT_USER_ID)
            self._log(f"    EC 现有 {len(ec_products)} 个产品")

            # Step 4: 逐个同步
            self._log(f"④ 开始逐个同步 {len(categories)} 个分类 ...")
            for i, cat in enumerate(categories, 1):
                cat_id = str(cat.get("id", ""))
                cat_name = cat.get("name", "").strip()
                cat_number = cat.get("number", "")
                cat_level = cat.get("level", "")
                is_leaf = cat.get("is_leaf", False)

                if not cat_name:
                    self._log(f"    [{i}/{len(categories)}] ⏭ 跳过：分类名称为空 (id={cat_id})")
                    self.skipped += 1
                    continue

                # 构建 EC 产品名称（带上金蝶编码区分同名分类）
                # ec_product_name = f"{cat_number}-{cat_name}" if cat_number else cat_name
                ec_product_name = cat_name

                # 4a. 检查是否已存在于映射表
                mapped_id = self.state.get_mapped_ec_product_id(cat_id)
                if mapped_id:
                    self._log(f"    [{i}/{len(categories)}] ⏭ 跳过：{cat_name}（已同步，EC产品ID={mapped_id}）")
                    self.skipped += 1
                    continue

                # 4b. 按名称在 EC 产品列表中匹配
                existing = self.ec.find_product_by_name(ec_product_name, ec_products)
                if existing:
                    ec_id = existing.get("id")
                    self.state.add_category_product_mapping(cat_id, ec_id, cat_name)
                    self._log(f"    [{i}/{len(categories)}] ⏭ 跳过：{cat_name}（名称已存在于EC，产品ID={ec_id}）")
                    self.skipped += 1
                    continue

                # 4c. 创建新产品
                try:
                    result = self.ec.add_product(
                        opt_user_id=EC_OPT_USER_ID,
                        product_name=ec_product_name,
                        group_id=PRODUCT_GROUP_ID,
                        product_unit=PRODUCT_DEFAULT_UNIT,
                        money=PRODUCT_DEFAULT_PRICE,
                        on_off=0,
                        specs=0,
                    )

                    if result.get("code") == 200:
                        ec_product_id = result.get("data")
                        self.state.add_category_product_mapping(cat_id, ec_product_id, cat_name)
                        self._log(
                            f"    [{i}/{len(categories)}] ✅ 新增：{cat_name} "
                            f"→ EC产品ID={ec_product_id} "
                            f"(层级={cat_level}, 叶子={'是' if is_leaf else '否'})"
                        )
                        self.created += 1
                    else:
                        err = f"{cat_name}: {result.get('msg', '未知错误')}"
                        self._log(f"    [{i}/{len(categories)}] ❌ 失败：{err}")
                        self.errors.append(err)

                except Exception as e:
                    err = f"{cat_name}: {str(e)}"
                    self._log(f"    [{i}/{len(categories)}] ❌ 异常：{err}")
                    self.errors.append(err)

                # 避免请求过快
                time.sleep(0.3)

        except Exception as e:
            self._log(f"❌ 同步过程出错: {e}")
            import traceback
            traceback.print_exc()
            return

        finally:
            # Step 5: 更新同步时间
            self.state.update_product_sync()

        # 打印汇总
        elapsed = (datetime.now() - start_time).total_seconds()
        self._log("=" * 60)
        self._log(f"同步完成！耗时 {elapsed:.1f} 秒")
        self._log(f"  新增产品: {self.created}")
        self._log(f"  跳过（已存在）: {self.skipped}")
        self._log(f"  失败: {len(self.errors)}")
        if self.errors:
            self._log(f"  错误详情: {self.errors}")
        self._log("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="金蝶商品分类 → EC 产品 同步")
    parser.add_argument("--full", action="store_true", help="全量同步（忽略上次同步时间）")
    args = parser.parse_args()

    runner = ProductSyncRunner()
    runner.run(full_sync=args.full)


if __name__ == "__main__":
    main()
