import time
from core.config_manager import config_manager, ConfigItem

# 注册核心配置项
config_manager.register_config(ConfigItem(
    key="napcat_http_url", 
    default="http://localhost:3000", 
    description="Napcat HTTP API地址"
))
config_manager.register_config(ConfigItem(
    key="robot_qq", 
    default="1972693082", 
    description="机器人QQ号", 
    required=True
))
config_manager.register_config(ConfigItem(
    key="callback_port", 
    default=3002, 
    description="回调服务端口",
    validate_func=lambda x: isinstance(x, int) and 1024 <= x <= 65535
))
config_manager.register_config(ConfigItem(
    key="master_qq", 
    default="192004908", 
    description="主人QQ号", 
    required=True
))
config_manager.register_config(ConfigItem(
    key="bot_version", 
    default="v1.8.5", 
    description="机器人版本"
))
config_manager.register_config(ConfigItem(
    key="log_encoding", 
    default="utf-8", 
    description="日志编码格式"
))
config_manager.register_config(ConfigItem(
    key="openai_api_key", 
    default="", 
    description="OpenAI API密钥"
))
config_manager.register_config(ConfigItem(
    key="openai_model", 
    default="deepseek-chat", 
    description="OpenAI模型名称"
))
config_manager.register_config(ConfigItem(
    key="openai_api_base", 
    default="https://api.deepseek.com/v1", 
    description="OpenAI API基础URL"
))
config_manager.register_config(ConfigItem(
    key="openai_default_character", 
    default="你是GracyBot的AI助手，性格友好、回答简洁，帮助用户解决问题。",
    description="OpenAI默认角色设定"
))
config_manager.register_config(ConfigItem(
    key="auto_replies", 
    default={
        "你好": "哈喽～ 我是 GracyBot，有什么可以帮你呀？",
        "在吗": "在呢在呢～ 随时在线为你服务！",
        "谢谢": "不客气呀～ 能帮到你我也很开心！",
        "再见": "拜拜～ 下次见啦，祝你生活愉快！",
        "早上好": "早上好呀～ 新的一天也要元气满满哦！",
        "晚上好": "晚上好～ 记得早点休息，不要熬夜呀！",
        "吃了吗": "哈哈，已经吃过啦～ 你也要按时吃饭呀！",
        "天气怎么样": "抱歉呀，我暂时没法查询天气，记得关注天气预报哦～",
        "你是谁": "我是 GracyBot，一款基于 Napcat 的 QQ 机器人，很高兴认识你！",
        "加油": "谢谢鼓励～ 你也超棒的，一起加油呀！"
    },
    description="自动回复配置"
))
config_manager.register_config(ConfigItem(
    key="debug_mode", 
    default=False, 
    description="调试模式"
))
config_manager.register_config(ConfigItem(
    key="log_level", 
    default="INFO", 
    description="日志级别",
    validate_func=lambda x: x in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
))

# 加载配置
if not config_manager.load():
    raise RuntimeError("配置加载失败，请检查配置文件或环境变量")

# 为兼容旧代码，提供直接访问方式
NAPCAT_HTTP_URL = config_manager.get("napcat_http_url")
ROBOT_QQ = config_manager.get("robot_qq")
CALLBACK_PORT = config_manager.get("callback_port")
MASTER_QQ = config_manager.get("master_qq")
BOT_VERSION = config_manager.get("bot_version")
LOG_ENCODING = config_manager.get("log_encoding")
OPENAI_API_KEY = config_manager.get("openai_api_key")
OPENAI_MODEL = config_manager.get("openai_model")
OPENAI_API_BASE = config_manager.get("openai_api_base")
OPENAI_DEFAULT_CHARACTER = config_manager.get("openai_default_character")
AUTO_REPLIES = config_manager.get("auto_replies")
DEBUG_MODE = config_manager.get("debug_mode")
LOG_LEVEL = config_manager.get("log_level")

# 非配置项常量
ROBOT_START_TIME = time.time()
