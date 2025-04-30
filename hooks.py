# hooks.py
from collections import defaultdict
from typing import Callable, Literal, TypeVar, Dict, List
from functools import wraps

import Log

# 设置日志
logger = Log.log()

# 定义泛型类型
T = TypeVar('T')

# 全局 hooks 注册中心，使用 defaultdict 确保线程安全
HOOKS: Dict[str, List[Callable]] = defaultdict(list)

# 定义所有可能的 hook 类型
HookType = Literal[
    "KILL",
    "TEAM KILL",
    "CHAT",
    "CONNECTED",
    "DISCONNECTED",
    "VOTE COMPLETED",
    "VOTE STARTED",
    "VOTE",
    "TEAMSWITCH",
    "TK AUTO",
    "TK AUTO KICKED",
    "TK AUTO BANNED",
    "ADMIN",
    "ADMIN KICKED",
    "ADMIN BANNED",
    "MATCH",
    "MATCH START",
    "MATCH ENDED",
    "MESSAGE"
]


def register_hook(action: HookType) -> Callable[[Callable], Callable]:
    """
    注册钩子函数的装饰器
    
    Args:
        action: 钩子类型
        
    Returns:
        装饰器函数
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                logger.error(f"钩子函数 {func.__name__} 执行失败: {e}")
                raise

        HOOKS[action].append(wrapper)
        return wrapper

    return decorator


# 常用快捷方式
on_kill = register_hook("KILL")
on_tk = register_hook("TEAM KILL")
on_chat = register_hook("CHAT")
on_connected = register_hook("CONNECTED")
on_disconnected = register_hook("DISCONNECTED")
on_vote_completed = register_hook("VOTE COMPLETED")
on_vote_started = register_hook("VOTE STARTED")
on_vote = register_hook("VOTE")
on_teamswitch = register_hook("TEAMSWITCH")
on_tk_auto = register_hook("TK AUTO")
on_tk_auto_kicked = register_hook("TK AUTO KICKED")
on_tk_auto_banned = register_hook("TK AUTO BANNED")
on_admin = register_hook("ADMIN")
on_admin_kicked = register_hook("ADMIN KICKED")
on_admin_banned = register_hook("ADMIN BANNED")
on_match = register_hook("MATCH")
on_match_start = register_hook("MATCH START")
on_match_ended = register_hook("MATCH ENDED")
on_message = register_hook("MESSAGE")


def get_hooks(action: HookType) -> List[Callable]:
    """
    获取指定动作的所有钩子函数
    
    Args:
        action: 钩子类型
        
    Returns:
        钩子函数列表
    """
    return HOOKS.get(action, [])


def clear_hooks(action: HookType = None) -> None:
    """
    清除指定动作或所有钩子函数
    
    Args:
        action: 钩子类型，如果为None则清除所有钩子
    """
    if action:
        HOOKS[action].clear()
    else:
        HOOKS.clear()
