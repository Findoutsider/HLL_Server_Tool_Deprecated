# HLL_Server_Tool - 人间地狱服务器工具

## 注意，这个工具版本及其久远，已被弃用，且不会再更新，推荐访问最新的仓库，使用最新版

---

支持服务器内监控和Q群远程执行Rcon命令

## 部署教程

- 初次使用使请先打开reset_credentials.py，并根据提示输入你的服务器ip，rcon端口和密码，如果需要更改登录凭据，同样打开reset_credentials.py

- Q群部分使用的api来自napcat，如果需要qq功能你需要自行部署napcat，然后启动一个http服务器，主机为127.0.0.1，端口为3000，将消息格式改为String，并打开config.txt，设置qq_group为你的Q群群号，其他部分无需调整

- 随后，打开dataStorage.py，按下Ctrl+F搜索DEFAULT_ADMIN_QQ，将后面的qq号改成你自己的，这样你才有权限执行qq命令。使用*+admin给其他人上qq管理，使用*help查看帮助文档

- 接下来打开customCMDs.py，所有的qq和游戏内命令都在这里，代码比较屎，非要使用的话请自行克服

  - 所有的命令你都可以修改，要注意，qq命令需要加上*为前缀
 

## 依赖

### 必须使用python3.10

- requests >= 2.32.3

下载方式：`pip install requests`
