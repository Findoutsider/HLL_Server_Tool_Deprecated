import asyncio
import os
import time
from typing import Optional

import requests

from Log import log
from connection import HLLConnection, async_close_all
from customCMDs import Context, qq_Commands

# 设置日志
logger = log()

# 全局变量
last_activity = time.time()
keepalive_interval = 30  # 保活间隔（秒）
max_idle_time = 60  # 最大空闲时间（秒）
processed_messages = set()  # 存储已处理的消息ID

# 正在处理中的连接请求计数
pending_connection_requests = 0


class Bot:
    def __init__(self, qq_group, read_amount, port, admin=None, ignore=None):
        self.port = port
        self.admin = admin if admin else []  # 初始化为空列表，后面会从数据库加载
        self.read_amount = read_amount
        self.qq_group = qq_group
        self.ignore = ignore if ignore else []
        self.receive_url = f"http://127.0.0.1:{self.port}/get_group_msg_history"
        self.send_url = f"http://127.0.0.1:{self.port}/send_group_msg"
        self.receive_payload = {
            "group_id": qq_group,
            "message_seq": "0",
            "count": read_amount,
            "reverseOrder": False
        }
        self.send_payload = {
            "group_id": qq_group,
            "message": ""
        }
        self.headers_bot = {
            'Content-Type': 'application/json'
        }

    def update_admin_list(self, new_admin_list):
        """更新管理员列表"""
        if new_admin_list:
            self.admin = new_admin_list
            logger.info(f"已更新管理员列表，共 {len(self.admin)} 名管理员")
        
    def msg_listener(self, r, get):
        if not r:
            return False
        try:
            if get == "id":
                msg_id = r[0].get("message_id")
                return msg_id
            qq_id = r[0].get("user_id")
            if get == "role":
                return str(qq_id) in self.admin
            elif get == "qq":
                return qq_id
        except Exception as e:
            logger.error(f"msg_listener出错: {e}")
            return False


class LoginInformation:
    def __init__(self, file_path="config.txt"):
        self.file_path = file_path

    def read(self):
        # 检查文件是否存在，如果不存在则创建并写入默认内容
        if not os.path.exists(self.file_path):
            with open(self.file_path, 'w') as file:
                log.warning("File not found. Creating an empty file.")
                log.warning("Please fill in the username and password or csrftoken and sessionid.")
                self.write(file)

            return None

        credentials = {}
        try:
            with open(self.file_path, 'r') as file:
                for line in file:
                    line = line.strip()
                    if line and '=' in line:
                        key, value = line.split('=', 1)
                        credentials[key] = value
        except Exception as e:
            log.error(f"Error reading file: {e}")

        return credentials

    def write(self, f):
        f.write("# 请填写username和password或csrftoken和sessionid，无需全部填写\n\n")
        f.write("cooldown=5\n")
        f.write("port=3000\n")
        f.write("# # 可使用远程命令的qq号\n")
        f.write("admin=[2275016544]\n\n")
        f.write("# 屏蔽的qq号\nignore=[3821743226]\n\n")
        f.write("read_amount=1\n")
        f.write("qq_group=532933387\n")


async def get_connection() -> Optional[HLLConnection]:
    """获取一个可用的连接，使用正确的异步方式"""
    global pending_connection_requests
    
    try:
        # 增加等待连接计数，用于防止连接风暴
        pending_connection_requests += 1
        
        # 如果有太多挂起的请求，则立即返回None
        if pending_connection_requests > 5:
            logger.warning(f"已有 {pending_connection_requests} 个连接请求，正在等待...")
            return None
            
        # 使用同步方法获取连接
        conn = ctx.connection_pool.get_connection()
        
        # 如果没有可用连接，等待一下再尝试一次
        if conn is None:
            logger.info("没有可用连接，等待500ms后重试...")
            await asyncio.sleep(0.5)
            conn = ctx.connection_pool.get_connection()
            
        return conn
    except Exception as e:
        # logger.error(f"获取连接失败: {e}")
        return None
    finally:
        # 减少挂起请求计数
        pending_connection_requests -= 1


