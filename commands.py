from Log import log
from connection import HLLConnectionPool, async_send_command

SUCCESS = "SUCCESS"


def convert_tabs_to_spaces(value: str) -> str:
    """Convert tabs to a space to not break HLL tab delimited lists"""
    return value.replace("\t", " ")


class Commands:
    def __init__(self):
        self.connection_pool = HLLConnectionPool("89.46.1.190", 7839, "2hm14")
        self.logger = log()

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
        result = await self.__send_quest("rotlist", can_fail=False)
        return result.split("\n") if result else []

    async def get_vip_ids(self):
        res = await self.__send_quest("get vipids")

        vip_ids = []
        for item in res:
            try:
                player_id, name = item.split(" ", 1)
                name = name.replace('"', "")
                name = name.replace("\n", "")
                name = name.strip()
                vip_ids.append({"player_id": player_id, "name": name})
            except ValueError as e:
                log.exception(e)
        return vip_ids

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
    ):
        reason = convert_tabs_to_spaces(reason)
        return "执行成功" if await self.__send_quest(
            f'tempban "{player_id or player_name}" {duration_hours} "{reason}" '
            f'"{admin_name}"') else "执行失败"

    async def perma_ban(
            self,
            player_name: str | None = None,
            player_id: str | None = None,
            reason: str = "",
            admin_name: str = "",
    ):
        reason = convert_tabs_to_spaces(reason)
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
        description = convert_tabs_to_spaces(description)
        return await self.__send_quest(
            f'vipadd "{player_id}" "{description}"', log_info=True
        ) == SUCCESS

    async def remove_vip(self, player_id) -> bool:
        return await self.__send_quest(f"vipdel {player_id}", log_info=True) == SUCCESS

    async def message_player(self, player_name: str, message: str) -> None:
        await self.__send_quest(f'message {player_name} {message}')
