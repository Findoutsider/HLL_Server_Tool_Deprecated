import asyncio
import datetime
import re
import time
from typing import Dict, Any, List

import Log
from MapList import MapList
from commands import Commands
from connection import HLLConnectionPool
from dataStorage import DataStorage
from credentials_manager import CredentialsManager
from hooks import on_kill, on_tk, on_chat

# 设置日志
logger = Log.log()

processed_ids = set()

pattern = r'[a-zA-Z0-9]'

qq_commands = {"status": "查服", "ban": "封禁", "banid": "ID封禁", "kick": "踢出", "switch": "换边", "msg": "msg",
               "unban": "解封", "search": "查询", "admin-list": "管理员", "add-admin": "aa", "remove-admin": "ra"}

suicide_commands = ["r", "rrrr"]
ops_commands = ["ops"]
switch_commands = ["换边"]
ban_command = ["ban", "封禁"]
banid_command = ["banid", "id封禁"]
msg_command = ["msg"]
report_command = ["report", ".r", "举报"]
kill_command = ["kill"]
kick_command = ["kick"]
map_commands = ["map", "切图"]

# 初始化管理员列表
admin_list = []

qq_group = 1020644075


class Context:
    """
    公共资源上下文类，用于在 hook 中共享连接和数据库
    
    Attributes:
        conn: RCON连接实例
        commands: 命令执行器实例
        data: 数据存储实例
    """

    def __init__(self):
        # 获取凭证
        cred_manager = CredentialsManager()
        credentials = cred_manager.get_credentials()
        
        if not credentials:
            logger.error("未找到服务器凭证，请先运行 reset_credentials.py 设置凭证")
            raise ValueError("未找到服务器凭证")
            
        # 创建连接池 - 使用从凭证管理器获取的信息
        self.connection_pool = HLLConnectionPool(
            credentials["host"], 
            int(credentials["port"]),  # 确保端口是整数类型
            credentials["password"]
        )
        self.commands = Commands()
        self.map = MapList()
        self.data = DataStorage("data.db")
        self.data.first_run()

    async def initialize(self):
        """异步初始化方法，加载管理员列表"""
        # 只在初始化时更新一次管理员列表
        await load_admin_list()
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """清理资源"""
        try:
            self.connection_pool.close_all()
        except Exception as e:
            logger.error(f"清理资源时出错: {e}")


# 创建全局上下文
ctx = Context()


