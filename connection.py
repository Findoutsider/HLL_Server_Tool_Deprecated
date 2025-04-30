import array
import logging
import socket
import time
import uuid
import threading
from threading import get_ident
from queue import Queue
from typing import Optional, Tuple

# 基础配置
MSGLEN = 32_768
TIMEOUT_SEC = None  # 移除超时时间，允许无限等待
MAX_CONNECTIONS = 3  # 减少最大连接数

logger = logging.getLogger(__name__)


class HLLAuthError(Exception):
    """认证错误异常"""
    pass


class HLLConnection:
    """HLL服务器socket连接类，包含XOR加密"""

    def __init__(self, host: str, port: int, password: str):
        self.host = host
        self.port = port
        self.password = password
        self.xorkey = None
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(None)  # 移除超时设置，让连接永久保持
        self.last_activity = time.time()
        self.lock = threading.RLock()
        self._is_connected = False
        self.id = f"{get_ident()}-{uuid.uuid4()}"
        
    def connect(self) -> bool:
        """建立连接并发送密码"""
        with self.lock:
            # 如果已连接，直接返回
            if self._is_connected and self.sock:
                return True

            # 确保关闭任何现有连接
            self._close_connection()
            
            # 尝试连接
            try:
                logger.info(f"正在连接到服务器 {self.host}:{self.port}")
                
                # 创建新socket
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.sock.settimeout(None)  # 移除超时设置，让连接永久保持
                
                # 连接到服务器
                self.sock.connect((self.host, self.port))
                
                # 接收XOR密钥
                self.xorkey = self.sock.recv(MSGLEN)
                logger.debug(f"接收到密钥，长度: {len(self.xorkey)}")
                
                # 设置保活选项
                self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                
                self._is_connected = True
                self.last_activity = time.time()
                
                # 发送密码
                logger.info("正在发送认证信息...")
                login_msg = f"login {self.password}".encode()
                self.send(login_msg)
                result = self.receive()
                
                if result != b"SUCCESS":
                    self._close_connection()
                    logger.error(f"认证失败: {result}")
                    raise HLLAuthError("认证失败")
                    
                logger.info("认证完成")
                return True
                
            except Exception as e:
                logger.error(f"连接失败: {e}")
                self._close_connection()
                return False

    def _close_connection(self) -> None:
        """关闭连接并清理资源"""
        try:
            if self.sock:
                try:
                    self.sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    logger.debug("无法发送socket关闭指令")
                self.sock.close()
        except Exception as e:
            logger.error(f"关闭连接出错: {e}")
        finally:
            self._is_connected = False
            self.sock = None
            self.xorkey = None

    def send(self, msg) -> int:
        """发送加密消息"""
        xored = self._xor(msg)
        sent = self.sock.send(xored)
        if sent != len(msg):
            raise RuntimeError("socket连接中断")
        return sent

    def _xor(self, msg) -> bytes:
        """XOR加密/解密"""
        if not self.xorkey:
            raise RuntimeError("游戏服务器没有返回密钥")
        
        n = []
        for i in range(len(msg)):
            n.append(msg[i] ^ self.xorkey[i % len(self.xorkey)])

        return array.array("B", n).tobytes()

    def receive(self, msglen=MSGLEN) -> bytes:
        """接收和解密消息"""
        buff = self.sock.recv(msglen)
        msg = self._xor(buff)

        while len(buff) >= msglen:
            try:
                buff = self.sock.recv(msglen)
            except socket.timeout:
                break
            msg += self._xor(buff)

        return msg

    def send_command(self, command: str) -> str:
        """发送命令并等待响应，带自动重连"""
        with self.lock:
            for attempt in range(2):
                # 检查连接状态，尝试重连
                if not self._is_connected or not self.sock:
                    if not self.connect():
                        raise ConnectionError("无法建立连接")
                
                try:
                    # 发送命令
                    self.last_activity = time.time()
                    self.send(command.encode())
                    
                    # 接收响应
                    response = self.receive()
                    
                    # 解码响应
                    decoded_response = None
                    for encoding in ['utf-8', 'gbk', 'latin1']:
                        try:
                            decoded_response = response.decode(encoding).strip()
                            break
                        except UnicodeDecodeError:
                            continue
                    
                    # 如果所有编码都失败，使用latin1
                    if decoded_response is None:
                        decoded_response = response.decode('latin1').strip()
                    
                    return decoded_response
                    
                except Exception as e:
                    # 第一次失败时尝试重新连接
                    if attempt == 0:
                        logger.warning(f"发送命令失败，准备重连: {e}")
                        self._close_connection()
                        time.sleep(1)  # 短暂等待后重试
                    else:
                        # 连续两次失败，抛出异常
                        logger.error(f"发送命令最终失败: {e}")
                        raise ConnectionError(f"发送命令失败: {e}")
            
            # 这里不应该到达，但为了完整性
            raise ConnectionError("发送命令失败")

    def close(self):
        """关闭连接"""
        with self.lock:
            self._close_connection()
            logger.info("连接已关闭")


