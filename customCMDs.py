import re
from typing import Dict, Any

import Log
from MapList import MapList
from commands import Commands
from connection import HLLConnectionPool
from dataStorage import DataStorage
from hooks import on_kill, on_tk, on_chat

# 设置日志
logger = Log.log()

processed_ids = set()

pattern = r'[a-zA-Z0-9]'

qq_commands = {"status": "查服", "ban": "封禁", "kick": "踢出", "switch": "换边", "msg": "msg", "vip": "v",
               "unban": "解封", "search": "查询", "admin-list": "管理员", "add-admin": "aa", "remove-admin": "ra"}

suicide_commands = ["r", "rrrr"]
ops_commands = ["ops"]
switch_commands = ["换边"]
ban_command = ["ban", "封禁"]
msg_command = ["msg"]
report_command = ["report", ".r", "举报"]
kill_command = ["kill"]
kick_command = ["kick"]

# 初始化管理员列表
admin_list = []


class Context:
    """
    公共资源上下文类，用于在 hook 中共享连接和数据库
    
    Attributes:
        conn: RCON连接实例
        commands: 命令执行器实例
        data: 数据存储实例
    """

    def __init__(self):
        # 创建连接池 - 现在是同步的，不需要特殊初始化
        self.connection_pool = HLLConnectionPool("89.46.1.190", 7839, "2hm14")
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


