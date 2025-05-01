import os
import base64
import logging
import sqlite3
import hashlib
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class CredentialsManager:
    """用于安全存储和检索服务器连接凭证的管理器"""
    
    def __init__(self, db_path: str = "data.db"):
        """初始化凭证管理器
        
        Args:
            db_path: 数据库文件路径
        """
        self.db_path = os.path.join(os.path.dirname(__file__), db_path)
        self._setup_logging()
        self._setup_database()
        self._encryption_key = None
    
    def _setup_logging(self):
        """设置日志记录"""
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
    
    def _setup_database(self):
        """设置数据库表"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 创建凭证表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS server_credentials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                host TEXT NOT NULL,
                port INTEGER NOT NULL,
                password TEXT NOT NULL,
                salt TEXT NOT NULL,
                is_active INTEGER DEFAULT 1
            )
        """)
        
        conn.commit()
        conn.close()
    
    def _get_connection(self) -> Tuple[sqlite3.Connection, sqlite3.Cursor]:
        """获取数据库连接"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        return conn, cursor
    
    def _generate_key(self, salt: Optional[bytes] = None) -> Tuple[bytes, bytes]:
        """生成加密密钥
        
        Args:
            salt: 可选的盐值，如果未提供则生成新的盐值
            
        Returns:
            (密钥, 盐值)的元组
        """
        if salt is None:
            salt = os.urandom(16)
        
        # 使用简单的机器标识作为密码
        # 在生产环境中，应该使用更强的密码策略
        password = (os.name + os.environ.get('USER', os.environ.get('USERNAME', 'user'))).encode()
        
        # 使用hashlib代替cryptography
        key = hashlib.pbkdf2_hmac('sha256', password, salt, 100000, 32)
        key = base64.urlsafe_b64encode(key)
        
        return key, salt
    
    def _encrypt(self, data: str, salt: Optional[bytes] = None) -> Tuple[str, bytes]:
        """使用简单的XOR加密数据
        
        Args:
            data: 要加密的数据
            salt: 可选的盐值
            
        Returns:
            (加密数据的Base64编码, 盐值)的元组
        """
        key, salt = self._generate_key(salt)
        
        # 简单的XOR加密
        key_bytes = base64.urlsafe_b64decode(key)
        data_bytes = data.encode('utf-8')
        encrypted = bytearray()
        
        for i in range(len(data_bytes)):
            encrypted.append(data_bytes[i] ^ key_bytes[i % len(key_bytes)])
        
        # 返回Base64编码的加密数据
        return base64.b64encode(encrypted).decode('utf-8'), salt
    
    def _decrypt(self, encrypted_data: str, salt: bytes) -> str:
        """解密数据
        
        Args:
            encrypted_data: Base64编码的加密数据
            salt: 用于生成密钥的盐值
            
        Returns:
            解密后的数据
        """
        key, _ = self._generate_key(salt)
        
        # 解码为字节
        encrypted_bytes = base64.b64decode(encrypted_data)
        key_bytes = base64.urlsafe_b64decode(key)
        
        # XOR解密
        decrypted = bytearray()
        for i in range(len(encrypted_bytes)):
            decrypted.append(encrypted_bytes[i] ^ key_bytes[i % len(key_bytes)])
        
        return decrypted.decode('utf-8')
    
    def save_credentials(self, host: str, port: int, password: str) -> bool:
        """加密并保存服务器凭证
        
        Args:
            host: 服务器IP地址
            port: 服务器端口
            password: 服务器密码
            
        Returns:
            操作是否成功
        """
        try:
            # 加密密码
            encrypted_password, salt = self._encrypt(password)
            
            conn, cursor = self._get_connection()
            
            # 先将所有现有凭证标记为非活动
            cursor.execute("UPDATE server_credentials SET is_active = 0")
            
            # 插入新的凭证
            cursor.execute("""
                INSERT INTO server_credentials (host, port, password, salt, is_active)
                VALUES (?, ?, ?, ?, 1)
            """, (
                host,
                port,
                encrypted_password,
                base64.b64encode(salt).decode()
            ))
            
            conn.commit()
            conn.close()
            
            logger.info("服务器凭证已安全保存")
            return True
        except Exception as e:
            logger.error(f"保存凭证失败: {e}")
            return False
    
    def get_credentials(self) -> Optional[Dict[str, str]]:
        """从数据库获取并解密当前活动的服务器凭证
        
        Returns:
            包含host, port, password的字典，如果没有找到则返回None
        """
        try:
            conn, cursor = self._get_connection()
            
            # 获取当前活动的凭证
            cursor.execute("""
                SELECT host, port, password, salt FROM server_credentials
                WHERE is_active = 1 ORDER BY id DESC LIMIT 1
            """)
            
            row = cursor.fetchone()
            conn.close()
            
            if not row:
                logger.info("没有找到活动的服务器凭证")
                return None
                
            host, port, encrypted_password, encoded_salt = row
            salt = base64.b64decode(encoded_salt)
            
            # 解密密码
            password = self._decrypt(encrypted_password, salt)
            
            return {
                "host": host,
                "port": port,
                "password": password
            }
        except Exception as e:
            logger.error(f"获取凭证失败: {e}")
            return None
    
    def has_credentials(self) -> bool:
        """检查是否有保存的凭证
        
        Returns:
            是否有保存的凭证
        """
        try:
            conn, cursor = self._get_connection()
            
            cursor.execute("SELECT COUNT(*) FROM server_credentials WHERE is_active = 1")
            count = cursor.fetchone()[0]
            
            conn.close()
            return count > 0
        except Exception as e:
            logger.error(f"检查凭证失败: {e}")
            return False 