class HLLConnectionPool:
    """HLL连接池管理类"""

    def __init__(self, host: str, port: int, password: str, max_connections: int = MAX_CONNECTIONS):
        self.host = host
        self.port = port
        self.password = password
        self.max_connections = max_connections
        self.connections = Queue(maxsize=max_connections)
        self.active_connections = 0
        self.lock = threading.RLock()
        
        # 启动清理线程
        self._stop_cleanup = threading.Event()
        self._cleanup_thread = threading.Thread(target=self._cleanup_job, daemon=True)
        self._cleanup_thread.start()

    def _cleanup_job(self):
        """清理空闲连接的线程函数"""
        while not self._stop_cleanup.is_set():
            try:
                # 每60秒检查一次
                for _ in range(60):
                    if self._stop_cleanup.is_set():
                        break
                    time.sleep(1)
                
                self._cleanup_idle_connections()
            except Exception as e:
                logger.error(f"连接池清理任务出错: {e}")
    
    def _cleanup_idle_connections(self):
        """清理空闲连接"""
        idle_threshold = 300  # 5分钟
        current_time = time.time()
        temp_connections = []
        
        with self.lock:
            # 检查所有连接
            closed_count = 0
            while not self.connections.empty():
                conn = self.connections.get()
                
                # 关闭长时间空闲的连接
                if current_time - conn.last_activity > idle_threshold:
                    conn.close()
                    closed_count += 1
                    self.active_connections -= 1
                else:
                    temp_connections.append(conn)
            
            # 恢复连接到原队列
            for conn in temp_connections:
                self.connections.put(conn)
            
            if closed_count > 0:
                logger.info(f"已清理 {closed_count} 个空闲连接")

    def get_connection(self) -> Optional[HLLConnection]:
        """获取一个可用的连接"""
        with self.lock:
            # 首先尝试从池中获取
            if not self.connections.empty():
                conn = self.connections.get()
                # 验证连接有效性
                if conn._is_connected:
                    return conn
                else:
                    # 连接无效，减少计数
                    self.active_connections -= 1

            # 如果池中没有可用连接且未达到最大值，创建新连接
            if self.active_connections < self.max_connections:
                conn = HLLConnection(self.host, self.port, self.password)
                if conn.connect():
                    self.active_connections += 1
                    return conn
                
            # 如果已达到最大值且所有连接都在使用中
            if self.active_connections >= self.max_connections:
                logger.warning(f"已达到最大连接数 {self.max_connections}")
                
            return None
    
    def release_connection(self, conn: HLLConnection):
        """释放连接回连接池"""
        with self.lock:
            if conn and conn._is_connected:
                # 刷新最后活动时间
                conn.last_activity = time.time()
                self.connections.put(conn)
            else:
                # 无效连接不放回池中
                if conn:
                    conn.close()
                    self.active_connections -= 1

    def close_all(self):
        """关闭所有连接"""
        # 停止清理线程
        self._stop_cleanup.set()
        if self._cleanup_thread.is_alive():
            self._cleanup_thread.join(timeout=2)
            
        with self.lock:
            while not self.connections.empty():
                conn = self.connections.get()
                conn.close()
            self.active_connections = 0
            logger.info("已关闭所有连接")

# 为了保持与异步代码的兼容性，添加异步接口
async def async_send_command(connection_pool, command):
    """异步接口函数，实际在同步上下文中执行"""
    conn = None
    try:
        conn = connection_pool.get_connection()
        if not conn:
            raise ConnectionError("无法获取连接")
        
        return conn.send_command(command)
    finally:
        if conn:
            connection_pool.release_connection(conn)

async def async_close_all(connection_pool):
    """异步关闭所有连接的接口函数"""
    connection_pool.close_all()
