# -*- coding: utf-8 -*-
"""支持 python -m codeassess 启动。"""
from codeassess.server import serve
from codeassess import db, seed_demo


def main():
    import argparse
    ap = argparse.ArgumentParser(description="代码理解测评系统")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--reset-demo", action="store_true",
                    help="重建演示数据")
    args = ap.parse_args()

    db.init_db()
    db.seed()
    wrote = seed_demo.seed_demo(force=args.reset_demo)
    if wrote:
        print("已写入演示数据。")
    serve(host=args.host, port=args.port)


if __name__ == "__main__":
    main()