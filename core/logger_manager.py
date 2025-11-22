import os
import json
import logging
import logging.handlers
import sys
import traceback
from datetime import datetime
from typing import Dict, Any, Optional

from core.config import LOG_ENCODING, LOG_LEVEL, DEBUG_MODE, ROBOT_QQ
# 导入Logo模块
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from start_logo.gracybot_logo import GracyBotLogo

# 日志目录
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'logs')

class StructuredLogFormatter(logging.Formatter):
    """结构化日志格式化器，支持JSON格式输出"""
    def __init__(self, structured: bool = False, include_stack_info: bool = False):
        self.structured = structured
        self.include_stack_info = include_stack_info
        if structured:
            # JSON格式不需要传统的格式字符串
            super().__init__()
        else:
            # 人类可读格式
            super().__init__(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
    
    def format(self, record: logging.LogRecord) -> str:
        if self.structured:
            # 构建结构化日志数据
            log_data = {
                'timestamp': datetime.utcnow().isoformat() + 'Z',
                'level': record.levelname,
                'logger': record.name,
                'message': record.getMessage(),
                'robot_qq': ROBOT_QQ,
                'process': record.process,
                'thread': record.threadName
            }
            
            # 添加额外的上下文信息
            if hasattr(record, 'context'):
                log_data['context'] = record.context
            
            # 添加错误信息
            if record.exc_info:
                log_data['error'] = {
                    'type': record.exc_info[0].__name__,
                    'message': str(record.exc_info[1])
                }
                if self.include_stack_info:
                    log_data['stack_trace'] = ''.join(
                        traceback.format_exception(*record.exc_info)
                    )
            
            return json.dumps(log_data, ensure_ascii=False)
        else:
            # 传统格式，添加颜色（仅控制台输出时生效）
            color_map = {
                'DEBUG': '\033[36m',    # 青色
                'INFO': '\033[32m',     # 绿色
                'WARNING': '\033[33m',  # 黄色
                'ERROR': '\033[31m',    # 红色
                'CRITICAL': '\033[35m', # 紫色
            }
            reset = '\033[0m'
            
            # 格式化原始记录
            formatted = super().format(record)
            
            # 如果是控制台输出且支持颜色，添加颜色
            if hasattr(record, 'color_enabled') and record.color_enabled:
                level_color = color_map.get(record.levelname, '')
                if level_color:
                    # 只对日志级别部分添加颜色
                    parts = formatted.split(' - ', 3)
                    if len(parts) >= 3:
                        parts[2] = f"{level_color}{parts[2]}{reset}"
                        formatted = ' - '.join(parts)
            
            return formatted

class LoggerManager:
    """企业级日志管理器"""
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._loggers = {}
            cls._instance._setup_completed = False
        return cls._instance
    
    def setup_logging(self, log_level: str = LOG_LEVEL, debug_mode: bool = False) -> bool:
        """设置日志系统（兼容旧版API）"""
        # 将debug_mode转换为structured参数
        # 在debug_mode下使用结构化日志
        return self.setup(log_level=log_level, structured=debug_mode)
    
    def setup(self, log_level: str = LOG_LEVEL, structured: bool = False) -> bool:
        """设置日志系统"""
        try:
            # 创建日志目录
            if not os.path.exists(LOG_DIR):
                os.makedirs(LOG_DIR, exist_ok=True)
            
            # 根日志记录器设置
            root_logger = logging.getLogger()
            root_logger.setLevel(getattr(logging, log_level))
            
            # 清除已有的处理器
            for handler in root_logger.handlers[:]:
                root_logger.removeHandler(handler)
            
            # 添加控制台处理器
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(getattr(logging, log_level))
            
            # 控制台使用人类可读格式，带颜色
            console_formatter = StructuredLogFormatter(structured=False)
            console_handler.setFormatter(console_formatter)
            
            # 为控制台日志记录器添加颜色支持标记
            def add_color_support(record):
                # Windows命令提示符可能不支持颜色，但PowerShell支持
                record.color_enabled = hasattr(sys.stdout, 'isatty') and sys.stdout.isatty()
                return True
            
            console_filter = logging.Filter()
            console_filter.filter = add_color_support
            console_handler.addFilter(console_filter)
            
            root_logger.addHandler(console_handler)
            
            # 添加文件处理器（轮转）
            log_file = os.path.join(LOG_DIR, 'gracybot.log')
            file_handler = logging.handlers.TimedRotatingFileHandler(
                log_file,
                when='midnight',  # 每天午夜轮转
                interval=1,       # 每天一个文件
                backupCount=7,    # 保留7天的日志
                encoding=LOG_ENCODING
            )
            file_handler.setLevel(logging.DEBUG)  # 文件记录所有日志
            
            # 文件使用结构化或人类可读格式
            file_formatter = StructuredLogFormatter(
                structured=structured,
                include_stack_info=True
            )
            file_handler.setFormatter(file_formatter)
            root_logger.addHandler(file_handler)
            
            # 添加错误日志文件处理器
            error_log_file = os.path.join(LOG_DIR, 'gracybot_error.log')
            error_handler = logging.handlers.TimedRotatingFileHandler(
                error_log_file,
                when='midnight',
                interval=1,
                backupCount=14,  # 错误日志保留14天
                encoding=LOG_ENCODING
            )
            error_handler.setLevel(logging.ERROR)
            error_formatter = StructuredLogFormatter(
                structured=structured,
                include_stack_info=True
            )
            error_handler.setFormatter(error_formatter)
            root_logger.addHandler(error_handler)
            
            # 创建一个特殊的HTTP访问日志
            http_logger = self.get_logger('GracyBot-HTTP')
            http_log_file = os.path.join(LOG_DIR, 'gracybot_http.log')
            http_handler = logging.handlers.TimedRotatingFileHandler(
                http_log_file,
                when='midnight',
                interval=1,
                backupCount=7,
                encoding=LOG_ENCODING
            )
            http_handler.setLevel(logging.INFO)
            http_formatter = StructuredLogFormatter(structured=structured)
            http_handler.setFormatter(http_formatter)
            
            # 清除HTTP日志器的处理器，只保留我们的文件处理器
            for handler in http_logger.handlers[:]:
                http_logger.removeHandler(handler)
            http_logger.addHandler(http_handler)
            
            self._setup_completed = True
            
            # 在日志系统初始化完成后显示Logo - 强制使用颜色
            logo = GracyBotLogo(force_color=True)
            logo.print_logo()
            
            # 获取主日志器并记录初始化信息
            main_logger = self.get_logger('GracyBot')
            main_logger.info(f"✅ 日志系统初始化完成，级别: {log_level}")
            main_logger.info(f"📁 日志文件目录: {LOG_DIR}")
            main_logger.info(f"🔄 结构化日志: {'是' if structured else '否'}")
            
            return True
        except Exception as e:
            print(f"❌ 日志系统初始化失败: {str(e)}")
            return False
    
    def get_logger(self, name: str) -> logging.Logger:
        """获取指定名称的日志器"""
        if name not in self._loggers:
            logger = logging.getLogger(name)
            self._loggers[name] = logger
        
        return self._loggers[name]
    
    def set_level(self, level: str, logger_name: Optional[str] = None) -> bool:
        """动态设置日志级别"""
        try:
            log_level = getattr(logging, level)
            
            if logger_name:
                # 设置特定日志器级别
                if logger_name in self._loggers:
                    self._loggers[logger_name].setLevel(log_level)
                else:
                    logging.getLogger(logger_name).setLevel(log_level)
                self.get_logger('GracyBot-Logger').info(f"🔄 日志器 {logger_name} 级别设置为 {level}")
            else:
                # 设置根日志器级别
                root_logger = logging.getLogger()
                root_logger.setLevel(log_level)
                # 更新所有处理器的级别
                for handler in root_logger.handlers:
                    if isinstance(handler, logging.StreamHandler):
                        handler.setLevel(log_level)
                self.get_logger('GracyBot-Logger').info(f"🔄 全局日志级别设置为 {level}")
            
            return True
        except Exception as e:
            print(f"❌ 设置日志级别失败: {str(e)}")
            return False
    
    def log_with_context(self, logger, level, message="无日志消息", context=None, exc_info=False, **kwargs) -> None:
        """带上下文信息的日志记录"""
        import traceback
        try:
            # 检查logger是否为字符串类型（可能传入的是logger名称）
            if isinstance(logger, str):
                logger = self.get_logger(logger)
            
            # 确保logger是有效的logging.Logger对象
            if not hasattr(logger, 'log'):
                print(f"❌ 无效的logger对象: {type(logger)}")
                return
            
            # 构建日志消息（包含上下文信息）
            if context:
                if isinstance(context, dict):
                    context_str = json.dumps(context, ensure_ascii=False)
                else:
                    context_str = str(context)
                full_message = f"{message} | 上下文: {context_str}"
            else:
                full_message = message
            
            # 尝试使用基本日志记录（不使用extra参数）
            try:
                logger.log(level, full_message, exc_info=exc_info)
                print(f"✅ 日志记录成功: {logger.name if hasattr(logger, 'name') else 'unknown'}")
            except Exception as inner_e:
                print(f"❌ 日志记录失败: {str(inner_e)}")
                # 作为最后的手段，尝试直接调用error方法
                if hasattr(logger, 'error'):
                    logger.error(f"日志记录失败: {full_message}", exc_info=exc_info)
        except Exception as e:
            print(f"❌ log_with_context异常: {str(e)}")
            traceback.print_exc()

# 创建全局日志管理器实例
logger_manager = LoggerManager()

# 兼容旧代码的全局日志实例
logger = logger_manager.get_logger('GracyBot-HTTP-Pure')
