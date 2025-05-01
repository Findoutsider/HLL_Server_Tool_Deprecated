#!/usr/bin/env python3
"""
重置服务器连接凭证的工具脚本
"""
import os
import sys
import traceback
from credentials_manager import CredentialsManager


def main():
    """重置服务器凭证的主函数"""
    print("\n=== HLL服务器连接凭证重置工具 ===")
    
    try:
        # 创建凭证管理器
        manager = CredentialsManager()

        # 检查是否有现有凭证
        has_credentials = manager.has_credentials()

        if has_credentials:
            print("已检测到现有的服务器连接凭证。")
            choice = input("确定要重置凭证吗？(y/n): ").strip().lower()

            if choice != 'y':
                print("操作已取消。")
                return

        # 提示用户输入新的凭证
        print("\n请输入新的服务器连接信息:")
        host = input("服务器IP地址: ").strip()

        # 端口验证
        while True:
            try:
                port = int(input("服务器端口: ").strip())
                if 1 <= port <= 65535:  # 有效端口范围
                    break
                else:
                    print("端口必须在1-65535之间，请重新输入。")
            except ValueError:
                print("请输入有效的数字端口。")

        password = input("服务器密码: ").strip()

        # 确认输入
        print("\n请确认以下信息:")
        print(f"服务器地址: {host}")
        print(f"端口: {port}")
        print(f"密码: {'*' * len(password)}")

        confirm = input("\n信息是否正确？(y/n): ").strip().lower()

        if confirm == 'y':
            # 保存凭证
            if manager.save_credentials(host, port, password):
                print("\n凭证已成功保存到数据库并加密。")
                print("下次启动程序时将自动使用这些信息连接服务器。")
            else:
                print("\n凭证保存失败，请稍后重试。")
        else:
            print("\n操作已取消。")
    
    except Exception as e:
        print(f"\n错误: {str(e)}")
        print("设置凭证时发生错误，详细信息如下:")
        traceback.print_exc()
        print("\n如果问题持续存在，请检查程序的权限和数据库访问权限。")
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
