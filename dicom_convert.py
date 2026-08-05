#!/usr/bin/env python3
"""
DICOM 序列转 MP4 工具
支持: 递归搜索、大写.DCM、含空格路径、自动窗宽窗位、按InstanceNumber排序
用法: python3 dicom_convert.py -i ./input/C252708 -o ./output/20260805 -f mp4
"""

import argparse
import os
import sys
import re
from pathlib import Path

# ===================== 依赖自动安装 =====================
REQUIRED_PACKAGES = {
    "numpy": "numpy",
    "pydicom": "pydicom",
    "imageio": "imageio[ffmpeg]",  # imageio-ffmpeg 是生成mp4的关键
}

def check_and_install_dependencies():
    missing = []
    for module, package in REQUIRED_PACKAGES.items():
        try:
            __import__(module)
        except ImportError:
            missing.append(package)

    if missing:
        print("发现缺失依赖：")
        for pkg in missing:
            print(f"  - {pkg}")
        print("\n开始自动安装...")
        import subprocess
        cmd = [sys.executable, "-m", "pip", "install"] + missing
        subprocess.check_call(cmd)
        print()

check_and_install_dependencies()

import numpy as np
import pydicom
import imageio

# ===================== 核心功能 =====================

def find_dicom_files(root_dir):
    """递归查找所有DICOM文件，兼容大写后缀、空格路径及非标准文件"""
    dicom_files = []
    root_path = Path(root_dir)

    if not root_path.exists():
        print(f"❌ 输入目录不存在: {root_dir}")
        return []

    for fpath in sorted(root_path.rglob('*')):
        if fpath.is_file() and fpath.suffix.upper() == '.DCM':
            try:
                ds = pydicom.dcmread(str(fpath), force=True)
                if hasattr(ds, 'pixel_array'):
                    dicom_files.append((fpath, ds))
            except Exception as e:
                print(f"⚠️ 跳过无效文件 {fpath.name}: {e}")

    return dicom_files


def get_instance_number(ds):
    """从DICOM中提取实例编号用于排序"""
    # 优先使用 InstanceNumber (0020,0013)
    if hasattr(ds, 'InstanceNumber') and ds.InstanceNumber is not None:
        try:
            return int(ds.InstanceNumber)
        except (ValueError, TypeError):
            pass
    # 回退到 ImagePositionPatient 的 Z 轴
    if hasattr(ds, 'ImagePositionPatient'):
        try:
            return float(ds.ImagePositionPatient[2])
        except (IndexError, ValueError, TypeError):
            pass
    return 0


def apply_window(pixel_data, ds):
    """应用窗宽窗位变换，支持从DICOM标签或文件名提取"""
    pixel = pixel_data.astype(np.float64)

    # 尝试从 DICOM tag 获取
    wc = getattr(ds, 'WindowCenter', None)
    ww = getattr(ds, 'WindowWidth', None)

    # 如果tag中没有，尝试从文件名解析 W2000L600 格式
    if wc is None or ww is None:
        fname = str(getattr(ds, 'filename', ''))
        match = re.search(r'[Ww](\d+)[Ll](-?\d+)', fname)
        if match:
            ww = float(match.group(1))
            wc = float(match.group(2))
            print(f"  📐 从文件名提取窗宽窗位: W={ww}, L={wc}")

    if wc is not None and ww is not None:
        # 处理多值情况
        if isinstance(wc, pydicom.multival.MultiValue):
            wc = float(wc[0])
        if isinstance(ww, pydicom.multival.MultiValue):
            ww = float(ww[0])
        wc, ww = float(wc), float(ww)

        lower = wc - ww / 2.0
        upper = wc + ww / 2.0
        pixel = np.clip(pixel, lower, upper)
        pixel = ((pixel - lower) / (upper - lower) * 255).astype(np.uint8)
    else:
        # 无窗宽窗位信息时做简单归一化
        pmin, pmax = pixel.min(), pixel.max()
        if pmax > pmin:
            pixel = ((pixel - pmin) / (pmax - pmin) * 255).astype(np.uint8)
        else:
            pixel = np.zeros_like(pixel, dtype=np.uint8)
        print("  ⚠️ 未找到窗宽窗位，已使用自动归一化")

    return pixel


def convert_series(dicom_pairs, output_path, fps=10):
    """将一个DICOM序列转换为MP4"""
    dicom_pairs.sort(key=lambda x: get_instance_number(x[1]))

    frames = []
    total = len(dicom_pairs)
    print(f"  📄 共 {total} 帧，正在处理...")

    for idx, (fpath, ds) in enumerate(dicom_pairs):
        pixel = ds.pixel_array
        frame = apply_window(pixel, ds)

        # 灰度转RGB
        if frame.ndim == 2:
            frame = np.stack([frame] * 3, axis=-1)

        # ✅ 关键修复：确保宽高均为偶数（libx264 硬性要求）
        h, w = frame.shape[:2]
        if h % 2 != 0 or w % 2 != 0:
            new_h = h + (h % 2)
            new_w = w + (w % 2)
            padded = np.zeros((new_h, new_w, 3), dtype=np.uint8)
            padded[:h, :w, :] = frame
            frame = padded

        frames.append(frame)

        if (idx + 1) % 20 == 0 or idx == total - 1:
            print(f"    进度: {idx + 1}/{total}")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    writer = imageio.get_writer(
        str(output_path),
        fps=fps,
        codec='libx264',
        quality=8,
        pixelformat='yuv420p',
        macro_block_size=1,
    )
    for frame in frames:
        writer.append_data(frame)
    writer.close()

    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"  ✅ 已保存: {output_path} ({size_mb:.1f} MB)")


# ===================== 主流程 =====================

def main():
    parser = argparse.ArgumentParser(description="DICOM序列转MP4")
    parser.add_argument("-i", "--input", required=True, help="DICOM输入目录")
    parser.add_argument("-o", "--output", required=True, help="MP4输出目录")
    parser.add_argument("-f", "--format", default="mp4", choices=["mp4"], help="输出格式")
    parser.add_argument("--fps", type=int, default=10, help="视频帧率 (默认10)")
    args = parser.parse_args()

    input_dir = Path(args.input)
    output_dir = Path(args.output)

    # 按患者ID -> 序列 两级分组
    all_files = find_dicom_files(input_dir)
    if not all_files:
        print("❌ 未找到任何有效DICOM文件")
        sys.exit(1)

    # 按 SeriesInstanceUID 分组
    series_map = {}
    for fpath, ds in all_files:
        uid = getattr(ds, 'SeriesInstanceUID', 'unknown')
        series_map.setdefault(uid, []).append((fpath, ds))

    print(f"\n🔍 发现 {len(series_map)} 个序列\n")

    for sid, pairs in series_map.items():
        # 尝试获取序列描述作为文件名
        desc = getattr(pairs[0][1], 'SeriesDescription', None) or sid[:12]
        safe_name = re.sub(r'[^\w\-]', '_', desc.strip())
        out_file = output_dir / f"{safe_name}.mp4"

        print(f"{'='*40}")
        print(f"📁 序列: {desc}")
        print(f"   UID:  {sid}")
        convert_series(pairs, out_file, fps=args.fps)

    print(f"\n🎉 全部完成！输出目录: {output_dir}")


if __name__ == "__main__":
    main()
