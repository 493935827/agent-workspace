"""本地文件/目录归档打包

python scripts/pack-local.py --paths "D:\config" --output-dir "D:\dest"
python scripts/pack-local.py --paths "D:\logs\*.log" --output-dir "D:\dest"
python scripts/pack-local.py --paths "D:\a\firmware.bin|D:\a\toolchain" --output-dir "D:\dest"
"""

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import ensure_7zr, create_7z, write_readme, print_summary


def parse_args():
    p = argparse.ArgumentParser(description="本地文件/目录归档打包")
    p.add_argument("--paths", required=True, help="路径，多个用 | 分隔，支持通配符")
    p.add_argument("--output-dir", required=True, help="输出目录")
    p.add_argument("--output-name", default="", help="7z 文件名，默认自动生成")
    p.add_argument("--flatten", action="store_true", help="平铺文件（不保留目录结构）")
    return p.parse_args()


def collect_and_copy(paths: str, dest: Path, flatten: bool):
    """解析路径，收集文件并复制到目标目录"""
    items = []
    for raw in paths.split("|"):
        raw = raw.strip()
        p = Path(raw)

        if p.is_dir():
            if flatten:
                for f in p.rglob("*"):
                    if f.is_file():
                        items.append(f)
            else:
                # 复制整个目录
                shutil.copytree(p, dest / p.name, dirs_exist_ok=True)
                print(f"  [目录] {p} -> {dest / p.name}")
                # 返回，因为 copytree 已复制
                continue
        elif p.parent.exists():
            matched = list(p.parent.glob(p.name))
            if matched:
                items.extend(matched)
            else:
                print(f"  [警告] 无匹配: {raw}")
        else:
            print(f"  [警告] 路径不存在: {raw}")

    copied = []
    for f in items:
        f = Path(f)
        if not f.is_file():
            continue
        target = dest / f.name if flatten else dest / f.relative_to(f.anchor)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, target)
        print(f"  [文件] {f} -> {target}")
        copied.append(target)

    if not list(dest.iterdir()):
        print("错误: 没有找到任何文件")
        sys.exit(1)

    return copied


def main():
    args = parse_args()
    out_dir = Path(args.output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    first_name = args.paths.split("|")[0].strip()
    name_part = Path(first_name).stem or "archive"
    output_name = args.output_name or f"{name_part}_archive.7z"

    with tempfile.TemporaryDirectory(prefix="local_", dir=out_dir) as tmp:
        tmp_path = Path(tmp)
        collect_and_copy(args.paths, tmp_path, args.flatten)

        # 统计文件
        all_files = [f for f in tmp_path.rglob("*") if f.is_file()]
        total_size = sum(f.stat().st_size for f in all_files)
        print(f"      共 {len(all_files)} 个文件, {total_size/1024/1024:.1f} MB")

        # 生成目录结构说明
        readme_lines = [
            "[目录结构]",
        ]
        for f in sorted(all_files):
            rel = f.relative_to(tmp_path)
            readme_lines.append(f"  {rel}  ({f.stat().st_size/1024/1024:.1f} MB)")

        root_folder = name_part

        write_readme(tmp_path, f"{name_part} 归档包", readme_lines)

        seven_zr = ensure_7zr()
        output_path = out_dir / output_name
        if output_path.exists():
            output_path.unlink()
        create_7z(seven_zr, output_path, tmp_path, root_folder)

    print_summary(output_path, len(all_files))


if __name__ == "__main__":
    main()
