"""
将 whisper_models 目录中 HuggingFace 缓存格式的 small 模型
拷贝到 standalone/bundled_model/（平铺目录，可直接传给 WhisperModel）。

用法：
    python3 prepare_model.py [--size small] [--download]
    --download   若本地缓存不存在则自动从 HuggingFace 下载（CI 环境使用）
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
            f"请先运行 server/run.py 下载 {size} 模型，"
            f"或使用 --download 参数自动下载。"
        )
    with open(refs_main, "r") as f:
        commit = f.read().strip()
    snap = os.path.join(model_dir, "snapshots", commit)
    if not os.path.isdir(snap):
        raise FileNotFoundError(f"找不到 snapshot 目录：{snap}")
    return snap


def download_model(size: str) -> None:
    """从 HuggingFace 下载模型到本地缓存（CI 环境）"""
    print(f"  Downloading {size} model from HuggingFace (~500 MB)...")
    try:
        from faster_whisper import WhisperModel
        os.makedirs(MODELS_ROOT, exist_ok=True)
        m = WhisperModel(size, device="cpu", compute_type="int8",
                         download_root=MODELS_ROOT)
        del m
        print("  [OK] Download complete")
    except Exception as e:
        print(f"  [ERROR] Download failed: {e}", file=sys.stderr)
        sys.exit(1)


def prepare(size: str = "small", auto_download: bool = False) -> None:
    print(f"[*] Preparing {size} model -> {DEST_DIR}")

    # 若本地缓存不存在且允许下载
    refs_file = os.path.join(MODELS_ROOT,
                             f"models--Systran--faster-whisper-{size}",
                             "refs", "main")
    if not os.path.exists(refs_file):
        if auto_download:
            download_model(size)
        else:
            print(f"  [ERROR] Local cache not found: {refs_file}", file=sys.stderr)
            print(f"  Hint: use --download to fetch from HuggingFace", file=sys.stderr)
            sys.exit(1)

    snap_dir = find_snapshot_dir(size)
    print(f"  snapshot: {snap_dir}")

    # 检查所有必需文件
    missing = [f for f in MODEL_FILES if not os.path.exists(os.path.join(snap_dir, f))]
    if missing:
        raise FileNotFoundError(f"Missing files in snapshot: {missing}")

    # 清理旧目录
    if os.path.exists(DEST_DIR):
        print("  Cleaning old bundled_model/...")
        shutil.rmtree(DEST_DIR)
    os.makedirs(DEST_DIR, exist_ok=True)

    # 拷贝文件（follow_symlinks=True，实际拷贝 blob 内容）
    total = 0
    for fname in MODEL_FILES:
        src = os.path.join(snap_dir, fname)
        dst = os.path.join(DEST_DIR, fname)
        print(f"  Copying {fname} ...", end="", flush=True)
        shutil.copy2(src, dst, follow_symlinks=True)
        size_mb = os.path.getsize(dst) / 1024 / 1024
        total  += os.path.getsize(dst)
        print(f" {size_mb:.1f} MB")

    print(f"\n[OK] bundled_model/ ready ({total/1024/1024:.1f} MB total)")
    print(f"     Path: {DEST_DIR}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--size", default="small", help="模型尺寸（默认 small）")
    parser.add_argument("--download", action="store_true",
                        help="本地缓存不存在时自动从 HuggingFace 下载（CI 使用）")
    args = parser.parse_args()
    try:
        prepare(args.size, args.download)
    except Exception as e:
        print(f"\n❌ 错误：{e}", file=sys.stderr)
        sys.exit(1)
