#!/usr/bin/env python3
"""
飞飞转录服务端启动脚本
用法：python server/run.py [--host HOST] [--port PORT]
"""
import argparse
import sys
import os

# 将项目根目录加入 Python 路径，支持从任意目录运行
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import uvicorn

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="飞飞转录 API 服务端")
    parser.add_argument("--host", default="0.0.0.0", help="监听地址（默认 0.0.0.0）")
    parser.add_argument("--port", type=int, default=8000, help="端口号（默认 8000）")
    parser.add_argument("--reload", action="store_true", help="开发模式：代码变更自动重载")
    args = parser.parse_args()

    print(f"🚀 飞飞转录服务端启动：http://{args.host}:{args.port}")
    print(f"📊 管理后台：http://localhost:{args.port}/")
    print(f"📖 API 文档：http://localhost:{args.port}/docs")

    uvicorn.run(
        "server.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )
