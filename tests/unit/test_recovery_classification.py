"""Tests for recovery intent classification logic."""

from __future__ import annotations

import unittest

from flower_vending.app.orchestrators.recovery_manager import classify_intent

_MANUAL_REVIEW_ACTIONS = (
    "motor_vend_requested",
    "window_open_requested",
    "window_close_requested",
    "refund_dispense_requested",
    "change_dispense_requested",
    "inventory_decrement",
)

_CANCEL_SAFE_ACTIONS = (
    "acceptance_disable_requested",
    "some_random_action",
    "",
)


class ClassifyIntentTests(unittest.TestCase):
    def test_manual_review_actions(self) -> None:
        for action_name in _MANUAL_REVIEW_ACTIONS:
            with self.subTest(action_name=action_name):
                result = classify_intent(action_name)
                self.assertEqual(result, "manual_review_required")

    def test_cancel_safe_actions(self) -> None:
        for action_name in _CANCEL_SAFE_ACTIONS:
            with self.subTest(action_name=action_name):
                result = classify_intent(action_name)
                self.assertEqual(result, "cancel_safe")

    def test_inventory_decrement_is_manual_review(self) -> None:
        result = classify_intent("inventory_decrement")
        self.assertEqual(result, "manual_review_required")
