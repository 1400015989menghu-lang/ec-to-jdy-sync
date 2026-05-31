"""
金蝶云星辰（JDY）API 客户端
签名规范：金蝶 API 2.0 签名认证（HMAC-SHA256 hex → Base64）
"""
import time
import json
import random
import base64
import hmac
import hashlib
import requests
from urllib.parse import quote
from typing import Dict, Any, Optional

from config import (
    JDY_BASE_URL, JDY_APP_KEY, JDY_APP_SECRET,
    JDY_CLIENT_ID, JDY_CLIENT_SECRET, JDY_INSTANCE_ID
)


class JDYClient:
    """金蝶云星辰 API 客户端"""

    def __init__(self, base_url: str = None):
        self.base_url = (base_url or JDY_BASE_URL).rstrip("/")
        self.app_key = JDY_APP_KEY
        self.app_secret = JDY_APP_SECRET
        self.client_id = JDY_CLIENT_ID
        self.client_secret = JDY_CLIENT_SECRET
        self.instance_id = JDY_INSTANCE_ID

        self._access_token: Optional[str] = None
        self._domain: Optional[str] = None
        self._token_expire_time: float = 0

    # ========== 加密工具 ==========

    @staticmethod
    def _hmac_sha256_hex(key: str, data: str) -> str:
        """HMAC-SHA256 → 16进制字符串 (lowercase)"""
        mac = hmac.new(key.encode("utf-8"), data.encode("utf-8"), hashlib.sha256)
        return mac.hexdigest()

    @staticmethod
    def _hex_to_base64(hex_str: str) -> str:
        """16进制字符串 → Base64"""
        return base64.b64encode(hex_str.encode("utf-8")).decode("utf-8")

    @staticmethod
    def _url_encode(s: str) -> str:
        """标准 URL 编码（大写字母，/ 编码为 %2F）"""
        return quote(s, safe="")

    @staticmethod
    def _double_url_encode(s: str) -> str:
        """双重 URL 编码"""
        return JDYClient._url_encode(JDYClient._url_encode(s))

    # ========== 签名生成（金蝶 API 2.0 规范） ==========

    def _build_signature(
        self, method: str, path: str, params: Dict[str, str], timestamp: int, nonce: int
    ) -> str:
        """
        构建 X-Api-Signature

        签名原文格式（每部分换行，最后有换行符）：
        {METHOD}\n
        {URL_ENCODED_PATH}\n
        {DOUBLE_URL_ENCODED_PARAMS}\n
        x-api-nonce:{nonce}\nx-api-timestamp:{timestamp}\n

        签名算法：HMAC-SHA256(clientSecret, 签名原文) → 16进制 → Base64
        """
        # 1. 请求方式大写
        method_str = method.upper()

        # 2. Path URL 编码（/ 编码为 %2F）
        path_encoded = self._url_encode(path)

        # 3. Params 双重 URL 编码，按 key ASCII 升序排序
        params_str = ""
        if params:
            sorted_keys = sorted(params.keys())
            param_parts = []
            for k in sorted_keys:
                v = params[k]
                if isinstance(v, (list, dict)):
                    v_str = json.dumps(v, ensure_ascii=False, separators=(",", ":"))
                else:
                    v_str = str(v)
                param_parts.append(f"{k}={self._double_url_encode(v_str)}")
            params_str = "&".join(param_parts)

        # 4. Headers 签名串（必须小写 key）
        headers_str = f"x-api-nonce:{nonce}\nx-api-timestamp:{timestamp}"

        # 5. 拼接签名原文（每部分换行，最后也换行）
        sign_content = f"{method_str}\n{path_encoded}\n{params_str}\n{headers_str}\n"

        # 6. HMAC-SHA256 → hex → Base64
        hex_sign = self._hmac_sha256_hex(self.client_secret, sign_content)
        signature = self._hex_to_base64(hex_sign)

        return signature

    def _make_sign_headers(self, method: str, path: str, params: Dict[str, str] = None) -> Dict[str, str]:
        """生成签名认证 Headers"""
        timestamp = int(time.time() * 1000)
        nonce = random.randint(1000000000, 9999999999)
        signature = self._build_signature(method, path, params or {}, timestamp, nonce)

        return {
            "X-Api-ClientID": str(self.client_id),
            "X-Api-Auth-Version": "2.0",
            "X-Api-TimeStamp": str(timestamp),
            "X-Api-SignHeaders": "X-Api-TimeStamp,X-Api-Nonce",
            "X-Api-Nonce": str(nonce),
            "X-Api-Signature": signature,
        }

    # ========== Token 管理 ==========

    def get_access_token(self, force_refresh: bool = False) -> str:
        """
        获取 app-token（24小时有效，自动缓存）

        app_signature = Base64(HMAC-SHA256(appSecret, appKey).hexdigest())
        GET /jdyconnector/app_management/kingdee_auth_token
        """
        if not force_refresh and self._access_token and time.time() < self._token_expire_time:
            return self._access_token

        token_base = "https://api.kingdee.com"
        path = "/jdyconnector/app_management/kingdee_auth_token"

        # app_signature = Base64(HMAC-SHA256(appSecret, appKey) → hex)
        app_hex = self._hmac_sha256_hex(self.app_secret, self.app_key)
        app_signature = self._hex_to_base64(app_hex)

        params = {"app_key": self.app_key, "app_signature": app_signature}

        # 生成签名头
        sign_headers = self._make_sign_headers("GET", path, params)

        # 构建 URL（手动拼接，保持 param 顺序）
        sorted_keys = sorted(params.keys())
        query_parts = [f"{k}={self._url_encode(str(params[k]))}" for k in sorted_keys]
        url = f"{token_base}{path}?{'&'.join(query_parts)}"

        headers = {"Content-Type": "application/json", **sign_headers}

        resp = requests.get(url, headers=headers, timeout=30)
        result = resp.json()

        if resp.status_code != 200 or result.get("errcode") != 0:
            raise Exception(
                f"金蝶获取 token 失败 (HTTP {resp.status_code}): {result.get('description', '未知错误')}"
            )

        data = result.get("data", {})
        self._access_token = data.get("app_token", "")
        self._domain = data.get("domain", "")
        self._token_expire_time = time.time() + 23 * 3600  # 提前1小时刷新

        return self._access_token

    # ========== 通用请求 ==========

    def _request(
        self, method: str, path: str,
        json_data: Dict = None,
        params: Dict = None,
        **kwargs
    ) -> Dict[str, Any]:
        """统一请求方法，自动注入认证头"""
        token = self.get_access_token()
        sign_headers = self._make_sign_headers(method, path, params or {})

        headers = kwargs.pop("headers", {})
        headers.update(sign_headers)
        headers["Content-Type"] = "application/json"
        headers["app-token"] = token
        if self._domain:
            headers["X-GW-Router-Addr"] = self._domain

        # GET 请求：用 params 拼接 URL
        if method.upper() == "GET" and params:
            query_parts = [
                f"{k}={self._url_encode(str(v))}"
                for k, v in sorted((params or {}).items())
            ]
            url = f"{self.base_url}{path}?{'&'.join(query_parts)}"
            resp = requests.request(method, url, headers=headers, timeout=30, **kwargs)
        else:
            url = f"{self.base_url}{path}"
            resp = requests.request(method, url, json=json_data, headers=headers, timeout=30, **kwargs)

        return resp.json()

    # ========== 客户操作 ==========

    def query_customers(self, number: str = None, page: int = 1) -> Dict[str, Any]:
        """查询金蝶客户列表"""
        params = {"page": str(page), "page_size": "100"}
        if number:
            params["search"] = number
        return self._request("GET", "/jdy/v2/bd/customer/list", params=params)

    def find_customer_by_number(self, number: str) -> Optional[Dict[str, Any]]:
        """根据编码查找客户"""
        result = self.query_customers(number=number)
        if result.get("errcode") != 0:
            return None
        data = result.get("data", [])
        for item in data:
            if str(item.get("number")) == str(number):
                return item
        # 翻页查找
        for p in range(2, 10):
            r = self.query_customers(number=number, page=p)
            if r.get("errcode") != 0:
                break
            for item in r.get("data", []):
                if str(item.get("number")) == str(number):
                    return item
        return None

    def save_customer(self, customer_data: Dict[str, Any]) -> Dict[str, Any]:
        """保存/更新客户"""
        return self._request("POST", "/jdy/v2/bd/customer/save", json_data=customer_data)

    # ========== 订单操作 ==========

    def save_sales_order(self, order_data: Dict[str, Any]) -> Dict[str, Any]:
        """保存销售订单"""
        order_data["billsource"] = "EC_SYNC"
        return self._request("POST", "/jdy/sal/sal_order_save", json_data=order_data)

    def query_orders(self, billno: str = None) -> Dict[str, Any]:
        """查询销售订单"""
        params = {}
        if billno:
            params["search"] = billno
        return self._request("GET", "/jdy/v2/scm/sal_order/list", params=params)

    def find_order_by_billno(self, billno: str) -> Optional[Dict[str, Any]]:
        """根据订单编码查找订单"""
        result = self.query_orders(billno=billno)
        if result.get("errcode") != 0:
            return None
        for item in result.get("data", []):
            if str(item.get("billno")) == str(billno):
                return item
        return None

    # ========== 商品分类操作 ==========

    def query_material_groups(
        self,
        modify_start_time: str = None,
        modify_end_time: str = None,
        page: int = 1,
        page_size: int = 100,
    ) -> Dict[str, Any]:
        """
        查询商品分类列表（material_group）

        modify_start_time: 修改开始时间，毫秒时间戳字符串
        modify_end_time: 修改结束时间，毫秒时间戳字符串
        """
        params: Dict[str, str] = {
            "page": str(page),
            "page_size": str(page_size),
        }
        if modify_start_time:
            params["modify_start_time"] = modify_start_time
        if modify_end_time:
            params["modify_end_time"] = modify_end_time

        return self._request("GET", "/jdy/v2/bd/material_group", params=params)

    def get_all_material_groups(
        self,
        modify_since_ms: str = None,
    ) -> list:
        """
        分页拉取全部商品分类（增量：只拉修改时间 > modify_since_ms 的分类）
        """
        now_ms = str(int(time.time() * 1000))
        all_groups = []
        page = 1

        while True:
            result = self.query_material_groups(
                modify_start_time=modify_since_ms,
                modify_end_time=now_ms if modify_since_ms else None,
                page=page,
            )
            if result.get("errcode") != 0:
                raise Exception(f"金蝶查询商品分类失败: {result.get('description')}")

            data = result.get("data", {})
            rows = data.get("rows", [])
            if not rows:
                break

            all_groups.extend(rows)

            total_page = data.get("total_page", 1)
            if page >= total_page:
                break
            page += 1

        return all_groups

    # ========== 销售退货单操作 ==========

    def query_return_orders(
        self,
        bill_status: str = "C",
        modify_start_time: str = None,
        modify_end_time: str = None,
        page: int = 1,
        page_size: int = 100,
    ) -> Dict[str, Any]:
        """
        查询销售退货单列表 /jdy/v2/scm/sal_in_bound

        bill_status: ""=所有, C=已审核, Z=未审核
        modify_start_time/modify_end_time: 修改时间范围，毫秒时间戳字符串
        """
        params: Dict[str, str] = {
            "bill_status": bill_status,
            "page": str(page),
            "page_size": str(page_size),
        }
        if modify_start_time:
            params["modify_start_time"] = modify_start_time
        if modify_end_time:
            params["modify_end_time"] = modify_end_time

        return self._request("GET", "/jdy/v2/scm/sal_in_bound", params=params)

    def get_all_return_orders(
        self,
        bill_status: str = "C",
        modify_since_ms: str = None,
    ) -> list:
        """
        分页拉取全部已审核销售退货单（增量：只拉 modify_time > modify_since_ms）
        列表接口返回的每条记录已包含 material_entity（商品分录）和 payment_entry（付款信息）
        """
        now_ms = str(int(time.time() * 1000))
        all_orders = []
        page = 1

        while True:
            result = self.query_return_orders(
                bill_status=bill_status,
                modify_start_time=modify_since_ms or None,
                modify_end_time=now_ms if modify_since_ms else None,
                page=page,
            )
            if result.get("errcode") != 0:
                raise Exception(f"金蝶查询销售退货单失败: {result.get('description')}")

            # 响应结构：data可能是dict含rows/total_page，或直接是list
            data = result.get("data", {})
            if isinstance(data, list):
                rows = data
                if not rows:
                    break
                all_orders.extend(rows)
                break  # 列表响应通常一次性返回
            elif isinstance(data, dict):
                rows = data.get("rows", [])
                if not rows:
                    break
                all_orders.extend(rows)
                total_page = data.get("total_page", 1)
                if page >= total_page:
                    break
            else:
                break

            page += 1

        return all_orders

    def get_return_order_detail(self, order_id: str) -> Optional[Dict[str, Any]]:
        """
        获取单条销售退货单详情
        通过查询列表接口并指定id过滤（列表接口已含完整detail字段）
        """
        params = {"id": order_id, "bill_status": ""}
        result = self._request("GET", "/jdy/v2/scm/sal_in_bound", params=params)
        if result.get("errcode") != 0:
            return None
        data = result.get("data", [])
        if isinstance(data, list) and data:
            return data[0]
        if isinstance(data, dict) and data:
            return data
        return None

    def query_customer_by_id(self, customer_id: str) -> Optional[Dict[str, Any]]:
        """
        根据金蝶内部客户ID查询客户详情
        用于获取 customer.number（即 EC crmId）做映射
        """
        params = {"id": customer_id}
        result = self._request("GET", "/jdy/v2/bd/customer/list", params=params)
        if result.get("errcode") != 0:
            return None
        data = result.get("data", [])
        if isinstance(data, list) and data:
            return data[0]
        if isinstance(data, dict):
            return data
        return None

    # ========== 销售出库单操作 ==========

    def query_outbound_orders(
        self,
        bill_status: str = "C",
        modify_start_time: str = None,
        modify_end_time: str = None,
        page: int = 1,
        page_size: int = 100,
    ) -> Dict[str, Any]:
        """
        查询销售出库单列表 /jdy/v2/scm/sal_out_bound

        bill_status: ""=所有, C=已审核, Z=未审核
        modify_start_time/modify_end_time: 修改时间范围，毫秒时间戳字符串
        """
        params: Dict[str, str] = {
            "bill_status": bill_status,
            "page": str(page),
            "page_size": str(page_size),
        }
        if modify_start_time:
            params["modify_start_time"] = modify_start_time
        if modify_end_time:
            params["modify_end_time"] = modify_end_time

        return self._request("GET", "/jdy/v2/scm/sal_out_bound", params=params)

    def get_all_outbound_orders(
        self,
        bill_status: str = "C",
        modify_since_ms: str = None,
    ) -> list:
        """
        分页拉取全部已审核销售出库单（增量：只拉 modify_time > modify_since_ms）
        列表接口返回的每条记录已包含 material_entity（商品分录）和 payment_entry（付款信息）
        """
        now_ms = str(int(time.time() * 1000))
        all_orders = []
        page = 1

        while True:
            result = self.query_outbound_orders(
                bill_status=bill_status,
                modify_start_time=modify_since_ms or None,
                modify_end_time=now_ms if modify_since_ms else None,
                page=page,
            )
            if result.get("errcode") != 0:
                raise Exception(f"金蝶查询销售出库单失败: {result.get('description')}")

            data = result.get("data", {})
            if isinstance(data, list):
                rows = data
                if not rows:
                    break
                all_orders.extend(rows)
                break
            elif isinstance(data, dict):
                rows = data.get("rows", [])
                if not rows:
                    break
                all_orders.extend(rows)
                total_page = data.get("total_page", 1)
                if page >= total_page:
                    break
            else:
                break

            page += 1

        return all_orders

    def get_outbound_order_detail(self, order_id: str) -> Optional[Dict[str, Any]]:
        """
        获取单条销售出库单详情
        通过查询列表接口并指定id过滤（列表接口已含完整detail字段）
        """
        params = {"id": order_id, "bill_status": ""}
        result = self._request("GET", "/jdy/v2/scm/sal_out_bound", params=params)
        if result.get("errcode") != 0:
            return None
        data = result.get("data", [])
        if isinstance(data, list) and data:
            return data[0]
        if isinstance(data, dict) and data:
            return data
        return None
