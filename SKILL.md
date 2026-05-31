---
name: ec-to-jdy-sync
description: EC与金蝶云星辰双向数据同步。核心能力：EC到金蝶客户/订单同步，金蝶商品分类到EC产品同步，金蝶退货单到EC退货单同步，金蝶出库单到EC订单同步，支持增量同步和全量同步，支持定时自动执行。触发词：EC同步、六度人和同步、金蝶同步、商品分类同步、EC数据同步、出库单同步、ec sync
---

# EC ↔ 金蝶云星辰 双向数据同步 Skill

## 功能概述

支持 EC（六度人和）与金蝶云星辰之间的双向数据同步：

### 方向一：EC → 金蝶（每小时）
- **客户同步**：从 EC 拉取全部客户 → 写入金蝶云星辰客户资料
- **订单同步**：从 EC 拉取已结单订单（status=3）→ 写入金蝶销售订单
- **增量同步**：每次同步后记录时间戳，下次只拉取变更数据
- **去重逻辑**：用 EC 的 `crmId` 作为金蝶客户编码 `number`，已存在则更新、不存在则新增

### 方向二：金蝶 → EC（每日凌晨1点）
- **商品分类同步**：从金蝶拉取商品分类列表 → 写入 EC 产品
- **增量同步**：基于分类修改时间，只同步变更数据
- **去重逻辑**：本地映射表 + EC 产品名称匹配，避免重复创建

### 方向三：金蝶退货单 → EC（每10分钟）
- **销售退货单同步**：从金蝶拉取已审核退货单（bill_status=C）→ 写入 EC 退货单
- **增量同步**：基于退货单修改时间，只同步变更数据
- **字段映射**：金蝶客户ID→EC crmId（查金蝶客户number字段）、商品ID→EC产品ID（本地映射表+名称匹配）
- **去重逻辑**：本地映射表记录已同步退货单，防止重复创建

### 方向四：金蝶出库单 → EC（每10分钟）
- **销售出库单同步**：从金蝶拉取已审核出库单（bill_status=C）→ 写入 EC 销售订单
- **增量同步**：基于出库单修改时间，只同步变更数据
- **字段映射**：金蝶客户ID→EC crmId（查金蝶客户number字段）、商品ID→EC产品ID（本地映射表+名称匹配）
- **去重逻辑**：本地映射表记录已同步出库单，防止重复创建

## 触发方式

当用户提到以下需求时触发此 Skill：
- "同步 EC 数据到金蝶"
- "执行客户同步"
- "同步订单"
- "EC 数据同步"
- "同步金蝶商品分类"
- "金蝶分类同步到 EC"
- "同步退货单"
- "金蝶退货单同步"
- "同步出库单"
- "金蝶出库单同步"
- "出库单转订单"
- "sync ec to jdy"
- "sync jdy products"

## 使用方式

### 1. 配置凭证

确保 `.env` 文件已配置（技能目录下的 `.env`），包含 EC 和金蝶的 API 密钥：

```
EC_APP_ID=900333116588032000
EC_APP_SECRET=9PUNq53k2RzwesWr9eJ
EC_CID=请填写企业唯一标识ID
JDY_APP_KEY=S4aaVJSF
JDY_APP_SECRET=336fdd32c484b0f6d238619862cc0b2e7ad59272
JDY_CLIENT_ID=267904
JDY_CLIENT_SECRET=dcdd1a0348f476f43331c614e754f666
JDY_INSTANCE_ID=293477853998223360
```

### 2. 执行同步

**EC → 金蝶（客户+订单）：**
```bash
cd /Users/menghu/.workbuddy/skills/ec-to-jdy-sync && python3 scripts/sync.py
```

**金蝶 → EC（商品分类→产品）：**
```bash
cd /Users/menghu/.workbuddy/skills/ec-to-jdy-sync && python3 scripts/sync_products.py
```

**金蝶 → EC（退货单同步）：**
```bash
cd /Users/menghu/.workbuddy/skills/ec-to-jdy-sync && python3 scripts/sync_returns.py
```

**金蝶 → EC（出库单→订单同步）：**
```bash
cd /Users/menghu/.workbuddy/skills/ec-to-jdy-sync && python3 scripts/sync_outbounds.py
```

**全量同步：**
```bash
python3 scripts/sync.py --full        # EC→金蝶 全量
python3 scripts/sync_products.py --full  # 金蝶→EC 全量
```

### 3. 定时自动执行

已配置四个 Automation：
- **每小时**：EC → 金蝶 客户+订单同步
- **每日凌晨1点**：金蝶 → EC 商品分类同步
- **每10分钟**：金蝶退货单 → EC 退货单同步
- **每10分钟**：金蝶出库单 → EC 订单同步

## 脚本架构