async def qq_Commands(message: list[str], admin=False) -> str | None | list[str] | Any:
    """
    处理QQ命令
    
    Args:
        message: 包含命令和参数的列表
        admin: 是否是管理员
        
    Returns:
        响应消息
    """
    try:
        if not message or len(message) < 1:
            return "消息格式错误"

        command, args = message
        command = command.lower()
        if not command:
            return ""

        if command == "帮助" or command == "help":
            return "命令列表：https://docs.qq.com/doc/DYW1jUktWU2VVb3JK"
        if command == qq_commands.get("status"):
            counts = await _get_player_count()
            server = await ctx.commands.get_server_name()
            current_map = await ctx.commands.get_map()
            current_map = ctx.map.parse_map_name(current_map)
            next_map = await get_next_map()

            return (f"{server}\n"
                    f"{counts}\t{current_map}\n"
                    f"下一局: {next_map}")

        if command == "图池":
            print(1)
            maps = await ctx.commands.get_map_rotation()
            return "\n".join(ctx.map.parse_map_list(maps))

        if command == "v":
            return await get_vip_info(args.split(" ")[0])

        if not admin:
            return ""
        if command == "+admin":
            # 使用parse_quoted_args处理参数，支持引号
            if not args:
                return "参数有误，格式：+admin <QQ号> [备注]"

            parsed_args = parse_quoted_args(args)
            if not parsed_args:
                return "参数有误，格式：+admin <QQ号> [备注]"

            qq_id = parsed_args[0]
            notes = " ".join(parsed_args[1:]) if len(parsed_args) > 1 else ""

            if ctx.data.add_qq_admin(qq_id, added_by=str(message[0]), notes=notes):
                return f"已添加QQ管理员: {qq_id}"
            else:
                return f"添加QQ管理员失败: {qq_id}"

        if command == "-admin":
            # 使用parse_quoted_args处理参数，支持引号
            if not args:
                return "参数有误，格式：-admin <QQ号>"

            parsed_args = parse_quoted_args(args)
            if not parsed_args:
                return "参数有误，格式：-admin <QQ号>"

            qq_id = parsed_args[0]

            if ctx.data.remove_qq_admin(qq_id):
                return f"已移除QQ管理员: {qq_id}"
            else:
                return f"移除QQ管理员失败: {qq_id}"

        if command == "addadmin" or command == "aa":
            if not args:
                return "参数有误，格式：addadmin <id> <角色> [玩家名]，玩家名包含空格时需要用引号"

            parsed_args = parse_quoted_args(args)
            if len(parsed_args) < 2:
                return "参数有误，格式：addadmin <id> <角色> [玩家名]，玩家名包含空格时需要用引号"

            # 处理玩家名
            player_name = parsed_args[0]

            if ctx.commands.add_admin(parsed_args, parsed_args[1], " ".join(parsed_args[2:])):
                return f"已添加游戏管理员: {player_name}"
            else:
                return f"添加游戏管理员失败: {player_name}"

        if command == "removeadmin" or command == "ra":
            if not args:
                return "参数有误，格式：removeadmin <id>，玩家名包含空格时需要用引号"
            parsed_args = parse_quoted_args(args)

            if ctx.commands.remove_admin(parsed_args[0]):
                return f"已移除游戏管理员: {parsed_args[0]}"
            else:
                return f"移除游戏管理员失败: {parsed_args[0]}"

        if command == "al":
            admin_list = ctx.data.get_all_qq_admins()
            if admin_list:
                return f"当前QQ管理员列表: {', '.join(admin_list)}"
            else:
                return "当前无QQ管理员"

        if command == "ops":
            if len(args) == 0:
                return "请输入要发送的信息"
            await ops(args[0])
            return f"向全体玩家发送信息: {args[0]}"

        if command == "+v":
            if len(args) == 0:
                return "请输入要添加的玩家ID"

            parsed_args = args.split(" ")

            return await handle_vip_command(parsed_args[0], parsed_args[1], parsed_args[2] if len(parsed_args) == 3 else None)

        if command == "-v":
            if len(args) == 0:
                return "请输入要删除的玩家ID"

            parsed_args = args.split(" ")

            return await handle_vip_command(parsed_args[0], "", None, "remove")

        if command == "切图" or command == "map":
            if not args:
                return "参数有误，格式：切图|map <地图名> <天气|时间> <模式>\n部分地图无天气/时间选择"

            parsed_args = args.split(" ", 1)
            if len(parsed_args) < 2:
                return "参数有误，格式：切图|map <地图名> [天气|时间] <模式>\n部分地图无天气/时间选择"

            return await change_map(f"{parsed_args}")

        if command == qq_commands.get("ban"):
            # 使用parse_quoted_args处理参数，支持引号
            if not args:
                return "参数有误，格式：封禁 <玩家名> <原因> [时间]，玩家名包含空格时需要用引号"

            parsed_args = parse_quoted_args(args)
            if len(parsed_args) < 2:
                return "参数有误，格式：封禁 <玩家名> <原因> [时间]，玩家名包含空格时需要用引号"
            
            # 处理玩家名
            target = parsed_args[0]
            reason = parsed_args[1]
            duration = parsed_args[2] if len(parsed_args) > 2 else None
            
            # 检查玩家是否在游戏中
            res = await _is_player_inGame(target)
            if res is None:
                return "无法找到玩家"
            elif res != "":
                return res

            if duration:
                try:
                    duration = int(duration)
                    return await ctx.commands.temp_ban(target, reason=reason, duration_hours=duration, use_id=False)
                except ValueError:
                    return f"时间参数错误，必须是数字: {duration}"
            else:
                return await ctx.commands.perma_ban(target, reason=reason, use_id=False)

        elif command == qq_commands.get("banid"):
            # 使用parse_quoted_args处理参数，支持引号
            if not args:
                return "参数有误，格式：ID封禁 <玩家ID> <原因> [时间]"

            parsed_args = parse_quoted_args(args)
            if len(parsed_args) < 2:
                return "参数有误，格式：ID封禁 <玩家ID> <原因> [时间]"
            
            # 处理玩家ID
            target_id = parsed_args[0]
            reason = parsed_args[1]
            duration = parsed_args[2] if len(parsed_args) > 2 else None

            if duration:
                try:
                    duration = int(duration)
                    return await ctx.commands.temp_ban(target_id, reason=reason, duration_hours=duration, use_id=True)
                except ValueError:
                    return f"时间参数错误，必须是数字: {duration}"
            else:
                return await ctx.commands.perma_ban(target_id, reason=reason, use_id=True)

        elif command == qq_commands.get("kick"):
            # 使用parse_quoted_args处理参数，支持引号
            if not args:
                return "参数有误，格式：踢出 <玩家名> <原因>，玩家名包含空格时需要用引号"

            parsed_args = parse_quoted_args(args)
            if len(parsed_args) < 2:
                return "参数有误，格式：踢出 <玩家名> <原因>，玩家名包含空格时需要用引号"

            # 处理玩家名
            player_name = parsed_args[0]

            res = await _is_player_inGame(player_name)
            if res is None:
                return "无法找到玩家"
            elif res != "":
                return res

            reason = parsed_args[1]

            return await ctx.commands.kick(player_name, reason)

        elif command == qq_commands.get("switch"):
            # 使用parse_quoted_args处理参数，支持引号
            if not args:
                return "参数有误，格式：换边 <玩家名>，玩家名包含空格时需要用引号"

            parsed_args = parse_quoted_args(args)
            if not parsed_args:
                return "参数有误，格式：换边 <玩家名>，玩家名包含空格时需要用引号"

            # 处理玩家名
            player_name = parsed_args[0]

            res = await _is_player_inGame(player_name)
            if res is None:
                return "无法找到玩家"
            elif res != "":
                return res

            return await ctx.commands.switch_player_now(player_name)

        elif command == qq_commands.get("msg"):
            # 使用parse_quoted_args处理参数，支持引号
            if not args:
                return "参数有误，格式：msg <玩家名> <消息内容>，玩家名包含空格时需要用引号"

            parsed_args = parse_quoted_args(args)
            if len(parsed_args) < 2:
                return "参数有误，格式：msg <玩家名> <消息内容>，玩家名包含空格时需要用引号"

            # 处理玩家名
            player_name = parsed_args[0]

            res = await _is_player_inGame(player_name)
            if res is None:
                return "无法找到玩家"
            elif res != "":
                return res

            message = " ".join(parsed_args[1:])

            await ctx.commands.message_player(player_name, message)
            return f"已向 {player_name} 发送消息：{message}"

        elif command == qq_commands.get("unban"):
            # 使用parse_quoted_args处理参数，支持引号
            if not args:
                return "参数有误，格式：解封 <玩家名>，玩家名包含空格时需要用引号"

            parsed_args = parse_quoted_args(args)
            if not parsed_args:
                return "参数有误，格式：解封 <玩家名>，玩家名包含空格时需要用引号"

            # 处理玩家名
            player_name = parsed_args[0]

            res = await ctx.commands.remove_temp_ban(player_name)
            res1 = await ctx.commands.remove_perma_ban(player_name)
            return str(res) if res else str(res1)

        elif command == qq_commands.get("search"):
            # 使用parse_quoted_args处理参数，支持引号
            if not args:
                return "参数有误，格式：查询 <玩家名/ID>，玩家名包含空格时需要用引号"

            parsed_args = parse_quoted_args(args)
            if not parsed_args:
                return "参数有误，格式：查询 <玩家名/ID>，玩家名包含空格时需要用引号"

            # 处理搜索项
            search_term = parsed_args[0]
            logger.info(f"开始查询玩家: {search_term}")
            
            # 记录是否找到玩家
            found_player = False
            result_message = ""

            # 先尝试获取当前在线玩家的信息
            try:
                logger.info(f"尝试获取当前在线玩家信息: {search_term}")
                current_info = await ctx.commands.get_player_info(search_term)
                
                if current_info and current_info != "FAIL":
                    player_current_info = parse_player_info(current_info)
                    if player_current_info and player_current_info.get('name'):
                        logger.info(f"找到当前在线玩家: {player_current_info.get('name')}")
                        found_player = True
                        result_message += f"当前在线玩家：{player_current_info.get('name')}\n"
                        result_message += f"SteamID: {player_current_info.get('steam_id', '未知')}\n"
                        result_message += f"队伍: {player_current_info.get('team', '未知')}\n"
                        result_message += f"角色: {player_current_info.get('role', '未知')}\n"
                        result_message += f"小队: {player_current_info.get('unit', '未知')}\n"
                        result_message += f"等级: {player_current_info.get('level', '未知')}\n"
                        
                        kills = player_current_info.get('kills', 0)
                        deaths = player_current_info.get('deaths', 0)
                        result_message += f"击杀: {kills} - 死亡: {deaths}\n\n"
                else:
                    logger.info(f"当前在线玩家查询无结果: {search_term}")
            except Exception as e:
                logger.error(f"获取当前玩家信息失败: {e}", exc_info=True)

            # 查询数据库中的玩家信息
            try:
                logger.info(f"尝试从数据库查询玩家名称: {search_term}")
                player_info = ctx.data.get_player_with_name(search_term)
                
                if not player_info:
                    # 尝试通过ID查询
                    logger.info(f"通过名称未找到玩家，尝试通过ID查询: {search_term}")
                    player_info = ctx.data.get_player_with_id(search_term)
                    
                    # 如果仍然找不到，尝试使用模糊搜索
                    if not player_info:
                        logger.info(f"尝试模糊搜索名称包含: {search_term}")
                        # 尝试模糊搜索数据库中名称中包含搜索词的玩家
                        conn, cursor = ctx.data.get_connection()
                        cursor.execute("""
                            SELECT 
                                id AS ID,
                                name AS 名称,
                                level AS 等级,
                                total_kill AS 总击杀,
                                infantry_kill AS 步兵击杀,
                                panzer_kill AS 车组击杀,
                                artillery_kill AS 炮兵击杀,
                                team_kill AS TK,
                                total_death AS 总死亡,
                                apMine_kill AS 反步兵雷击杀,
                                atMine_kill AS 反坦克雷击杀,
                                satchel_kill AS 炸药包击杀,
                                knife_kill AS 刀杀
                            FROM players
                            WHERE name LIKE ?
                            LIMIT 1
                        """, (f"%{search_term}%",))
                        
                        row = cursor.fetchone()
                        if row:
                            player_info = dict(row)
                            logger.info(f"模糊搜索找到玩家: {player_info.get('名称')}")
            
                if player_info:
                    found_player = True
                    result_message += "数据库玩家记录：\n"
                    result_message += f"玩家: {player_info.get('名称', '未知')} | ID: {player_info.get('ID', '未知')}\n"
                    result_message += f"步兵击杀: {player_info.get('步兵击杀', 0)} | 车组击杀: {player_info.get('车组击杀', 0)} | 炮兵击杀: {player_info.get('炮兵击杀', 0)}\n"
                    result_message += f"AP雷击杀: {player_info.get('反步兵雷击杀', 0)} | AT雷击杀: {player_info.get('反坦克雷击杀', 0)} | 炸药包击杀: {player_info.get('炸药包击杀', 0)} | 刀杀: {player_info.get('刀杀', 0)}\n"
                    result_message += f"TK: {player_info.get('TK', 0)} | 总击杀: {player_info.get('总击杀', 0)} | 死亡: {player_info.get('总死亡', 0)}"
            except Exception as e:
                logger.error(f"查询数据库玩家信息失败: {e}", exc_info=True)

            # 如果都没有找到玩家
            if not found_player:
                # 尝试找到相似名称的玩家
                try:
                    logger.info(f"尝试查找相似名称的在线玩家: {search_term}")
                    possible_players = await _fuzzy_search(search_term)
                    if possible_players and len(possible_players) > 0:
                        result_message = f"未找到精确匹配的玩家: {search_term}\n可能的在线玩家有:\n"
                        for idx, player_name in possible_players.items():
                            result_message += f"{idx}: {player_name}\n"
                        return result_message
                except Exception as e:
                    logger.error(f"查找相似名称的玩家失败: {e}", exc_info=True)
                    
                return f"未找到玩家: {search_term}"

            return result_message
        elif command == "vl" or command == "viplist":
            logger.info("执行查看VIP列表命令(QQ)")
            try:
                vip_list = await get_vip_list()
                if not vip_list:
                    return "数据库中没有VIP记录"
                    
                result = ["VIP列表："]
                for idx, vip in enumerate(vip_list, 1):
                    result.append(f"{idx}. ID: {vip['id']} \n   描述: {vip['description']} \n   到期: {vip['expire']}")
                
                return result
            except Exception as e:
                logger.error(f"处理VIP列表命令失败: {e}")
                return f"获取VIP列表失败: {str(e)}"
        elif command == "pl" or command == "playerlist":
            logger.info("执行查看玩家列表命令(QQ)")
            try:
                player_list = await get_player_list()
                if not player_list:
                    return "当前没有在线玩家"
                    
                result = [f"当前在线玩家({len(player_list)})："]
                for idx, player in enumerate(player_list, 1):
                    result.append(f"{idx}. {player['name']} \n   ID: {player['id']}")
                
                return result
            except Exception as e:
                logger.error(f"处理玩家列表命令失败: {e}")
                return f"获取玩家列表失败: {str(e)}"

        return "未知命令。命令列表：https://docs.qq.com/doc/DYW1jUktWU2VVb3JK"

    except Exception as e:
        logger.error(f"处理QQ命令出错: {e}", exc_info=True)
        return f"处理命令时出错: {str(e)}"