async def qq_Commands(message: list[str], admin=False) -> str:
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
        if not command:
            return ""
            
        if command == qq_commands.get("status"):
            counts = await _get_player_count()
            server = await ctx.commands.get_server_name()
            current_map = await ctx.commands.get_map()
            current_map = ctx.map.parse_map_name(current_map)

            return (f"{server}\n"
                    f"{counts}\t{current_map}")

        if command == "图池":
            maps = await ctx.commands.get_map_rotation()
            return "\n".join(ctx.map.parse_map_list(maps))

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
                return "参数有误，格式：addadmin <id> <角色> [玩家名]，玩家名有空格可以用引号或_替代"

            parsed_args = parse_quoted_args(args)
            if len(parsed_args) < 2:
                return "参数有误，格式：addadmin <id> <角色> [玩家名]，玩家名有空格可以用引号或_替代"

            # 处理玩家名中的下划线
            player_name = parsed_args[0].replace("_", " ")

            if ctx.commands.add_admin(parsed_args, parsed_args[1], " ".join(parsed_args[2:])):
                return f"已添加游戏管理员: {player_name}"
            else:
                return f"添加游戏管理员失败: {player_name}"

        if command == "removeadmin" or command == "ra":
            if not args:
                return "参数有误，格式：removeadmin <id>，玩家名有空格可以用引号或_替代"
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

        if command == qq_commands.get("ban"):
            # 使用parse_quoted_args处理参数，支持引号
            if not args:
                return "参数有误，格式：封禁 <玩家名> <原因> [时间]，玩家名有空格可以用引号或_替代"
                
            parsed_args = parse_quoted_args(args)
            if len(parsed_args) < 2:
                return "参数有误，格式：封禁 <玩家名> <原因> [时间]，玩家名有空格可以用引号或_替代"
            
            # 处理玩家名中的下划线
            player_name = parsed_args[0].replace("_", " ")
            reason = parsed_args[1]
            
            if len(parsed_args) > 2:
                duration = parsed_args[2]
                try:
                    duration = int(duration)
                    return await ctx.commands.temp_ban(player_name, reason=reason, duration_hours=duration)
                except ValueError:
                    return f"时间参数错误，必须是数字: {duration}"
            else:
                return await ctx.commands.perma_ban(player_name, reason=reason)

        if command == qq_commands.get("kick"):
            # 使用parse_quoted_args处理参数，支持引号
            if not args:
                return "参数有误，格式：踢出 <玩家名> <原因>，玩家名有空格可以用引号或_替代"
                
            parsed_args = parse_quoted_args(args)
            if len(parsed_args) < 2:
                return "参数有误，格式：踢出 <玩家名> <原因>，玩家名有空格可以用引号或_替代"
            
            # 处理玩家名中的下划线
            player_name = parsed_args[0].replace("_", " ")
            reason = parsed_args[1]
            
            return await ctx.commands.kick(player_name, reason)
            
        if command == qq_commands.get("switch"):
            # 使用parse_quoted_args处理参数，支持引号
            if not args:
                return "参数有误，格式：换边 <玩家名>，玩家名有空格可以用引号或_替代"
                
            parsed_args = parse_quoted_args(args)
            if not parsed_args:
                return "参数有误，格式：换边 <玩家名>，玩家名有空格可以用引号或_替代"
            
            # 处理玩家名中的下划线
            player_name = parsed_args[0].replace("_", " ")
            
            return await ctx.commands.switch_player_now(player_name)
            
        if command == qq_commands.get("msg"):
            # 使用parse_quoted_args处理参数，支持引号
            if not args:
                return "参数有误，格式：msg <玩家名> <消息内容>，玩家名有空格可以用引号或_替代"
                
            parsed_args = parse_quoted_args(args)
            if len(parsed_args) < 2:
                return "参数有误，格式：msg <玩家名> <消息内容>，玩家名有空格可以用引号或_替代"
            
            # 处理玩家名中的下划线
            player_name = parsed_args[0].replace("_", " ")
            message = " ".join(parsed_args[1:])
            
            await ctx.commands.message_player(player_name, message)
            return f"已向 {player_name} 发送消息：{message}"
            
        if command == qq_commands.get("vip"):
            pass
            
        if command == qq_commands.get("unban"):
            # 使用parse_quoted_args处理参数，支持引号
            if not args:
                return "参数有误，格式：解封 <玩家名>，玩家名有空格可以用引号或_替代"
                
            parsed_args = parse_quoted_args(args)
            if not parsed_args:
                return "参数有误，格式：解封 <玩家名>，玩家名有空格可以用引号或_替代"
            
            # 处理玩家名中的下划线
            player_name = parsed_args[0].replace("_", " ")
            
            res = await ctx.commands.remove_temp_ban(player_name)
            res1 = await ctx.commands.remove_perma_ban(player_name)
            return str(res) if res else str(res1)

        if command == qq_commands.get("search"):
            # 使用parse_quoted_args处理参数，支持引号
            if not args:
                return "参数有误，格式：查询 <玩家名/ID>，玩家名有空格可以用引号或_替代"
                
            parsed_args = parse_quoted_args(args)
            if not parsed_args:
                return "参数有误，格式：查询 <玩家名/ID>，玩家名有空格可以用引号或_替代"
            
            # 处理玩家名中的下划线
            search_term = parsed_args[0].replace("_", " ")
            
            # 先尝试获取当前在线玩家的信息
            try:
                current_info = await ctx.commands.get_player_info(search_term)
                player_current_info = parse_player_info(current_info) if current_info else None
                if player_current_info:
                    logger.info(f"找到当前在线玩家: {search_term}")
            except Exception as e:
                logger.error(f"获取当前玩家信息失败: {e}")
                player_current_info = None
            
            # 查询数据库中的玩家信息
            player_info = ctx.data.get_player_with_name(search_term)
            if not player_info:
                # 尝试通过ID查询
                player_info = ctx.data.get_player_with_id(search_term)
            
            # 如果数据库和当前在线都没有找到玩家
            if not player_info and not player_current_info:
                return f"未找到玩家: {search_term}"
            
            # 如果找到了当前在线玩家但数据库中没有记录
            if player_current_info and not player_info:
                # 显示当前在线玩家的基本信息
                return (f"玩家：{player_current_info.get('name')}\n"
                        f"SteamID: {player_current_info.get('steam_id')}\n"
                        f"队伍: {player_current_info.get('team')}\n"
                        f"角色: {player_current_info.get('role')}\n"
                        f"小队: {player_current_info.get('unit')}\n"
                        f"等级: {player_current_info.get('level')}\n"
                        f"击杀: {player_current_info.get('kills')} - 死亡: {player_current_info.get('deaths')}")
            
            # 如果找到了数据库中的玩家记录
            if player_info:
                name = player_info.get('名称', "未知")
                player_id = player_info.get('ID', "未知")
                infantry_kill = player_info.get('步兵击杀', 0)
                panzer_kill = player_info.get('车组击杀', 0)
                artillery_kill = player_info.get('炮兵击杀', 0)
                ap = player_info.get('反步兵雷击杀', 0)
                at = player_info.get('反坦克雷击杀', 0)
                satchel = player_info.get('炸药包击杀', 0)
                knife_kill = player_info.get('刀杀', 0)
                TK = player_info.get('TK', 0)
                death = player_info.get('总死亡', 0)
                total_kill = player_info.get('总击杀', 0)
                return (f"玩家：{name}\nID: {player_id}\n"
                        f"步兵击杀：{infantry_kill} 车组击杀：{panzer_kill} 炮兵击杀：{artillery_kill}\n"
                        f"ap雷击杀：{ap} at雷击杀：{at} 炸药包击杀：{satchel} 刀杀：{knife_kill}\n"
                        f"tk：{TK} 总击杀：{total_kill} 死亡：{death}")
        return ""

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
    :return: 只有玩家名的列表
    """
    result = await ctx.commands.get_players()
    return result.split("\t")[1:] if result else []


async def _get_admins() -> list:
    """获取管理员ID列表"""
    try:
        logger.info("正在获取管理员ID列表...")
        result = await ctx.commands.get_admin_ids()

        if not result:
            logger.warning("获取管理员ID失败，返回为空")
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
        logger.error(f"获取管理员ID时出错: {e}")
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

        # 精确匹配玩家名称
        exact_matches = []
        partial_matches = []

        for entry in entries:
            # 尝试解析格式为 "玩家名称 : ID" 的条目
            if " : " in entry:
                name_part, id_part = entry.split(" : ", 1)
                name_part = name_part.strip()
                id_part = id_part.strip()

                if name_part.lower() == player_name.lower():  # 精确匹配
                    return id_part
                elif player_name.lower() in name_part.lower():  # 部分匹配
                    partial_matches.append((name_part, id_part))
            # 尝试使用正则表达式匹配
            elif player_name in entry:
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

        # 更新受害者死亡统计
        if not ctx.data.get_player_with_id(victim_id):
            ctx.data.add_player(player_id=victim_id, name=victim_name)
        victim_info = ctx.data.get_player_with_id(victim_id).get("total_death")
        ctx.data.update_player(player_id=victim_id, total_death=victim_info + 1)

        if not ctx.data.get_player_with_id(attacker_id):
            ctx.data.add_player(player_id=attacker_id, name=attacker_name)
        attacker_info = ctx.data.get_player_with_id(attacker_id)
        # 更新击杀者统计
        stats_to_update = {"total_kill": attacker_info.get("total_kill") + 1}

        # 根据武器类型更新特定击杀统计
        if "HOWITZER" in weapon:
            stats_to_update["artillery_kill"] = attacker_info.get("artillery_kill") + 1
        else:
            role = await commands.get_player_info(attacker_id)
            if "tankcommander" in role.lower() or "crewman" in role.lower():
                stats_to_update["panzer_kill"] = attacker_info.get("panzer_kill") + 1
            else:
                stats_to_update["infantry_kill"] = attacker_info.get("infantry_kill") + 1

        if "satchel" in weapon.lower():
            stats_to_update["satchel_kill"] = attacker_info.get("satchel_kill") + 1
        if "ap" in weapon.lower():
            stats_to_update["apMine_kill"] = attacker_info.get("apMine_kill") + 1
        if "at" in weapon.lower():
            stats_to_update["atMine_kill"] = attacker_info.get("atMine_kill") + 1
        if "knife" in weapon.lower():
            stats_to_update["knife_kill"] = attacker_info.get("knife_kill") + 1

        stats_to_update["total_kill"] = attacker_info.get("total_kill") + 1

        ctx.data.update_player(player_id=attacker_id, **stats_to_update)

        logger.info(f"{attacker_name} 使用 {weapon} 击杀了 {victim_name}")

    except Exception as e:
        logger.error(f"处理击杀事件失败: {e}")


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

        # 更新受害者死亡统计
        ctx.data.update_player(player_id=victim_id, total_death=1)

        # 更新击杀者误杀统计
        ctx.data.update_player(player_id=attacker_id, team_kill=1)

        # 发送消息给误杀者
        await ctx.commands.message_player(
            player_name=attacker_name,
            message=f"[死亡信息]\n你使用 {weapon} 误伤了友军 {victim_name}，请按K发送sry道歉"
        )

        logger.info(f"{attacker_name} 使用 {weapon} 误伤了友军 {victim_name}")

    except Exception as e:
        logger.error(f"处理误杀事件失败: {e}")


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
            # 处理引号和下划线
            suspect = suspect.replace("_", " ")
            
            await ctx.commands.message_player(player_name, f"你举报了 {suspect}，原因：{reason}"
                                                       f"\n请等待管理员处理\n若长时间无回复可加群532933387求助")
            for admin in current_admin_list:
                await ctx.commands.message_player(admin, f"玩家 {player_name} 举报了 {suspect}，原因：{reason}")
            logger.info(f"玩家 {player_name} 执行了举报命令")
        else:
            await ctx.commands.message_player(player_name,
                                              f"举报格式错误，正确格式: report <玩家名> <原因> 或 report \"玩家名\" <原因> 或 report \"{chr(8220)}玩家名{chr(8221)}\" <原因>")
        return

    # 获取玩家ID并记录日志
    player_id = await _get_id(player_name)
    logger.info(f"玩家 '{player_name}' 的ID: {player_id}")
    logger.info(f"当前管理员列表: {current_admin_list}")

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
            target_player = args[1].replace("_", " ")
            reason = args[2]
            duration = args[3] if len(args) > 3 else None
            
            logger.info(f"执行封禁命令: 玩家={target_player}, 原因={reason}, 时长={duration}")
            
            try:
                if duration:
                    res = await ban(target_player, reason=reason, duration=duration)
                else:
                    res = await ban(target_player, reason=reason)
                
                await ctx.commands.message_player(player_name, res)
            except Exception as e:
                logger.error(f"处理封禁命令失败: {e}")
                await ctx.commands.message_player(player_name, f"封禁命令执行失败: {str(e)}")
        else:
            await ctx.commands.message_player(player_name,
                                              f"命令格式错误: ban <玩家名> <原因> [时间] 或 ban \"玩家名\" <原因> [时间] 或使用中文引号")
        return

    elif command in kick_command:
        if len(args) >= 3:
            # 解析kick命令参数
            target_player = args[1].replace("_", " ")
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
                                              f"命令格式错误: kick <玩家名> <原因> 或 kick \"玩家名\" <原因> 或使用中文引号")
        return

    elif command in kill_command:
        if len(args) >= 3:
            # 解析kill命令参数
            target_player = args[1].replace("_", " ")
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
                                              f"命令格式错误: kill <玩家名> <原因> 或 kill \"玩家名\" <原因> 或使用中文引号")
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
                player = player.strip().replace("_", " ")
                res = await ctx.commands.switch_player_now(player)
                await ctx.commands.message_player(player_name, f"切换玩家 {player} 结果: {res}")
        else:
            await ctx.commands.message_player(player_name,
                                              f"命令格式错误: 换边 <玩家名1>,<玩家名2>,... 或 换边 \"玩家名1\" \"玩家名2\"... 或使用中文引号")
        return

    elif command in msg_command:
        logger.info(f"尝试发送信息")
        if len(args) >= 3:
            target_player = args[1].replace("_", " ")
            message = " ".join(args[2:])
            
            await ctx.commands.message_player(target_player, message)
            await ctx.commands.message_player(player_name, f"已向 {target_player} 发送消息")
        else:
            await ctx.commands.message_player(player_name,
                                              f"命令格式错误: msg <玩家名> <消息内容> 或 msg \"玩家名\" <消息内容> 或使用中文引号")
        return


async def suicide(player_name: str) -> None:
    """
    处理玩家自杀请求
    
    Args:
        player_name: 玩家名称
    """
    try:
        logger.info(f"尝试执行玩家 {player_name} 的自杀请求")
        # 使用commands的punish方法
        await ctx.commands.punish(player_name, "自杀成功,加群532933387领取免费vip")

        logger.info(f"玩家 {player_name} 执行了自杀命令")
    except Exception as e:
        logger.error(f"处理自杀事件失败: {e}")


async def ops(message: str = "") -> None:
    res = None
    try:
        logger.info(f"尝试发送ops：{message}")
        players = await _get_players()

        # 检测消息中的空格并转换为换行
        # 以双空格或制表符为分隔符转换为换行
        formatted_message = message.replace(" ", "\n").replace("\t", "\n")

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

        # 确保处理可能包含空格的玩家名
        suspect = suspect.replace("_", " ")

        await ctx.commands.message_player(player_name, f"[举报]\n你举报了 {suspect}，原因：{reason}，请等待管理处理")

        for admin in admins:
            await ctx.commands.message_player(admin, f"[举报]\n玩家 {player_name} 举报了 {suspect}"
                                                     f"\n请及时处理并回报"
                                                     f"\n原因：{reason}\n请及时处理")
    except Exception as e:
        logger.error(f"处理举报事件失败: {e}")
    return res


async def msg(player_name: str, message: str):
    res = None
    try:
        logger.info(f"尝试给玩家 {player_name} 发送 {message}")
        # 确保处理可能包含空格的玩家名
        player_name = player_name.replace("_", " ")
        await ctx.commands.message_player(player_name, message)
    except Exception as e:
        logger.error(f"处理事件失败: {e}")

    return res


async def ban(player_name: str, reason: str, duration=None):
    res = None
    try:
        logger.info(f"尝试执行玩家 {player_name} 的封禁请求，reason: {reason}, duration: {duration}")
        # 确保处理可能包含空格的玩家名
        player_name = player_name.replace("_", " ")
        if duration is None:
            res = await ctx.commands.perma_ban(player_name, reason)
        else:
            res = await ctx.commands.temp_ban(player_name, reason=reason, duration_hours=duration)
    except Exception as e:
        logger.error(f"处理封禁事件失败: {e}")

    return res


async def kick(player_name: str, reason: str):
    res = None
    try:
        logger.info(f"尝试执行玩家 {player_name} 的踢出请求，reason: {reason}")
        # 确保处理可能包含空格的玩家名
        player_name = player_name.replace("_", " ")
        res = await ctx.commands.kick(player_name, reason)
    except Exception as e:
        logger.error(f"处理踢出事件失败: {e}")

    return res


async def kill(player_name: str, reason: str):
    res = None
    try:
        logger.info(f"尝试杀死 {player_name}，reason: {reason}")
        # 确保处理可能包含空格的玩家名
        player_name = player_name.replace("_", " ")
        res = await ctx.commands.punish(player_name, reason)
    except Exception as e:
        logger.error(f"处理死亡事件失败: {e}")

    return res
