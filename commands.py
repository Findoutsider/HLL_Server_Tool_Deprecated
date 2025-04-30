from Log import log
from connection import HLLConnectionPool, async_send_command
from dataStorage import DataStorage
from credentials_manager import CredentialsManager

SUCCESS = "SUCCESS"


def convert_tabs_to_spaces(value: str) -> str:
    return value.replace("\t", " ")


class Commands:
    def __init__(self):
        # 获取凭证
        cred_manager = CredentialsManager()
        credentials = cred_manager.get_credentials()
        
        if not credentials:
            self.logger = log()
            self.logger.error("未找到服务器凭证，请先运行 reset_credentials.py 设置凭证")
            raise ValueError("未找到服务器凭证")
            
        # 创建连接池 - 使用从凭证管理器获取的信息
        self.connection_pool = HLLConnectionPool(
            credentials["host"], 
            int(credentials["port"]),  # 确保端口是整数类型
            credentials["password"]
        )
        self.logger = log()
        self.data = DataStorage("data.db")  # 初始化数据存储

    async def __send_quest(self, command: str, can_fail=True, log_info=False) -> str:
        """使用连接池发送命令，使用异步包装函数调用同步方法"""
        try:
            if log_info:
                self.logger.info(f"发送命令: {command}")

            # 使用异步包装函数，保持异步API兼容性
            result = await async_send_command(self.connection_pool, command)

            if log_info:
                self.logger.info(f"命令结果: {result}")

            return result
        except Exception as e:
            if not can_fail:
                raise
            self.logger.error(f"命令 '{command}' 执行失败: {e}")
            return ""

    async def get_map(self) -> str:
        return await self.__send_quest("get map")

    async def get_playerids(self) -> str:
        return await self.__send_quest("get playerids")

    async def get_players(self) -> str:
        return await self.__send_quest("get players")

    async def get_server_name(self) -> str:
        return await self.__send_quest("get name")

    async def get_map_list(self) -> str:
        return await self.__send_quest("get mapsforrotation")

    async def get_admin_ids(self) -> str:
        return await self.__send_quest("get adminids")

    async def get_temp_bans(self) -> str:
        return await self.__send_quest("get tempbans")

    async def get_perma_bans(self) -> str:
        return await self.__send_quest("get permabans")

    async def get_team_switch_cooldown(self) -> str:
        return await self.__send_quest("get teamswitchcooldown")

    async def get_autobalance_threshold(self) -> str:
        return await self.__send_quest("get autobalancethreshold")

    async def get_vip_slots_num(self) -> str:
        return await self.__send_quest("get vipslotsnum")

    async def get_votekick_threshold(self) -> str:
        return await self.__send_quest("get votekickthreshold")

    async def get_slots(self) -> str:
        return await self.__send_quest("get slots")

    async def get_objectives_row(self, row: int) -> str:
        return await self.__send_quest(f"get objectiverow_{row}")

    def _is_info_correct(self, player, raw_data) -> bool:
        try:
            lines = raw_data.encode().split("\n")
            return lines[0] == f"Name: {player}"
        except Exception:
            log.exception("Bad playerinfo data")
            return False

    async def get_player_info(self, player_name: str, can_fail=True) -> str:
        data = await self.__send_quest(f"playerinfo {player_name}", can_fail=can_fail)
        return data

    async def get_votekick_enabled(self) -> str:
        return await self.__send_quest("get votekickenabled", can_fail=False)

    async def get_votekick_thresholds(self) -> str:
        return await self.__send_quest("get votekickthreshold", can_fail=False)

    async def get_map_rotation(self) -> list[str]:
        """获取地图轮换列表
        
        Returns:
            地图ID列表，如 ["stmariedumont_warfare", "foy_offensive_ger", ...]
        """
        result = await self.__send_quest("rotlist", can_fail=False)
        if not result:
            return []
            
        # 分行处理
        map_list = []
        lines = result.split("\n")
        for line in lines:
            if not line.strip():
                continue
                
            # 处理可能的格式：序号+地图ID，如 "1 stmariedumont_warfare"
            parts = line.strip().split(" ", 1)
            if len(parts) == 2 and parts[0].isdigit():
                map_list.append(parts[1].strip())
            else:
                map_list.append(line.strip())
                
        # 过滤掉所有纯数字项
        map_list = [x for x in map_list if not x.isdigit()]
        
        # 记录日志以便调试
        self.logger.debug(f"地图轮换列表解析结果: {map_list}")
        
        return map_list

    async def get_vip_ids(self):
        res = await self.__send_quest("get vipids")
        if not res:
            return []

        try:
            # 分割结果
            parts = res.split("\t")
            if len(parts) < 2:
                self.logger.warning(f"VIP列表格式错误: {res}")
                return []

            # 跳过第一个数字（VIP数量）
            vip_list = parts[1]
            vip_ids = []

            # 处理VIP列表
            for item in vip_list.split("\t"):
                if not item:
                    continue

                # 尝试解析ID和名称
                try:
                    # 分割ID和名称
                    if " " in item:
                        player_id, name = item.split(" ", 1)
                        # 清理名称中的引号
                        name = name.replace('"', "").strip()
                        vip_ids.append({"player_id": player_id.strip(), "name": name})
                    else:
                        # 如果没有名称，只添加ID
                        vip_ids.append({"player_id": item.strip(), "name": ""})
                except ValueError as e:
                    self.logger.warning(f"解析VIP项失败: {item}, 错误: {e}")
                    continue

            return vip_ids
        except Exception as e:
            self.logger.error(f"处理VIP列表失败: {e}")
            return []

    async def get_admin_groups(self):
        return await self.__send_quest("get admingroups")

    async def get_autobalance_enabled(self) -> str:
        return await self.__send_quest("get autobalanceenabled")

    async def get_log(self, minutes_ago: int = 1) -> str:
        """
        获取服务器日志
        
        Args:
            minutes_ago: 获取多少分钟前的日志
            
        Returns:
            日志内容
        """
        response = await self.__send_quest(f"showlog 1")
        return response

    async def set_autobalance_enabled(self, value: str):
        """
        String bool is on / off
        """
        return await self.__send_quest(f"setautobalanceenabled {value}")

    async def set_welcome_message(self, message):
        return await self.__send_quest(f"say {message}")

    async def set_map(self, map_name: str):
        return await self.__send_quest(f"map {map_name}")

    async def set_idle_autokick_time(self, minutes):
        return await self.__send_quest(f"setkickidletime {minutes}")

    async def set_max_ping_autokick(self, max_ms):
        return await self.__send_quest(f"sethighping {max_ms}")

    async def set_autobalance_threshold(self, max_diff: int):
        return await self.__send_quest(f"setautobalancethreshold {max_diff}")

    async def set_team_switch_cooldown(self, minutes: int):
        return await self.__send_quest(f"setteamswitchcooldown {minutes}")

    async def set_queue_length(self, value: int):
        return await self.__send_quest(f"setmaxqueuedplayers {value}")

    async def set_vip_slots_num(self, value: int):
        return await self.__send_quest(f"setnumvipslots {value}")

    async def set_broadcast(self, message: str):
        return await self.__send_quest(f'broadcast "{message}"')

    async def set_game_layout(self, objectives: list[str]):
        if len(objectives) != 5:
            raise ValueError("5 objectives must be provided")
        await self.__send_quest(
            f'gamelayout "{objectives[0]}" "{objectives[1]}" "{objectives[2]}" "{objectives[3]}" "{objectives[4]}"',
            log_info=True,
            can_fail=False,
        )
        return list(objectives)

    async def set_votekick_enabled(self, value: str):
        """
        String bool is on / off
        """
        return await self.__send_quest(f"setvotekickenabled {value}")

    async def switch_player_on_death(self, player_name):
        return await self.__send_quest(f"switchteamondeath {player_name}", log_info=True)

    async def switch_player_now(self, player_name: str):
        return await self.__send_quest(f"switchteamnow {player_name}", log_info=True)

    async def add_map_to_rotation(
            self,
            map_name: str,
            after_map_name: str,
            after_map_name_number: int | None = None,
    ) -> str:
        cmd = f"rotadd {map_name} {after_map_name}"
        if after_map_name_number:
            cmd = f"{cmd} {after_map_name_number}"

        return await self.__send_quest(cmd, can_fail=False, log_info=True)

    async def remove_map_from_rotation(
            self, map_name: str, map_number: int | None = None
    ) -> str:
        cmd = f"rotdel {map_name}"
        if map_number:
            cmd = f"{cmd} {map_number}"

        return await self.__send_quest(cmd, can_fail=False, log_info=True)

    async def punish(self, player_name: str, reason: str) -> None:
        """
        惩罚玩家
        
        Args:
            player_name: 玩家名称
            reason: 惩罚原因
        """
        try:
            await self.__send_quest(f"punish {player_name} {reason}")
            self.logger.info(f"已惩罚玩家 {player_name}: {reason}")
        except Exception as e:
            self.logger.error(f"惩罚玩家失败: {e}")

    async def kick(self, player_name: str, reason: str):
        return await self.__send_quest(f'kick "{player_name}" "{reason}"')

    async def temp_ban(
            self,
            player_name: str | None = None,
            player_id: str | None = None,
            duration_hours: int = 2,
            reason: str = "",
            admin_name: str = "",
            use_id: bool = False
    ):
        reason = convert_tabs_to_spaces(reason)
        # 当use_id为True时，player_name被视为ID
        if use_id and player_name:
            player_id = player_name
            player_name = None
        
        return "执行成功" if await self.__send_quest(
            f'tempban "{player_id or player_name}" {duration_hours} "{reason}" '
            f'"{admin_name}"') else "执行失败"

    async def perma_ban(
            self,
            player_name: str | None = None,
            player_id: str | None = None,
            reason: str = "",
            admin_name: str = "",
            use_id: bool = False
    ):
        reason = convert_tabs_to_spaces(reason)
        # 当use_id为True时，player_name被视为ID
        if use_id and player_name:
            player_id = player_name
            player_name = None
            
        return "执行成功" if await self.__send_quest(f'permaban "{player_id or player_name}" "{reason}" "{admin_name}"') \
            else "执行失败"

    async def remove_temp_ban(self, player_id: str):
        return "执行成功" if await self.__send_quest(f"pardontempban {player_id}", log_info=True) == SUCCESS \
            else "执行失败"

    async def remove_perma_ban(self, player_id: str):
        return "执行成功" if await self.__send_quest(f"pardonpermaban {player_id}", log_info=True) == SUCCESS \
            else "执行失败"

    async def add_admin(self, player_id, role, description) -> bool:
        description = convert_tabs_to_spaces(description)
        res = await self.__send_quest(
            f'adminadd "{player_id}" "{role}" "{description}"', log_info=True
        )

        return res == SUCCESS

    async def remove_admin(self, player_id) -> bool:
        return await self.__send_quest(f"admindel {player_id}", log_info=True) == SUCCESS

    async def add_vip(self, player_id: str, description: str) -> bool:
        """添加VIP到游戏系统
        
        Args:
            player_id: 玩家ID
            description: 描述
            
        Returns:
            bool: 是否成功
        """
        try:
            # 使用游戏命令添加VIP
            result = await self.__send_quest(f"vipadd {player_id} '{description}'", log_info=True)
            return result == SUCCESS
        except Exception as e:
            self.logger.error(f"添加游戏VIP失败: {str(e)}")
            return False

    async def remove_vip(self, player_id) -> bool:
        """移除VIP
        
        Args:
            player_id: 玩家ID
            
        Returns:
            bool: 是否成功
        """
        try:
            # 先检查数据库中是否有记录
            existing_vip = await self.data.async_get_vip(player_id)
            if not existing_vip:
                self.logger.warning(f"玩家 {player_id} 不是数据库中的VIP，跳过移除")
                return True

            # 从游戏VIP系统移除
            game_vip_removed = await self.__send_quest(f"vipdel {player_id}", log_info=True) == SUCCESS
            if not game_vip_removed:
                self.logger.error(f"从游戏移除VIP失败: {player_id}")
                return False

            # 从数据库VIP系统移除
            db_vip_removed = await self.data.async_remove_vip(player_id)
            if not db_vip_removed:
                self.logger.error(f"从数据库移除VIP失败: {player_id}")
                return False

            return True

        except Exception as e:
            self.logger.error(f"移除VIP失败: {str(e)}")
            return False

    async def message_player(self, player_name: str, message: str) -> None:
        await self.__send_quest(f'message {player_name} {message}')
