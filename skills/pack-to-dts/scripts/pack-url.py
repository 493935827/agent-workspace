"""URL / 文件下载打包

python scripts/pack-url.py --urls "https://example.com/file.zip" --output-dir "D:\dest"
python scripts/pack-url.py --urls "https://site.com/a.exe|https://site.com/b.msi" --output-dir "D:\dest"
"""

import argparse
import os
import sys
import tempfile
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).parent))
from common import ensure_7zr, create_7z, write_readme, print_summary


def parse_args():
    p = argparse.ArgumentParser(description="URL 文件下载打包")
    p.add_argument("--urls", required=True, help="下载链接，多个用 | 分隔")
    p.add_argument("--output-dir", required=True, help="输出目录")
    p.add_argument("--output-name", default="", help="7z 文件名，默认自动生成")
    p.add_argument("--rename", default="", help="重命名下载后的文件（仅单文件时有效）")
    return p.parse_args()


def download_file(url: str, dest: Path):
    """下载单个文件"""
    parsed = urlparse(url)
    filename = os.path.basename(parsed.path) or "downloaded_file"
    filepath = dest / filename

    print(f"[下载] {filename}")
    print(f"      来源: {url}")
    try:
        urllib.request.urlretrieve(url, filepath)
    except Exception as e:
        print(f"      下载失败: {e}")
        return None

    size_mb = filepath.stat().st_size / 1024 / 1024
    print(f"      下载完成: {filename} ({size_mb:.1f} MB)")
    return filepath


def download_github_release(repo: str, pattern: str, dest: Path):
    """从 GitHub Release 下载匹配的文件"""
    import subprocess
    import json

    api_url = f"https://api.github.com/repos/{repo}/releases/latest"
    print(f"[GitHub] 获取 {repo} 最新 Release...")
    try:
        req = urllib.request.Request(api_url, headers={"User-Agent": "pack-to-dts"})
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        print(f"      获取 Release 信息失败: {e}")
        return []

    tag = data.get("tag_name", "")
    print(f"      版本: {tag}")
    assets = data.get("assets", [])
    downloaded = []
    for asset in assets:
        name = asset["name"]
        if pattern and pattern not in name:
            continue
        dl_url = asset["browser_download_url"]
        filepath = dest / name
        print(f"      下载: {name}")
        try:
            urllib.request.urlretrieve(dl_url, filepath)
            size_mb = filepath.stat().st_size / 1024 / 1024
            print(f"        -> ({size_mb:.1f} MB)")
            downloaded.append(filepath)
        except Exception as e:
            print(f"        -> 失败: {e}")

    return downloaded


def main():
    args = parse_args()
    out_dir = Path(args.output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    urls = [u.strip() for u in args.urls.split("|") if u.strip()]
    output_name = args.output_name or "downloaded_files.7z"

    with tempfile.TemporaryDirectory(prefix="url_", dir=out_dir) as tmp:
        tmp_path = Path(tmp)
        downloaded_files = []

        for url in urls:
            # 检查 GitHub Release 格式: gh:owner/repo:pattern
            if url.startswith("gh:") or url.startswith("github:"):
                parts = url.replace("gh:", "").replace("github:", "").split(":", 1)
                repo = parts[0]
                pattern = parts[1] if len(parts) > 1 else ""
                files = download_github_release(repo, pattern, tmp_path)
                downloaded_files.extend(files)
            else:
                f = download_file(url, tmp_path)
                if f:
                    downloaded_files.append(f)

        if not downloaded_files:
            print("错误: 没有成功下载任何文件")
            sys.exit(1)

        # 重命名（仅单文件）
        if args.rename and len(downloaded_files) == 1:
            old = downloaded_files[0]
            new = old.with_name(args.rename)
            old.rename(new)
            downloaded_files[0] = new

        # root_folder: 用第一个文件名推导
        root_folder = ""
        if downloaded_files:
            first_name = downloaded_files[0].stem
            root_folder = first_name[:40]

        readme_lines = [
            "[文件来源]",
        ]
        for url in urls:
            readme_lines.append(f"  {url}")
        readme_lines += [
            "",
            "[文件列表]",
        ]
        for f in sorted(tmp_path.iterdir()):
            if f.is_file() and f.name != "使用说明.txt":
                readme_lines.append(f"  {f.name}  ({f.stat().st_size/1024/1024:.1f} MB)")

        write_readme(tmp_path, "下载文件包", readme_lines)

        seven_zr = ensure_7zr()
        output_path = out_dir / output_name
        if output_path.exists():
            output_path.unlink()
        create_7z(seven_zr, output_path, tmp_path, root_folder)

    print_summary(output_path, len(downloaded_files))


if __name__ == "__main__":
    main()
