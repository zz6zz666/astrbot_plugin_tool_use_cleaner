from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api.provider import ProviderRequest
from astrbot.api import logger, AstrBotConfig

@register("tool_use_cleaner", "author", "在本轮LLM请求前，将先前轮请求中的工具调用和返回结果从请求体中移除，减少 token 浪费", "1.0.0")
class ToolUseCleanerPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config  # AstrBotConfig继承自Dict，可以直接使用字典方法访问
        logger.info("工具调用清洗插件已初始化")
        
    @filter.on_llm_request()
    async def clean_context(self, event: AstrMessageEvent, req: ProviderRequest):
        """
        清洗上下文中的tool use和function字段
        每当AstrBot接收到用户消息并准备向LLM发送请求时触发，移除先前轮次的工具调用和返回结果
        """
        if req.contexts:
            # 记录原始上下文数量，用于调试
            original_count = len(req.contexts)
            
            # 过滤掉tool角色的消息和包含tool_calls或function_call的消息
            cleaned_contexts = []

            # 从配置中读取enable_function_call_cleaner，默认为True
            enable_function_call_cleaner = bool(self.config.get("enable_function_call_cleaner", True))
            
            for ctx in req.contexts:
                # 跳过tool角色的消息（工具调用输出）
                if ctx.get("role") == "tool":
                    continue
                
                if enable_function_call_cleaner and ctx.get("role") == "assistant":
                    if not ctx.get("content"):
                        continue
                    elif "tool_calls" in ctx:
                        # 创建一个新的上下文对象，移除tool_calls字段但保留其他内容
                        cleaned_ctx = ctx.copy()
                        del cleaned_ctx["tool_calls"]
                        cleaned_contexts.append(cleaned_ctx)
                        continue

                cleaned_contexts.append(ctx)
            
            # 更新上下文
            req.contexts = cleaned_contexts
            
            # 记录清洗结果，用于调试
            cleaned_count = len(req.contexts)
            removed_count = original_count - cleaned_count
            if removed_count > 0:
                logger.info(f"上下文清洗: 移除了 {removed_count} 条工具调用及其响应消息")

    async def terminate(self):
        """插件卸载时的清理工作"""
        logger.info("工具调用清洗插件已卸载")
        