```
ec-to-jdy-sync/
├── SKILL.md              # 本文件
├── .env                  # API 密钥配置
├── state.json            # 同步状态（自动生成，含映射表）
└── scripts/
    ├── sync.py           # EC→金蝶 主同步脚本（客户+订单）
    ├── sync_products.py  # 金蝶→EC 商品分类同步脚本
    ├── sync_returns.py   # 金蝶→EC 退货单同步脚本
    ├── sync_outbounds.py # 金蝶→EC 出库单→订单同步脚本
    ├── ec_client.py      # EC API 客户端
    ├── jdy_client.py     # 金蝶 API 客户端
    ├── state.py          # 同步状态管理（含分类→产品、退货单、出库单、商品映射）
    └── config.py         # 配置加载
```

## 字段映射

### 方向一：客户映射（EC → 金蝶）

| EC 字段 | 金蝶字段 | 说明 |
|---------|----------|------|
| `crmId` | `number` | 客户编码（唯一键，用于去重） |
| `name` / `company` | `name` | 客户名称（企业用 company，个人用 name） |
| `mobile` | `mobile` | 手机号 |
| `phone` | `telephone` | 座机 |
| `email` | `email` | 邮箱 |
| `prefecture` | `region_name` | 地区 |
| `companyAddress` | `address` | 地址 |
| `memo` | `remark` | 备注 |
| `crmType` | `customer_type` | 客户类型（0→person, 1→company） |

### 方向一：销售订单映射（EC → 金蝶）

| EC 字段 | 金蝶字段 | 说明 |
|---------|----------|------|
| `code` | `billno` | 订单编码（加 EC- 前缀） |
| `crmId` | `customerid_id` | 关联金蝶客户编码 |
| `money` | `material_entity[].price` | 订单金额 |
| `productId` | `material_entity[].materialid_id` | 物料编码（关联已有物料） |
| `createTime` / `dealDate` | `billdate` | 订单日期 |
| `productDes` + `remark` | `remark` | 订单备注 |

### 方向二：商品分类映射（金蝶 → EC）

| 金蝶字段 | EC 字段 | 说明 |
|----------|---------|------|
| `id` | 本地映射表记录 | 用于去重判断 |
| `name` | `productName` | 分类名称 → 产品名称 |
| `number` | 附加信息 | 编码可拼接至产品名 |
| — | `productUnit` | 默认「个」 |
| — | `money` | 默认 0.00 |
| — | `onOff` | 默认 0（上架） |
| — | `specs` | 默认 0（无规格） |
| — | `optUserId` | 操作用户 3446438 |

### 方向三：退货单映射（金蝶 → EC）

| 金蝶字段 | EC 字段 | 说明 |
|----------|---------|------|
| `id` | 本地映射表 | 金蝶退货单ID，用于去重 |
| `bill_no` | `code` / `title` | 金蝶单据编码→EC退货单编码，标题="金蝶退货-{bill_no}" |
| `customer_id` → 查金蝶客户 `number` | `crmId` | 通过金蝶客户详情获取number（=EC crmId） |
| `material_entity[].material_id` → 查映射表 | `saleReturnProducts[].productId` | 本地material_id→EC product_id映射表 |
| `material_entity[].material_name` | `saleReturnProducts[].productName` | 商品名称 |
| `material_entity[].price` | `saleReturnProducts[].returnMoney` | 退货单价（自动检测分→元转换） |
| `material_entity[].return_qty_unit` | `saleReturnProducts[].returnQuantity` | 退货数量 |
| `material_entity[].all_amount` | `saleReturnProducts[].returnTotal` | 退货总计金额 |
| `material_entity[].material_model` | `saleReturnProducts[].specsName` | 商品规格 |
| `src_inter_id` → 解析源单 `bill_no` | `saleId` | 尝试从金蝶源单ID解析EC订单ID |
| `remark` | `memo` | 退货备注（截断50字符） |
| — | `returnReason` | 默认7（其他原因） |
| — | `specsId` | 默认0（无规格） |
| — | `userId` | 固定3446438 |

### 方向四：出库单映射（金蝶 → EC）

| 金蝶字段 | EC 字段 | 说明 |
|----------|---------|------|
| `id` | 本地映射表 | 金蝶出库单ID，用于去重 |
| `bill_no` | `code` / `"1"`(title) | 金蝶单据编码→EC订单编码，标题="金蝶出库-{bill_no}" |
| `customer_id` → 查金蝶客户 `number` | `crmId` | 通过金蝶客户详情获取number（=EC crmId） |
| `material_entity[].material_id` → 查映射表 | `product[].productId` | 本地material_id→EC product_id映射表 |
| `material_entity[].qty` | `product[].productNum` | 出库数量 |
| `material_entity[].price` | `product[].saleMoney` | 销售单价（自动检测分→元转换） |
| `material_entity[].cost` | `product[].costMoney` | 成本价（自动检测分→元转换） |
| `material_entity[].comment` | `product[].productMemo` | 商品行备注 |
| `total_amount` | `"4"`(订单金额) | 出库单总金额（自动检测分→元转换） |
| — | `product[].specsId` | 默认0（无规格） |
| — | `product[].saleDiscount` | 默认100（无折扣） |
| — | `"3"`(订单状态) | 默认2（发现机会） |
| — | `optUserId` | 固定3446438 |

