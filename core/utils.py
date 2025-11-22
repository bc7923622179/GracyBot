import requests
import json
import logging
from typing import Optional, Dict, Any

# 从core包导入配置模块
from .config import NAPCAT_HTTP_URL, AUTO_REPLIES, LOG_LEVEL, DEBUG_MODE

# 导入配置管理器
from .config_manager import config_manager

# 先导入logger_manager但不使用，避免循环导入问题
from .logger_manager import LoggerManager

# 创建日志管理器实例
logger_manager = LoggerManager()

# 初始化日志系统
logger_manager.setup_logging(
    log_level=LOG_LEVEL,
    debug_mode=DEBUG_MODE  # 调试模式下使用结构化日志
)

# 再导入其他需要的模块
from .security import SanitizeLogFilter

# 创建日志实例
logger = logger_manager.get_logger('GracyBot-HTTP-Pure')
    
# 为所有日志器添加脱敏过滤器
def add_sanitize_filter_to_loggers():
    sanitize_filter = SanitizeLogFilter()
    # 添加到根日志器
    root_logger = logger_manager.get_logger('')
    root_logger.addFilter(sanitize_filter)
    
    # 添加到主要日志器
    for logger_name in ['GracyBot', 'GracyBot-HTTP-Pure', 'GracyBot-Plugin']:
        named_logger = logger_manager.get_logger(logger_name)
        named_logger.addFilter(sanitize_filter)

# 添加脱敏过滤器
add_sanitize_filter_to_loggers()

# ========== 通用消息发送工具（全局唯一实现，所有模块复用） ==========
def send_http_msg(target: str, content: str, chat_type: str = "private", 
                 context: Optional[Dict[str, Any]] = None) -> bool:
    """
    统一处理私聊/群聊消息发送，适配Napcat接口
    :param target: 目标ID（私聊=用户ID，群聊=群ID）
    :param content: 消息内容
    :param chat_type: 聊天类型（private/group）
    :param context: 附加上下文信息
    :return: 发送成功返回True，失败返回False
    """
    # 构建日志上下文
    log_context = {
        "target": target,
        "chat_type": chat_type,
        "content_preview": content[:50] + ("..." if len(content) > 50 else "")
    }
    
    if context:
        log_context.update(context)
    
    try:
        # 参数验证
        if not target or not content:
            logger_manager.log_with_context(
                logger, 
                logging.ERROR, 
                "[消息发送] 目标或内容不能为空", 
                context=log_context
            )
            return False
        
        # 按聊天类型拼接接口URL和参数
        if chat_type == "private":
            url = f"{NAPCAT_HTTP_URL}/send_private_msg"
            params = {"user_id": int(target), "message": content}
        else:
            url = f"{NAPCAT_HTTP_URL}/send_group_msg"
            params = {"group_id": int(target), "message": content}
        
        # 发送POST请求（JSON格式，UTF-8编码）
        headers = {"Content-Type": "application/json; charset=utf-8"}
        response = requests.post(
            url,
            data=json.dumps(params, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            timeout=10  # 超时保护，避免阻塞
        )
        
        # 检查HTTP状态码
        response.raise_for_status()
        
        result = response.json()
        
        # 结果判断与日志记录
        if result.get("retcode") == 0:
            logger_manager.log_with_context(
                logger, 
                logging.INFO, 
                f"[消息发送] 成功发送{chat_type}消息", 
                context=log_context
            )
            return True
        else:
            error_msg = result.get('msg', '未知错误')
            log_context['error_msg'] = error_msg
            logger_manager.log_with_context(
                logger, 
                logging.ERROR, 
                f"[消息发送] {chat_type}消息发送失败", 
                context=log_context
            )
            return False
    
    # 细分异常捕获（精准定位问题）
    except requests.exceptions.Timeout:
        logger_manager.log_with_context(
            logger, 
            logging.ERROR, 
            "[消息发送] 请求超时（10秒）", 
            context=log_context,
            exc_info=True
        )
        return False
    except requests.exceptions.HTTPError as e:
        log_context['status_code'] = e.response.status_code if e.response else None
        logger_manager.log_with_context(
            logger, 
            logging.ERROR, 
            f"[消息发送] HTTP错误: {str(e)}", 
            context=log_context,
            exc_info=True
        )
        return False
    except requests.exceptions.ConnectionError:
        logger_manager.log_with_context(
            logger, 
            logging.ERROR, 
            "[消息发送] 连接失败，可能Napcat服务未运行", 
            context=log_context,
            exc_info=True
        )
        return False
    except ValueError as e:
        logger_manager.log_with_context(
            logger, 
            logging.ERROR, 
            f"[消息发送] 参数格式错误: {str(e)}", 
            context=log_context,
            exc_info=True
        )
        return False
    except Exception as e:
        logger_manager.log_with_context(
            logger, 
            logging.ERROR, 
            f"[消息发送] 未知异常: {type(e).__name__}", 
            context=log_context,
            exc_info=True
        )
        return False

# ========== 自动回复工具（全局复用，关键词匹配逻辑） ==========
def handle_auto_reply(msg: str) -> Optional[str]:
    """
    关键词自动回复匹配（基于配置文件AUTO_REPLIES）
    :param msg: 用户输入消息
    :return: 匹配到关键词返回回复内容，无匹配返回None
    """
    if not msg:
        return None
    
    # 转换为小写进行匹配，提高匹配率
    msg_lower = msg.lower()
    
    # 记录匹配过程（DEBUG级别）
    logger.debug(f"[自动回复] 尝试匹配消息：{msg[:50]}{'...' if len(msg) > 50 else ''}")
    
    # 优先匹配最长的关键词，避免短关键词错误匹配
    sorted_keywords = sorted(AUTO_REPLIES.keys(), key=len, reverse=True)
    
    for keyword in sorted_keywords:
        if keyword.lower() in msg_lower:
            reply = AUTO_REPLIES[keyword]
            logger_manager.log_with_context(
                logger, 
                logging.INFO, 
                "[自动回复] 关键词匹配成功",
                context={
                    "keyword": keyword,
                    "reply_preview": reply[:30] + ("..." if len(reply) > 30 else "")
                }
            )
            return reply
    
    logger.debug("[自动回复] 未匹配到任何关键词")
    return None


def sanitize_log(text: str) -> str:
    """
    对日志内容进行脱敏处理，移除敏感信息
    
    :param text: 原始日志文本
    :return: 脱敏后的日志文本
    """
    # 这里可以添加各种脱敏规则
    # 例如：隐藏QQ号、手机号、邮箱等敏感信息
    import re
    
    # 隐藏QQ号（9-12位数字）
    text = re.sub(r'(?<!\d)([1-9]\d{8,11})(?!\d)', lambda m: m.group(1)[:3] + '*' * (len(m.group(1)) - 6) + m.group(1)[-3:], text)
    
    # 隐藏手机号（中国大陆）
    text = re.sub(r'(?<!\d)(1[3-9]\d{9})(?!\d)', lambda m: m.group(1)[:3] + '****' + m.group(1)[-4:], text)
    
    # 隐藏邮箱地址
    text = re.sub(r'([a-zA-Z0-9._%+-]+)@([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', lambda m: m.group(1)[:3] + '***@' + m.group(2), text)
    
    # 隐藏URL中的token或key参数
    text = re.sub(r'(token|key|secret)=([^&]+)', lambda m: f"{m.group(1)}=****", text)
    
    return text























































































