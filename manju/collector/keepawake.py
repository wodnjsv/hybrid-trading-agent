"""크로스플랫폼 절전 방지. 무인 수집 박스(특히 Windows)가 장중 잠들지 않게 한다.

Windows: SetThreadExecutionState로 시스템 절전 억제.
그 외 OS(macOS/Linux): no-op (절전 제어는 caffeinate 등 OS 도구로).
"""
from __future__ import annotations
import sys
import logging

logger = logging.getLogger(__name__)

_ES_CONTINUOUS = 0x80000000
_ES_SYSTEM_REQUIRED = 0x00000001


class keep_awake:
    """컨텍스트 매니저. 진입 시 절전 억제, 종료 시 원복."""

    def __enter__(self) -> "keep_awake":
        if sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.kernel32.SetThreadExecutionState(
                    _ES_CONTINUOUS | _ES_SYSTEM_REQUIRED)
                logger.info("Windows 절전 방지 활성화")
            except Exception as e:                       # noqa: BLE001
                logger.warning("절전 방지 설정 실패: %s", e)
        return self

    def __exit__(self, *exc) -> None:
        if sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.kernel32.SetThreadExecutionState(_ES_CONTINUOUS)
            except Exception:                            # noqa: BLE001
                pass