## 同步流程

### 方向一：EC → 金蝶（sync.py）

```
1. 获取金蝶 app-token（HMAC-SHA256 签名认证）
2. 读取上次同步时间（state.json）
3. 从 EC 拉取变更的客户列表（modifyTime >= last_customer_sync）
   ├── 对每个客户：检查金蝶是否存在（number = crmId）
   │   ├── 存在 → 更新
   │   └── 不存在 → 新增
4. 从 EC 拉取已结单订单列表（creatTime >= last_order_sync, status=3）
   ├── 先确保对应客户已同步到金蝶
   ├── 检查订单是否已存在（billno）
   │   └── 不存在 → 新增
5. 更新同步时间到 state.json
6. 输出同步报告
```

### 方向二：金蝶 → EC（sync_products.py）

```
1. 获取金蝶 app-token
2. 读取上次同步时间（state.json）
3. 从金蝶拉取变更的商品分类（modify_start_time >= last_product_sync）
4. 拉取 EC 已有产品列表（用于名称匹配去重）
5. 对每个分类：
   ├── 查本地映射表，已存在 → 跳过
   ├── 按 productName 匹配 EC 产品，已存在 → 记录映射、跳过
   └── 不存在 → 调用 EC addProduct 创建
6. 更新映射表和同步时间到 state.json
7. 输出同步报告
```

### 方向四：金蝶出库单 → EC（sync_outbounds.py）

```
1. 获取金蝶 app-token
2. 读取上次同步时间（state.json）
3. 从金蝶拉取已审核出库单列表（bill_status=C, modify_start_time >= last_outbound_sync）
4. 对每条出库单：
   ├── 查本地出库单映射表，已同步 → 跳过
   ├── 查金蝶客户详情，获取 number 作为 EC crmId
   ├── 解析 material_entity → EC产品列表：
   │   ├── 查本地 material_id→EC product_id 映射表
   │   ├── 未命中 → 按商品名称在EC产品中匹配
   │   └── 未匹配 → 跳过该商品行
   ├── 金额检测与转换（分→元自动检测）
   └── 调用 EC addSales 创建订单
5. 记录出库单映射到 state.json
6. 更新同步时间到 state.json
7. 输出同步报告
```

### 方向三：金蝶退货单 → EC（sync_returns.py）

```
1. 获取金蝶 app-token
2. 读取上次同步时间（state.json）
3. 从金蝶拉取已审核退货单列表（bill_status=C, modify_start_time >= last_return_sync）
4. 对每条退货单：
   ├── 查本地退货单映射表，已同步 → 跳过
   ├── 查金蝶客户详情，获取 number 作为 EC crmId
   ├── 解析 src_inter_id → 金蝶源单 → bill_no → EC订单编码 → saleId
   ├── 解析 material_entity → EC产品列表：
   │   ├── 查本地 material_id→EC product_id 映射表
   │   ├── 未命中 → 按商品名称在EC产品中匹配
   │   └── 未匹配 → 跳过该商品行
   ├── 金额检测与转换（分→元自动检测）
   └── 调用 EC saveReturn 创建退货单
5. 记录退货单映射到 state.json
6. 更新同步时间到 state.json
7. 输出同步报告
```

## 依赖

- Python 3.9+
- requests 库（标准安装）

首次使用请确保安装 requests：
```bash
pip install requests
```

## 注意事项

1. **EC `getSales` 接口 creatTime 间隔不超过31天**，批量同步时需注意
2. **金蝶 app-token 24小时有效**，脚本自动缓存和刷新
3. **增量同步**：首次执行会从已有数据开始增量，如需全量用 `--full`
4. **产品映射**：EC 的 `productId` 直接作为金蝶物料编码 `materialid_id`，需确保金蝶中已存在对应物料
5. **字段映射调整**：如需修改字段对应关系，编辑 `sync.py` 中的 `map_ec_customer_to_jdy()` 和 `map_ec_order_to_jdy()` 函数
6. **退货单客户映射**：依赖金蝶客户 `number` 字段 = EC `crmId`，客户同步（EC→金蝶）会设置此字段
7. **退货单商品映射**：首次同步会按名称匹配EC产品并记录映射表，后续复用映射表加速
8. **saleId 解析**：自动尝试从金蝶源单ID→源单bill_no→EC订单编码→EC订单ID链式解析，无法解析时默认为0
9. **金额单位**：自动检测金蝶金额是否为分单位（>100000 则除以100），无需手动调整
