"""pack-to-dts 共用工具"""

import os
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path


def ensure_7zr() -> Path:
    """返回 7zr.exe 路径，找不到则自动下载"""
    possible = Path(r"C:\Program Files\7-Zip\7z.exe")
    if possible.exists():
        return possible
    possible = Path(r"C:\Program Files (x86)\7-Zip\7z.exe")
    if possible.exists():
        return possible
    seven_zr = Path(tempfile.gettempdir()) / "7zr.exe"
    if not seven_zr.exists():
        url = "https://www.7-zip.org/a/7zr.exe"
        print("      正在下载 7zr...")
        try:
            urllib.request.urlretrieve(url, seven_zr)
        except Exception as e:
            print(f"      下载 7zr 失败: {e}")
            sys.exit(1)
    return seven_zr


def create_7z(seven_zr: Path, output_path: Path, source_dir: Path, root_folder: str = ""):
    """将 source_dir 下所有文件打包为 7z。root_folder 非空时在包内多套一层文件夹。"""
    if root_folder:
        wrapper = source_dir / root_folder
        wrapper.mkdir(exist_ok=True)
        for item in source_dir.iterdir():
            if item.name == root_folder:
                continue
            item.rename(wrapper / item.name)
        cmd = [str(seven_zr), "a", "-mx=9", str(output_path), str(wrapper)]
    else:
        cmd = [str(seven_zr), "a", "-mx=9", str(output_path), f"{source_dir}\\*"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        sys.exit(1)
    size_mb = output_path.stat().st_size / 1024 / 1024
    print(f"      打包完成: {output_path.name} ({size_mb:.1f} MB)")


def write_readme(work_dir: Path, title: str, lines: list):
    """写使用说明.txt 到 work_dir"""
    content = [
        f"# {title}",
        f"# 生成时间: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
    ]
    content.extend(lines)
    (work_dir / "使用说明.txt").write_text("\n".join(content), encoding="utf-8")
    print("      使用说明已生成")


def print_summary(output_path: Path, file_count: int):
    """打印最终摘要"""
    size_mb = output_path.stat().st_size / 1024 / 1024
    print(f"\n{'='*50}")
    print(f"[完成] 打包成功!")
    print(f"   文件: {output_path}")
    print(f"   大小: {size_mb:.1f} MB")
    print(f"   包含: {file_count} 个文件 + 使用说明")
    print(f"{'='*50}")
