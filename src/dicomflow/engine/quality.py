from __future__ import annotations

from dataclasses import dataclass

from dicomflow.core.models import Quality


@dataclass(frozen=True)
class QualityProfile:
    scale: float  # 1.0 = original
    max_side: int | None
    mp4_crf: int
    gif_max_side: int
    gif_max_frames: int
    gif_colors: int
    fps_cap: int | None


PROFILES: dict[Quality, QualityProfile] = {
    Quality.LOW: QualityProfile(
        scale=0.5,
        max_side=None,
        mp4_crf=28,
        gif_max_side=256,
        gif_max_frames=80,
        gif_colors=64,
        fps_cap=8,
    ),
    Quality.MEDIUM: QualityProfile(
        scale=1.0,
        max_side=1024,
        mp4_crf=23,
        gif_max_side=480,
        gif_max_frames=120,
        gif_colors=128,
        fps_cap=None,
    ),
    Quality.HIGH: QualityProfile(
        scale=1.0,
        max_side=None,
        mp4_crf=18,
        gif_max_side=640,
        gif_max_frames=150,
        gif_colors=256,
        fps_cap=None,
    ),
}


def get_profile(quality: Quality) -> QualityProfile:
    return PROFILES[quality]
