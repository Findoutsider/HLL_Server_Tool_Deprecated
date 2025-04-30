import sqlite3
import threading
import os
import logging
from typing import Optional, Dict, List, Tuple, Any


class DataStorage:
    def __init__(self, db_path: str):
        self.db_path = os.path.join(os.path.dirname(__file__), db_path)
        self.local = threading.local()
        self.logger = logging.getLogger(__name__)
        self._setup_logging()

    def _setup_logging(self):
        """设置日志记录"""
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)

    def get_connection(self) -> Tuple[sqlite3.Connection, sqlite3.Cursor]:
        """获取数据库连接，使用线程本地存储确保线程安全"""
        try:
            if not hasattr(self.local, 'conn'):
                self.local.conn = sqlite3.connect(
                    self.db_path,
                    timeout=30,
                    check_same_thread=False
                )
                self.local.conn.row_factory = sqlite3.Row
                self.local.cursor = self.local.conn.cursor()
            return self.local.conn, self.local.cursor
        except sqlite3.Error as e:
            self.logger.error(f"数据库连接错误: {e}")
            raise

    def close_connection(self):
        """关闭数据库连接"""
        if hasattr(self.local, 'conn'):
            try:
                self.local.conn.close()
            except sqlite3.Error as e:
                self.logger.error(f"关闭连接时出错: {e}")
            finally:
                del self.local.conn
                del self.local.cursor

    def first_run(self):
        """初始化数据库和表结构"""
        try:
            if not os.path.exists(self.db_path):
                with open(self.db_path, 'x') as file:
                    file.close()
            
            conn, cursor = self.get_connection()
            
            # 创建玩家表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS players (
                    id TEXT UNIQUE PRIMARY KEY,
                    name TEXT,
                    level INTEGER DEFAULT 0, 
                    total_playtime INTEGER DEFAULT 0,
                    infantry_time INTEGER DEFAULT 0,
                    panzer_time INTEGER DEFAULT 0,
                    total_kill INTEGER DEFAULT 0,
                    infantry_kill INTEGER DEFAULT 0,
                    panzer_kill INTEGER DEFAULT 0,
                    artillery_kill INTEGER DEFAULT 0,
                    team_kill INTEGER DEFAULT 0,
                    total_death INTEGER DEFAULT 0,
                    apMine_kill INTEGER DEFAULT 0,
                    atMine_kill INTEGER DEFAULT 0,
                    satchel_kill INTEGER DEFAULT 0,
                    knife_kill INTEGER DEFAULT 0
                )
            """)
            
            # 创建管理员表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS qq_admins (
                    qq_id TEXT UNIQUE PRIMARY KEY,
                    added_time INTEGER NOT NULL,
                    added_by TEXT,
                    notes TEXT
                )
            """)
            
            # 创建索引
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_player_id ON players(id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_player_name ON players(name)")
            
            # 检查表结构，添加缺失的列
            self._check_and_add_missing_columns()
            
            # 检查默认管理员
            self._check_default_admin()
            
            conn.commit()
            self.logger.info("数据库初始化完成")
        except sqlite3.Error as e:
            self.logger.error(f"数据库初始化失败: {e}")
            raise

    def _check_and_add_missing_columns(self):
        """检查并添加缺失的列"""
        try:
            conn, cursor = self.get_connection()
            
            # 获取表结构
            cursor.execute("PRAGMA table_info(players)")
            existing_columns = {row[1] for row in cursor.fetchall()}
            
            # 检查并添加所有必需的列
            required_columns = {
                'id': 'TEXT',
                'name': 'TEXT',
                'level': 'INTEGER DEFAULT 0', 
                'total_playtime': 'INTEGER DEFAULT 0',
                'infantry_time': 'INTEGER DEFAULT 0',
                'panzer_time': 'INTEGER DEFAULT 0',
                'total_kill': 'INTEGER DEFAULT 0',
                'infantry_kill': 'INTEGER DEFAULT 0',
                'panzer_kill': 'INTEGER DEFAULT 0',
                'artillery_kill': 'INTEGER DEFAULT 0',
                'team_kill': 'INTEGER DEFAULT 0',
                'total_death': 'INTEGER DEFAULT 0',
                'apMine_kill': 'INTEGER DEFAULT 0',
                'atMine_kill': 'INTEGER DEFAULT 0',
                'satchel_kill': 'INTEGER DEFAULT 0',
                'knife_kill': 'INTEGER DEFAULT 0'
            }
            
            for column, data_type in required_columns.items():
                if column not in existing_columns:
                    self.logger.info(f"添加缺失的列: {column}")
                    cursor.execute(f"ALTER TABLE players ADD COLUMN {column} {data_type}")
            
            conn.commit()
        except sqlite3.Error as e:
            self.logger.error(f"检查表结构失败: {e}")
            raise

    def _check_default_admin(self):
        """确保默认管理员存在"""
        try:
            DEFAULT_ADMIN_QQ = "2275016544"  # 默认管理员QQ
            
            conn, cursor = self.get_connection()
            
            # 检查默认管理员是否存在
            cursor.execute("SELECT qq_id FROM qq_admins WHERE qq_id = ?", (DEFAULT_ADMIN_QQ,))
            if not cursor.fetchone():
                # 添加默认管理员
                import time
                current_time = int(time.time())
                cursor.execute("""
                    INSERT INTO qq_admins (qq_id, added_time, added_by, notes)
                    VALUES (?, ?, ?, ?)
                """, (DEFAULT_ADMIN_QQ, current_time, "系统", "默认管理员"))
                conn.commit()
                self.logger.info(f"添加默认管理员: {DEFAULT_ADMIN_QQ}")
        except sqlite3.Error as e:
            self.logger.error(f"检查默认管理员失败: {e}")
            
    def get_all_qq_admins(self) -> List[str]:
        """获取所有QQ管理员ID列表"""
        try:
            conn, cursor = self.get_connection()
            cursor.execute("SELECT qq_id FROM qq_admins")
            
            rows = cursor.fetchall()
            return [row[0] for row in rows]
        except sqlite3.Error as e:
            self.logger.error(f"获取QQ管理员列表失败: {e}")
            return []
            
    def add_qq_admin(self, qq_id: str, added_by: str = "系统", notes: str = "") -> bool:
        """添加QQ管理员
        
        Args:
            qq_id: 管理员QQ号
            added_by: 添加者
            notes: 备注
            
        Returns:
            添加是否成功
        """
        try:
            conn, cursor = self.get_connection()
            
            # 检查管理员是否已存在
            cursor.execute("SELECT qq_id FROM qq_admins WHERE qq_id = ?", (qq_id,))
            if cursor.fetchone():
                self.logger.info(f"QQ管理员 {qq_id} 已存在")
                return True
                
            # 添加新管理员
            import time
            current_time = int(time.time())
            cursor.execute("""
                INSERT INTO qq_admins (qq_id, added_time, added_by, notes)
                VALUES (?, ?, ?, ?)
            """, (qq_id, current_time, added_by, notes))
            
            conn.commit()
            self.logger.info(f"添加QQ管理员 {qq_id} 成功")
            return True
        except sqlite3.Error as e:
            self.logger.error(f"添加QQ管理员失败: {e}")
            return False
            
    def remove_qq_admin(self, qq_id: str) -> bool:
        """移除QQ管理员
        
        Args:
            qq_id: 管理员QQ号
            
        Returns:
            移除是否成功
        """
        try:
            # 不允许移除默认管理员
            DEFAULT_ADMIN_QQ = "2275016544"
            if qq_id == DEFAULT_ADMIN_QQ:
                self.logger.warning(f"不能移除默认管理员: {qq_id}")
                return False
                
            conn, cursor = self.get_connection()
            
            cursor.execute("DELETE FROM qq_admins WHERE qq_id = ?", (qq_id,))
            
            if cursor.rowcount > 0:
                conn.commit()
                self.logger.info(f"移除QQ管理员 {qq_id} 成功")
                return True
            else:
                self.logger.warning(f"QQ管理员 {qq_id} 不存在")
                return False
        except sqlite3.Error as e:
            self.logger.error(f"移除QQ管理员失败: {e}")
            return False

    def _validate_player_data(self, player_data: Dict[str, Any]) -> bool:
        """验证玩家数据"""
        required_fields = {'id', 'name'}
        if not all(field in player_data for field in required_fields):
            self.logger.error(f"玩家数据缺少必要字段: {required_fields - set(player_data.keys())}")
            return False
        return True

    def get_player_with_id(self, player_id: str) -> Optional[Dict[str, Any]]:
        """通过ID查询玩家"""
        try:
            conn, cursor = self.get_connection()
            cursor.execute("""
                SELECT 
                    id,
                    name,
                    level,
                    total_kill,
                    infantry_kill,
                    panzer_kill,
                    artillery_kill,
                    team_kill,
                    total_death,
                    apMine_kill,
                    atMine_kill,
                    satchel_kill,
                    knife_kill
                FROM players
                WHERE id = ?
            """, (player_id,))
            
            row = cursor.fetchone()
            if row:
                return {
                    "ID": row[0],
                    "名称": row[1],
                    "等级": row[2],
                    "总击杀": row[6],
                    "步兵击杀": row[7],
                    "车组击杀": row[8],
                    "炮兵击杀": row[9],
                    "TK": row[10],
                    "总死亡": row[11],
                    "反步兵雷击杀": row[12],
                    "反坦克雷击杀": row[13],
                    "炸药包击杀": row[14],
                    "刀杀": row[15]
                }
            return None
        except sqlite3.Error as e:
            self.logger.error(f"查询玩家数据失败: {e}")
            return None

    def get_player_with_name(self, name: str) -> Optional[Dict[str, Any]]:
        """通过名称查询玩家"""
        try:
            conn, cursor = self.get_connection()
            cursor.execute("""
                SELECT 
                    id AS ID,
                    name AS 名称,
                    level AS 等级,
                    total_playtime AS 游戏时长,
                    infantry_time AS 步兵时长,
                    panzer_time AS 车组时长,
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
                WHERE name = ?
            """, (name,))
            
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None
        except sqlite3.Error as e:
            self.logger.error(f"查询玩家数据失败: {e}")
            return None

    def add_player(self, player_id: str, name: str) -> bool:
        """添加新玩家
        
        Args:
            player_id: 玩家ID
            name: 玩家名称
            
        Returns:
            添加是否成功
        """
        try:
            conn, cursor = self.get_connection()
            
            # 检查玩家是否已存在
            cursor.execute("SELECT id FROM players WHERE id = ?", (player_id,))
            if cursor.fetchone():
                self.logger.info(f"玩家 {name}({player_id}) 已存在")
                return True
                
            # 插入新玩家
            cursor.execute("""
                INSERT INTO players (
                    id, name, level, total_playtime, infantry_time, panzer_time, 
                    total_kill, infantry_kill, panzer_kill, artillery_kill, 
                    team_kill, total_death, apMine_kill, atMine_kill, 
                    satchel_kill, knife_kill
                ) VALUES (?, ?, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
            """, (player_id, name))
            
            conn.commit()
            self.logger.info(f"玩家 {name}({player_id}) 添加成功")
            return True
        except sqlite3.Error as e:
            self.logger.error(f"添加玩家失败: {e}")
            return False

    def insert_player(self, **kwargs) -> bool:
        """插入新玩家数据"""
        try:
            if not self._validate_player_data(kwargs):
                return False
                
            conn, cursor = self.get_connection()
            cursor.execute("""
                INSERT OR REPLACE INTO players (
                    id, name, level, total_playtime, infantry_time, panzer_time, 
                    total_kill, infantry_kill, panzer_kill, artillery_kill, 
                    team_kill, total_death, apMine_kill, atMine_kill, 
                    satchel_kill, knife_kill
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                kwargs.get('player_id'),
                kwargs.get('name'),
                kwargs.get('level', 0),
                kwargs.get('total_kill', 0),
                kwargs.get('infantry_kill', 0),
                kwargs.get('panzer_kill', 0),
                kwargs.get('artillery_kill', 0),
                kwargs.get('team_kill', 0),
                kwargs.get('total_death', 0),
                kwargs.get('apMine_kill', 0),
                kwargs.get('atMine_kill', 0),
                kwargs.get('satchel_kill', 0),
                kwargs.get('knife_kill', 0)
            ))
            conn.commit()
            return True
        except sqlite3.Error as e:
            self.logger.error(f"插入玩家数据失败: {e}")
            return False

    def update_player(self, player_id: str, **kwargs) -> bool:
        """更新玩家数据"""
        try:
            if not player_id:
                self.logger.error("更新玩家数据失败: 缺少玩家ID")
                return False
                
            conn, cursor = self.get_connection()
            update_fields = []
            params = []
            
            for field, value in kwargs.items():
                if value is not None:
                    update_fields.append(f"{field} = ?")
                    params.append(value)
            
            if not update_fields:
                return True
                
            sql = f"UPDATE players SET {', '.join(update_fields)} WHERE id = ?"
            params.append(player_id)
            
            cursor.execute(sql, params)
            conn.commit()
            return True
        except sqlite3.Error as e:
            self.logger.error(f"更新玩家数据失败: {e}")
            return False

    def batch_update_players(self, player_data_list: List[Dict[str, Any]]) -> bool:
        """批量更新玩家数据"""
        try:
            conn, cursor = self.get_connection()
            for player_data in player_data_list:
                if not self._validate_player_data(player_data):
                    continue
                    
                cursor.execute("""
                    UPDATE players SET 
                        name = ?, level = ?, total_playtime = ?,
                        infantry_time = ?, panzer_time = ?, total_kill = ?,
                        infantry_kill = ?, panzer_kill = ?, artillery_kill = ?,
                        team_kill = ?, total_death = ?, apMine_kill = ?,
                        atMine_kill = ?, satchel_kill = ?, knife_kill = ?
                    WHERE id = ?
                """, (
                    player_data.get('name'),
                    player_data.get('level', 0),
                    player_data.get('total_playtime', 0),
                    player_data.get('infantry_time', 0),
                    player_data.get('panzer_time', 0),
                    player_data.get('total_kill', 0),
                    player_data.get('infantry_kill', 0),
                    player_data.get('panzer_kill', 0),
                    player_data.get('artillery_kill', 0),
                    player_data.get('team_kill', 0),
                    player_data.get('total_death', 0),
                    player_data.get('apMine_kill', 0),
                    player_data.get('atMine_kill', 0),
                    player_data.get('satchel_kill', 0),
                    player_data.get('knife_kill', 0),
                    player_data.get('id')
                ))
            
            conn.commit()
            return True
        except sqlite3.Error as e:
            self.logger.error(f"批量更新玩家数据失败: {e}")
            conn.rollback()
            return False


if __name__ == '__main__':

    db = DataStorage("data.db")
    print(db.get_player_with_name("彼岸"))

