from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout

from tests._support import make_temp_simulator_runtime, workspace_temp_dir

from flower_vending.runtime import cli


class OperatorObservabilityCliTests(unittest.IsolatedAsyncioTestCase):
    async def test_status_json_reads_persisted_sqlite_state(self) -> None:
        with workspace_temp_dir(prefix="status-cli-") as tmp:
            runtime = make_temp_simulator_runtime(tmp)
            environment = await runtime.build()
            await environment.start()
            await environment.stop()

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = cli.main(
                    [
                        "status",
                        "--config",
                        str(runtime.config_path),
                        "--json",
                    ]
                )

            payload = json.loads(stdout.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["machine_id"], "flower-vending-sim-01")
            self.assertEqual(payload["machine"]["machine_state"], "IDLE")
            self.assertEqual(payload["machine"]["sale_blockers"], [])
            self.assertEqual(payload["unresolved_transactions"], [])
            self.assertEqual(payload["unresolved_intents"], [])
            self.assertEqual(payload["unacknowledged_faults"], [])
            self.assertEqual(payload["money_inventory"]["currency_code"], "RUB")

    async def test_events_limit_reads_recent_persisted_events(self) -> None:
        with workspace_temp_dir(prefix="events-cli-") as tmp:
            runtime = make_temp_simulator_runtime(tmp)
            environment = await runtime.build()
            await environment.start()
            try:
                await environment.simulator_controls.execute_action(
                    "open_service_door",
                    correlation_id="events-cli-correlation",
                )
            finally:
                await environment.stop()

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = cli.main(
                    [
                        "events",
                        "--config",
                        str(runtime.config_path),
                        "--limit",
                        "2",
                        "--json",
                    ]
                )

            payload = json.loads(stdout.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["limit"], 2)
            self.assertLessEqual(len(payload["events"]), 2)
            self.assertTrue(
                any(
                    event["correlation_id"] == "events-cli-correlation"
                    for event in payload["events"]
                )
            )


if __name__ == "__main__":
    unittest.main()
