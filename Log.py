import logging
import sys
from typing import Optional


class Log:
    """日志处理器单例类"""
    _instance: Optional['Log'] = None
    _initialized: bool = False
    _logger: Optional[logging.Logger] = None

    def __new__(cls) -> 'Log':
        if cls._instance is None:
            cls._instance = super(Log, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._initialized:
            self._setup_logger()
            self._initialized = True

    def _setup_logger(self):
        """设置日志处理器"""
        # 创建日志记录器
        self._logger = logging.getLogger("[HLL Bot]")
        self._logger.setLevel(logging.INFO)

        # 检查是否已经有处理器
        if not self._logger.handlers:
            # 创建控制台处理器
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(logging.INFO)

            # 创建文件处理器
            file_handler = logging.FileHandler("hll_bot.log", encoding='utf-8')
            file_handler.setLevel(logging.INFO)

            # 设置日志格式
            formatter = logging.Formatter(
                '[HLL Bot] - %(asctime)s - %(levelname)s - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            console_handler.setFormatter(formatter)
            file_handler.setFormatter(formatter)

            # 添加处理器到日志记录器
            self._logger.addHandler(console_handler)
            self._logger.addHandler(file_handler)

    def __call__(self) -> logging.Logger:
        """返回日志记录器实例"""
        return self._logger

    def info(self, msg: str) -> None:
        self._logger.info(msg)

    def error(self, msg: str) -> None:
        self._logger.error(msg)

    def warning(self, msg: str) -> None:
        self._logger.warning(msg)

    def debug(self, msg: str) -> None:
        self._logger.debug(msg)

    def exception(self, msg: str) -> None:
        """
        记录异常信息，包括完整的堆栈跟踪
        
        Args:
            msg: 异常消息
        """
        self._logger.exception(msg)


# 创建全局日志记录器实例
log = Log()