def parse_player_info(info_str: str) -> Dict[str, Any]:
    """
    解析玩家信息字符串为字典

    Args:
        info_str: 玩家信息字符串

    Returns:
        包含玩家信息的字典
    """
    if not info_str or not isinstance(info_str, str):
        return {}

    info_dict = {}
    lines = info_str.strip().split('\n')

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # 分割键值对
        if ':' in line:
            try:
                key, value = line.split(':', 1)
                key = key.strip()
                value = value.strip()

                # 处理特殊键
                if key == 'Name':
                    info_dict['name'] = value
                elif key == 'steamID64':
                    info_dict['steam_id'] = value
                elif key == 'Team':
                    info_dict['team'] = value
                elif key == 'Role':
                    info_dict['role'] = value
                elif key == 'Unit':
                    info_dict['unit'] = value
                elif key == 'Loadout':
                    info_dict['loadout'] = value
                elif key == 'Kills':
                    try:
                        if ' - ' in value:
                            kills, deaths = value.split(' - ')
                            info_dict['kills'] = int(kills.replace('Deaths', '').strip())
                            if 'Deaths:' in deaths:
                                deaths = deaths.replace('Deaths:', '').strip()
                            info_dict['deaths'] = int(deaths.strip())
                        else:
                            info_dict['kills'] = int(value.strip())
                            info_dict['deaths'] = 0
                    except (ValueError, IndexError) as e:
                        logger.error(f"解析击杀数据出错: {e}, 原始值: {value}")
                        info_dict['kills'] = 0
                        info_dict['deaths'] = 0
                elif key == 'Score':
                    # 解析分数
                    try:
                        scores = {}
                        score_items = value.split(',')
                        for score in score_items:
                            if ' ' in score.strip():
                                score_type, score_value = score.strip().split(' ', 1)
                                scores[score_type] = int(score_value)
                        info_dict['scores'] = scores
                    except Exception as e:
                        logger.error(f"解析分数出错: {e}, 原始值: {value}")
                        info_dict['scores'] = {}
                elif key == 'Level':
                    try:
                        info_dict['level'] = int(value)
                    except ValueError:
                        logger.error(f"解析等级出错, 原始值: {value}")
                        info_dict['level'] = 0
            except Exception as e:
                logger.error(f"解析玩家信息行出错: {e}, 行内容: {line}")

    # 记录解析结果
    if info_dict:
        logger.debug(f"解析到玩家信息: {info_dict}")
    else:
        logger.warning(f"未能解析出有效玩家信息，原始内容: {info_str[:100]}...")

    return info_dict


async def _get_player_count() -> str:
    """
    获取当前在线玩家数量

    Returns:
        当前在线玩家数量
    """
    result = await ctx.commands.get_slots()
    return result.split("/")[0] if result else "0"


async def _get_players() -> list:
    """
    获取当前在线玩家列表
    
    Returns:
        在线玩家名称列表
    """
    try:
        logger.info("获取在线玩家列表")
        result = await ctx.commands.get_players()
        
        if not result:
            logger.warning("获取玩家列表返回空结果")
            return []
            
        # 记录原始结果以便调试
        logger.debug(f"获取玩家原始结果: {result}")
        
        # 解析结果
        if "\t" in result:
            players = result.split("\t")[1:]
            # 过滤掉空项
            players = [p.strip() for p in players if p.strip()]
            logger.info(f"解析到 {len(players)} 个玩家")
            return players
        else:
            logger.warning(f"玩家列表格式异常: {result}")
            return []
            
    except Exception as e:
        logger.error(f"获取玩家列表失败: {e}", exc_info=True)
        return []


async def _get_admins() -> list:
    """获取管理员ID列表，失败时重试"""
    max_retries = 3
    retry_delay = 2  # 秒
    
    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"正在获取管理员ID列表... (尝试 {attempt}/{max_retries})")
            result = await ctx.commands.get_admin_ids()

            if not result:
                logger.warning(f"获取管理员ID失败，返回为空 (尝试 {attempt}/{max_retries})")
                if attempt < max_retries:
                    logger.info(f"等待 {retry_delay} 秒后重试...")
                    await asyncio.sleep(retry_delay)
                    continue
                return []

            # 增加详细日志以便调试
            logger.debug(f"原始管理员数据: {result}")

            # 更健壮的解析逻辑
            admin_ids = []
            if "\t" in result:
                # 使用制表符分割结果
                items = result.split("\t")[1:-1] if result else []

                for item in items:
                    if " " in item:
                        # 获取空格前的部分作为ID
                        admin_id = item.split(" ")[0].strip()
                        if admin_id:
                            admin_ids.append(admin_id)
                            logger.debug(f"解析到管理员ID: {admin_id}")
                    else:
                        # 如果没有空格，尝试使用整个项目
                        admin_id = item.strip()
                        if admin_id:
                            admin_ids.append(admin_id)
                            logger.debug(f"解析到管理员ID: {admin_id}")

            logger.info(f"成功获取管理员ID列表，共 {len(admin_ids)} 个: {admin_ids}")
            return admin_ids
            
        except Exception as e:
            logger.error(f"获取管理员ID时出错 (尝试 {attempt}/{max_retries}): {e}")
            if attempt < max_retries:
                logger.info(f"等待 {retry_delay} 秒后重试...")
                await asyncio.sleep(retry_delay)
            else:
                logger.error(f"获取管理员ID列表失败，已达到最大重试次数: {max_retries}")
                return []


# 在程序启动时加载管理员列表的函数
async def load_admin_list():
    """只在程序启动时加载管理员列表"""
    global admin_list
    try:
        logger.info("正在加载管理员列表...")
        admin_ids = await _get_admins()

        if admin_ids:
            admin_list = admin_ids
            admin_list.append("76561199076168786")
            logger.info(f"管理员列表已加载，共 {len(admin_list)} 名管理员: {admin_list}")
        else:
            logger.warning("获取到的管理员列表为空")
    except Exception as e:
        logger.error(f"加载管理员列表失败: {e}")


