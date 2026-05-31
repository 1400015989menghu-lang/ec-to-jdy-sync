"""
EC（六度人和）API 客户端
认证方式：标准签名算法
- X-Ec-Cid: 企业唯一标识ID
- X-Ec-Sign: MD5(appId=xxx&appSecret=xxx&timeStamp=xxx) 转大写
- X-Ec-TimeStamp: 毫秒时间戳（120秒有效期）
"""
import requests
import time
import hashlib
from typing import Optional, List, Dict, Any

from config import (
    EC_BASE_URL, EC_APP_ID, EC_APP_SECRET, EC_CID, PAGE_SIZE
)


class ECClient:
    """EC 开放平台 API 客户端"""

    def __init__(self, base_url: str = None, app_id: str = None,
                 app_secret: str = None, cid: str = None):
        self.base_url = (base_url or EC_BASE_URL).rstrip("/")
        self.app_id = app_id or EC_APP_ID
        self.app_secret = app_secret or EC_APP_SECRET
        self.cid = cid or EC_CID
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json",
        })

    def _make_sign(self, timestamp: str) -> str:
        """
        生成 EC 请求签名
        规则：MD5(appId=xxx&appSecret=xxx&timeStamp=xxx) → 转大写
        """
        sign_str = f"appId={self.app_id}&appSecret={self.app_secret}&timeStamp={timestamp}"
        md5_hash = hashlib.md5(sign_str.encode("utf-8")).hexdigest()
        return md5_hash.upper()

    def _request(self, method: str, path: str, **kwargs) -> Dict[str, Any]:
        """统一请求方法，自动注入认证头"""
        timestamp = str(int(time.time() * 1000))
        headers = kwargs.pop("headers", {})
        headers.update({
            "X-Ec-Cid": self.cid,
            "X-Ec-Sign": self._make_sign(timestamp),
            "X-Ec-TimeStamp": timestamp,
        })
        url = f"{self.base_url}{path}"
        resp = self.session.request(method, url, headers=headers, timeout=30, **kwargs)
        resp.raise_for_status()
        return resp.json()

    def query_customers(
        self,
        modify_start: Optional[str] = None,
        modify_end: Optional[str] = None,
        page_no: int = 1,
        page_size: int = None,
    ) -> Dict[str, Any]:
        """
        查询客户列表
        modify_start/modify_end 格式: "2024-01-01 00:00:00"
        返回: {"code": 200, "data": {"customerInfoList": [...], "pageInfo": {...}}}
        """
        payload: Dict[str, Any] = {
            "pageNo": page_no,
            "pageSize": page_size or PAGE_SIZE,
        }
        if modify_start or modify_end:
            payload["modifyTime"] = {}
            if modify_start:
                payload["modifyTime"]["startTime"] = modify_start
            if modify_end:
                payload["modifyTime"]["endTime"] = modify_end

        result = self._request("POST", "/v2/customer/queryList", json=payload)
        return result

    def get_all_customers(self, modify_since: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        分页拉取全部客户（增量：只拉 modifyTime > modify_since 的客户）
        modify_since 格式: "2024-01-01 00:00:00"
        """
        all_customers: List[Dict[str, Any]] = []
        page_no = 1

        while True:
            result = self.query_customers(
                modify_start=modify_since,
                page_no=page_no,
            )
            if result.get("code") != 200:
                raise Exception(f"EC 查询客户失败: {result.get('msg')}")

            data = result.get("data", {})
            customer_list = data.get("customerInfoList", [])
            if not customer_list:
                break

            all_customers.extend(customer_list)

            page_info = data.get("pageInfo", {})
            if page_no >= page_info.get("maxPageNo", 1):
                break
            page_no += 1

        return all_customers

    def get_sales_orders(
        self,
        status: int = 3,
        creat_start: Optional[str] = None,
        creat_end: Optional[str] = None,
        page_no: int = 1,
    ) -> Dict[str, Any]:
        """
        查询销售订单列表
        status: 2=发现机会, 3=结单, 4=无效
        creat_start/creat_end 格式: "2018-03-20 00:00:00"
        返回: {"code": 200, "data": [...], "total": N}
        """
        payload: Dict[str, Any] = {
            "status": status,
            "pageNo": page_no,
        }
        if creat_start or creat_end:
            time_range = ""
            if creat_start:
                time_range += creat_start
            time_range += ";"
            if creat_end:
                time_range += creat_end
            payload["creatTime"] = time_range

        return self._request("POST", "/v2/sales/getSales", json=payload)

    def get_all_orders(
        self,
        status: int = 3,
        creat_since: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        分页拉取全部订单（增量：只拉 creatTime > creat_since 的订单）
        ⚠️ EC getSales 接口 creatTime 间隔不能超过31天
        """
        all_orders: List[Dict[str, Any]] = []
        page_no = 1

        while True:
            result = self.get_sales_orders(
                status=status,
                creat_start=creat_since,
                page_no=page_no,
            )
            if result.get("code") != 200:
                raise Exception(f"EC 查询订单失败: {result.get('msg')}")

            order_list = result.get("data", [])
            if not order_list:
                break

            all_orders.extend(order_list)

            if page_no >= result.get("maxPageNo", 1):
                break
            page_no += 1

        return all_orders

    def get_order_detail(self, sale_id: int) -> Optional[Dict[str, Any]]:
        """
        查询订单详情（获取自定义字段等完整信息）
        """
        result = self._request("GET", "/v2/sales/getSalesDetail", params={"saleId": sale_id})
        if result.get("code") == 200:
            return result.get("data")
        return None

    # ========== 产品操作 ==========

    def get_product_list(
        self,
        opt_user_id: int,
        page_no: int = 1,
        page_size: int = 200,
    ) -> Dict[str, Any]:
        """
        分页获取产品源数据
        POST /v2/sales/getProductList
        """
        payload = {
            "optUserId": opt_user_id,
            "pageNo": page_no,
            "pageSize": page_size,
        }
        return self._request("POST", "/v2/sales/getProductList", json=payload)

    def get_all_products(self, opt_user_id: int) -> list:
        """分页拉取全部产品"""
        all_products = []
        page_no = 1

        while True:
            result = self.get_product_list(opt_user_id, page_no=page_no)
            if result.get("code") != 200:
                raise Exception(f"EC 查询产品列表失败: {result.get('msg')}")

            data = result.get("data", {})
            products = data.get("list", [])
            if not products:
                break

            all_products.extend(products)

            if page_no >= data.get("maxPageNo", 1):
                break
            page_no += 1

        return all_products

    def find_product_by_name(self, product_name: str, all_products: list = None) -> Optional[Dict[str, Any]]:
        """按产品名称查找已有产品（用于去重）"""
        products = all_products or []
        for p in products:
            if p.get("productName", "").strip() == product_name.strip():
                return p
        return None

    def add_product(
        self,
        opt_user_id: int,
        product_name: str,
        group_id: int = 0,
        product_unit: str = "个",
        money: float = 0.0,
        on_off: int = 0,
        specs: int = 0,
    ) -> Dict[str, Any]:
        """
        新增产品
        POST /v2/sales/addProduct

        返回: {"code": 200, "msg": "成功", "data": 19646}
        """
        payload = {
            "optUserId": opt_user_id,
            "product": {
                "groupId": group_id,
                "productName": product_name,
                "productUnit": product_unit,
                "money": money,
                "onOff": on_off,
                "specs": specs,
            },
        }
        return self._request("POST", "/v2/sales/addProduct", json=payload)

    def get_product_group_list(self) -> Dict[str, Any]:
        """
        获取产品分组列表
        GET /v2/sales/getProductGroupList
        """
        return self._request("GET", "/v2/sales/getProductGroupList")

    # ========== 退货单操作 ==========

    def create_return_order(
        self,
        user_id: int,
        title: str,
        group_id: int,
        crm_id: int,
        sale_id: int,
        return_reason: int,
        products: list,
        code: str = None,
        memo: str = None,
    ) -> Dict[str, Any]:
        """
        创建退货单
        POST /v2/sales/saveReturn

        products: [{"productId": int, "productName": str, "returnMoney": float,
                     "returnQuantity": float, "returnTotal": float,
                     "specsId": int, "specsName": str}, ...]

        返回: {"code": 200, "msg": "成功", "data": <退货单ID>}
        """
        payload = {
            "userId": user_id,
            "saleReturn": {
                "title": title[:35],  # 限制35字符
                "groupId": group_id,
                "crmId": crm_id,
                "saleId": sale_id,
                "returnReason": return_reason,
                "saleReturnProducts": products,
            },
        }
        if code:
            payload["saleReturn"]["code"] = code
        if memo:
            payload["saleReturn"]["memo"] = memo[:50]  # 限制50字符

        return self._request("POST", "/v2/sales/saveReturn", json=payload)

    def query_order_by_code(self, code: str) -> Optional[Dict[str, Any]]:
        """
        按订单编码模糊搜索EC订单（用于解析saleId）
        POST /v2/sales/getSales
        返回匹配的第一条订单（含 id 字段即 saleId）
        """
        payload = {"search": code, "pageNo": 1}
        result = self._request("POST", "/v2/sales/getSales", json=payload)
        if result.get("code") != 200:
            return None
        data = result.get("data", [])
        if not data:
            return None
        for order in data:
            if order.get("code") == code:
                return order
        return None

    # ========== 订单创建操作 ==========

    def create_sales_order(
        self,
        opt_user_id: int,
        crm_id: int,
        title: str,
        products: list,
        order_amount: float = None,
        order_status: int = 2,
        code: str = None,
    ) -> Dict[str, Any]:
        """
        创建销售订单
        POST /v2/sales/addSales

        products: [{"productId": int, "specsId": int, "saleMoney": float,
                     "costMoney": float, "productNum": int, "saleDiscount": int,
                     "productMemo": str}, ...]

        order_status: 2=发现机会(默认), 3=结单
        返回: {"code": 200, "msg": "成功", "data": <订单ID>}
        """
        # EC 创建订单 API 使用数字ID作为字段名
        payload: Dict[str, Any] = {
            "optUserId": opt_user_id,
            "crmId": crm_id,
            "1": title[:100],  # 订单主题，100字以内
            "3": order_status,  # 订单状态
        }
        if order_amount is not None:
            payload["4"] = round(order_amount, 2)  # 订单金额
        if code:
            payload["code"] = code
        if products:
            payload["product"] = products

        return self._request("POST", "/v2/sales/addSales", json=payload)
