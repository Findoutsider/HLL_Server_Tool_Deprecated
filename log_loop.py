# log_loop.py
import asyncio
import re
from collections import deque
from typing import Iterable, Tuple, Union

from Log import log
from commands import Commands
from hooks import get_hooks

# 设置日志
logger = log()

# 定义日志正则表达式模式
LOG_PATTERNS = {
    "CHAT": re.compile(r"CHAT\[(Team|Unit)]\[(.*)\((Allies|Axis)/(.*)\)]: (.*)"),
    "CHAT_SIMPLE": re.compile(r"CHAT.*\[(.*?)]:\s*(.*)"),  # 简化的聊天匹配
    "LOG_TIME": re.compile(r".*\((\d+)\).*"),
}

# 日志缓存大小
LOG_CACHE_SIZE = 1000

# 日志处理队列
log_queue = asyncio.Queue()


def split_raw_log_lines(raw_logs: Union[str, bytes]) -> Iterable[Tuple[str, str, str]]:
    """
    将原始游戏服务器日志分割为相对时间、时间戳和内容
    
    Args:
        raw_logs: 原始日志字符串或字节
        
    Yields:
        包含相对时间、时间戳和日志内容的元组
    """
    if not raw_logs:
        logger.info("收到空日志")
        return
        
    # 如果是字节类型，尝试不同的编码方式
    if isinstance(raw_logs, bytes):
        encodings = ['utf-8', 'latin1', 'gbk', 'gb2312', 'gb18030']
        decoded = None
        
        for encoding in encodings:
            try:
                decoded = raw_logs.decode(encoding)
                logger.debug(f"成功使用 {encoding} 解码日志")
                break
            except UnicodeDecodeError:
                continue
                
        if decoded is None:
            logger.error("无法解码日志，尝试使用 latin1 编码（可能丢失部分信息）")
            try:
                decoded = raw_logs.decode('latin1')
            except Exception as e:
                logger.error(f"最终解码尝试失败: {e}")
                return
                
        raw_logs = decoded
            
    if not isinstance(raw_logs, str):
        logger.info(f"收到非字符串日志: {type(raw_logs)}")
        return
        
    try:
        for line in raw_logs.strip().split('\n'):
            line = line.strip()
            if not line:
                continue
            
            # 提取时间戳
            time_match = LOG_PATTERNS["LOG_TIME"].match(line)
            if not time_match:
                logger.debug(f"无法匹配时间戳: {line}")
                continue
                
            timestamp = time_match.group(1)
            content = line
            
            # 提取相对时间（如果有）
            relative_time = "00:00:00"  # 默认值
            if "[" in line and "]" in line:
                time_part = line[line.find("[")+1:line.find("]")]
                if ":" in time_part:
                    relative_time = time_part
            
            logger.debug(f"解析结果: 时间={relative_time}, 时间戳={timestamp}, 内容={content}")
            yield relative_time, timestamp, content

    except Exception as e:
        logger.error(f"分割日志行时出错: {e}")
        return


class LogProcessor:
    """日志处理器类，用于管理日志处理状态"""

    def __init__(self):
        self.seen_logs = deque(maxlen=LOG_CACHE_SIZE)
        self.logger = log()
        self.commands = Commands()  # 每个处理器实例都有自己的命令实例

    async def process_log(self, relative_time: str, timestamp: str, content: str) -> None:
        try:
            # 创建唯一标识符
            log_id = f"{timestamp}:{content}"
            if log_id in self.seen_logs:
                return

            self.seen_logs.append(log_id)
            
            # 处理聊天消息
            if "CHAT" in content:
                for chat_type in ["CHAT", "CHAT_SIMPLE"]:
                    if pattern := LOG_PATTERNS.get(chat_type):
                        match = pattern.search(content)
                        if match:
                            hooks = get_hooks("CHAT")
                            for hook in hooks:
                                try:
                                    await hook(self.commands, {
                                        "message": content,
                                        "timestamp": timestamp,
                                        "relative_time": relative_time,
                                        "type": "CHAT",
                                        "match": match.groups()
                                    })
                                except Exception as e:
                                    self.logger.error(f"执行聊天钩子函数失败: {e}")
                            break
        except Exception as e:
            self.logger.error(f"处理日志时出错: {e}, 内容: {content}")


async def log_processor_worker():
    """日志处理工作线程"""
    processor = LogProcessor()
    while True:
        try:
            log_data = await log_queue.get()
            await processor.process_log(*log_data)
            log_queue.task_done()
        except Exception as e:
            logger.error(f"日志处理工作线程出错: {e}")


async def log_loop():
    """异步日志循环"""
    processor = LogProcessor()
    last_logs = set()
    current_logs = set()
    retry_count = 0
    max_retries = 5
    retry_delay = 5  # 重试延迟时间（秒）

    # 启动日志处理工作线程
    worker_task = asyncio.create_task(log_processor_worker())

    try:
        while True:
            try:
                # 获取最近1分钟的日志
                raw_logs = await processor.commands.get_log(minutes_ago=1)
                if not raw_logs:
                    await asyncio.sleep(1)
                    continue
                
                # 清空当前日志集合
                current_logs.clear()
                
                # 处理新日志
                for relative_time, timestamp, content in split_raw_log_lines(raw_logs):
                    log_id = f"{timestamp}:{content}"
                    if log_id not in last_logs:
                        current_logs.add(log_id)
                        await log_queue.put((relative_time, timestamp, content))
                
                # 更新最后看到的日志集合
                last_logs = current_logs.copy()
                
                # 重置重试计数
                retry_count = 0
                
                # 等待一段时间
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"日志循环出错: {e}")
                
                # 检查是否是连接错误
                if "无法获取可用连接" in str(e) or "连接失败" in str(e):
                    retry_count += 1
                    if retry_count >= max_retries:
                        logger.error(f"达到最大重试次数 ({max_retries})，停止重试")
                        break
                    
                    logger.info(f"连接失败，将在 {retry_delay} 秒后重试 (尝试 {retry_count}/{max_retries})")
                    await asyncio.sleep(retry_delay)
                else:
                    # 其他错误，等待1秒后重试
                    await asyncio.sleep(1)
    finally:
        # 确保在退出时取消工作线程
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass


async def main():
    """主函数"""
    try:
        logger.info("启动命令监控...")
        await log_loop()
    except Exception as e:
        logger.error(f"命令监控异常: {e}")


if __name__ == "__main__":
    asyncio.run(main())
