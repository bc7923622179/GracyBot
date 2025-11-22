import os
import json
import logging
from typing import Dict, Any, Optional, TypeVar, Generic

# 配置文件路径
CONFIG_FILE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config.json')

# 配置类型定义
T = TypeVar('T')

class ConfigItem(Generic[T]):
    """配置项类，支持类型转换和验证"""
    def __init__(self, key: str, default: T, description: str = '', required: bool = False, 
                 env_var: Optional[str] = None, validate_func=None):
        self.key = key
        self.default = default
        self.description = description
        self.required = required
        self.env_var = env_var or f"GRACY_{key.upper()}"
        self.validate_func = validate_func
        self.value: Optional[T] = None
    
    def validate(self, value: Any) -> bool:
        """验证配置值是否合法"""
        if self.validate_func:
            return self.validate_func(value)
        return True

class ConfigManager:
    """企业级配置管理器，支持环境变量、配置文件和默认值"""
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
            cls._instance._config_items = {}
            cls._instance._file_config = {}
            cls._instance._logger = logging.getLogger("GracyBot-Config")
        return cls._instance
    
    def register_config(self, config_item: ConfigItem) -> None:
        """注册配置项"""
        self._config_items[config_item.key] = config_item
    
    def load(self) -> bool:
        """加载配置，优先级：环境变量 > 配置文件 > 默认值"""
        try:
            # 加载配置文件
            if os.path.exists(CONFIG_FILE_PATH):
                try:
                    with open(CONFIG_FILE_PATH, 'r', encoding='utf-8') as f:
                        self._file_config = json.load(f)
                    self._logger.info(f"✅ 配置文件加载成功: {CONFIG_FILE_PATH}")
                except json.JSONDecodeError as e:
                    self._logger.error(f"❌ 配置文件格式错误: {str(e)}")
                    return False
            else:
                self._logger.warning(f"⚠️ 配置文件不存在: {CONFIG_FILE_PATH}，将使用默认值和环境变量")
            
            # 处理每个配置项
            for key, item in self._config_items.items():
                # 1. 尝试从环境变量获取
                env_value = os.environ.get(item.env_var)
                if env_value is not None:
                    # 根据默认值类型进行转换
                    if isinstance(item.default, bool):
                        item.value = env_value.lower() in ('true', '1', 'yes', 'y')
                    elif isinstance(item.default, int):
                        try:
                            item.value = int(env_value)
                        except ValueError:
                            self._logger.error(f"❌ 环境变量 {item.env_var} 不是有效的整数")
                            item.value = item.default
                    else:
                        item.value = env_value
                    self._logger.debug(f"🔧 从环境变量加载配置 {key}: {item.env_var}")
                # 2. 尝试从配置文件获取
                elif key in self._file_config:
                    item.value = self._file_config[key]
                    self._logger.debug(f"📄 从配置文件加载配置 {key}")
                # 3. 使用默认值
                else:
                    item.value = item.default
                    self._logger.debug(f"📌 使用默认配置 {key}: {item.default}")
                
                # 验证配置
                if not item.validate(item.value):
                    self._logger.error(f"❌ 配置 {key} 的值 {item.value} 无效")
                    if item.required:
                        return False
                    # 无效时回退到默认值
                    item.value = item.default
                
                # 检查必填项
                if item.required and item.value is None:
                    self._logger.error(f"❌ 缺少必填配置 {key}")
                    return False
            
            self._initialized = True
            self._logger.info("✅ 所有配置加载完成")
            return True
        except Exception as e:
            self._logger.error(f"❌ 配置加载异常: {str(e)}", exc_info=True)
            return False
    
    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值"""
        if not self._initialized:
            if not self.load():
                return default
        
        item = self._config_items.get(key)
        if item:
            return item.value
        return default
    
    def set(self, key: str, value: Any) -> bool:
        """动态设置配置值"""
        item = self._config_items.get(key)
        if item:
            if item.validate(value):
                item.value = value
                self._logger.info(f"🔄 动态更新配置 {key}: {value}")
                return True
            else:
                self._logger.error(f"❌ 无法设置配置 {key}: 无效值 {value}")
        return False
    
    def save_to_file(self) -> bool:
        """保存当前配置到文件（不包含环境变量覆盖的值）"""
        try:
            # 只保存非环境变量覆盖的配置
            config_to_save = self._file_config.copy()
            for key, item in self._config_items.items():
                if item.env_var not in os.environ and key not in os.environ:
                    config_to_save[key] = item.value
            
            with open(CONFIG_FILE_PATH, 'w', encoding='utf-8') as f:
                json.dump(config_to_save, f, ensure_ascii=False, indent=2)
            
            self._logger.info(f"✅ 配置已保存到: {CONFIG_FILE_PATH}")
            return True
        except Exception as e:
            self._logger.error(f"❌ 保存配置文件失败: {str(e)}")
            return False
    
    def generate_default_config(self) -> Dict[str, Any]:
        """生成默认配置字典"""
        default_config = {}
        for key, item in self._config_items.items():
            default_config[key] = {
                'value': item.default,
                'description': item.description,
                'env_var': item.env_var,
                'required': item.required
            }
        return default_config

# 创建全局配置管理器实例
config_manager = ConfigManager()