async def release_connection(conn: Optional[HLLConnection]):
    """安全地释放连接回连接池"""
    if conn is None:
        # 不需要处理None连接
        return
        
    try:
        ctx.connection_pool.release_connection(conn)
    except Exception as e:
        logger.error(f"释放连接失败: {e}")


async def send_command(command: str) -> str:
    """发送命令到HLL服务器，使用更可靠的连接管理"""
    conn = None
    retries = 2
    
    for attempt in range(retries):
        try:
            conn = await get_connection()
            if not conn:
                if attempt == retries - 1:
                    return "无法获取连接到游戏服务器"
                logger.warning(f"无法获取连接，等待重试 ({attempt+1}/{retries})...")
                await asyncio.sleep(1)
                continue
            
            # 使用连接发送命令
            response = conn.send_command(command)
            return response
        except Exception as e:
            logger.error(f"发送命令失败 (尝试 {attempt+1}/{retries}): {e}")
            if attempt == retries - 1:
                return f"命令执行失败: {str(e)}"
            await asyncio.sleep(1)  # 等待一会再重试
        finally:
            # 确保连接被释放
            if conn:
                await release_connection(conn)
    
    return "命令执行失败: 连接问题"


async def handle_qq_message(message: list[str], is_admin: bool = False) -> None:
    """处理QQ消息"""
    try:
        # 更新最后活动时间
        global last_activity
        last_activity = time.time()
        
        # 获取消息内容
        if not message:
            return
            
        # 检查是否是命令
        response = await qq_Commands(message, is_admin)
        # 发送响应到QQ
        bot.send_payload["message"] = response
        if bot.send_payload["message"]:
            qq_response = requests.post(bot.send_url, json=bot.send_payload, headers=bot.headers_bot)
            logger.info(f"尝试发送消息到QQ: {bot.send_payload['message']}")
            logger.info(f"发送消息到QQ: {qq_response.json()}")
        logger.info(f"执行命令: {message}, 响应: {response}")
    except Exception as e:
        logger.error(f"处理QQ消息时出错: {e}", exc_info=True)


async def keepalive_loop():
    """保活循环"""
    while True:
        try:
            current_time = time.time()
            if current_time - last_activity > keepalive_interval:
                # 发送空命令保持连接活跃
                await send_command("")
                logger.debug("发送保活命令")
            
            # 检查是否超过最大空闲时间
            if current_time - last_activity > max_idle_time:
                logger.warning("连接空闲时间过长，重新连接...")
                # 重新初始化连接池
                await async_close_all(ctx.connection_pool)
            
            await asyncio.sleep(1)
        except Exception as e:
            logger.error(f"保活循环出错: {e}")
            await asyncio.sleep(5)  # 出错后等待更长时间


async def receive_qq_message():
    global processed_messages
    
    # 清理过旧的消息ID，防止集合过大
    if len(processed_messages) > 100:
        logger.info(f"清理消息ID集合，当前大小: {len(processed_messages)}")
        processed_messages.clear()
        
    while True:
        try:
            response = requests.post(bot.receive_url, json=bot.receive_payload, headers=bot.headers_bot)
            res = response.json().get('data').get("messages")
            
            if not res:
                await asyncio.sleep(0.5)
                continue
            if bot.msg_listener(res, "qq") in bot.ignore:
                continue
            # 获取消息ID并检查是否已处理过
            message_id = bot.msg_listener(res, "id")
            if message_id and str(message_id) in processed_messages:
                logger.debug(f"跳过已处理的消息ID: {message_id}")
                await asyncio.sleep(0.5)
                continue
                
            # 添加到已处理集合
            if message_id:
                processed_messages.add(str(message_id))
                logger.debug(f"添加消息ID到已处理集合: {message_id}")

            is_admin = bot.msg_listener(res, "role")
            qq_id = bot.msg_listener(res, "qq")
            
            # 确保qq_id和ignore中的元素类型匹配
            if qq_id is not None and bot.ignore:
                # 转换qq_id和ignore为同一类型进行比较
                try:
                    if isinstance(qq_id, int):
                        ignore_list = [int(x) if isinstance(x, str) and x.isdigit() else x for x in bot.ignore]
                        if qq_id in ignore_list:
                            continue
                    else:
                        if str(qq_id) in [str(x) for x in bot.ignore]:
                            continue
                except Exception as e:
                    logger.error(f"类型转换出错: {e}")
                    continue
            
            try:
                res = ''.join(res[0].get('message'))
                if not res.strip():  # 忽略空消息
                    continue
            except IndexError:
                continue
            except TypeError as e:
                logger.error(f"消息拼接出错: {e}")
                continue
                
            res = res.split(" ", 1)
            if len(res) == 1:
                res.append("")  # 确保res至少有两个元素
            
            logger.info(f"收到新消息: {res[0]}, 消息ID: {message_id}, 是否管理员: {is_admin}")
            return res, is_admin
        except Exception as e:
            logger.error(f"receive_qq_message出错: {e}")
            await asyncio.sleep(1)
            return None, False


