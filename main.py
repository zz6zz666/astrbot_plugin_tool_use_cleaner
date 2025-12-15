from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api.provider import ProviderRequest
from astrbot.api import logger, AstrBotConfig

@register("tool_use_cleaner", "zz6zz666", "在本轮LLM请求前，将先前轮请求中的工具调用和返回结果从请求体中移除，减少 token 浪费", "1.3.0")
class ToolUseCleanerPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config  # AstrBotConfig继承自Dict，可以直接使用字典方法访问
        # 读取轮数控制配置，默认为0（不保留任何工具调用信息）
        self.tool_context_keep_rounds = int(self.config.get("tool_context_keep_rounds", 0))
        logger.info(f"工具调用清洗插件已初始化，保留最近{self.tool_context_keep_rounds}轮的工具调用信息")
        
    @filter.on_llm_request()
    async def clean_context(self, event: AstrMessageEvent, req: ProviderRequest):
        """
        清洗上下文中的tool use和function字段
        每当AstrBot接收到用户消息并准备向LLM发送请求时触发，移除先前轮次的工具调用和返回结果
        """
        if req.contexts:
            # 记录原始上下文数量，用于调试
            original_count = len(req.contexts)
            
            # 如果没有启用轮数控制，使用原有逻辑
            if self.tool_context_keep_rounds <= 0:
                # 过滤掉tool角色的消息和包含tool_calls或function_call的消息
                cleaned_contexts = []
                
                for ctx in req.contexts:
                    # 跳过tool角色的消息（工具调用输出）
                    if ctx.get("role") == "tool":
                        continue
                    
                    if ctx.get("role") == "assistant":
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
            else:
                # 启用轮数控制，使用新的清理逻辑
                contexts = req.contexts
                new_contexts = []
                
                # 使用简单逻辑找到所有轮次的结束位置：当上一条是a而下一条是u/s即意味着轮的分割
                round_ends = []
                
                # 遍历所有消息，找到a->u/s的转换点
                for i in range(len(contexts) - 1):
                    current_role = contexts[i].get("role")
                    next_role = contexts[i + 1].get("role")
                    
                    # 如果当前是assistant，下一个是user或system，则当前assistant是轮次结束
                    if current_role == "assistant" and next_role in ["user", "system"]:
                        round_ends.append(i)
                
                # 处理最后一个消息：如果最后一个是assistant，它也是一个轮次的结束
                if contexts and contexts[-1].get("role") == "assistant":
                    round_ends.append(len(contexts) - 1)
                
                # 找到cutoff_index
                cutoff_index = -1  # 默认不清除任何工具调用信息
                if self.tool_context_keep_rounds > 0 and round_ends:
                    # 如果轮次数量不足，返回第一个轮次结束位置
                    if len(round_ends) < self.tool_context_keep_rounds:
                        cutoff_index = round_ends[0]
                    else:
                        # 返回倒数第tool_context_keep_rounds轮的结束位置
                        cutoff_index = round_ends[-self.tool_context_keep_rounds]
                
                # 遍历所有上下文，决定是否保留工具调用信息
                for i, ctx in enumerate(contexts):
                    role = ctx.get("role")
                    
                    # 如果在cutoff_index之前，则清除工具调用信息
                    if i <= cutoff_index:
                        # 跳过tool角色的消息（工具调用输出）
                        if role == "tool":
                            continue
                        
                        # 如果是assistant消息，移除tool_calls
                        if role == "assistant" and "tool_calls" in ctx:
                            # 创建一个新的上下文对象，移除tool_calls字段但保留其他内容
                            cleaned_ctx = ctx.copy()
                            del cleaned_ctx["tool_calls"]
                            new_contexts.append(cleaned_ctx)
                            continue
                    
                    # 保留所有其他消息
                    new_contexts.append(ctx)
                
                # 更新上下文
                req.contexts = new_contexts
                logger.debug(f"已清理工具调用上下文，保留最近 {self.tool_context_keep_rounds} 轮的工具调用信息")
            
            # 记录清洗结果，用于调试
            cleaned_count = len(req.contexts)
            removed_count = original_count - cleaned_count
            if removed_count > 0:
                logger.info(f"上下文清洗: 移除了 {removed_count} 条工具调用及其响应消息")

    async def terminate(self):
        """插件卸载时的清理工作"""
        logger.info("工具调用清洗插件已卸载")
        