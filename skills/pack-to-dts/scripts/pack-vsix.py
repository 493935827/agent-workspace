"""VS Code 扩展下载打包

python scripts/pack-vsix.py --extensions "ms-python.python" --output-dir "D:\dest"
python scripts/pack-vsix.py --extensions "ms-python.python|ms-python.vscode-pylance" --output-dir "D:\dest"
"""

import argparse
import json
import sys
import tempfile
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import ensure_7zr, create_7z, write_readme, print_summary


def parse_args():
    p = argparse.ArgumentParser(description="VS Code 扩展下载打包")
    p.add_argument("--extensions", required=True, help="扩展 ID，多个用 | 分隔，如 ms-python.python|ms-python.vscode-pylance")
    p.add_argument("--output-dir", required=True, help="输出目录")
    p.add_argument("--output-name", default="", help="7z 文件名，默认自动生成")
    p.add_argument("--version", default="latest", help="版本号，默认 latest")
    return p.parse_args()


def get_latest_version(publisher: str, extension: str) -> str:
    """从 Marketplace API 获取最新版本号"""
    api_url = "https://marketplace.visualstudio.com/_apis/public/gallery/extensionquery?api-version=3.0-preview.1"
    body = json.dumps({
        "filters": [{
            "criteria": [
                {"filterType": 7, "value": f"{publisher}.{extension}"}
            ]
        }],
        "flags": 870
    }).encode()
    req = urllib.request.Request(api_url, data=body, headers={
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        ext = data["results"][0]["extensions"][0]
        version = ext["versions"][0]["version"]
        return version
    except Exception as e:
        print(f"      获取版本信息失败: {e}")
        return ""


def download_vsix(publisher: str, extension: str, version: str, dest: Path) -> Path:
    """下载 VSIX 文件"""
    ext_id = f"{publisher}.{extension}"

    # 如果是 latest，先查版本号
    if version == "latest" or not version:
        v = get_latest_version(publisher, extension)
        if not v:
            print(f"      [错误] 无法获取 {ext_id} 的版本号")
            return None
        version = v

    url = (f"https://marketplace.visualstudio.com/_apis/public/gallery/publishers/"
           f"{publisher}/vsextensions/{extension}/{version}/vspackage")
    filename = f"{ext_id}-{version}.vsix"
    filepath = dest / filename

    print(f"[下载] {ext_id} ({version})")
    try:
        urllib.request.urlretrieve(url, filepath)
    except Exception as e:
        print(f"      下载失败: {e}")
        return None

    size_mb = filepath.stat().st_size / 1024 / 1024
    print(f"      下载完成: {filename} ({size_mb:.1f} MB)")
    return filepath


def main():
    args = parse_args()
    out_dir = Path(args.output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    ext_list = [e.strip() for e in args.extensions.split("|") if e.strip()]
    first_ext = ext_list[0].replace(".", "_")
    output_name = args.output_name or f"{first_ext}_vsix.7z"
    root_folder = first_ext.replace(".", "_")

    with tempfile.TemporaryDirectory(prefix="vsix_", dir=out_dir) as tmp:
        tmp_path = Path(tmp)
        downloaded = []

        for ext_id in ext_list:
            parts = ext_id.split(".")
            publisher = parts[0]
            extension = ".".join(parts[1:])
            f = download_vsix(publisher, extension, args.version, tmp_path)
            if f:
                downloaded.append(f)

        if not downloaded:
            print("错误: 没有成功下载任何扩展")
            sys.exit(1)

        readme_lines = [
            "[安装命令]",
        ]
        for f in sorted(downloaded):
            readme_lines.append(f"  code --install-extension {f.name}")
        readme_lines += [
            "",
            "或在 VS Code 扩展面板 → ... → 从 VSIX 安装",
            "",
            "[文件列表]",
        ]
        for f in sorted(tmp_path.iterdir()):
            if f.is_file() and f.name != "使用说明.txt":
                readme_lines.append(f"  {f.name}  ({f.stat().st_size/1024/1024:.1f} MB)")

        write_readme(tmp_path, "VS Code 扩展离线包", readme_lines)

        seven_zr = ensure_7zr()
        output_path = out_dir / output_name
        if output_path.exists():
            output_path.unlink()
        create_7z(seven_zr, output_path, tmp_path, root_folder)

    print_summary(output_path, len(downloaded))


if __name__ == "__main__":
    main()
