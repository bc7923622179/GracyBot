import os
import importlib.util
from typing import Dict, List, Callable, Optional, Set, Tuple
import re
# 使用相对导入
from .utils import logger
from .config import ROBOT_QQ, MASTER_QQ

# 全局插件注册池：存储所有合法插件的元信息+处理函数
PLUGIN_REGISTRY: List[Dict] = []
# 存储已加载插件的版本信息，用于依赖检查
LOADED_PLUGIN_VERSIONS: Dict[str, str] = {}
# 用于检测循环依赖
DEPENDENCY_GRAPH: Dict[str, List[str]] = {}
VISITED: Set[str] = set()


class PluginManager:
    """插件管理器单例类：负责扫描、加载、注册插件，提供指令匹配能力，支持版本控制和依赖管理"""
    _instance = None
    _initialized = False

    def __new__(cls):
        """单例模式：确保全局只有一个插件管理器实例"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def parse_version(self, version: str) -> List[int]:
        """解析版本号字符串为整数列表，用于版本比较
        例如："1.2.3" -> [1, 2, 3]
        """
        try:
            parts = re.findall(r'\d+', version)
            return [int(part) for part in parts]
        except Exception as e:
            logger.error(f"解析版本号失败: {version} - {str(e)}")
            return [0]
    
    def compare_versions(self, version1: str, version2: str) -> int:
        """比较两个版本号
        返回 1 如果 version1 > version2
        返回 0 如果 version1 == version2
        返回 -1 如果 version1 < version2
        """
        v1_parts = self.parse_version(version1)
        v2_parts = self.parse_version(version2)
        
        # 确保版本号长度相等，不足补0
        max_len = max(len(v1_parts), len(v2_parts))
        v1_parts += [0] * (max_len - len(v1_parts))
        v2_parts += [0] * (max_len - len(v2_parts))
        
        # 逐位比较
        for i in range(max_len):
            if v1_parts[i] > v2_parts[i]:
                return 1
            elif v1_parts[i] < v2_parts[i]:
                return -1
        return 0
    
    def check_circular_dependency(self, plugin_name: str, visited: Set[str], path: List[str]) -> bool:
        """检测循环依赖
        使用深度优先搜索算法检测循环依赖
        """
        visited.add(plugin_name)
        path.append(plugin_name)
        
        if plugin_name in DEPENDENCY_GRAPH:
            for dependency in DEPENDENCY_GRAPH[plugin_name]:
                if dependency not in visited:
                    if self.check_circular_dependency(dependency, visited, path):
                        return True
                elif dependency in path:
                    # 找到循环依赖
                    cycle_start_index = path.index(dependency)
                    cycle = " -> ".join(path[cycle_start_index:]) + " -> " + dependency
                    logger.error(f"❌ 检测到循环依赖: {cycle}")
                    return True
        
        path.pop()
        return False
    
    def check_plugin_dependencies(self, plugin_name: str, dependencies: List[Dict]) -> Tuple[bool, str]:
        """检查插件依赖是否满足
        返回 (是否满足, 错误信息)
        """
        if not dependencies:
            return True, ""
        
        for dep in dependencies:
            dep_name = dep.get('name')
            min_version = dep.get('min_version', '0.0.0')
            max_version = dep.get('max_version', None)
            
            # 检查依赖插件是否已加载
            if dep_name not in LOADED_PLUGIN_VERSIONS:
                return False, f"依赖插件 '{dep_name}' 未加载"
            
            # 获取已加载插件的版本
            loaded_version = LOADED_PLUGIN_VERSIONS[dep_name]
            
            # 检查最小版本要求
            if self.compare_versions(loaded_version, min_version) < 0:
                return False, f"依赖插件 '{dep_name}' 版本过低，需要 >= {min_version}，当前版本 {loaded_version}"
            
            # 检查最大版本限制
            if max_version and self.compare_versions(loaded_version, max_version) > 0:
                return False, f"依赖插件 '{dep_name}' 版本过高，需要 <= {max_version}，当前版本 {loaded_version}"
        
        return True, ""

    def _convert_adapter_to_meta(self, adapter_data: Dict, plugin_name: str) -> Dict:
        """将adapter.json格式转换为PLUGIN_META格式
        
        Args:
            adapter_data: adapter.json文件内容
            plugin_name: 插件目录名称
            
        Returns:
            转换后的PLUGIN_META字典
        """
        # 基础字段映射
        meta = {
            "name": adapter_data.get("name", plugin_name),
            "version": adapter_data.get("version", "1.0.0"),
            "description": adapter_data.get("description", ""),
            "author": adapter_data.get("author", ""),
            "chat_type": adapter_data.get("chat_type", ["private", "group"]),
            "permission": adapter_data.get("permission", "all"),
            "is_at_required": adapter_data.get("is_at_required", False)
        }
        
        # 处理commands字段
        commands = []
        if "commands" in adapter_data:
            # 如果commands是列表，直接使用
            if isinstance(adapter_data["commands"], list):
                commands = adapter_data["commands"]
            # 如果commands是字典，提取命令列表
            elif isinstance(adapter_data["commands"], dict):
                commands = list(adapter_data["commands"].keys())
        
        meta["commands"] = commands
        
        # 处理handler字段
        if "handler" in adapter_data:
            meta["handler"] = adapter_data["handler"]
        else:
            # 默认handler命名规则
            meta["handler"] = f"handle_{plugin_name.replace('_plugin', '').replace('-', '_')}"
        
        # 处理依赖项
        if "dependencies" in adapter_data:
            meta["dependencies"] = adapter_data["dependencies"]
        
        # 处理配置项
        if "config" in adapter_data:
            meta["config"] = adapter_data["config"]
        
        return meta

    def init(self, plugin_dir: str = "./plugins") -> None:
        """初始化入口：扫描插件目录并注册所有合法插件（bot.py仅需调用这1行）"""
        if self._initialized:
            logger.warning("⚠️ 插件管理器已初始化，无需重复调用")
            return
        # 清空全局数据结构
        PLUGIN_REGISTRY.clear()
        LOADED_PLUGIN_VERSIONS.clear()
        DEPENDENCY_GRAPH.clear()
        
        # 打印绝对路径，方便调试目录是否正确
        abs_plugin_dir = os.path.abspath(plugin_dir)
        logger.info(f"📌 开始扫描插件目录（绝对路径）：{abs_plugin_dir}")
        
        # 第一阶段：扫描并加载所有插件的元信息（不执行功能导入）
        plugins_meta = self._scan_plugins_metadata(plugin_dir)
        
        # 检测循环依赖
        VISITED.clear()
        for plugin_name in DEPENDENCY_GRAPH:
            if plugin_name not in VISITED:
                if self.check_circular_dependency(plugin_name, set(), []):
                    logger.error("❌ 检测到循环依赖，初始化失败！")
                    return
        
        # 第二阶段：按依赖顺序加载插件
        self._load_plugins_by_dependency(plugins_meta, plugin_dir)
        
        self._initialized = True
        # 打印注册结果（关键调试信息，明确注册成功数量）
        logger.info(f"\n✅ 插件管理器初始化完成！")
        logger.info(f"📊 共注册成功 {len(PLUGIN_REGISTRY)} 个插件：")
        for idx, plugin in enumerate(PLUGIN_REGISTRY, 1):
            # 只显示前3个指令，避免日志过长
            show_commands = plugin['commands'][:3] + ["..."] if len(plugin['commands']) > 3 else plugin['commands']
            version_info = f" | 版本：{plugin.get('version', '未指定')}"
            logger.info(f"   {idx}. 插件名称：{plugin['name']}{version_info} | 触发指令：{show_commands}")

    def _scan_plugins_metadata(self, plugin_dir: str) -> Dict[str, Dict]:
        """第一阶段：扫描所有插件的元信息
        返回 {plugin_name: 插件元信息} 的字典
        """
        plugins_meta = {}
        
        # 校验插件目录是否存在
        if not os.path.exists(plugin_dir):
            logger.error(f"❌ 插件目录 {plugin_dir} 不存在，跳过插件加载")
            return plugins_meta

        # 遍历插件目录下所有子目录（每个子目录对应一个插件）
        for plugin_name in os.listdir(plugin_dir):
            plugin_path = os.path.join(plugin_dir, plugin_name)
            # 仅处理目录，跳过文件
            if not os.path.isdir(plugin_path):
                logger.debug(f"⚠️ 跳过非目录项：{plugin_name}（不是插件目录）")
                continue
            
            # 检查插件目录是否包含必要的元信息文件
            plugin_files = os.listdir(plugin_path)
            has_init_py = "__init__.py" in plugin_files
            has_adapter_json = "adapter.json" in plugin_files
            
            # 必须至少有一个元信息文件
            if not has_init_py and not has_adapter_json:
                logger.warning(f"❌ 插件 {plugin_name} 目录下缺失元信息文件（__init__.py 或 adapter.json），跳过加载")
                continue

            try:
                plugin_meta = None
                
                # 优先使用adapter.json文件（如果存在）
                if has_adapter_json:
                    adapter_file_path = os.path.join(plugin_path, "adapter.json")
                    try:
                        with open(adapter_file_path, 'r', encoding='utf-8') as f:
                            adapter_data = json.load(f)
                        
                        # 转换adapter.json格式为PLUGIN_META格式
                        plugin_meta = self._convert_adapter_to_meta(adapter_data, plugin_name)
                        logger.info(f"📄 插件 {plugin_name} 使用 adapter.json 元信息")
                    except Exception as e:
                        logger.error(f"❌ 读取插件 {plugin_name} 的 adapter.json 失败: {str(e)}")
                
                # 如果adapter.json不存在或读取失败，使用__init__.py
                if plugin_meta is None and has_init_py:
                    # 动态导入插件的 __init__.py，读取元信息
                    init_file_path = os.path.join(plugin_path, "__init__.py")
                    spec = importlib.util.spec_from_file_location(
                        name=f"plugins.{plugin_name}",
                        location=init_file_path
                    )
                    plugin_meta_module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(plugin_meta_module)

                    # 校验元信息是否存在且完整
                    if not hasattr(plugin_meta_module, "PLUGIN_META"):
                        logger.error(f"❌ 插件 {plugin_name} 的 __init__.py 中缺失 PLUGIN_META 元信息，跳过加载")
                        continue
                    
                    plugin_meta = plugin_meta_module.PLUGIN_META
                    logger.info(f"📄 插件 {plugin_name} 使用 __init__.py 元信息")
                
                # 如果两种方式都失败，跳过该插件
                if plugin_meta is None:
                    logger.error(f"❌ 插件 {plugin_name} 无法读取元信息，跳过加载")
                    continue
                
                # 必选元信息字段（缺失则视为非法插件）
                required_meta_fields = ["name", "commands", "handler", "chat_type", "permission"]
                if not all(field in plugin_meta for field in required_meta_fields):
                    logger.error(f"❌ 插件 {plugin_name} 元信息缺失必选字段！需包含：{required_meta_fields}，跳过加载")
                    continue
                
                # 提取版本信息，默认为 "1.0.0"
                if "version" not in plugin_meta:
                    plugin_meta["version"] = "1.0.0"
                    logger.warning(f"⚠️ 插件 {plugin_name} 未指定版本号，默认为 1.0.0")
                
                # 提取依赖信息，默认为空列表
                plugin_meta["dependencies"] = plugin_meta.get("dependencies", [])
                
                # 构建依赖图
                if plugin_meta["dependencies"]:
                    DEPENDENCY_GRAPH[plugin_name] = [dep["name"] for dep in plugin_meta["dependencies"]]
                else:
                    DEPENDENCY_GRAPH[plugin_name] = []
                
                # 保存插件路径信息
                plugin_meta["plugin_path"] = plugin_path
                
                plugins_meta[plugin_name] = plugin_meta
                logger.debug(f"🔍 成功读取插件 {plugin_name} 元信息，版本：{plugin_meta['version']}")

            except Exception as e:
                logger.error(f"❌ 读取插件 {plugin_name} 元信息时发生异常：{str(e)}", exc_info=True)
                continue
        
        return plugins_meta
    
    def _load_plugins_by_dependency(self, plugins_meta: Dict[str, Dict], plugin_dir: str) -> None:
        """第二阶段：按依赖顺序加载插件核心功能"""
        # 使用深度优先搜索按依赖顺序加载插件
        loaded = set()
        
        def load_plugin(plugin_name: str):
            if plugin_name in loaded:
                return True
            
            # 检查插件是否存在
            if plugin_name not in plugins_meta:
                logger.error(f"❌ 依赖插件 '{plugin_name}' 不存在")
                return False
            
            # 先加载所有依赖
            dependencies = plugins_meta[plugin_name].get("dependencies", [])
            for dep in dependencies:
                dep_name = dep["name"]
                if dep_name not in loaded:
                    if not load_plugin(dep_name):
                        return False
            
            # 检查依赖是否满足
            plugin_meta = plugins_meta[plugin_name]
            dependencies_ok, error_msg = self.check_plugin_dependencies(plugin_name, dependencies)
            if not dependencies_ok:
                logger.error(f"❌ 插件 '{plugin_name}' 依赖检查失败: {error_msg}")
                return False
            
            # 加载插件核心功能
            try:
                plugin_path = plugin_meta["plugin_path"]
                core_file_name = f"{plugin_name}.py"
                core_module_path = os.path.join(plugin_path, core_file_name)
                
                # 校验核心文件是否存在
                if not os.path.exists(core_module_path):
                    logger.error(f"❌ 插件 {plugin_name} 缺失核心文件 {core_file_name}，跳过加载")
                    return False
                
                # 导入核心模块
                core_module_name = f"plugins.{plugin_name}.{core_file_name[:-3]}"
                core_spec = importlib.util.spec_from_file_location(
                    name=core_module_name,
                    location=core_module_path
                )
                plugin_core_module = importlib.util.module_from_spec(core_spec)
                core_spec.loader.exec_module(plugin_core_module)
                
                # 校验核心处理函数
                handler_func_name = plugin_meta["handler"]
                if not hasattr(plugin_core_module, handler_func_name):
                    logger.error(f"❌ 插件 {plugin_name} 中缺失核心处理函数 {handler_func_name}，跳过加载")
                    return False
                
                handler_func = getattr(plugin_core_module, handler_func_name)
                if not callable(handler_func):
                    logger.error(f"❌ 插件 {plugin_name} 中 {handler_func_name} 不是可调用函数，跳过加载")
                    return False
                
                # 注册插件
                registered_plugin = {
                    **plugin_meta,  # 插件元信息（名称、指令、版本、依赖等）
                    "handler_func": handler_func,  # 插件核心处理函数
                    "core_module": plugin_core_module  # 插件核心模块（备用）
                }
                PLUGIN_REGISTRY.append(registered_plugin)
                LOADED_PLUGIN_VERSIONS[plugin_name] = plugin_meta["version"]
                loaded.add(plugin_name)
                
                logger.info(f"✅ 插件 {plugin_name} (版本 {plugin_meta['version']}) 注册成功！触发指令共 {len(plugin_meta['commands'])} 个")
                if dependencies:
                    dep_info = ", ".join([f"{dep['name']} (>= {dep.get('min_version', '0.0.0')})" for dep in dependencies])
                    logger.info(f"   依赖: {dep_info}")
                    
                return True
                
            except Exception as e:
                logger.error(f"❌ 加载插件 {plugin_name} 时发生异常：{str(e)}", exc_info=True)
                return False
        
        # 加载所有未被依赖的插件（起点）
        for plugin_name in plugins_meta:
            if plugin_name not in loaded:
                load_plugin(plugin_name)

    def get_matched_plugin(self, raw_msg: str, chat_type: str, sender_id: str, is_at_bot: bool) -> Optional[Dict]:
        """公共方法：根据用户消息匹配对应的插件（供handler调用，优化匹配逻辑）"""
        logger.debug(f"\n[插件匹配] 开始匹配指令：{raw_msg[:20]}... | 聊天类型：{chat_type} | 发送者ID：{sender_id} | @机器人：{is_at_bot}")
        logger.debug(f"[插件匹配] 当前注册池插件数量：{len(PLUGIN_REGISTRY)}")
        
        for plugin in PLUGIN_REGISTRY:
            # 1. 校验聊天场景（私聊/群聊）是否匹配
            if chat_type not in plugin["chat_type"]:
                logger.debug(f"[插件匹配] 插件 {plugin['name']} v{plugin.get('version', 'N/A')} 场景不匹配（支持：{plugin['chat_type']}，当前：{chat_type}），跳过")
                continue
            # 2. 校验权限（仅主人可用的插件需过滤非主人用户）
            if plugin["permission"] == "master" and str(sender_id) != str(MASTER_QQ):
                logger.debug(f"[插件匹配] 插件 {plugin['name']} v{plugin.get('version', 'N/A')} 权限不足（仅主人可用），跳过")
                continue
            # 3. 群聊场景需@机器人的插件，校验是否@机器人
            if chat_type == "group" and plugin.get("is_at_required", False) and not is_at_bot:
                logger.debug(f"[插件匹配] 插件 {plugin['name']} v{plugin.get('version', 'N/A')} 群聊需@机器人，当前未@，跳过")
                continue
            # 4. 指令匹配（消息包含插件任一触发指令即匹配，优化匹配逻辑）
            matched_cmd = [cmd for cmd in plugin["commands"] if cmd in raw_msg]
            if matched_cmd:
                logger.debug(f"[插件匹配] 插件 {plugin['name']} v{plugin.get('version', 'N/A')} 匹配成功！触发指令：{matched_cmd}")
                return plugin
        
        # 无匹配插件返回None，打印调试日志
        logger.warning(f"[插件匹配] 无插件匹配指令：{raw_msg[:20]}...")
        return None
    
    def get_plugin_metadata(self, plugin_name: str) -> Optional[Dict]:
        """获取插件的元信息
        返回插件的详细元数据，包括版本、依赖等信息
        """
        for plugin in PLUGIN_REGISTRY:
            if plugin.get('name') == plugin_name:
                # 返回插件的完整元信息
                return {
                    'name': plugin['name'],
                    'version': plugin.get('version', 'N/A'),
                    'commands': plugin['commands'],
                    'chat_type': plugin['chat_type'],
                    'permission': plugin['permission'],
                    'dependencies': plugin.get('dependencies', []),
                    'plugin_path': plugin.get('plugin_path', '')
                }
        return None
    
    def get_all_plugins_metadata(self) -> List[Dict]:
        """获取所有已加载插件的元信息列表"""
        return [self.get_plugin_metadata(plugin['name']) for plugin in PLUGIN_REGISTRY]
    
    def reload_plugin(self, plugin_name: str) -> bool:
        """重载指定的插件
        返回是否重载成功
        """
        # 找到插件的路径
        plugin_path = None
        for plugin in PLUGIN_REGISTRY:
            if plugin.get('name') == plugin_name:
                plugin_path = plugin.get('plugin_path')
                break
        
        if not plugin_path:
            logger.error(f"❌ 未找到插件 {plugin_name}")
            return False
        
        try:
            # 从注册池中移除插件
            # 由于这些变量已经在模块级别定义为全局变量，不需要额外声明global
            PLUGIN_REGISTRY = [p for p in PLUGIN_REGISTRY if p.get('name') != plugin_name]
            if plugin_name in LOADED_PLUGIN_VERSIONS:
                del LOADED_PLUGIN_VERSIONS[plugin_name]
            
            logger.info(f"🔄 开始重载插件 {plugin_name}")
            
            # 重新扫描并加载该插件
            # 由于插件可能有依赖，这里简单实现为重新初始化整个插件系统
            # 在实际应用中可以实现更细粒度的重载
            self._initialized = False
            self.init(os.path.dirname(plugin_path))
            
            logger.info(f"✅ 插件 {plugin_name} 重载完成")
            return True
            
        except Exception as e:
            logger.error(f"❌ 重载插件 {plugin_name} 时发生异常：{str(e)}", exc_info=True)
            return False
    
    def shutdown(self):
        """关闭插件管理器，清理资源
        调用所有插件的on_shutdown方法（如果存在）
        """
        logger.info("🔒 开始关闭插件管理器")
        
        for plugin in PLUGIN_REGISTRY:
            try:
                # 检查插件是否有on_shutdown方法
                core_module = plugin.get('core_module')
                if core_module and hasattr(core_module, 'on_shutdown'):
                    shutdown_func = getattr(core_module, 'on_shutdown')
                    if callable(shutdown_func):
                        logger.debug(f"调用插件 {plugin['name']} 的 on_shutdown 方法")
                        shutdown_func()
            except Exception as e:
                logger.error(f"调用插件 {plugin['name']} 的 on_shutdown 方法时出错：{str(e)}")
        
        # 清空注册池
        PLUGIN_REGISTRY.clear()
        LOADED_PLUGIN_VERSIONS.clear()
        DEPENDENCY_GRAPH.clear()
        
        self._initialized = False
        logger.info("✅ 插件管理器已关闭")

# 全局单例插件管理器实例（供外部模块直接导入使用）
plugin_manager = PluginManager()
