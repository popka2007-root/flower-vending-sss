"""Qt launcher for the simulator kiosk UI."""

from __future__ import annotations

import asyncio
from pathlib import Path
import sys
from typing import Callable

from flower_vending.runtime.bootstrap import (
    build_simulator_environment,
    resolve_runtime_path,
    validate_config_file,
)
from flower_vending.ui.presenters import KioskPresenter
from flower_vending.ui.views.kiosk_window import KioskMainWindow


_IDLE_TIMEOUT_MS = 60_000


def reset_simulator_state(*, config_path: str) -> tuple[Path, ...]:
    config, _, report = validate_config_file(config_path, prepare_directories=True)
    database_path = resolve_runtime_path(report.state_root, config.persistence.sqlite_path).resolve()
    state_root = report.state_root.resolve()
    if database_path != state_root and not database_path.is_relative_to(state_root):
        raise RuntimeError(f"refusing to reset simulator state outside runtime state root: {database_path}")

    removed: list[Path] = []
    for candidate in (
        database_path,
        database_path.with_name(database_path.name + "-wal"),
        database_path.with_name(database_path.name + "-shm"),
        database_path.with_name(database_path.name + "-journal"),
    ):
        if candidate.exists():
            candidate.unlink()
            removed.append(candidate)
    return tuple(removed)


def run_simulator_ui(*, config_path: str, reset_state: bool = False) -> int:
    try:
        from PySide6.QtCore import QEvent, QObject, QTimer
        from PySide6.QtWidgets import QApplication
    except ImportError as exc:  # pragma: no cover - exercised only when PySide6 is missing
        raise RuntimeError(
            "PySide6 is not installed. Install the UI extra with: python -m pip install -e .[ui]"
        ) from exc

    class InactivityFilter(QObject):
        def __init__(self, *, timeout_ms: int, timeout_callback: Callable[[], None]) -> None:
            super().__init__()
            self._timer = QTimer(self)
            self._timer.setInterval(timeout_ms)
            self._timer.timeout.connect(timeout_callback)
            self._timer.start()

        def eventFilter(self, watched: QObject, event: QEvent) -> bool:
            del watched
            if event.type() in (
                QEvent.Type.MouseButtonPress,
                QEvent.Type.TouchBegin,
                QEvent.Type.TouchUpdate,
            ):
                self._timer.start()
            return False

    if reset_state:
        removed_paths = reset_simulator_state(config_path=config_path)
        if removed_paths:
            print("Reset simulator state:")
            for path in removed_paths:
                print(f"  - {path}")
        else:
            print("Reset simulator state: no existing database files found.")

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    environment = loop.run_until_complete(
        build_simulator_environment(config_path=config_path, prepare_directories=True)
    )
    loop.run_until_complete(environment.start())

    app = QApplication(sys.argv)
    cfg = environment.config
    pm = cfg.machine.payment_methods
    environment.ui_facade._payment_methods = {
        "cash": pm.cash,
        "card": pm.card,
        "qr": pm.qr,
        "sbp": pm.sbp,
    }
    presenter = KioskPresenter(environment.ui_facade)
    window = KioskMainWindow(
        presenter,
        window_title=cfg.ui.window_title,
        service_visible=cfg.machine.service_mode.visible_button,
    )
    environment.ui_facade._on_service_visible_changed = (
        lambda vis: window._catalog_screen.set_service_visible(vis)
    )
    loop.run_until_complete(window.bootstrap())

    inactivity_filter = InactivityFilter(
        timeout_ms=_IDLE_TIMEOUT_MS,
        timeout_callback=window.handle_inactivity_timeout,
    )
    app.installEventFilter(inactivity_filter)

    if environment.config.ui.kiosk_fullscreen:
        window.showFullScreen()
    else:
        window.show()

    timer = QTimer()

    def pump_asyncio() -> None:
        if loop.is_closed():
            timer.stop()
            return
        loop.call_soon(loop.stop)
        loop.run_forever()

    def shutdown() -> None:
        timer.stop()
        if loop.is_closed():
            return
        loop.run_until_complete(environment.stop())
        loop.close()

    timer.timeout.connect(pump_asyncio)
    timer.start(10)
    app.aboutToQuit.connect(shutdown)
    return app.exec()
