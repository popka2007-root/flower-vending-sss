"""Display rotation controller for showcase turntable."""

from __future__ import annotations

import logging

from flower_vending.app.fsm import MachineState, StateMachineEngine
from flower_vending.app.services.machine_status_service import MachineStatusService
from flower_vending.devices.interfaces import MotorController


_logger = logging.getLogger(__name__)


class DisplayRotationController:
    def __init__(
        self,
        *,
        motor_controller: MotorController,
        fsm: StateMachineEngine,
        machine_status_service: MachineStatusService | None = None,
    ) -> None:
        self._motor = motor_controller
        self._fsm = fsm
        self._machine_status = machine_status_service
        self._motor_is_on: bool = False

    async def poll_once(self) -> None:
        state_ok = self._fsm.current_state is MachineState.IDLE
        sales_ok = self._machine_status is None or self._machine_status.sales_allowed()
        should_run = state_ok and sales_ok
        if should_run and not self._motor_is_on:
            try:
                await self._motor.start_motion()
            except Exception:
                _logger.exception("display_rotation_start_failed")
                return
            self._motor_is_on = True
            _logger.debug("display_rotation_started")
        elif not should_run and self._motor_is_on:
            try:
                await self._motor.stop_motion()
            except Exception:
                _logger.exception("display_rotation_stop_failed")
                return
            self._motor_is_on = False
            _logger.debug("display_rotation_stopped")
