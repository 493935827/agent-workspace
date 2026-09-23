"""npm 包下载打包

python scripts/pack-npm.py --packages "react lodash" --output-dir "D:\dest"
python scripts/pack-npm.py --packages "express@4.18" --output-dir "D:\dest"
"""

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import ensure_7zr, create_7z, write_readme, print_summary


def parse_args():
    p = argparse.ArgumentParser(description="npm 包下载打包")
    p.add_argument("--packages", required=True, help="包名，多个空格分隔，如 react lodash")
    p.add_argument("--registry", default="", help="npm registry 地址")
    p.add_argument("--output-dir", required=True, help="输出目录")
    p.add_argument("--output-name", default="", help="7z 文件名，默认自动生成")
    return p.parse_args()


def npm_pack(packages, registry, work_dir):
    """对每个包执行 npm pack，下载到 work_dir"""
    import platform
    npm_cmd = "npm.cmd" if platform.system() == "Windows" else "npm"
    downloaded = []
    for pkg in packages.split():
        cmd = [npm_cmd, "pack", pkg, "--pack-destination", str(work_dir)]
        if registry:
            cmd.extend(["--registry", registry])

        print(f"[下载] npm 包: {pkg}")
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            print(r.stderr, file=sys.stderr)
            print(f"      跳过 {pkg}")
            continue

        # npm pack 输出文件名到 stdout
        for line in r.stdout.strip().splitlines():
            line = line.strip()
            if line.endswith(".tgz"):
                downloaded.append(work_dir / line)
                size = (work_dir / line).stat().st_size
                print(f"      下载完成: {line} ({size/1024/1024:.1f} MB)")

    if not downloaded:
        print("错误: 没有下载到任何包")
        sys.exit(1)
    return downloaded


def main():
    args = parse_args()
    out_dir = Path(args.output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    first_pkg = args.packages.split()[0].split("@")[0]
    output_name = args.output_name or f"{first_pkg}_offline.7z"

    with tempfile.TemporaryDirectory(prefix="npm_", dir=out_dir) as tmp:
        tmp_path = Path(tmp)
        tgz_files = npm_pack(args.packages, args.registry, tmp_path)

        pkg_names = " ".join(p.split("@")[0] for p in args.packages.split())
        root_folder = f"{first_pkg}_npm_offline"

        readme_lines = [
            "[安装命令]",
            f"  npm install {pkg_names}",
            "",
            "[在项目中使用]",
            f"  将 .tgz 文件放到项目目录，在 package.json 中引用或执行:",
            *[f"  npm install ./{f.name}" for f in tgz_files],
            "",
            "[文件列表]",
        ]
        for f in sorted(tmp_path.iterdir()):
            if f.suffix == ".tgz":
                readme_lines.append(f"  {f.name}  ({f.stat().st_size/1024/1024:.1f} MB)")

        write_readme(tmp_path, f"{args.packages} npm 离线包", readme_lines)

        seven_zr = ensure_7zr()
        output_path = out_dir / output_name
        if output_path.exists():
            output_path.unlink()
        create_7z(seven_zr, output_path, tmp_path, root_folder)

    print_summary(output_path, len(tgz_files))


if __name__ == "__main__":
    main()
