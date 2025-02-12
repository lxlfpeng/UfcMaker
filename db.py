import sqlite3
import json
# 1. 连接到数据库（如果没有数据库文件，会自动创建）
# conn = sqlite3.connect('ufc.db')
#
# # 2. 创建游标对象（用于执行SQL语句）
# cursor = conn.cursor()
# # 3. 创建表
# cursor.execute('''
#     CREATE TABLE IF NOT EXISTS player (
#         id INTEGER PRIMARY KEY AUTOINCREMENT,
#         name TEXT NOT NULL,     -- 用户名
#         name_cn TEXT,           -- 用户名(中文)
#         nick_name TEXT,         -- 昵称
#         nick_name_cn TEXT,      -- 昵称(中文)
#         page TEXT,              -- 个人主页
#         division TEXT,          -- 级别
#         avatar TEXT,            -- 头像
#         avatar_local TEXT,      -- 头像(本地)
#         cover TEXT,             -- 封面
#         cover_local TEXT,       -- 封面(本地)
#         record TEXT,            -- 战绩
#         age TEXT,               -- 年龄
#         status TEXT,            -- 状态
#         home_town TEXT,         -- 国籍
#         team TEXT,              -- 团队
#         style TEXT,             -- 风格
#         height TEXT,            -- 身高
#         weight TEXT,            -- 体重
#         reach TEXT,             -- 臂展
#         leg_reach TEXT,         -- 腿长
#         debut TEXT,             -- 首次亮像
#         historys TEXT,          -- 历史
#         wins_stats TEXT,        -- 获胜方式
#         created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
#         updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
#     )
# ''')

# cursor.execute('''
#     CREATE TABLE IF NOT EXISTS translate (
#         id INTEGER PRIMARY KEY AUTOINCREMENT,
#         original TEXT NOT NULL,     -- 原文
#         translation TEXT            -- 译文
#     )
# ''')

# # 打开 JSON 文件
# with open('./json/ufc_athlete_data.json', 'r', encoding='utf-8') as file:
#     # 读取文件内容并将其转换为 Python 对象（字典或列表）
#     data = json.load(file)

# print(len(data['data']))
# for user in data['data']:
#     print(user.get('backLocal',None))
#     cursor.execute(
#     '''
#     INSERT INTO player (name, page,division,avatar,avatar_local,cover,cover_local,record)
#     VALUES (?,?,?,?,?,?,?,?)
#     ''', (user['name'], user['playerPage'],user['weightClass'],user['cover'],user.get('coverLocal',''),user['back'],user.get('backLocal',''),user['record'])
#     )
# # cursor.execute('''
# #     INSERT INTO users (name, age)
# #     VALUES (?, ?)
# # ''', ('Alice', 30))

# # # 4. 插入数据
# # cursor.execute('''
# #     INSERT INTO users (name, age)
# #     VALUES (?, ?)
# # ''', ('Alice', 30))

# # cursor.execute('''
# #     INSERT INTO users (name, age)
# #     VALUES (?, ?)
# # ''', ('Bob', 25))

# # 5. 提交更改
# conn.commit()

# #6. 查询数据
# cursor.execute('''SELECT *
# FROM player
# WHERE name IN (
#     SELECT name
#     FROM player
#     GROUP BY name
#     HAVING COUNT(name) > 1
# )''')
# rows = cursor.fetchall()
# # 获取字段名
# # column_names = [description[0] for description in cursor.description]
# # print(column_names)
# for row in rows:
#     print(row)
#     data=json.dumps(row)
#     print(data)


import sqlite3

# # 连接到 ufc_total.db 数据库
# conn = sqlite3.connect('ufc_total.db')
# cursor = conn.cursor()
# cursor.execute('''
#             CREATE TABLE IF NOT EXISTS rank (
#              id INTEGER PRIMARY KEY AUTOINCREMENT, -- 主键
#              name TEXT NOT NULL,                   -- 用户名
#              page TEXT,                            -- 个人主页
#              rank_name TEXT,                       -- 排名类型
#              rank TEXT                            -- 排名
#             )
#             ''')
# # 将 ufc.db 附加为一个附加数据库，别名为 `ufc_db`
# cursor.execute("ATTACH DATABASE 'ufc.db' AS ufc_db")
#
# # 将 ufc.db 中的 rank 表内容复制到 ufc_total.db 的 rank 表
# # 假设两个数据库的 rank 表结构相同
# cursor.execute("INSERT INTO rank SELECT * FROM ufc_db.rank")
#
# # 提交更改并解除附加的数据库
# conn.commit()
# cursor.execute("DETACH DATABASE ufc_db")
# conn.close()
#
# print("Data copied successfully from ufc.db to ufc_total.db.")

# 1. 连接到数据库（如果没有数据库文件，会自动创建）
conn = sqlite3.connect('ufc_translate.db')
# 2. 创建游标对象（用于执行SQL语句）
cursor = conn.cursor()




cursor.execute("SELECT * FROM translate WHERE original = ?", ('key',))

# 7. 关闭连接
conn.close()



