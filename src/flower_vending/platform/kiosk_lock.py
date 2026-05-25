"""Kiosk lock/unlock platform abstraction.

Defines the KioskLock protocol that OS-specific implementations
must satisfy, and a software-only SimulatorKioskLock for dev/test.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class KioskLock(ABC):
    """Protocol for kiosk-screen lockdown on the host OS.

    Implementations must provide lock() and unlock() that are safe
    to call multiple times (idempotent).
    """

    @abstractmethod
    async def lock(self) -> None:
        """Enter kiosk lockdown — hide desktop, disable Alt+Tab, etc."""

    @abstractmethod
    async def unlock(self) -> None:
        """Release kiosk lockdown — restore normal desktop interaction."""


class SimulatorKioskLock(KioskLock):
    """Software-only kiosk lock that just logs calls."""

    async def lock(self) -> None:
        logger.info("SimulatorKioskLock: kiosk locked (no OS effect)")

    async def unlock(self) -> None:
        logger.info("SimulatorKioskLock: kiosk unlocked (no OS effect)")
