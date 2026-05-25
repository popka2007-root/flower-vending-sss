"""Allowed machine-state transitions."""

from __future__ import annotations

from flower_vending.app.fsm.states import MachineState


ALLOWED_TRANSITIONS: dict[MachineState, set[MachineState]] = {
    MachineState.BOOT: {MachineState.SELF_TEST, MachineState.FAULT},
    MachineState.SELF_TEST: {
        MachineState.IDLE,
        MachineState.RECOVERY_PENDING,
        MachineState.OUT_OF_SERVICE,
        MachineState.FAULT,
    },
    MachineState.IDLE: {
        MachineState.PRODUCT_SELECTED,
        MachineState.SERVICE_MODE,
        MachineState.OUT_OF_SERVICE,
        MachineState.FAULT,
    },
    MachineState.PRODUCT_SELECTED: {
        MachineState.CHECKING_AVAILABILITY,
        MachineState.CANCELLED,
        MachineState.FAULT,
    },
    MachineState.CHECKING_AVAILABILITY: {
        MachineState.CHECKING_CHANGE,
        MachineState.CANCELLED,
        MachineState.OUT_OF_SERVICE,
        MachineState.FAULT,
    },
    MachineState.CHECKING_CHANGE: {
        MachineState.WAITING_FOR_PAYMENT,
        MachineState.CANCELLED,
        MachineState.OUT_OF_SERVICE,
    },
    MachineState.WAITING_FOR_PAYMENT: {
        MachineState.ACCEPTING_CASH,
        MachineState.CANCELLED,
        MachineState.FAULT,
        MachineState.OUT_OF_SERVICE,
    },
    MachineState.ACCEPTING_CASH: {
        MachineState.PAYMENT_ACCEPTED,
        MachineState.CANCELLED,
        MachineState.FAULT,
        MachineState.OUT_OF_SERVICE,
        MachineState.RECOVERY_PENDING,
        MachineState.REFUND,
    },
    MachineState.PAYMENT_ACCEPTED: {
        MachineState.DISPENSING_CHANGE,
        MachineState.DISPENSING_PRODUCT,
        MachineState.FAULT,
        MachineState.RECOVERY_PENDING,
    },
    MachineState.DISPENSING_CHANGE: {
        MachineState.DISPENSING_PRODUCT,
        MachineState.FAULT,
        MachineState.RECOVERY_PENDING,
    },
    MachineState.DISPENSING_PRODUCT: {
        MachineState.OPENING_DELIVERY_WINDOW,
        MachineState.FAULT,
        MachineState.RECOVERY_PENDING,
        MachineState.REFUND,
    },
    MachineState.OPENING_DELIVERY_WINDOW: {
        MachineState.WAITING_FOR_CUSTOMER_PICKUP,
        MachineState.FAULT,
        MachineState.RECOVERY_PENDING,
    },
    MachineState.WAITING_FOR_CUSTOMER_PICKUP: {
        MachineState.CLOSING_DELIVERY_WINDOW,
        MachineState.FAULT,
        MachineState.RECOVERY_PENDING,
    },
    MachineState.CLOSING_DELIVERY_WINDOW: {
        MachineState.COMPLETED,
        MachineState.FAULT,
        MachineState.RECOVERY_PENDING,
    },
    MachineState.COMPLETED: {MachineState.IDLE, MachineState.OUT_OF_SERVICE},
    MachineState.CANCELLED: {MachineState.IDLE, MachineState.OUT_OF_SERVICE, MachineState.REFUND},
    MachineState.OUT_OF_SERVICE: {
        MachineState.SERVICE_MODE,
        MachineState.IDLE,
        MachineState.RECOVERY_PENDING,
    },
    MachineState.FAULT: {
        MachineState.IDLE,
        MachineState.OUT_OF_SERVICE,
        MachineState.SERVICE_MODE,
        MachineState.RECOVERY_PENDING,
    },
    MachineState.SERVICE_MODE: {
        MachineState.OUT_OF_SERVICE,
        MachineState.IDLE,
        MachineState.FAULT,
        MachineState.RECOVERY_PENDING,
    },
    MachineState.REFUND: {
        MachineState.CANCELLED,
        MachineState.MANUAL_REVIEW,
        MachineState.FAULT,
        MachineState.RECOVERY_PENDING,
    },
    MachineState.MANUAL_REVIEW: {
        MachineState.IDLE,
        MachineState.OUT_OF_SERVICE,
        MachineState.FAULT,
        MachineState.SERVICE_MODE,
        MachineState.RECOVERY_PENDING,
    },
    MachineState.RECOVERY_PENDING: {
        MachineState.IDLE,
        MachineState.OUT_OF_SERVICE,
        MachineState.FAULT,
        MachineState.SERVICE_MODE,
    },
}
