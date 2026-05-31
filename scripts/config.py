"""
配置文件 - 从环境变量或 .env 文件读取凭证
首次使用时复制 config_template.py 为 config.py 并填入真实凭证
"""
import os
from pathlib import Path

# 从环境变量读取，若不存在则从 .env 文件加载
env_file = Path(__file__).parent.parent / ".env"
if env_file.exists():
    with open(env_file, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())

# ===== EC（六度人和）配置 =====
EC_BASE_URL = os.environ.get("EC_BASE_URL", "https://open.workec.com")
EC_APP_ID = os.environ.get("EC_APP_ID", "")
EC_APP_SECRET = os.environ.get("EC_APP_SECRET", "")
EC_CID = os.environ.get("EC_CID", "")  # 企业唯一标识ID（从EC后台获取）

# ===== 金蝶云星辰配置 =====
JDY_BASE_URL = os.environ.get("JDY_BASE_URL", "https://api.kingdee.com/jdy")
JDY_APP_KEY = os.environ.get("JDY_APP_KEY", "")       # appKey (S4aaVJSF)
JDY_APP_SECRET = os.environ.get("JDY_APP_SECRET", "")  # appSecret
JDY_CLIENT_ID = os.environ.get("JDY_CLIENT_ID", "")    # 应用ID Client ID (267904)
JDY_CLIENT_SECRET = os.environ.get("JDY_CLIENT_SECRET", "")  # 应用Secret (dcdd1...)
JDY_INSTANCE_ID = os.environ.get("JDY_INSTANCE_ID", "")  # 第三方实例ID

# ===== 同步配置 =====
SYNC_INTERVAL_HOURS = int(os.environ.get("SYNC_INTERVAL_HOURS", "1"))
SYNC_ORDER_STATUS = os.environ.get("SYNC_ORDER_STATUS", "3")  # 只同步已结单
PAGE_SIZE = int(os.environ.get("PAGE_SIZE", "200"))  # EC 每页条数，最大200

# 状态文件存放位置（记录上次同步时间）
STATE_FILE = Path(__file__).parent.parent / "state.json"

# ===== 产品同步配置（金蝶→EC） =====
EC_OPT_USER_ID = int(os.environ.get("EC_OPT_USER_ID", "3446438"))  # EC 操作用户ID
PRODUCT_DEFAULT_UNIT = os.environ.get("PRODUCT_DEFAULT_UNIT", "个")  # 产品默认单位
PRODUCT_DEFAULT_PRICE = float(os.environ.get("PRODUCT_DEFAULT_PRICE", "0.00"))  # 产品默认价格
PRODUCT_GROUP_ID = int(os.environ.get("PRODUCT_GROUP_ID", "0"))  # EC 产品分组ID，0=不设分组

# ===== 退货单同步配置（金蝶→EC） =====
RETURN_SYNC_USER_ID = int(os.environ.get("RETURN_SYNC_USER_ID", "3446438"))  # EC 创建退货单操作用户ID
RETURN_GROUP_ID = int(os.environ.get("RETURN_GROUP_ID", "0"))  # EC 退货单产品分类ID，0=不设分组
RETURN_REASON_DEFAULT = int(os.environ.get("RETURN_REASON_DEFAULT", "7"))  # 默认退货原因（7=其他原因）
RETURN_PAGE_SIZE = int(os.environ.get("RETURN_PAGE_SIZE", "50"))  # 金蝶退货单每页条数

# ===== 出库单同步配置（金蝶→EC） =====
OUTBOUND_SYNC_USER_ID = int(os.environ.get("OUTBOUND_SYNC_USER_ID", "3446438"))  # EC 创建订单操作用户ID
OUTBOUND_ORDER_STATUS = int(os.environ.get("OUTBOUND_ORDER_STATUS", "2"))  # EC 订单状态（2=发现机会，3=结单）
OUTBOUND_PAGE_SIZE = int(os.environ.get("OUTBOUND_PAGE_SIZE", "50"))  # 金蝶出库单每页条数
