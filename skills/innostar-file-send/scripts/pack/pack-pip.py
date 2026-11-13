"""Python pip 包下载打包

python scripts/pack-pip.py --packages "pandas" --python-version 3.10 --output-dir "D:\dest"
"""

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import ensure_7zr, create_7z, write_readme, print_summary


def parse_args():
    p = argparse.ArgumentParser(description="pip 包下载打包")
    p.add_argument("--packages", required=True, help="包名，多个空格分隔，如 pandas requests")
    p.add_argument("--python-version", default="3.10", help="Python 版本，默认 3.10")
    p.add_argument("--platform", default="win_amd64", help="目标平台，默认 win_amd64")
    p.add_argument("--output-dir", required=True, help="输出目录")
    p.add_argument("--output-name", default="", help="7z 文件名，默认自动生成")
    p.add_argument("--index-url", default="", help="PyPI 镜像源")
    p.add_argument("--extra-index-url", default="", help="额外 PyPI 源")
    return p.parse_args()


def pip_download(packages, py_ver, platform, out_dir, index_url, extra_index_url):
    parts = py_ver.split(".")
    py_tag = f"cp{parts[0]}{parts[1]}"

    cmd = [
        sys.executable, "-m", "pip", "download",
        *packages.split(),
        "-d", str(out_dir),
        "--only-binary", ":all:",
        "--platform", platform,
        "--python-version", py_ver,
        "--implementation", "cp",
        "--abi", py_tag,
    ]
    if index_url:
        cmd.extend(["--index-url", index_url])
    if extra_index_url:
        cmd.extend(["--extra-index-url", extra_index_url])

    print(f"[下载] {packages}  (Python {py_ver}, {platform})")
    r = subprocess.run(cmd, capture_output=True, text=True)
    print(r.stdout)
    if r.returncode != 0:
        print(r.stderr, file=sys.stderr)
        sys.exit(1)

    whl_files = list(out_dir.glob("*.whl"))
    if not whl_files:
        print("错误: 没有下载到任何 .whl 文件")
        sys.exit(1)
    total = sum(f.stat().st_size for f in whl_files)
    print(f"      下载完成: {len(whl_files)} 个文件, {total/1024/1024:.1f} MB")
    return whl_files


def main():
    args = parse_args()
    out_dir = Path(args.output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    first_pkg = args.packages.split()[0]
    clean_name = first_pkg.split("==")[0].split(">")[0].split("<")[0].split("~")[0]
    py_tag = args.python_version.replace(".", "")
    output_name = args.output_name or f"{clean_name}_py{py_tag}_{args.platform}.7z"
    root_folder = f"{clean_name}_py{py_tag}_{args.platform}"

    with tempfile.TemporaryDirectory(prefix="pypi_", dir=out_dir) as tmp:
        tmp_path = Path(tmp)
        whl_files = pip_download(args.packages, args.python_version, args.platform,
                                  tmp_path, args.index_url, args.extra_index_url)

        install_pkgs = " ".join(
            p.split("==")[0].split(">")[0].split("<")[0].split("~")[0]
            for p in args.packages.split()
        )
        readme_lines = [
            "[安装命令]",
            f"  python -m pip install --no-index --find-links=. {install_pkgs}",
            "",
            "[验证]",
        ]
        for p in install_pkgs.split():
            readme_lines.append(f"  python -c \"import {p.replace('-','_')}; print({p.replace('-','_')}.__version__)\"")
        readme_lines += [
            "",
            f"[目标环境] Python {args.python_version}, 平台 {args.platform}",
            "",
            "[文件列表]",
        ]
        for f in sorted(tmp_path.iterdir()):
            if f.suffix == ".whl":
                readme_lines.append(f"  {f.name}  ({f.stat().st_size/1024/1024:.1f} MB)")

        write_readme(tmp_path, f"{install_pkgs} 离线安装包", readme_lines)

        seven_zr = ensure_7zr()
        output_path = out_dir / output_name
        if output_path.exists():
            output_path.unlink()
        create_7z(seven_zr, output_path, tmp_path, root_folder)

    print_summary(output_path, len(whl_files))


if __name__ == "__main__":
    main()