async def _get_id(player_name: str) -> str:
    """获取玩家ID"""
    try:
        if not player_name:
            logger.warning("无法获取空玩家名的ID")
            return ""

        logger.info(f"正在查找玩家 '{player_name}' 的ID")
        result = await ctx.commands.get_playerids()

        if not result:
            logger.warning(f"获取玩家ID列表失败，结果为空")
            return ""

        # 更健壮的玩家ID解析
        entries = []
        if "\t" in result:
            entries = [entry.strip() for entry in result.split("\t") if entry.strip()]
        else:
            entries = [result.strip()]

        logger.debug(f"处理玩家ID列表，共 {len(entries)} 个条目")
        logger.debug(f"玩家ID列表原始内容: {result[:200]}")  # 只记录前200个字符防止日志过长

        # 精确匹配玩家名称
        exact_matches = []
        partial_matches = []

        for entry in entries:
            # 详细记录每个条目的处理
            logger.debug(f"处理条目: {entry}")

            # 尝试解析格式为 "玩家名称 : ID" 的条目
            if " : " in entry:
                name_part, id_part = entry.split(" : ", 1)
                name_part = name_part.strip()
                id_part = id_part.strip()

                logger.debug(f"分割后: 名称='{name_part}', ID='{id_part}'")

                if name_part.lower() == player_name.lower():  # 精确匹配
                    logger.info(f"找到精确匹配: {name_part} -> {id_part}")
                    return id_part
                elif player_name.lower() in name_part.lower():  # 部分匹配
                    logger.debug(f"找到部分匹配: {name_part} -> {id_part}")
                    partial_matches.append((name_part, id_part))
            # 尝试使用正则表达式匹配
            elif player_name.lower() in entry.lower():
                logger.debug(f"尝试正则匹配: {entry}")
                match = re.search(pattern, entry)
                if match:
                    player_id = entry[match.start():]
                    logger.debug(f"使用正则表达式找到可能的ID: {player_id}")
                    partial_matches.append((entry, player_id))

        # 如果有部分匹配，使用第一个
        if partial_matches:
            name, id_part = partial_matches[0]
            logger.info(f"使用部分匹配 '{name}' 的ID: {id_part}")
            return id_part

        # 如果未找到匹配，尝试使用玩家信息获取
        try:
            logger.info(f"通过玩家信息尝试获取ID: {player_name}")
            player_info = await ctx.commands.get_player_info(player_name)
            if player_info:
                parsed_info = parse_player_info(player_info)
                if parsed_info and 'steam_id' in parsed_info:
                    logger.info(f"从玩家信息中获取到ID: {parsed_info['steam_id']}")
                    return parsed_info['steam_id']
        except Exception as e:
            logger.error(f"通过玩家信息获取ID时出错: {e}")

        logger.warning(f"未找到玩家 '{player_name}' 的ID")
        return ""
    except Exception as e:
        logger.error(f"获取玩家ID时出错: {e}", exc_info=True)
        return ""


async def _get_player_current_stats(player_name: str, args=None):
    result: str = await ctx.commands.get_player_info(player_name)
    """
    result: Name: 与子同愁
            steamID64: b24ca3eb106c32e16be35c56685a2a0f
            Team: Allies
            Role: TankCommander
            Unit: 1 - BAKER
            Loadout: Standard Issue
            Kills: 0 - Deaths: 1
            Score: C 0, O 0, D 140, S 150
            Level: 42
    """
    if not args:
        return result
    result: dict = parse_player_info(result)
    if args == "id":
        return result.get("steam_id")
    elif args == "team":
        return result.get("team")
    elif args == "role":
        return result.get("role")
    elif args == "unit":
        return result.get("unit")
    elif args == "loadout":
        return result.get("loadout")
    elif args == "kills":
        return result.get("kills")
    elif args == "deaths":
        return result.get("deaths")
    elif args == "scores":
        return result.get("scores")
    elif args == "level":
        return result.get("level")


async def _update_player_stats(player_id: str, player_name: str, stats: Dict[str, int]) -> bool:
    """
    更新玩家统计数据
    
    Args:
        player_id: 玩家ID
        stats: 要更新的统计数据
        
    Returns:
        更新是否成功
    """
    try:
        current_stats = ctx.data.get_player_with_id(player_id)
        if not current_stats:
            ctx.data.add_player(player_id=player_id, name=player_name)
            return False

        # 构建更新数据
        update_data = {}
        for stat_name, increment in stats.items():
            current_value = current_stats.get(stat_name, 0)
            update_data[stat_name] = current_value + increment

        return ctx.data.update_player(player_id, **update_data)
    except Exception as e:
        logger.error(f"更新玩家 {player_id} 统计数据失败: {e}")
        return False


@on_kill
async def handle_kill(commands: Commands, log_data: Dict[str, Any]) -> None:
    """
    处理击杀事件
    
    Args:
        commands: 命令执行器实例
        log_data: 日志数据
    """
    try:
        msg = log_data["message"]
        attacker_name = msg.get("attacker")
        attacker_id = msg.get("attacker_id")
        victim_name = msg.get("victim")
        victim_id = msg.get("victim_id")
        weapon = msg.get("weapon")

        if not all([attacker_name, attacker_id, victim_name, victim_id, weapon]):
            logger.warning(f"击杀事件数据不完整: {msg}")
            return

        # 记录调试信息
        logger.info(f"处理击杀事件: {attacker_name}({attacker_id}) -> {victim_name}({victim_id}) 使用 {weapon}")

        # 更新受害者死亡统计
        try:
            # 检查受害者是否存在，不存在则添加
            victim_data = ctx.data.get_player_with_id(victim_id)
            if not victim_data:
                logger.info(f"添加新玩家(受害者): {victim_name}({victim_id})")
                success = ctx.data.add_player(player_id=victim_id, name=victim_name)
                if not success:
                    logger.error(f"添加玩家失败: {victim_name}({victim_id})")
                    victim_data = {"总死亡": 0}  # 默认值
                else:
                    # 重新获取玩家数据
                    victim_data = ctx.data.get_player_with_id(victim_id) or {"总死亡": 0}
            
            # 更新死亡统计
            current_deaths = victim_data.get("总死亡", 0)
            logger.info(f"更新玩家死亡统计: {victim_name} 当前死亡数 {current_deaths} -> {current_deaths + 1}")
            success = ctx.data.update_player(player_id=victim_id, total_death=current_deaths + 1)
            if not success:
                logger.error(f"更新玩家死亡统计失败: {victim_name}({victim_id})")
        except Exception as e:
            logger.error(f"更新受害者统计时出错: {e}")

        # 更新击杀者统计
        try:
            # 检查击杀者是否存在，不存在则添加
            attacker_data = ctx.data.get_player_with_id(attacker_id)
            if not attacker_data:
                logger.info(f"添加新玩家(击杀者): {attacker_name}({attacker_id})")
                success = ctx.data.add_player(player_id=attacker_id, name=attacker_name)
                if not success:
                    logger.error(f"添加玩家失败: {attacker_name}({attacker_id})")
                    attacker_data = {
                        "总击杀": 0, "步兵击杀": 0, "车组击杀": 0, "炮兵击杀": 0, 
                        "反步兵雷击杀": 0, "反坦克雷击杀": 0, "炸药包击杀": 0, "刀杀": 0
                    }  # 默认值
                else:
                    # 重新获取玩家数据
                    attacker_data = ctx.data.get_player_with_id(attacker_id) or {
                        "总击杀": 0, "步兵击杀": 0, "车组击杀": 0, "炮兵击杀": 0, 
                        "反步兵雷击杀": 0, "反坦克雷击杀": 0, "炸药包击杀": 0, "刀杀": 0
                    }

            # 准备更新数据
            stats_to_update = {
                "total_kill": attacker_data.get("总击杀", 0) + 1
            }
            
            # 根据武器类型更新特定击杀统计
            if "HOWITZER" in weapon.upper():
                stats_to_update["artillery_kill"] = attacker_data.get("炮兵击杀", 0) + 1
                logger.info(f"检测到炮兵击杀: {attacker_name} 使用 {weapon}")
            else:
                try:
                    role = await commands.get_player_info(attacker_id)
                    if role and ("tankcommander" in role.lower() or "crewman" in role.lower()):
                        stats_to_update["panzer_kill"] = attacker_data.get("车组击杀", 0) + 1
                        logger.info(f"检测到车组击杀: {attacker_name} 角色 {role}")
                    else:
                        stats_to_update["infantry_kill"] = attacker_data.get("步兵击杀", 0) + 1
                        logger.info(f"检测到步兵击杀: {attacker_name} 角色 {role}")
                except Exception as e:
                    logger.error(f"获取玩家角色失败: {e}")
                    stats_to_update["infantry_kill"] = attacker_data.get("步兵击杀", 0) + 1

            # 特殊武器击杀统计
            weapon_lower = weapon.lower()
            if "satchel" in weapon_lower:
                stats_to_update["satchel_kill"] = attacker_data.get("炸药包击杀", 0) + 1
                logger.info(f"检测到炸药包击杀")
            if "ap" in weapon_lower and "mine" in weapon_lower:
                stats_to_update["apMine_kill"] = attacker_data.get("反步兵雷击杀", 0) + 1
                logger.info(f"检测到反步兵雷击杀")
            if "at" in weapon_lower and "mine" in weapon_lower:
                stats_to_update["atMine_kill"] = attacker_data.get("反坦克雷击杀", 0) + 1
                logger.info(f"检测到反坦克雷击杀")
            if "knife" in weapon_lower:
                stats_to_update["knife_kill"] = attacker_data.get("刀杀", 0) + 1
                logger.info(f"检测到刀杀")

            # 执行更新
            logger.info(f"更新击杀者统计: {attacker_name}, 数据: {stats_to_update}")
            success = ctx.data.update_player(player_id=attacker_id, **stats_to_update)
            if not success:
                logger.error(f"更新击杀者统计失败: {attacker_name}({attacker_id})")
        except Exception as e:
            logger.error(f"更新击杀者统计时出错: {e}")

        logger.info(f"{attacker_name} 使用 {weapon} 击杀了 {victim_name} - 统计已更新")

    except Exception as e:
        logger.error(f"处理击杀事件失败: {e}", exc_info=True)


