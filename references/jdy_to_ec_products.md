# 金蝶云星辰 → EC 产品同步 参考文档

## 金蝶云星辰 — 商品分类列表

```
GET https://api.kingdee.com/jdy/v2/bd/material_group
```

### 请求参数（Query，全部选填）
| 参数 | 类型 | 说明 |
|------|------|------|
| `search` | string | 模糊搜索 - 按名称 |
| `parent` | array | 上级分类ID |
| `create_start_time` | string | 创建开始（毫秒时间戳） |
| `create_end_time` | string | 创建结束（毫秒时间戳） |
| `modify_start_time` | string | 修改开始（毫秒时间戳） |
| `modify_end_time` | string | 修改结束（毫秒时间戳） |
| `page` | string | 页码，默认1 |
| `page_size` | string | 每页条数，默认10 |

### 响应字段
| 字段 | 类型 | 说明 |
|------|------|------|
| `errcode` | int | 0=成功 |
| `description` | string | 返回信息 |
| `data.rows` | array | 分类列表 |
| `rows[].id` | string | 分类ID |
| `rows[].number` | string | 分类编码 |
| `rows[].name` | string | 分类名称 |
| `rows[].level` | string | 级次 |
| `rows[].is_leaf` | boolean | 是否叶子节点 |
| `rows[].create_time` | string | 创建时间 |
| `rows[].modify_time` | string | 修改时间 |
| `data.total_page` | int | 总页数 |
| `data.count` | string | 总记录数 |

---

## EC（六度人和）— 新增产品

```
POST https://open.workec.com/v2/sales/addProduct
```

### 请求参数
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `optUserId` | Long | ✅ | 操作用户ID |
| `product.groupId` | Long | ✅ | 产品分组ID |
| `product.productName` | String | ✅ | 产品名称 |
| `product.productUnit` | String | ✅ | 产品单位 |
| `product.money` | BigDecimal | ✅ | 销售单价（无规格时） |
| `product.onOff` | int | ✅ | 0=上架, 1=下架 |
| `product.specs` | int | ✅ | 0=无规格, 1=有规格 |

### 响应
```json
{"code": 200, "msg": "成功", "data": 19646}
```

---

## EC — 分页获取产品源数据（去重用）

```
POST https://open.workec.com/v2/sales/getProductList
```

### 请求参数
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `optUserId` | Long | ✅ | 用户ID |
| `pageNo` | Integer | ✅ | 页码 |
| `pageSize` | Integer | ✅ | 每页条数 |

### 响应 list 字段
| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | Long | 产品ID |
| `productName` | String | 产品名称 |
| `groupId` | Integer | 分组ID |
| `productMoney` | Double | 金额 |
| `unit` | String | 单位 |
| `onOff` | Integer | 上下架 |

---

## 同步配置

| 配置项 | 值 | 说明 |
|--------|-----|------|
| EC_OPT_USER_ID | 3446438 | 操作用户ID |
| PRODUCT_DEFAULT_UNIT | 个 | 默认单位 |
| PRODUCT_DEFAULT_PRICE | 0.00 | 默认价格 |
| PRODUCT_GROUP_ID | 0 | 产品分组（0=不设） |
