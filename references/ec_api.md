# EC（六度人和）开放平台 API 参考

## 认证方式

EC 开放平台使用 appId + appSecret 进行认证，通过 HTTP Headers 传递：

```
X-EC-AppId: {app_id}
X-EC-Timestamp: {13位毫秒时间戳}
X-EC-Signature: HMAC-SHA256(appSecret, appId + timestamp)
```

## 接口列表

### 1. 查询客户列表

```
POST /v2/customer/queryList
Content-Type: application/json
```

**请求参数**：
- `name` (string) - 客户姓名/公司名
- `mobile` (string) - 手机号（逗号分隔，最多50个）
- `crmIds` (long[]) - 客户ID列表（最多200个）
- `step` (int[]) - 客户阶段（最多20个）
- `followUserId` (long[]) - 跟进人ID
- `crmType` (int) - 客户类型：0=个人，1=企业
- `createTime` (object) - 创建时间范围 {startTime, endTime}
- `modifyTime` (object) - 修改时间范围 {startTime, endTime}
- `pageNo` (int) - 页码（默认1，最大50）
- `pageSize` (int) - 每页大小（默认200，最大200）
- `includes` (string[]) - 指定返回字段
- `orderBy` (SortBaseVO[]) - 排序规则

**响应格式**：
```json
{
  "code": 200,
  "msg": "OK",
  "data": {
    "customerInfoList": [
      {
        "crmId": 1592313334,
        "name": "客户姓名",
        "company": "公司名",
        "mobile": "13522222222",
        "mobiles": ["13522222222"],
        "phone": "0755-12345678",
        "email": "email@example.com",
        "emails": ["email@example.com"],
        "companyAddress": "广东省深圳市...",
        "companyUrl": "https://company.com",
        "gender": "男",
        "qq": "12345678",
        "wechat": "wechat_id",
        "wechats": ["wechat_id"],
        "fax": "0755-12345678",
        "memo": "备注信息",
        "title": "经理",
        "birthday": "1990-01-01",
        "step": 1,
        "channel": "搜索引擎",
        "followUserId": 12345,
        "createUserId": 12345,
        "createTime": "2018-06-04 11:43:13",
        "modifyTime": "2019-03-12 03:47:07",
        "contactTime": "2019-03-12 03:47:07",
        "prefecture": "中国/广东/深圳/南山",
        "vocation": "互联网 通讯技术",
        "stars": 3,
        "crmType": 1,
        "location": {"lon": 123.0221, "lat": 32.23455}
      }
    ],
    "pageInfo": {
      "pageNo": 1,
      "pageSize": 200,
      "total": 291062,
      "maxPageNo": 291062
    }
  }
}
```

**⚠️ 限制**：最多返回 1 万条数据，数据变更后查询有约 10 秒延迟。

### 2. 查询销售订单列表

```
POST /v2/sales/getSales
Content-Type: application/json
```

**请求参数**：
- `userIds` (string) - 创建人员工ID（分号分隔）
- `crmIds` (string) - 客户ID（分号分隔）
- `deptIds` (string) - 部门ID（分号分隔）
- `creatTime` (string) - 创建时间范围（格式：yyyy-MM-dd HH:mm:ss;yyyy-MM-dd HH:mm:ss，间隔不超过31天）
- `lastModifyTime` (string) - 最后更新时间范围
- `salesStatus` (int) - 订单状态：2=发现机会，3=结单，4=无效
- `pageNo` (int) - 页码
- `sortFlag` (int) - 排序：0=降序，1=升序

**响应格式**：
```json
{
  "code": 200,
  "msg": "success",
  "total": 100,
  "pageSize": 50,
  "maxPageNo": 2,
  "pageNo": 1,
  "data": [
    {
      "id": 12345,
      "code": "SO20240001",
      "money": 586749,
      "productId": "PROD001",
      "productDes": "产品说明",
      "projectName": "订单主题",
      "status": 3,
      "crmId": "1592313334",
      "name": "客户姓名",
      "userId": 12345,
      "userName": "创建人",
      "createTime": "2024-01-15 10:00:00",
      "changeTime": "2024-01-15 10:00:00",
      "dealDate": "2024-01-15 00:00:00",
      "guessTime": "2024-01-30",
      "groupId": "100",
      "remark": "备注",
      "changeUser": "12345",
      "doUserid": "12345"
    }
  ]
}
```

### 3. 查询订单详情

```
GET /v2/sales/getSalesDetail
```

**请求参数**：
- `saleId` (long) - 订单ID

**响应**：包含订单全部字段 + `customFieldValues`（自定义字段列表）
