"""
项目包初始化。

生产环境使用 Docker（python:3.12-slim）+ MySQL 8。
Django 默认只能用 MySQLdb 驱动，但 MySQLdb 需要编译 C 扩展，
这里用纯 Python 实现的 PyMySQL 顶替，安装后即可被 Django 当作
MySQLdb 使用，Docker 构建无需任何编译环境。
"""
import pymysql

pymysql.install_as_MySQLdb()

__version__ = "1.0.0"
