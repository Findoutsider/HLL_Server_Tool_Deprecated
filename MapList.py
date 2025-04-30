class MapList:
    maps = {
        "stmariedumont": "圣玛丽德蒙特",
        "stmereeglise": "圣梅尔埃格利斯",
        "remagen": "雷马根",
        "omahabeach": "奥马哈海滩",
        "stalingrad": "斯大林格勒",
        "utahbeach": "犹他海滩",
        "kharkov": "哈尔科夫",
        "driel": "德里尔",
        "tobruk": "托布鲁克",
        "elsenbornridge": "艾森伯恩岭",
        "foy": "佛依",
        "hill400": "400号高地",
        "hurtgenforest": "许特根森林",
        "kursk": "库尔斯克",
        "carentan": "卡朗唐",
        "elalamein": "阿拉曼",
        "phl": "紫心小道",
        "mortain": "莫尔坦",
        "smdm": "圣玛丽德蒙特",
        "sme": "圣梅尔埃格利斯",
        "car": "卡朗唐",
        "hil": "400号高地",
        "drl": "德里尔",
        "ela": "阿拉曼"
    }

    # 确保所有键都是小写的，以便于匹配
    maps = {k.lower(): v for k, v in maps.items()}

    modes = {
        "warfare": "冲突",
        "offensive_us": "美军进攻",
        "offensive_ger": "德军进攻",
        "offensive_rus": "苏军进攻",
        "offensiveUS": "美军进攻",
        "offensiveger": "德军进攻",
        "offensive_CW": "英军进攻",
        "offensivebritish": "英军进攻",
        "skirmish": "遭遇战",
        "Skirmish": "遭遇战"
    }

    times = {
        "day": "白天",
        "night": "夜晚",
        "dusk": "黄昏",
        "morning": "清晨",
        "overcast": "阴天",
        "rain": "雨天"
    }

    @staticmethod
    def parse_map_name(map_id: str) -> str:
        """解析地图ID并转换为中文名称
        
        Args:
            map_id: 地图ID，如 stmereeglise_warfare
            
        Returns:
            中文地图名称，如 圣梅尔埃格利斯 · 冲突 或 许特根森林 夜晚 · 冲突
        """
        if not map_id:
            return "未知地图"

        try:
            # 转换为小写，便于匹配
            map_id = map_id.lower()

            # 处理特殊格式，如 PHL_S_1944_Night_P_Skirmish
            if "_s_" in map_id and "_p_" in map_id:
                # 提取地图代码 (如 PHL, SME)
                map_code = map_id.split('_')[0]
                map_name = MapList.maps.get(map_code.lower(), map_code)

                # 提取时间
                time_weather = ""
                for time_key, time_value in MapList.times.items():
                    if time_key in map_id.lower():
                        time_weather = time_value
                        break

                # 对于遭遇战模式
                return f"{map_name}{' ' + time_weather if time_weather else ''} · 遭遇战"

            # 分割地图ID
            parts = map_id.split('_')

            # 提取地图基础名称
            map_base = parts[0]
            map_name = MapList.maps.get(map_base, map_base)

            # 检查直接匹配的特殊组合格式
            # 例如: stmereeglise_offensive_ger => 圣梅尔埃格利斯 · 德军进攻
            for mode_pattern, mode_name in {
                "offensive_ger": "德军进攻",
                "offensive_us": "美军进攻",
                "offensive_rus": "苏军进攻",
                "offensive_cw": "英军进攻",
                "offensivebritish": "英军进攻"
            }.items():
                if mode_pattern in map_id:
                    mode = mode_name
                    break
            else:
                # 常规处理模式
                mode = ""
                # 检查是否包含模式
                for part in parts[1:]:
                    if part in MapList.modes:
                        mode = MapList.modes[part]
                        break
                    # 处理可能的组合格式
                    elif "offensive" in part:
                        if "us" in part:
                            mode = "美军进攻"
                            break
                        elif "ger" in part:
                            mode = "德军进攻"
                            break
                        elif "rus" in part:
                            mode = "苏军进攻"
                            break
                        elif "british" in part or "cw" in part:
                            mode = "英军进攻"
                            break
                    # 处理简化格式，如 off_us, off_ger 
                    elif part == "off_us" or part == "offus":
                        mode = "美军进攻"
                        break
                    elif part == "off_ger" or part == "offger":
                        mode = "德军进攻"
                        break
                    elif part == "skirmish":
                        mode = "遭遇战"
                        break

            # 提取时间/天气
            time_weather = ""
            for part in parts[1:]:
                # 检查常规时间格式
                if part in MapList.times:
                    time_weather = MapList.times[part]
                    break
                # 检查组合格式
                for time_key, time_value in MapList.times.items():
                    if time_key in part:
                        time_weather = time_value
                        break
                if time_weather:
                    break

            # 组合结果 - 新格式: "地图名 天气/时间 · 模式"
            result = map_name
            if time_weather:
                result += f" {time_weather}"  # 天气与地图名直接相连
            if mode:
                result += f" · {mode}"  # 模式与前面用中文点分隔

            return result

        except Exception as e:
            print(f"解析地图名称出错: {e}")
            return map_id

    @staticmethod
    def parse_map_list(map_list_str: str | list) -> list:
        """解析地图列表，返回中文地图名称列表
        
        Args:
            map_list_str: 地图ID列表字符串，用制表符或空格分隔
            
        Returns:
            中文地图名称列表
        """
        maps = []
        if type(map_list_str) == str:
            if not map_list_str:
                return []

            # 分割地图列表
            if "\t" in map_list_str:
                maps = map_list_str.split("\t")
            else:
                maps = map_list_str.split()

        # 过滤掉可能的数字开头
        filtered_maps = []
        for map_item in maps:
            if map_item.isdigit():
                continue
            filtered_maps.append(map_item)

        # 解析每个地图ID
        return [MapList.parse_map_name(map_id) for map_id in filtered_maps]
