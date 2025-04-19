import asyncio
import signal
import sys
from typing import List, Optional

from Log import log
from customCMDs import ctx
from log_loop import log_loop

# 设置日志
logger = log()


class HLLBot:
    """HLL 机器人主类"""

    def __init__(self):
        self.tasks: List[asyncio.Task] = []
        self.running = True

        # 设置信号处理
        signal.signal(signal.SIGINT, self.handle_shutdown)
        signal.signal(signal.SIGTERM, self.handle_shutdown)

    async def start(self):
        """启动机器人"""
        try:
            logger.info("正在启动 HLL 机器人...")

            # 创建并启动日志循环任务
            log_task = asyncio.create_task(
                self._run_log_loop(),
                name="LogLoop"
            )
            self.tasks.append(log_task)

            logger.info("HLL 机器人启动成功")

            # 保持主循环运行
            while self.running:
                await asyncio.sleep(1)

        except Exception as e:
            logger.error(f"启动失败: {e}")
            await self.shutdown()

    async def _run_log_loop(self):
        """运行日志循环"""
        try:
            await log_loop()
        except Exception as e:
            logger.error(f"日志循环异常: {e}")
            self.running = False

    def handle_shutdown(self, signum: int, frame: Optional[object]):
        """处理关闭信号"""
        logger.info(f"收到关闭信号: {signum}")
        asyncio.create_task(self.shutdown())

    async def shutdown(self):
        """关闭机器人"""
        logger.info("正在关闭 HLL 机器人...")
        self.running = False

        # 取消所有任务
        for task in self.tasks:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        # 清理资源
        try:
            # 使用ctx的连接池
            ctx.connection_pool.close_all()
        except Exception as e:
            logger.error(f"断开连接时出错: {e}")

        logger.info("HLL 机器人已关闭")
        sys.exit(0)


async def main():
    """主函数"""
    # 初始化上下文
    await ctx.initialize()
    
    # 创建并启动机器人
    bot = HLLBot()
    await bot.start()


if __name__ == "__main__":
    asyncio.run(main())