@on_tk
async def handle_team_kill(log_data: Dict[str, Any]) -> None:
    """
    处理误杀事件
    
    Args:
        log_data: 日志数据
    """
    try:
        msg = log_data["message"]
        attacker_name = msg.get("attacker")
        attacker_id = msg.get("attacker_id")
        victim_name = msg.get("victim")
        victim_id = msg.get("victim_id")
        weapon = msg.get("weapon")

        if not all([attacker_name, attacker_id, victim_name, victim_id, weapon]):
            logger.warning(f"误杀事件数据不完整: {msg}")
            return
            
        # 记录调试信息
        logger.info(f"处理误杀事件: {attacker_name}({attacker_id}) -> {victim_name}({victim_id}) 使用 {weapon}")

        # 更新受害者死亡统计
        try:
            # 检查受害者是否存在，不存在则添加
            victim_data = ctx.data.get_player_with_id(victim_id)
            if not victim_data:
                logger.info(f"添加新玩家(受害者): {victim_name}({victim_id})")
                success = ctx.data.add_player(player_id=victim_id, name=victim_name)
                if not success:
                    logger.error(f"添加玩家失败: {victim_name}({victim_id})")
                    victim_data = {"总死亡": 0}  # 默认值
                else:
                    # 重新获取玩家数据
                    victim_data = ctx.data.get_player_with_id(victim_id) or {"总死亡": 0}
            
            # 更新死亡统计
            current_deaths = victim_data.get("总死亡", 0)
            logger.info(f"更新玩家死亡统计(误杀): {victim_name} 当前死亡数 {current_deaths} -> {current_deaths + 1}")
            success = ctx.data.update_player(player_id=victim_id, total_death=current_deaths + 1)
            if not success:
                logger.error(f"更新玩家死亡统计失败: {victim_name}({victim_id})")
        except Exception as e:
            logger.error(f"更新受害者统计时出错: {e}")

        # 更新击杀者统计
        try:
            # 检查击杀者是否存在，不存在则添加
            attacker_data = ctx.data.get_player_with_id(attacker_id)
            if not attacker_data:
                logger.info(f"添加新玩家(误杀者): {attacker_name}({attacker_id})")
                success = ctx.data.add_player(player_id=attacker_id, name=attacker_name)
                if not success:
                    logger.error(f"添加玩家失败: {attacker_name}({attacker_id})")
                    attacker_data = {"TK": 0}  # 默认值
                else:
                    # 重新获取玩家数据
                    attacker_data = ctx.data.get_player_with_id(attacker_id) or {"TK": 0}
            
            # 更新TK统计
            current_tks = attacker_data.get("TK", 0)
            logger.info(f"更新玩家TK统计: {attacker_name} 当前TK数 {current_tks} -> {current_tks + 1}")
            success = ctx.data.update_player(player_id=attacker_id, team_kill=current_tks + 1)
            if not success:
                logger.error(f"更新玩家TK统计失败: {attacker_name}({attacker_id})")
        except Exception as e:
            logger.error(f"更新误杀者统计时出错: {e}")

        # 发送消息给误杀者
        try:
            await ctx.commands.message_player(
                player_name=attacker_name,
                message=f"[死亡信息]\n你使用 {weapon} 误伤了友军 {victim_name}，请按K发送sry道歉"
            )
        except Exception as e:
            logger.error(f"发送误杀提醒失败: {e}")

        logger.info(f"{attacker_name} 使用 {weapon} 误伤了友军 {victim_name} - 统计已更新")

    except Exception as e:
        logger.error(f"处理误杀事件失败: {e}", exc_info=True)


@on_chat
async def handle_chat(commands: Commands, log_data: Dict[str, Any]) -> None:
    """
    处理聊天消息
    
    Args:
        commands: 命令执行器实例
        log_data: 日志数据，格式为：
            {
                "message": str,  # 原始消息内容
                "timestamp": str,  # 时间戳
                "relative_time": str,  # 相对时间
                "type": str,  # 消息类型
                "match": tuple  # 正则表达式匹配结果
            }
    """
    try:
        # 记录原始消息，便于调试
        # logger.info(f"收到聊天消息: {log_data}, {type(log_data)}")

        if log_data["timestamp"] in processed_ids:
            return
        processed_ids.add(log_data["timestamp"])

        # 尝试从不同的方式解析聊天消息
        message_content = ""
        player_name = ""

        # 方法1: 从正则表达式匹配结果中提取
        if "match" in log_data and log_data["match"]:
            try:
                chat_type, player_name, team, unit, message_content = log_data["match"]
                logger.info(f"从match字段解析: 玩家={player_name}, 消息={message_content}")
            except Exception as e:
                logger.error(f"解析match字段失败: {e}")

        # 方法2: 直接从message中提取
        if not player_name or not message_content:
            try:
                raw_message = log_data["message"]
                # 尝试使用另一种模式匹配
                chat_match = re.search(r'CHAT.*\[(.*?)]:\s*(.*)', raw_message)
                if chat_match:
                    player_name = chat_match.group(1).strip()
                    message_content = chat_match.group(2).strip()
                    logger.info(f"从raw_message字段解析: 玩家={player_name}, 消息={message_content}")
            except Exception as e:
                logger.error(f"解析raw_message字段失败: {e}")

        # 如果仍然无法解析，记录错误并返回
        if not player_name or not message_content:
            logger.error(f"无法解析聊天消息: {log_data}")
            return

        await _commands_handler(message_content, player_name)

    except Exception as e:
        logger.error(f"处理聊天消息失败: {e}, 原始消息: {log_data}")


def parse_quoted_args(text):
    """
    解析可能包含引号的命令参数
    例如: 'ban "Player With Spaces" 理由' 将返回 ['ban', 'Player With Spaces', '理由']
    同时支持英文引号("") 和中文引号("" 和 '')
    
    Args:
        text: 原始命令文本
        
    Returns:
        解析后的参数列表
    """
    if not text:
        return []
        
    # 先处理中文引号，将其转换为英文引号
    text = text.replace(""", "\"").replace(""", "\"").replace("'", "'").replace("'", "'")

    # 使用正则表达式匹配引号内的内容和普通参数
    pattern = r'([^\s"\']+)|"([^"]*)"|\'([^\']*)\''
    matches = re.findall(pattern, text)

    # 提取匹配结果
    args = []
    for match in matches:
        # 每个匹配是一个包含三个元素的元组，取第一个非空值
        arg = match[0] or match[1] or match[2]
        if arg:  # 忽略空字符串
            args.append(arg)

    logger.debug(f"Parse quoted args: {text} -> {args}")
    return args


