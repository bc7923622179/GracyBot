# 插件元信息（严格匹配插件功能和核心函数）
PLUGIN_META = {
    "name": "OpenAI_plugin",  # 插件唯一名称，与目录/核心文件一致
    "commands": ["//", "/chat帮助", "/设置OpenAI", "/新增人设", "/删除人设", "/查看人设列表", "/切换人设", "/清除记忆", "/persona", "/+persona", "/-persona", "/persona=", "/戳一戳开关", "/戳一戳状态"],  # 所有触发指令（包含//用于AI聊天触发）
    "handler": "handle_openai_plugin",  # 核心处理函数名（对应插件主入口函数）
    "chat_type": ["private", "group"],  # 支持私聊和群聊场景
    "permission": "all",  # 全员可用（主人专属命令插件内已做权限校验）
    "is_at_required": False,  # 群聊无需@机器人触发（插件管理指令可直接使用）
    "description": "AI对话插件，支持//前缀触发聊天、人设切换、上下文记忆，主人专属配置权限，集成戳一戳功能",
    "version": "v1.0.3",
    "author": "GracyBot开发者"
}

# 导入戳一戳功能模块
from .poke_handler import handle_poke_event, set_poke_enabled, set_auto_reply, set_poke_back, set_ai_response, get_poke_status
