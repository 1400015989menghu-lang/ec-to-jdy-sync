# 金蝶云星辰（JDY）API 参考

## 认证体系

金蝶云星辰使用**双层认证**：签名认证 + Token 认证。

### 1. 获取 app-token

```
GET https://api.kingdee.com/jdyconnector/app_management/kingdee_auth_token
```

**URL 参数**：
- `app_key` - 应用 Key（S4aaVJSF）
- `app_signature` - Base64(HMAC-SHA256(appSecret, appKey))

**请求头**：
- `X-Api-ClientID` - 应用 ID（267904）
- `X-Api-Auth-Version` - API 版本（固定 2.0）
- `X-Api-TimeStamp` - 13位毫秒时间戳
- `X-Api-Nonce` - 随机整数
- `X-Api-SignHeaders` - 参与签名的 Header（固定 X-Api-TimeStamp,X-Api-Nonce）
- `X-Api-Signature` - 签名值

**签名原文构建规则**：
```
METHOD\nURL_PATH\nPARAMS\nHEADERS_SIGN_STR
```
- METHOD：大写（GET/POST）
- URL_PATH：URL 编码后的路径
- PARAMS：双重 URL 编码后的 query string（按 key 排序）
- HEADERS_SIGN_STR：`X-Api-TimeStamp:{ts}\nX-Api-Nonce:{nonce}`

**响应的 data**：
```json
{
  "errcode": 0,
  "description": "success",
  "data": {
    "app_token": "xxxx",
    "domain": "https://xxx.jdy.com/"
  }
}
```

> ⚠️ app-token 默认 24 小时有效（过期时间取决于账套配置），需缓存避免频繁获取。

### 2. 后续 API 调用

所有业务 API 调用需在请求头中携带：
- 签名头（同上，每次请求重新生成）
- `app-token` - 获取到的 token
- `X-GW-Router-Addr` - 从 token 响应中的 `domain` 字段获取

## 业务 API

### 客户保存

```
POST /jdy/v2/bd/customer/save
Content-Type: application/json
```

**请求体字段**（已确认）：
| 字段 | 类型 | 说明 |
|------|------|------|
| `number` | string | 客户编码（唯一键） |
| `name` | string | 客户名称 |

**请求体字段**（待验证）：
| 字段 | 类型 | 说明 |
|------|------|------|
| `mobile` | string | 手机号 |
| `telephone` | string | 座机 |
| `email` | string | 邮箱 |
| `region_name` | string | 地区 |
| `address` | string | 地址 |
| `remark` | string | 备注 |
| `customer_type` | string | 客户类型（person/company） |
| `id` | string | 更新时必传（客户内部ID） |

**响应**：
```json
{
  "errcode": 0,
  "description": "success",
  "data": {"id": "xxx", "number": "xxx"}
}
```

### 客户列表查询

```
GET /jdy/v2/bd/customer/list
```

**请求参数**：
- `page` - 页码
- `page_size` - 每页大小
- `search` - 搜索关键词（号码/名称）

**响应**：
```json
{
  "errcode": 0,
  "data": [...]
}
```

### 销售订单保存

```
POST /jdy/sal/sal_order_save
Content-Type: application/json
```

**请求体字段**：
| 字段 | 类型 | 说明 |
|------|------|------|
| `billno` | string | 订单编码 |
| `customerid_id` | string | 客户编码（关联金蝶客户 number） |
| `billdate` | string | 订单日期（yyyy-MM-dd） |
| `billsource` | string | 单据来源（固定 EC_SYNC） |
| `remark` | string | 单据备注 |
| `material_entity` | array | 分录明细 |
| `material_entity[].materialid_id` | string | 物料编码 |
| `material_entity[].qty` | string | 数量 |
| `material_entity[].unit_id` | string | 单位 |
| `material_entity[].price` | string | 单价 |

**响应**：
```json
{
  "errcode": 0,
  "description": "success"
}
```

## 错误码说明

| errcode | 说明 |
|---------|------|
| 0 | 成功 |
| > 0 | 业务异常，参考 description 字段 |

## ⚠️ 重要说明

1. 金蝶 API 完整字段列表需参考金蝶开放平台官方文档：https://open.jdy.com/
2. 上述字段中标记「待验证」的字段需要实际调用 API 确认字段名和格式
3. 签名规则可能因金蝶版本更新而调整，以官方文档为准