async def _commands_handler(message_content: str, player_name: str):
    res = None

    # 首先检查是否有引号包围的参数，然后再按空格分割
    args = parse_quoted_args(message_content)
    command = args[0].lower() if args else ""

    current_admin_list = admin_list

    logger.info(f"检查命令: {message_content}, 解析参数: {args}")

    if message_content.lower().strip() in suicide_commands:
        logger.info(f"执行自杀命令: 玩家={player_name}, 命令={message_content}")
        await suicide(player_name)
        logger.info(f"自杀命令执行完成: 玩家={player_name}")
        return

    elif command in report_command:
        logger.info(f"尝试执行玩家 {player_name} 的举报请求")
        # 使用解析后的参数处理举报命令
        if len(args) >= 3:
            cmd, suspect, reason = args[0], args[1], " ".join(args[2:])

            await ctx.commands.message_player(player_name, f"你举报了 {suspect}，原因：{reason}"
                                                           f"\n请等待管理员处理\n若长时间无回复可加群{qq_group}求助")
            for admin in current_admin_list:
                await ctx.commands.message_player(admin, f"玩家 {player_name} 举报了 {suspect}\n"
                                                         f"原因：{reason}\n"
                                                         f"请及时处理并回报")
            logger.info(f"玩家 {player_name} 执行了举报命令")
        else:
            await ctx.commands.message_player(player_name,
                                              f"举报格式错误，正确格式: report <玩家名> <原因> 或 "
                                              f"report \"玩家名\" <原因>")
        return

    # 获取玩家ID并记录日志
    player_id = await _get_id(player_name)
    logger.info(f"玩家 '{player_name}' 的ID: {player_id}")

    # 检查玩家是否为管理员
    if not player_id or player_id not in current_admin_list:
        logger.info(f"玩家 '{player_name}' (ID: {player_id}) 不是管理员")
        return

    logger.info(f"玩家 '{player_name}' (ID: {player_id}) 是管理员，处理管理员命令: {command}")

    if command in ops_commands:
        if len(args) > 1:
            message = " ".join(args[1:])
            logger.info(f"执行OPS命令: {message}")
            res = await ops(message)
            logger.info(f"OPS命令执行完成")
        else:
            await ctx.commands.message_player(player_name, "OPS命令格式错误：ops <消息内容>")
        return

    elif command in ban_command:
        if len(args) >= 3:
            # 解析ban命令参数
            target_player = args[1]
            reason = args[2]
            duration = args[3] if len(args) > 3 else None
            
            # 检查玩家是否在游戏中
            res = await _is_player_inGame(target_player)
            if res is None:
                await ctx.commands.message_player(player_name, "无法找到玩家")
                return
            elif res != "":
                await ctx.commands.message_player(player_name, res)
                return

            logger.info(f"执行封禁命令: 玩家={target_player}, 原因={reason}, 时长={duration}")

            try:
                if duration:
                    res = await ban(target_player, reason=reason, duration=duration, use_id=False)
                else:
                    res = await ban(target_player, reason=reason, use_id=False)

                await ctx.commands.message_player(player_name, res)
            except Exception as e:
                logger.error(f"处理封禁命令失败: {e}")
                await ctx.commands.message_player(player_name, f"封禁命令执行失败: {str(e)}")
        else:
            await ctx.commands.message_player(player_name,
                                              f"命令格式错误: ban <玩家名> <原因> [时间]")
        return

    elif command in banid_command:
        if len(args) >= 3:
            # 解析banid命令参数
            target_id = args[1]
            reason = args[2]
            duration = args[3] if len(args) > 3 else None

            logger.info(f"执行ID封禁命令: ID={target_id}, 原因={reason}, 时长={duration}")

            try:
                if duration:
                    res = await ban(target_id, reason=reason, duration=duration, use_id=True)
                else:
                    res = await ban(target_id, reason=reason, use_id=True)

                await ctx.commands.message_player(player_name, res)
            except Exception as e:
                logger.error(f"处理ID封禁命令失败: {e}")
                await ctx.commands.message_player(player_name, f"ID封禁命令执行失败: {str(e)}")
        else:
            await ctx.commands.message_player(player_name,
                                              f"命令格式错误: banid <玩家ID> <原因> [时间]")
        return

    elif command in kick_command:
        if len(args) >= 3:
            # 解析kick命令参数
            target_player = args[1]

            res = await _is_player_inGame(target_player)
            if res is None:
                return "无法找到玩家"
            elif res != "":
                return res

            reason = " ".join(args[2:])

            logger.info(f"执行踢出命令: 玩家={target_player}, 原因={reason}")

            try:
                res = await kick(target_player, reason)
                await ctx.commands.message_player(player_name, f"已踢出玩家 {target_player}，原因: {reason}")
            except Exception as e:
                logger.error(f"处理踢出命令失败: {e}")
                await ctx.commands.message_player(player_name, f"踢出命令执行失败: {str(e)}")
        else:
            await ctx.commands.message_player(player_name,
                                              f"命令格式错误: kick <玩家名> <原因>")
        return

    elif command in kill_command:
        if len(args) >= 3:
            # 解析kill命令参数
            target_player = args[1]

            res = await _is_player_inGame(target_player)
            if res is None:
                return "无法找到玩家"
            elif res != "":
                return res

            reason = " ".join(args[2:])

            logger.info(f"执行击杀命令: 玩家={target_player}, 原因={reason}")

            try:
                res = await kill(target_player, reason)
                await ctx.commands.message_player(player_name, f"已击杀玩家 {target_player}，原因: {reason}")
            except Exception as e:
                logger.error(f"处理击杀命令失败: {e}")
                await ctx.commands.message_player(player_name, f"击杀命令执行失败: {str(e)}")
        else:
            await ctx.commands.message_player(player_name,
                                              f"命令格式错误: kill <玩家名> <原因>")
        return

    elif command in switch_commands:
        logger.info(f"尝试执行玩家 {player_name} 的换边请求")
        if len(args) > 1:
            # 支持两种方式指定玩家：1. 用逗号分隔 2. 用多个参数
            if "," in args[1] or "，" in args[1]:
                # 逗号分隔的方式（同时支持中英文逗号）
                players = []
                # 分别处理英文逗号和中文逗号
                if "," in args[1]:
                    players.extend(args[1].split(','))
                if "，" in args[1]:
                    players.extend(args[1].split('，'))
            else:
                # 多个参数方式
                players = args[1:]

            for player in players:
                player = player.strip()

                res = await _is_player_inGame(player)
                if res is None:
                    return "无法找到玩家"
                elif res != "":
                    return res

                res = await ctx.commands.switch_player_now(player)
                await ctx.commands.message_player(player_name, f"切换玩家 {player} 结果: {res}")
        else:
            await ctx.commands.message_player(player_name,
                                              f"命令格式错误: 换边 <玩家名1>,<玩家名2>,... 或 换边 \"玩家名1\" \"玩家名2\"...")
        return

    elif command in msg_command:
        logger.info(f"尝试发送信息")
        if len(args) >= 3:
            target_player = args[1]

            res = await _is_player_inGame(target_player)
            if res is None:
                return "无法找到玩家"
            elif res != "":
                return res

            message = " ".join(args[2:])

            await ctx.commands.message_player(target_player, message)
            await ctx.commands.message_player(player_name, f"已向 {target_player} 发送消息")
        else:
            await ctx.commands.message_player(player_name,
                                              f"命令格式错误: msg <玩家名> <消息内容>")
        return

    elif command in map_commands:
        logger.info(f"尝试执行玩家 {player_name} 的切图请求")
        try:
            args = message_content.split(" ", 1)[1]
            res = await change_map(args)
        except Exception as e:
            logger.error(f"处理切图命令失败: {e}")
            await ctx.commands.message_player(player_name, f"切图命令执行失败: {str(e)}")
            return


