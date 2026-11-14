# -*- coding: utf-8 -*-
"""启动入口：python run.py [--port 8765] [--host 127.0.0.1] [--reset-demo]

首次启动会自动建库、写入演示数据（教师、学生、15 份示例代码、1 份已发布测评
与 1 份已评分作答），便于直接查看完整流程。

云平台部署时自动读取 PORT 环境变量并监听 0.0.0.0（Render/Railway/Fly 等要求）。
"""
import argparse
import os

from codeassess import db, seed_demo
from codeassess.config import DB_PATH, APP_NAME


def main():
    ap = argparse.ArgumentParser(description=APP_NAME)
    ap.add_argument("--host", default=None)
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--reset-demo", action="store_true",
                    help="重建演示数据（会保留已有数据库表结构）")
    args = ap.parse_args()

    port_env = os.environ.get("PORT")
    host = args.host or os.environ.get("HOST") or ("0.0.0.0" if port_env else "127.0.0.1")
    port = args.port or int(port_env or 8765)

    db.init_db()
    db.seed()
    wrote = seed_demo.seed_demo(force=args.reset_demo)
    if wrote:
        print("已写入演示数据：15 份示例代码、2 份已发布测评、1 份待审核测评、1 份已评分作答。")
    print("数据库：%s" % DB_PATH)
    from codeassess.server import serve
    serve(host=host, port=port)


if __name__ == "__main__":
    main()