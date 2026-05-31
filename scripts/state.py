"""
同步状态管理 - 记录上次同步时间（用于增量同步）
"""
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
from config import STATE_FILE


class SyncState:
    """管理同步状态（存储在 state.json 中）"""

    def __init__(self, filepath: Path = None):
        self.filepath = filepath or STATE_FILE
        self._data: dict = {
            "last_customer_sync": None,
            "last_order_sync": None,
            "last_product_sync": None,
            "last_return_sync": None,
            "last_outbound_sync": None,
            "category_product_map": {},
            "return_order_map": {},        # JDY退货单ID → EC退货单ID
            "material_product_map": {},    # JDY商品ID(material_id) → EC产品ID
            "outbound_order_map": {},      # JDY出库单ID → EC订单ID
        }
        self._load()

    def _load(self):
        """从文件加载状态"""
        if self.filepath.exists():
            try:
                with open(self.filepath, "r") as f:
                    self._data = json.load(f)
            except (json.JSONDecodeError, IOError):
                pass

    def _save(self):
        """保存状态到文件"""
        self.filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(self.filepath, "w") as f:
            json.dump(self._data, f, indent=2)

    @property
    def last_customer_sync(self) -> Optional[str]:
        """
        上次客户同步时间
        格式: "2024-01-01 00:00:00"
        """
        return self._data.get("last_customer_sync")

    def update_customer_sync(self, sync_time: str = None):
        """更新客户同步时间"""
        self._data["last_customer_sync"] = sync_time or self._now_str()
        self._save()

    @property
    def last_order_sync(self) -> Optional[str]:
        """上次订单同步时间"""
        return self._data.get("last_order_sync")

    def update_order_sync(self, sync_time: str = None):
        """更新订单同步时间"""
        self._data["last_order_sync"] = sync_time or self._now_str()
        self._save()

    # ===== 产品同步状态 =====

    @property
    def last_product_sync(self) -> Optional[str]:
        """上次产品（金蝶分类→EC产品）同步时间"""
        return self._data.get("last_product_sync")

    def update_product_sync(self, sync_time: str = None):
        """更新产品同步时间"""
        self._data["last_product_sync"] = sync_time or self._now_str()
        self._save()

    @property
    def category_product_map(self) -> dict:
        """金蝶分类ID → EC产品信息 映射表"""
        return self._data.get("category_product_map", {})

    def add_category_product_mapping(self, jdy_category_id: str, ec_product_id: int, jdy_name: str):
        """记录一条映射"""
        if "category_product_map" not in self._data:
            self._data["category_product_map"] = {}
        self._data["category_product_map"][str(jdy_category_id)] = {
            "ec_product_id": ec_product_id,
            "jdy_name": jdy_name,
        }
        self._save()

    def get_mapped_ec_product_id(self, jdy_category_id: str) -> Optional[int]:
        """查询金蝶分类ID对应的EC产品ID"""
        mapping = self.category_product_map.get(str(jdy_category_id))
        return mapping["ec_product_id"] if mapping else None

    # ===== 退货单同步状态 =====

    @property
    def last_return_sync(self) -> Optional[str]:
        """上次退货单同步时间 (格式: "2024-01-01 00:00:00")"""
        return self._data.get("last_return_sync")

    def update_return_sync(self, sync_time: str = None):
        """更新退货单同步时间"""
        self._data["last_return_sync"] = sync_time or self._now_str()
        self._save()

    # ---- 退货单去重映射 ----

    @property
    def return_order_map(self) -> dict:
        """JDY退货单ID → {ec_return_id, synced_at} 映射表"""
        return self._data.get("return_order_map", {})

    def add_return_order_mapping(self, jdy_return_id: str, ec_return_id: int):
        """记录一条退货单同步映射"""
        if "return_order_map" not in self._data:
            self._data["return_order_map"] = {}
        self._data["return_order_map"][str(jdy_return_id)] = {
            "ec_return_id": ec_return_id,
            "synced_at": self._now_str(),
        }
        self._save()

    def is_return_order_synced(self, jdy_return_id: str) -> bool:
        """检查退货单是否已同步"""
        return str(jdy_return_id) in self.return_order_map

    # ---- 商品ID映射（JDY material_id → EC product_id） ----

    @property
    def material_product_map(self) -> dict:
        """JDY商品ID(material_id) → {ec_product_id, material_name} 映射表"""
        return self._data.get("material_product_map", {})

    def add_material_product_mapping(self, jdy_material_id: str, ec_product_id: int, material_name: str = ""):
        """记录JDY商品ID到EC产品ID的映射"""
        if "material_product_map" not in self._data:
            self._data["material_product_map"] = {}
        self._data["material_product_map"][str(jdy_material_id)] = {
            "ec_product_id": ec_product_id,
            "material_name": material_name,
        }
        self._save()

    def get_mapped_ec_product_id_for_material(self, jdy_material_id: str) -> Optional[int]:
        """查询JDY商品ID对应的EC产品ID"""
        mapping = self.material_product_map.get(str(jdy_material_id))
        return mapping["ec_product_id"] if mapping else None

    # ===== 出库单同步状态 =====

    @property
    def last_outbound_sync(self) -> Optional[str]:
        """上次出库单同步时间 (格式: "2024-01-01 00:00:00")"""
        return self._data.get("last_outbound_sync")

    def update_outbound_sync(self, sync_time: str = None):
        """更新出库单同步时间"""
        self._data["last_outbound_sync"] = sync_time or self._now_str()
        self._save()

    # ---- 出库单去重映射 ----

    @property
    def outbound_order_map(self) -> dict:
        """JDY出库单ID → {ec_order_id, synced_at} 映射表"""
        return self._data.get("outbound_order_map", {})

    def add_outbound_order_mapping(self, jdy_outbound_id: str, ec_order_id: int):
        """记录一条出库单同步映射"""
        if "outbound_order_map" not in self._data:
            self._data["outbound_order_map"] = {}
        self._data["outbound_order_map"][str(jdy_outbound_id)] = {
            "ec_order_id": ec_order_id,
            "synced_at": self._now_str(),
        }
        self._save()

    def is_outbound_order_synced(self, jdy_outbound_id: str) -> bool:
        """检查出库单是否已同步"""
        return str(jdy_outbound_id) in self.outbound_order_map

    # ---- 工具方法 ----

    def get_timestamp_ms(self, date_str: str) -> int:
        """将时间字符串转为毫秒时间戳（13位）"""
        if not date_str:
            return 0
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
            return int(dt.timestamp() * 1000)
        except ValueError:
            return 0

    @staticmethod
    def _now_str() -> str:
        """当前时间字符串"""
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