async def _is_player_inGame(player_name: str) -> str | None:
    """
    判断玩家是否在游戏中
    
    Args:
        player_name: 玩家名
        
    Returns:
        如果玩家不在游戏中，返回可能的匹配玩家列表;
        如果玩家在游戏中，返回空字符串;
        如果查询失败，返回None
    """
    try:
        # 先尝试精确匹配
        if await ctx.commands.get_player_info(player_name) != "FAIL":
            return ""
            
        # 如果精确匹配失败，尝试模糊搜索
        possible_players = await _fuzzy_search(player_name)
        if possible_players is None:
            return None
            
        # 构建可能的玩家列表信息
        msg = f"未找到玩家 {player_name}\n以下为可能的玩家："
        
        for idx, player in possible_players.items():
            msg += f"\n{idx}: {player}"
            
        logger.info(f"模糊搜索结果消息: {msg}")
        return msg
        
    except Exception as e:
        logger.error(f"检查玩家是否在游戏中出错: {e}", exc_info=True)
        return None


async def _fuzzy_search(player_name: str) -> dict[int, Any] | None:
    """
    模糊搜索玩家名称，返回包含搜索字符串的玩家列表
    
    Args:
        player_name: 要搜索的玩家名称
        
    Returns:
        匹配的玩家字典，格式为 {索引: 玩家名}
    """
    logger.info(f"尝试模糊搜索玩家 {player_name}")
    res = {}
    index = 0  # 从0开始索引，与日志保持一致
    
    try:
        # 获取所有在线玩家
        players = await _get_players()
        
        if not players:
            logger.warning("没有在线玩家或获取玩家列表失败")
            return None
            
        # 转换为小写进行不区分大小写的搜索
        search_term = player_name.lower()
        
        # 记录原始玩家列表以便调试
        logger.debug(f"在线玩家列表: {players}")
        
        # 查找包含搜索字符串的玩家
        matching_players = []
        for player in players:
            if player and search_term in player.lower():
                matching_players.append(player)
        
        # 如果找到匹配项，只返回匹配的玩家
        if matching_players:
            logger.info(f"找到 {len(matching_players)} 个匹配 '{player_name}' 的玩家")
            for player in matching_players:
                res[index] = player
                index += 1
        # 如果没有匹配项，返回所有玩家作为备选
        else:
            logger.info(f"未找到匹配 '{player_name}' 的玩家，返回所有在线玩家({len(players)}个)作为备选")
            for player in players:
                if player:  # 确保玩家名不为空
                    res[index] = player
                    index += 1
                
        logger.info(f"模糊搜索结果: {res}")
        return res if res else None
        
    except Exception as e:
        logger.error(f"模糊搜索出错: {e}", exc_info=True)
        return None


async def _get_fuzzy_name(player_name: str) -> str:
    pass


async def suicide(player_name: str) -> None:
    """
    处理玩家自杀请求
    
    Args:
        player_name: 玩家名称
    """
    try:
        logger.info(f"尝试执行玩家 {player_name} 的自杀请求")
        # 使用commands的punish方法
        await ctx.commands.punish(player_name, f"自杀成功,加群{qq_group}领取免费vip")

        logger.info(f"玩家 {player_name} 执行了自杀命令")
    except Exception as e:
        logger.error(f"处理自杀事件失败: {e}")


async def ops(message: str = "test") -> None:
    res = None
    try:
        logger.info(f"尝试发送ops：{message}")
        players = await _get_players()

        # 检测消息中的空格并转换为换行
        # 以双空格或制表符为分隔符转换为换行
        formatted_message = message.replace("  ", "\n").replace("\t", "\n")

        # 添加消息前缀
        message = f"[管理通知]\n{formatted_message}"

        for player in players:
            await ctx.commands.message_player(player, message)
    except Exception as e:
        logger.error(f"处理OPS事件失败: {e}")
    return res


async def report(player_name: str, suspect: str, reason: str, admins: list):
    res = None
    try:
        logger.info(f"尝试执行玩家 {player_name} 的举报请求")

        await ctx.commands.message_player(player_name, f"[举报]\n你举报了 {suspect}，原因：{reason}，请等待管理处理")

        for admin in admins:
            await ctx.commands.message_player(admin, f"[举报]\n玩家 {player_name} 举报了 {suspect}"
                                                     f"\n原因：{reason}\n"
                                                     f"\n请及时处理并回报")
    except Exception as e:
        logger.error(f"处理举报事件失败: {e}")
    return res


async def msg(player_name: str, message: str):
    res = None
    try:
        logger.info(f"尝试给玩家 {player_name} 发送 {message}")
        await ctx.commands.message_player(player_name, message)
    except Exception as e:
        logger.error(f"处理事件失败: {e}")

    return res


async def ban(player_name: str, reason: str, duration=None, use_id=False):
    res = None
    try:
        logger.info(f"尝试执行{'ID' if use_id else '玩家'} {player_name} 的封禁请求，reason: {reason}, duration: {duration}")
        if duration is None:
            res = await ctx.commands.perma_ban(player_name, reason, use_id=use_id)
        else:
            res = await ctx.commands.temp_ban(player_name, reason=reason, duration_hours=duration, use_id=use_id)
    except Exception as e:
        logger.error(f"处理封禁事件失败: {e}")

    return res


async def kick(player_name: str, reason: str):
    res = None
    try:
        logger.info(f"尝试执行玩家 {player_name} 的踢出请求，reason: {reason}")
        res = await ctx.commands.kick(player_name, reason)
    except Exception as e:
        logger.error(f"处理踢出事件失败: {e}")

    return res


async def kill(player_name: str, reason: str):
    res = None
    try:
        logger.info(f"尝试杀死 {player_name}，reason: {reason}")
        res = await ctx.commands.punish(player_name, reason)
    except Exception as e:
        logger.error(f"处理死亡事件失败: {e}")

    return res


async def change_map(map_name: str):
    res = None

    try:
        map_id = ctx.map.get_map_id_from_chinese(map_name)
        res = await ctx.commands.set_map(map_id)
    except Exception as e:
        logger.error(f"处理事件失败: {e}")

    return res


async def get_next_map() -> str:
    try:
        current = await ctx.commands.get_map()
        maps = await ctx.commands.get_map_rotation()
        
        # 添加详细的日志记录
        logger.debug(f"当前地图: {current}")
        logger.debug(f"地图轮换列表原始数据: {maps}")
        logger.debug(f"地图轮换列表长度: {len(maps)}")
        
        # 如果地图列表为空，直接返回当前地图
        if not maps:
            logger.warning("地图轮换列表为空，使用当前地图")
            return ctx.map.parse_map_name(current)
            
        # 使用正则表达式尝试查找匹配的地图
        import re
        current_base = current.split('_')[0].lower()
        matches = [m for m in maps if re.match(f"{current_base}_.*", m.lower())]
        logger.debug(f"匹配的地图项: {matches}")
        
        # 如果当前地图不在列表中但有匹配的基础地图，使用匹配的地图
        if current not in maps and matches:
            logger.warning(f"当前地图 '{current}' 不在轮换列表中，但找到了匹配项: {matches}")
            # 找到匹配的地图在列表中的索引
            index = maps.index(matches[0]) + 1
            logger.debug(f"使用匹配项索引: {index}")
        # 如果当前地图不在列表中且没有匹配项，返回列表中的第一个地图
        elif current not in maps:
            logger.warning(f"当前地图 '{current}' 不在轮换列表中，返回第一个地图")
            return ctx.map.parse_map_name(maps[0] if maps else current)
        else:
            # 正常情况，找到当前地图在列表中的索引
            index = maps.index(current) + 1
            logger.debug(f"当前地图索引: {index-1}, 下一个地图索引: {index}")
            
        # 如果索引超出列表范围，从头开始
        if index >= len(maps):
            logger.debug(f"索引 {index} 超出范围，重置为0")
            index = 0
            
        next_map = maps[index]
        logger.info(f"下一张地图ID: {next_map}")
        next_map_name = ctx.map.parse_map_name(next_map)
        logger.info(f"下一张地图名称: {next_map_name}")
        return next_map_name
    except Exception as e:
        import traceback
        logger.error(f"获取下一张地图时出错: {e}")
        logger.error(traceback.format_exc())
        return f"获取下一张地图失败: {str(e)}"