async def qq_bot():
    """QQ机器人主循环"""
    keepalive_task = None  # 初始化变量
    last_message_time = time.time()  # 上次处理消息的时间
    last_admin_refresh_time = time.time()  # 上次刷新管理员列表的时间
    admin_refresh_interval = 60  # 管理员列表刷新间隔（秒）
    min_message_interval = 0.5  # 最小消息处理间隔（秒）
    
    try:
        # 首次加载管理员列表
        admin_list = ctx.data.get_all_qq_admins()
        if admin_list:
            bot.update_admin_list(admin_list)
            logger.info(f"从数据库加载管理员列表: {admin_list}")
        
        # 启动保活循环
        keepalive_task = asyncio.create_task(keepalive_loop())
        
        # 初始化QQ机器人连接
        logger.info("QQ机器人启动完成，正在监听消息...")
        
        while True:
            try:
                # 定期刷新管理员列表
                current_time = time.time()
                if current_time - last_admin_refresh_time > admin_refresh_interval:
                    admin_list = ctx.data.get_all_qq_admins()
                    bot.update_admin_list(admin_list)
                    last_admin_refresh_time = current_time
                
                # 接收QQ消息
                message = await receive_qq_message()
                
                # 处理消息，包含频率限制
                if message:
                    current_time = time.time()
                    time_since_last_message = current_time - last_message_time
                    
                    if time_since_last_message < min_message_interval:
                        # 如果距离上次处理消息时间太短，等待一下
                        await asyncio.sleep(min_message_interval - time_since_last_message)
                    
                    # 处理消息
                    await handle_qq_message(message[0], message[1])
                    last_message_time = time.time()
                
                # 适当等待，避免CPU使用率过高
                await asyncio.sleep(0.2)
            except Exception as e:
                logger.error(f"QQ机器人循环出错: {e}")
                await asyncio.sleep(1)
    except Exception as e:
        logger.error(f"QQ机器人异常: {e}")
    finally:
        if keepalive_task is not None:
            keepalive_task.cancel()
            try:
                await keepalive_task
            except asyncio.CancelledError:
                pass
        
        logger.info("关闭QQ机器人连接池...")
        await async_close_all(ctx.connection_pool)


async def main():
    """主函数"""
    try:
        # 初始化上下文
        await ctx.initialize()
        
        logger.info("启动QQ机器人...")
        await qq_bot()
    except Exception as e:
        logger.error(f"QQ机器人异常: {e}")

if __name__ == "__main__":
    login_info = LoginInformation()
    credentials = login_info.read()
    
    # 解析配置文件中的ignore列表
    ignore_list = eval(credentials.get("ignore", "[]")) if "ignore" in credentials else []
    
    bot = Bot(
        qq_group=credentials.get("qq_group", "532933387"),
        read_amount=credentials.get("read_amount", "1"),
        port=credentials.get("port", "3000"),
        ignore=ignore_list
    )
    
    # 初始化连接池
    ctx = Context()
    asyncio.run(main())
