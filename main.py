import asyncio
import signal
import sys
import os
import subprocess
from typing import List, Optional

from Log import log
from customCMDs import ctx, start_vip_check_task, check_expired_vips
from log_loop import log_loop
from credentials_manager import CredentialsManager

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
            
            # 程序启动时立即执行一次VIP过期检查
            logger.info("执行启动时VIP过期检查...")
            try:
                await check_expired_vips()
                logger.info("启动时VIP过期检查完成")
            except Exception as e:
                logger.error(f"启动时VIP过期检查失败: {e}")
            
            # 创建并启动VIP检查定时任务
            vip_check_task = asyncio.create_task(
                start_vip_check_task(),
                name="VIPCheck"
            )
            self.tasks.append(vip_check_task)

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
            
    async def _run_vip_cleaner(self):
        """运行VIP清理定时任务"""
        try:
            logger.info("启动VIP清理定时任务")
            
            # 首次启动时清理一次
            try:
                # 清理数据库中过期的VIP
                cleaned_count = await ctx.data.async_clean_expired_vips()
                
                # 清理游戏中的过期VIP
                await self._clean_expired_vips_from_game()
                
                logger.info(f"初始化清理过期VIP: 已从数据库清理 {cleaned_count} 个")
            except Exception as e:
                logger.error(f"初始化清理VIP失败: {e}")
            
            # 每天定期清理
            while self.running:
                try:
                    # 等待24小时
                    await asyncio.sleep(24 * 3600)
                    
                    # 清理数据库中过期的VIP
                    cleaned_count = await ctx.data.async_clean_expired_vips()
                    
                    # 清理游戏中的过期VIP
                    await self._clean_expired_vips_from_game()
                    
                    if cleaned_count > 0:
                        logger.info(f"定时清理过期VIP: 已从数据库清理 {cleaned_count} 个")
                except asyncio.CancelledError:
                    logger.info("VIP清理任务被取消")
                    break
                except Exception as e:
                    logger.error(f"VIP清理任务异常: {e}")
                    # 出错后等待10分钟再重试
                    await asyncio.sleep(600)
        except Exception as e:
            logger.error(f"VIP清理定时任务异常: {e}")
            # 不会导致主程序终止
            return
            
    async def _clean_expired_vips_from_game(self):
        """从游戏服务器清理已过期的VIP"""
        try:
            # 获取数据库中所有有效的VIP ID
            active_vips = await ctx.data.async_get_all_active_vips()
            active_vip_ids = [vip['player_id'] for vip in active_vips]
            
            # 获取游戏中所有的VIP
            game_vips = await ctx.commands.get_vip_ids()
            if not game_vips:
                logger.info("游戏服务器中无VIP，无需清理")
                return
                
            # 处理返回结果可能是列表或单个字典的情况
            if isinstance(game_vips, dict):
                game_vips = [game_vips]
                
            # 计数器
            removed_count = 0
            
            # 移除游戏中已过期的VIP
            for game_vip in game_vips:
                player_id = game_vip.get('player_id')
                player_name = game_vip.get('name', '')
                
                if player_id and player_id not in active_vip_ids:
                    # 从游戏中移除VIP
                    success = await ctx.commands.remove_vip(player_id)
                    if success:
                        removed_count += 1
                        logger.info(f"已从游戏服务器移除过期VIP: {player_name} ({player_id})")
                    else:
                        logger.warning(f"从游戏服务器移除VIP失败: {player_name} ({player_id})")
            
            if removed_count > 0:
                logger.info(f"从游戏服务器清理过期VIP完成，共移除 {removed_count} 个")
        except Exception as e:
            logger.error(f"从游戏服务器清理过期VIP失败: {e}")
            # 不抛出异常，继续执行其他任务
            
    async def _run_vip_sync(self):
        """运行VIP同步定时任务，将数据库中的VIP信息同步到游戏服务器"""
        try:
            logger.info("启动VIP同步定时任务")
            
            # 首次启动时同步一次
            try:
                await self._sync_vips_to_game()
                logger.info("初始化同步VIP信息到游戏服务器完成")
            except Exception as e:
                logger.error(f"初始化同步VIP失败: {e}")
            
            # 每6小时定期同步
            while self.running:
                try:
                    # 等待6小时
                    await asyncio.sleep(6 * 3600)
                    
                    # 同步VIP
                    await self._sync_vips_to_game()
                    logger.info("定时同步VIP信息到游戏服务器完成")
                except asyncio.CancelledError:
                    logger.info("VIP同步任务被取消")
                    break
                except Exception as e:
                    logger.error(f"VIP同步任务异常: {e}")
                    # 出错后等待10分钟再重试
                    await asyncio.sleep(600)
        except Exception as e:
            logger.error(f"VIP同步定时任务异常: {e}")
            # 不会导致主程序终止
            return
    
    async def _sync_vips_to_game(self):
        """同步数据库中的VIP信息到游戏服务器"""
        try:
            # 获取数据库中所有有效的VIP
            vips = await ctx.data.async_get_all_active_vips()
            logger.info(f"准备同步 {len(vips)} 个VIP到游戏服务器")
            
            # 获取游戏中现有的VIP
            game_vips = await ctx.commands.get_vip_ids()
            game_vip_ids = [vip.get("player_id") for vip in game_vips] if game_vips else []
            logger.info(f"游戏服务器中已有 {len(game_vip_ids)} 个VIP")
            
            # 同步VIP信息
            sync_count = 0
            for vip in vips:
                player_id = vip.get("player_id")
                player_name = vip.get("player_name")
                notes = vip.get("notes", "")
                
                # 如果VIP不在游戏中，添加它
                if player_id not in game_vip_ids:
                    success = await ctx.commands.add_vip(player_id, notes)
                    if success:
                        sync_count += 1
                        logger.info(f"已同步VIP到游戏服务器: {player_name} ({player_id})")
                    else:
                        logger.warning(f"同步VIP失败: {player_name} ({player_id})")
            
            # 移除游戏中存在但数据库中已过期的VIP
            db_vip_ids = [vip.get("player_id") for vip in vips]
            remove_count = 0
            
            for game_vip_id in game_vip_ids:
                if game_vip_id not in db_vip_ids:
                    success = await ctx.commands.remove_vip(game_vip_id)
                    if success:
                        remove_count += 1
                        logger.info(f"已从游戏服务器移除过期VIP: {game_vip_id}")
                    else:
                        logger.warning(f"移除过期VIP失败: {game_vip_id}")
            
            logger.info(f"VIP同步完成: 添加 {sync_count} 个, 移除 {remove_count} 个")
        except Exception as e:
            logger.error(f"同步VIP信息到游戏服务器失败: {e}")
            raise

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
    try:
        # 检查凭证
        cred_manager = CredentialsManager()
        if not cred_manager.has_credentials():
            logger.warning("未找到服务器连接凭证！")
            logger.info("请运行 reset_credentials.py 设置凭证后再启动程序。")
            
            # 询问用户是否立即运行凭证设置工具
            try:
                response = input("是否立即设置凭证？(y/n): ").strip().lower()
                if response == 'y':
                    # 获取reset_credentials.py的绝对路径
                    script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reset_credentials.py")
                    
                    # 使用Python解释器运行脚本
                    subprocess.run([sys.executable, script_path], check=True)
                    logger.info("凭证设置完成，继续启动程序...")
                else:
                    logger.info("退出程序，请在设置凭证后重新启动。")
                    sys.exit(0)
            except Exception as e:
                logger.error(f"运行凭证设置工具失败: {e}")
                logger.info("请手动运行 reset_credentials.py 设置凭证后再启动程序。")
                sys.exit(1)
    
        # 初始化上下文
        await ctx.initialize()
        
        # 创建并启动机器人
        bot = HLLBot()
        await bot.start()
    except ValueError as e:
        # 捕获凭证相关的错误
        if "未找到服务器凭证" in str(e):
            logger.error("启动失败：未找到有效的服务器凭证")
            logger.info("请运行 reset_credentials.py 设置凭证后再启动程序。")
        else:
            logger.error(f"启动失败: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"启动时出现未预期的错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
