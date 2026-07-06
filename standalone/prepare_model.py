"""
将 whisper_models 目录中 HuggingFace 缓存格式的 small 模型
拷贝到 standalone/bundled_model/（平铺目录，可直接传给 WhisperModel）。

用法：
    python3 prepare_model.py [--size small]
"""
import argparse
import os
import shutil
import sys

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
MODELS_ROOT = os.path.join(PROJECT_DIR, "whisper_models")
DEST_DIR    = os.path.join(SCRIPT_DIR, "bundled_model")

MODEL_FILES = ["model.bin", "config.json", "tokenizer.json", "vocabulary.txt"]


def find_snapshot_dir(size: str) -> str:
    """返回 snapshot 目录路径（读取 refs/main 找 commit hash）"""
    model_dir = os.path.join(MODELS_ROOT, f"models--Systran--faster-whisper-{size}")
    refs_main = os.path.join(model_dir, "refs", "main")
    if not os.path.exists(refs_main):
        raise FileNotFoundError(
            f"找不到模型引用文件：{refs_main}\n"
            f"请先在服务端下载 {size} 模型，或确认 whisper_models 目录是否正确。"
        )
    with open(refs_main, "r") as f:
        commit = f.read().strip()
    snap = os.path.join(model_dir, "snapshots", commit)
    if not os.path.isdir(snap):
        raise FileNotFoundError(f"找不到 snapshot 目录：{snap}")
    return snap


def prepare(size: str = "small") -> None:
    print(f"→ 准备 {size} 模型 → {DEST_DIR}")

    snap_dir = find_snapshot_dir(size)
    print(f"  snapshot 目录：{snap_dir}")

    # 检查所有必需文件
    missing = [f for f in MODEL_FILES if not os.path.exists(os.path.join(snap_dir, f))]
    if missing:
        raise FileNotFoundError(f"snapshot 目录缺少文件：{missing}")

    # 清理旧目录
    if os.path.exists(DEST_DIR):
        print(f"  清理旧 bundled_model/…")
        shutil.rmtree(DEST_DIR)
    os.makedirs(DEST_DIR, exist_ok=True)

    # 拷贝文件（follow_symlinks=True，实际拷贝 blob 内容）
    total = 0
    for fname in MODEL_FILES:
        src = os.path.join(snap_dir, fname)
        dst = os.path.join(DEST_DIR, fname)
        print(f"  拷贝 {fname} …", end="", flush=True)
        shutil.copy2(src, dst, follow_symlinks=True)
        size_mb = os.path.getsize(dst) / 1024 / 1024
        total  += os.path.getsize(dst)
        print(f" {size_mb:.1f} MB")

    print(f"\n✅ bundled_model/ 准备完成（共 {total/1024/1024:.1f} MB）")
    print(f"   目录：{DEST_DIR}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--size", default="small",
                        help="模型尺寸（默认 small）")
    args = parser.parse_args()
    try:
        prepare(args.size)
    except Exception as e:
        print(f"\n❌ 错误：{e}", file=sys.stderr)
        sys.exit(1)