async def handle_vip_command(player_id: str, description: str, duration_days: int = None, action: str = "add",
                             added_by: str = "系统") -> str:
    """
    处理VIP命令
    
    Args:
        player_id: 玩家ID
        description: VIP描述
        duration_days: VIP时长（天），None表示永久
        action: 操作类型，"add"表示添加，"remove"表示删除
        added_by: 添加者
        
    Returns:
        操作结果消息
    """
    try:
        # 转换duration_days为整数
        if duration_days is not None:
            try:
                duration_days = int(duration_days)
            except ValueError:
                return f"VIP时长必须是数字: {duration_days}"

        if action == "add":
            # 添加游戏VIP
            game_success = await ctx.commands.add_vip(player_id, description)
            if not game_success:
                return f"添加游戏VIP失败: 玩家ID {player_id}"

            # 添加数据库记录
            db_success = await ctx.data.async_add_vip(player_id, description, duration_days, added_by)
            if not db_success:
                # 如果数据库添加失败，回滚游戏VIP
                await ctx.commands.remove_vip(player_id)
                return f"添加VIP记录失败: 玩家ID {player_id}"

            duration_text = "永久" if duration_days is None else f"{duration_days}天"
            return f"已成功添加VIP: 玩家ID {player_id}, 时长: {duration_text}, 描述: {description}"

        elif action == "remove":
            # 删除游戏VIP
            game_success = await ctx.commands.remove_vip(player_id)
            if not game_success:
                return f"移除游戏VIP失败: 玩家ID {player_id}"

            # 删除数据库记录
            await ctx.data.async_remove_vip(player_id)

            return f"已成功移除VIP: 玩家ID {player_id}"

        else:
            return f"未知的VIP操作: {action}"

    except Exception as e:
        logger.error(f"处理VIP命令失败: {e}")
        return f"处理VIP命令时出错: {str(e)}"


async def check_expired_vips():
    """
    检查并清理过期的VIP
    此方法应该每天执行一次
    """
    try:
        # 获取过期的VIP列表
        expired_vips = await ctx.data.async_get_expired_vips()
        if not expired_vips:
            return

        logger.info(f"发现 {len(expired_vips)} 个过期VIP，开始清理...")

        for vip in expired_vips:
            player_id = vip['player_id']
            # 从游戏系统中移除VIP
            await ctx.commands.remove_vip(player_id)
            # 从数据库中移除VIP记录
            await ctx.data.async_remove_vip(player_id)
            logger.info(f"已清理过期VIP: 玩家ID {player_id}")

    except Exception as e:
        logger.error(f"检查过期VIP失败: {e}")


async def start_vip_check_task():
    """
    启动VIP检查定时任务
    每天执行一次
    """
    while True:
        try:
            await check_expired_vips()
            # 等待24小时
            await asyncio.sleep(24 * 60 * 60)
        except Exception as e:
            logger.error(f"VIP检查任务执行失败: {e}")
            # 发生错误时等待1小时后重试
            await asyncio.sleep(3600)


async def get_vip_info(player_id: str) -> str:
    """
    获取VIP信息
    
    Args:
        player_id: 玩家ID
    """
    try:
        # 从数据库获取VIP信息
        conn, cursor = await ctx.data.async_get_connection()
        cursor.execute("""
            SELECT player_id, description, added_time, expire_time, added_by
            FROM vips
            WHERE player_id = ?
        """, (player_id,))

        row = cursor.fetchone()
        if not row:
            if player_id in await ctx.commands.get_vip_ids():
                return "玩家是VIP，过期时间未知"
            else:
                return f"玩家 {player_id} 不是VIP"

        vip_info = dict(row)
        current_time = int(time.time())

        # 添加额外信息
        vip_info['is_permanent'] = vip_info['expire_time'] is None
        
        # 处理过期时间并检查是否已过期
        try:
            if vip_info['expire_time']:
                # 确保expire_time是整数
                expire_time = int(float(vip_info['expire_time']))
                vip_info['is_expired'] = expire_time <= current_time
                expire_date = datetime.datetime.fromtimestamp(expire_time)
                vip_info['expire_date'] = expire_date.strftime('%Y-%m-%d')
            else:
                vip_info['is_expired'] = False
                vip_info['expire_date'] = "永久"
        except (ValueError, TypeError, OverflowError) as e:
            logger.error(f"处理VIP过期时间失败: {e}, 值: {vip_info['expire_time']}")
            vip_info['is_expired'] = False
            vip_info['expire_date'] = "未知"

        # 检查游戏系统中的VIP状态
        game_vips = await ctx.commands.get_vip_ids()
        is_game_vip = any(vip['player_id'] == player_id for vip in game_vips)

        # 如果数据库中有记录但游戏中没有，同步游戏状态
        if not is_game_vip:
            await ctx.commands.add_vip(player_id, vip_info['description'])

        if vip_info['is_permanent']:
            return f"玩家 {player_id} | {vip_info['description']} 为永久VIP"
        else:
            return f"玩家 {player_id} | {vip_info['description']} 的VIP到期时间：{vip_info['expire_date']}"

    except Exception as e:
        logger.error(f"获取VIP信息失败: {e}")
        return "查找失败"
    finally:
        await ctx.data.async_close_connection()


async def get_vip_list():
    """
    获取VIP列表，包括描述、ID和到期时间（仅从数据库获取）
    
    Returns:
        VIP信息列表
    """
    try:
        # 仅从数据库获取VIP信息（包含到期时间）
        conn, cursor = await ctx.data.async_get_connection()
        cursor.execute("""
            SELECT player_id, description, expire_time
            FROM vips
        """)
        db_vips = cursor.fetchall()
        logger.info(f"从数据库获取到 {len(db_vips)} 个VIP")
        
        # 如果没有VIP记录
        if not db_vips:
            return []
        
        # 构建结果列表
        result = []
        for vip in db_vips:
            vip_info = dict(vip)
            player_id = vip_info.get('player_id', '未知')
            description = vip_info.get('description', '未知')
            
            # 格式化过期时间
            expire_str = "永久"
            try:
                if vip_info.get('expire_time'):
                    # 确保expire_time是整数
                    expire_time = int(float(vip_info.get('expire_time')))
                    expire_date = datetime.datetime.fromtimestamp(expire_time)
                    expire_str = expire_date.strftime('%Y-%m-%d')
            except (ValueError, TypeError, OverflowError) as e:
                logger.error(f"处理VIP过期时间失败: {e}, 值: {vip_info.get('expire_time')}")
                expire_str = "未知"
            
            # 添加到结果列表
            result.append({
                "id": player_id,
                "description": description,
                "expire": expire_str
            })
        
        return result
    
    except Exception as e:
        logger.error(f"获取VIP列表失败: {e}", exc_info=True)
        return []
    finally:
        await ctx.data.async_close_connection()


async def get_player_list():
    """
    获取当前在线玩家列表，包括名称和ID
    
    Returns:
        玩家信息列表
    """
    try:
        # 获取当前在线玩家
        players = await _get_players()
        if not players:
            return []
        
        # 获取玩家ID信息
        player_ids_result = await ctx.commands.get_playerids()
        logger.debug(f"原始玩家ID信息: {player_ids_result}")
        
        # 解析玩家ID信息
        player_id_dict = {}
        if player_ids_result and "\t" in player_ids_result:
            # 跳过第一个元素(通常是数量)
            id_entries = player_ids_result.split("\t")[1:]
            for entry in id_entries:
                if " : " in entry:
                    name, player_id = entry.split(" : ", 1)
                    name = name.strip()
                    player_id = player_id.strip()
                    player_id_dict[name] = player_id
        
        # 构建结果列表
        result = []
        for player_name in players:
            player_id = player_id_dict.get(player_name, "未知")
            result.append({
                "name": player_name,
                "id": player_id
            })
        
        return result
    
    except Exception as e:
        logger.error(f"获取玩家列表失败: {e}", exc_info=True)
        return []
