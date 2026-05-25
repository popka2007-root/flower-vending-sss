"""Command-line entrypoints for simulator-safe workflows."""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from flower_vending.devices.dbv300sd.bench import DBV300SDSerialSmokeBench, parse_hex_bytes
from flower_vending.devices.dbv300sd.config import SerialTransportSettings
from flower_vending.devices.exceptions import DeviceAdapterError
from flower_vending.runtime.bootstrap import (
    BootstrapReport,
    build_simulator_environment,
    discover_project_root,
    read_runtime_events,
    read_runtime_status,
    validate_config_file,
)
from flower_vending.runtime.discover import discover_arduino, format_discovery, list_com_ports
from flower_vending.runtime.production import build_production_environment
from flower_vending.simulators.scenarios.catalog import run_default_scenario_suite


def build_parser() -> argparse.ArgumentParser:
    project_root = discover_project_root()
    default_config = project_root / "config" / "examples" / "machine.simulator.yaml"

    parser = argparse.ArgumentParser(prog="python -m flower_vending")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_config_argument(target: argparse.ArgumentParser) -> None:
        target.add_argument(
            "--config",
            default=str(default_config),
            help="Path to the YAML configuration file.",
        )
        target.add_argument(
            "--json",
            action="store_true",
            help="Render the command output as JSON.",
        )

    validate_parser = subparsers.add_parser(
        "validate-config", help="Validate configuration and bootstrap checks."
    )
    add_config_argument(validate_parser)
    validate_parser.add_argument(
        "--prepare",
        action="store_true",
        help="Create runtime directories such as var/data and var/log when they are missing.",
    )

    diagnostics_parser = subparsers.add_parser(
        "diagnostics", help="Start simulator runtime and print diagnostics."
    )
    add_config_argument(diagnostics_parser)

    status_parser = subparsers.add_parser(
        "status", help="Read persisted machine status from SQLite."
    )
    add_config_argument(status_parser)

    events_parser = subparsers.add_parser(
        "events", help="Read recent persisted events from SQLite."
    )
    add_config_argument(events_parser)
    events_parser.add_argument(
        "--limit",
        type=_positive_int,
        default=50,
        help="Maximum number of recent events to render.",
    )

    clear_drift_parser = subparsers.add_parser(
        "clear-drift", help="Clear the drift_detected flag on money inventory."
    )
    add_config_argument(clear_drift_parser)

    service_parser = subparsers.add_parser(
        "service", help="Enter service mode and print a service snapshot."
    )
    add_config_argument(service_parser)
    service_parser.add_argument(
        "--operator", default="technician", help="Service operator identifier."
    )
    service_parser.add_argument("--pin", default="0000", help="4-digit service PIN.")
    service_parser.add_argument(
        "--lock-purchase",
        action="store_true",
        help="Lock purchase button in service mode.",
    )
    service_parser.add_argument(
        "--action",
        action="append",
        default=[],
        help="Optional simulator action to apply before printing the service report.",
    )

    runtime_parser = subparsers.add_parser(
        "simulator-runtime", help="Run simulator runtime or deterministic scenarios."
    )
    add_config_argument(runtime_parser)
    runtime_parser.add_argument(
        "--duration",
        type=float,
        default=0.0,
        help="Keep the runtime alive for the given number of seconds before shutting down.",
    )
    runtime_parser.add_argument(
        "--scenario",
        action="append",
        default=[],
        help="Deterministic scenario name to run. May be passed multiple times.",
    )
    runtime_parser.add_argument(
        "--use-config-scenarios",
        action="store_true",
        help="Run the scenario suite listed in config.simulator.scenario_suite.",
    )

    ui_parser = subparsers.add_parser("simulator-ui", help="Launch the simulator kiosk UI.")
    ui_parser.add_argument(
        "--config",
        default=str(default_config),
        help="Path to the YAML configuration file.",
    )
    ui_parser.add_argument(
        "--reset-state",
        action="store_true",
        help="Delete the simulator SQLite state database before launching the UI.",
    )

    bench_parser = subparsers.add_parser(
        "dbv300sd-serial-smoke",
        help="Open DBV-300-SD serial transport and optionally exchange explicit raw bytes.",
    )
    bench_parser.add_argument("--port", required=True, help="Serial port path, for example COM3.")
    bench_parser.add_argument("--baudrate", type=int, default=9600, help="Serial baud rate.")
    bench_parser.add_argument("--bytesize", type=int, default=8, help="Serial byte size.")
    bench_parser.add_argument("--parity", default="N", help="Serial parity.")
    bench_parser.add_argument("--stopbits", type=int, default=1, help="Serial stop bits.")
    bench_parser.add_argument("--read-timeout-s", type=float, default=0.2, help="Read timeout.")
    bench_parser.add_argument("--write-timeout-s", type=float, default=0.2, help="Write timeout.")
    bench_parser.add_argument(
        "--trace-log",
        default=str(project_root / "var" / "log" / "dbv300sd-bench-trace.jsonl"),
        help="Dedicated JSONL bench log for serial settings and raw rx/tx frames.",
    )
    bench_parser.add_argument(
        "--tx-hex",
        help="Explicit raw bytes to transmit, e.g. '01 02 FF'. No bytes are sent if omitted.",
    )
    bench_parser.add_argument(
        "--read-size",
        type=int,
        default=0,
        help="Read this many bytes after --tx-hex is written. Requires --tx-hex.",
    )
    bench_parser.add_argument("--correlation-id", help="Optional trace correlation id.")
    bench_parser.add_argument("--note", help="Optional trace note.")
    bench_parser.add_argument(
        "--json",
        action="store_true",
        help="Render the command output as JSON.",
    )

    discover_parser = subparsers.add_parser(
        "discover", help="Discover COM ports and connected hardware."
    )
    discover_parser.add_argument(
        "--json",
        action="store_true",
        help="Render the command output as JSON.",
    )

    run_parser = subparsers.add_parser("run", help="Start production runtime with real hardware.")
    add_config_argument(run_parser)
    run_parser.add_argument(
        "--duration",
        type=float,
        default=0.0,
        help="Keep running for N seconds then exit (0 = forever until Ctrl+C).",
    )
    run_parser.add_argument(
        "--no-ui",
        action="store_true",
        help="Run without UI (headless mode).",
    )

    printer_parser = subparsers.add_parser("printer-test", help="Print a test receipt.")
    printer_parser.add_argument("--port", help="Printer COM port (auto-discover if omitted).")
    printer_parser.add_argument("--baudrate", type=int, default=19200, help="Printer baud rate.")

    analyze_parser = subparsers.add_parser(
        "dbv300sd-analyze",
        help="Analyze DBV-300-SD protocol by probing different frame formats.",
    )
    analyze_parser.add_argument("--port", required=True, help="Serial port (e.g. COM3).")
    analyze_parser.add_argument("--timeout", type=float, default=0.5, help="Per-probe timeout.")
    analyze_parser.add_argument(
        "--read-size", type=int, default=32, help="Bytes to read per probe."
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "validate-config":
        return _command_validate_config(args)
    if args.command == "diagnostics":
        return asyncio.run(_command_diagnostics(args))
    if args.command == "status":
        return _command_status(args)
    if args.command == "events":
        return _command_events(args)
    if args.command == "clear-drift":
        return asyncio.run(_command_clear_drift(args))
    if args.command == "service":
        return asyncio.run(_command_service(args))
    if args.command == "simulator-runtime":
        return asyncio.run(_command_simulator_runtime(args))
    if args.command == "simulator-ui":
        from flower_vending.runtime.ui_runner import run_simulator_ui

        return run_simulator_ui(config_path=args.config, reset_state=args.reset_state)
    if args.command == "dbv300sd-serial-smoke":
        return asyncio.run(_command_dbv300sd_serial_smoke(args, parser))
    if args.command == "discover":
        return asyncio.run(_command_discover(args))
    if args.command == "run":
        return asyncio.run(_command_run(args))
    if args.command == "printer-test":
        return asyncio.run(_command_printer_test(args))
    if args.command == "dbv300sd-analyze":
        return asyncio.run(_command_dbv300sd_analyze(args))
    parser.error(f"unsupported command: {args.command}")


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def _command_validate_config(args: argparse.Namespace) -> int:
    config, _, report = validate_config_file(args.config, prepare_directories=args.prepare)
    payload = {
        "valid": report.valid,
        "machine_id": config.machine.machine_id,
        "resource_root": str(report.project_root),
        "state_root": str(report.state_root),
        "created_directories": [str(path) for path in report.created_directories],
        "messages": [asdict(message) for message in report.messages],
        "platform": report.platform_profile.target_os,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        _print_report(report)
    return 0 if report.valid else 1


async def _command_diagnostics(args: argparse.Namespace) -> int:
    environment = await build_simulator_environment(
        config_path=args.config, prepare_directories=True
    )
    await environment.start()
    try:
        payload = environment.diagnostics_report()
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(_format_diagnostics(payload))
        return 0
    finally:
        await environment.stop()


def _command_status(args: argparse.Namespace) -> int:
    payload = read_runtime_status(args.config)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(_format_status(payload))
    return 0


def _command_events(args: argparse.Namespace) -> int:
    payload = read_runtime_events(args.config, limit=args.limit)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(_format_events(payload))
    return 0


async def _command_service(args: argparse.Namespace) -> int:
    from flower_vending.runtime.bootstrap import validate_config_file

    config, _, _ = validate_config_file(args.config)
    pin = config.machine.service_mode.pin

    environment = await build_simulator_environment(
        config_path=args.config, prepare_directories=True
    )
    await environment.start()
    try:
        cid = environment.ui_facade.new_correlation_id()
        try:
            await environment.ui_facade.enter_service_mode(
                operator_id=args.operator,
                correlation_id=cid,
                pin=args.pin or pin,
            )
        except ValueError:
            print("Error: Invalid service PIN")
            return 1

        if args.lock_purchase:
            await environment.ui_facade.lock_purchase_button(
                operator_id=args.operator,
                locked=True,
                correlation_id=cid,
            )

        for action_id in args.action:
            await environment.simulator_controls.execute_action(
                action_id,
                correlation_id=cid,
            )

        d = environment.ui_facade.diagnostics_snapshot()
        payload = {
            "operator_id": args.operator,
            "machine_state": d.machine.machine_state,
            "sale_blockers": list(d.machine.sale_blockers),
            "unresolved_transaction_ids": list(d.unresolved_transaction_ids),
            "recent_events": [
                {
                    "event_type": e.event_type,
                    "correlation_id": e.correlation_id,
                    "summary": str(e.summary),
                }
                for e in d.recent_events
            ],
        }
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(_format_service(payload))
        return 0
    finally:
        await environment.stop()


async def _command_clear_drift(args: argparse.Namespace) -> int:
    environment = await build_simulator_environment(
        config_path=args.config, prepare_directories=True
    )
    await environment.start()
    try:
        environment.ui_facade.clear_drift()
        payload = {"drift_detected": False}
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print("Drift flag cleared.")
        return 0
    finally:
        await environment.stop()


async def _command_simulator_runtime(args: argparse.Namespace) -> int:
    validate_config_file(args.config, prepare_directories=True)
    scenario_names = tuple(args.scenario)
    if args.use_config_scenarios:
        config, _, _ = validate_config_file(args.config, prepare_directories=True)
        scenario_names = tuple(config.simulator.scenario_suite)
    if scenario_names:
        results = await run_default_scenario_suite(scenario_names)
        scenario_payload = [asdict(result) for result in results]
        if args.json:
            print(json.dumps(scenario_payload, ensure_ascii=False, indent=2))
        else:
            print(_format_scenarios(results))
        return 0 if all(result.success for result in results) else 1

    environment = await build_simulator_environment(
        config_path=args.config, prepare_directories=True
    )
    await environment.start()
    try:
        diagnostics_payload = environment.diagnostics_report()
        if args.json:
            print(json.dumps(diagnostics_payload, ensure_ascii=False, indent=2))
        else:
            print(_format_diagnostics(diagnostics_payload))
        if args.duration > 0:
            await asyncio.sleep(args.duration)
        return 0
    finally:
        await environment.stop()


async def _command_run(args: argparse.Namespace) -> int:
    environment = await build_production_environment(
        config_path=args.config, prepare_directories=True
    )
    await environment.start()
    try:
        payload = environment.diagnostics_report()
        print("=== Production Runtime Started ===")
        print(f"State: {payload['machine']['machine_state']}")
        for device in payload["devices"]:
            print(f"  {device['device_name']}: {device['state']}")
        if payload["machine"]["sale_blockers"]:
            print(f"Blockers: {', '.join(payload['machine']['sale_blockers'])}")
        if not args.no_ui:
            print("Production UI handoff is not available in this build, running headless.")
        if args.duration > 0:
            await asyncio.sleep(args.duration)
        else:
            print("Running... Press Ctrl+C to stop.")
            while True:
                await asyncio.sleep(3600)
        return 0
    except KeyboardInterrupt:
        return 0
    finally:
        await environment.stop()


async def _command_printer_test(args: argparse.Namespace) -> int:
    from flower_vending.devices.printer import PrinterAdapter, PrinterAdapterConfig

    config = PrinterAdapterConfig(port=args.port or "", baudrate=args.baudrate)
    printer = PrinterAdapter(config)
    try:
        await printer.connect()
        await printer.print_test()
        print("Test receipt printed successfully.")
        return 0
    except Exception as exc:
        print(f"Printer test failed: {exc}")
        return 1
    finally:
        await printer.disconnect()


async def _command_dbv300sd_analyze(args: argparse.Namespace) -> int:
    from flower_vending.devices.dbv300sd.analyzer import analyze_port, format_analysis

    print(f"Analyzing {args.port}... (this may take a minute)")
    results = await analyze_port(args.port, read_size=args.read_size, timeout_s=args.timeout)
    print(format_analysis(results))
    return 0


async def _command_discover(args: argparse.Namespace) -> int:
    result = await discover_arduino()
    ports = list_com_ports()
    payload = {
        "esp32": result,
        "available_ports": ports,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(format_discovery(result))
    return 0


async def _command_dbv300sd_serial_smoke(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
) -> int:
    if args.read_size > 0 and args.tx_hex is None:
        parser.error("--read-size requires --tx-hex so bench reads are tied to explicit raw bytes")
    try:
        tx_payload = parse_hex_bytes(args.tx_hex) if args.tx_hex is not None else None
        settings = SerialTransportSettings(
            port=args.port,
            baudrate=args.baudrate,
            bytesize=args.bytesize,
            parity=args.parity,
            stopbits=args.stopbits,
            read_timeout_s=args.read_timeout_s,
            write_timeout_s=args.write_timeout_s,
        )
        bench = DBV300SDSerialSmokeBench(settings=settings, trace_log=Path(args.trace_log))
        result = await bench.run(
            tx_payload=tx_payload,
            read_size=args.read_size,
            correlation_id=args.correlation_id,
            note=args.note,
        )
    except DeviceAdapterError as exc:
        print(f"DBV-300-SD serial smoke failed: {exc}")
        return 1

    payload = result.to_json_payload()
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(_format_dbv300sd_serial_smoke(payload))
    return 0


def _print_report(report: BootstrapReport) -> None:
    print(f"Config: {report.config_path}")
    print(f"Resource root: {report.project_root}")
    print(f"State root: {report.state_root}")
    if report.created_directories:
        print("Created directories:")
        for path in report.created_directories:
            print(f"  - {path}")
    if report.messages:
        print("Messages:")
        for message in report.messages:
            print(f"  - [{message.severity}] {message.code}: {message.message}")
    else:
        print("Messages: none")


def _format_diagnostics(payload: dict[str, Any]) -> str:
    lines = [
        f"Machine state: {payload['machine']['machine_state']}",
        "Sale blockers: " + (", ".join(payload["machine"]["sale_blockers"]) or "none"),
        "Devices:",
    ]
    lines.extend(f"  - {device['device_name']}: {device['state']}" for device in payload["devices"])
    lines.append("Recent events:")
    if payload["recent_events"]:
        lines.extend(
            f"  - {item['event_type']} [{item['correlation_id']}] {item['summary']}"
            for item in payload["recent_events"]
        )
    else:
        lines.append("  - none")
    lines.append("Platform extension points:")
    lines.extend(
        f"  - {item['name']}: {item['status']} ({item['mode']})"
        for item in payload["platform"]["extension_points"]
    )
    return "\n".join(lines)


def _format_status(payload: dict[str, Any]) -> str:
    machine = payload["machine"]
    if machine is None:
        machine_lines = [
            "Machine state: unknown (no persisted machine_status_projection row)",
            "Sale blockers: unknown",
        ]
    else:
        machine_lines = [
            f"Machine state: {machine['machine_state']}",
            f"Service mode: {machine['service_mode']}",
            f"Exact change only: {machine['exact_change_only']}",
            "Sale blockers: " + (", ".join(machine["sale_blockers"]) or "none"),
            "Warnings: " + (", ".join(machine["warnings"]) or "none"),
            f"Active transaction: {machine['active_transaction_id'] or 'none'}",
            f"Cash sales allowed: {machine['allow_cash_sales']}",
            f"Vending allowed: {machine['allow_vending']}",
            f"Updated at: {machine['updated_at']}",
        ]
    money_inventory = payload["money_inventory"]
    if money_inventory is None:
        inventory_lines = ["Money inventory: not initialized"]
    else:
        inventory_lines = [
            "Money inventory:",
            f"  - currency: {money_inventory['currency_code']}",
            f"  - available counts: {money_inventory['available_counts']}",
            f"  - exact change only: {money_inventory['exact_change_only']}",
            f"  - drift detected: {money_inventory['drift_detected']}",
        ]
    lines = [
        f"Machine id: {payload['machine_id']}",
        f"Database: {payload['database_path']}",
        *machine_lines,
        *inventory_lines,
        f"Unresolved transactions: {len(payload['unresolved_transactions'])}",
        f"Unresolved intents: {len(payload['unresolved_intents'])}",
        f"Unacknowledged faults: {len(payload['unacknowledged_faults'])}",
    ]
    if payload["latest_applied_config"] is not None:
        lines.append(f"Latest applied config: {payload['latest_applied_config']['applied_at']}")
    if payload["hardware_warnings"]:
        lines.append("Hardware warnings:")
        lines.extend(f"  - {warning}" for warning in payload["hardware_warnings"])
    return "\n".join(lines)


def _format_events(payload: dict[str, Any]) -> str:
    lines = [
        f"Machine id: {payload['machine_id']}",
        f"Database: {payload['database_path']}",
        f"Recent events: {len(payload['events'])}",
    ]
    if not payload["events"]:
        lines.append("  - none")
        return "\n".join(lines)
    for event in payload["events"]:
        transaction_suffix = ""
        if event.get("transaction_id"):
            transaction_suffix = f" transaction={event['transaction_id']}"
        lines.append(
            "  - "
            f"{event['occurred_at']} "
            f"{event['source']} "
            f"{event['event_type']} "
            f"correlation={event['correlation_id']}"
            f"{transaction_suffix}"
        )
    return "\n".join(lines)


def _format_service(payload: dict[str, Any]) -> str:
    lines = [
        f"Operator: {payload['operator_id']}",
        f"Machine state: {payload['machine_state']}",
        "Sale blockers: " + (", ".join(payload["sale_blockers"]) or "none"),
    ]
    if payload["unresolved_transaction_ids"]:
        lines.append("Unresolved transactions: " + ", ".join(payload["unresolved_transaction_ids"]))
    else:
        lines.append("Unresolved transactions: none")
    lines.append("Recent events:")
    if payload["recent_events"]:
        lines.extend(
            f"  - {item['event_type']} [{item['correlation_id']}] {item['summary']}"
            for item in payload["recent_events"]
        )
    else:
        lines.append("  - none")
    return "\n".join(lines)


def _format_scenarios(results: tuple[Any, ...]) -> str:
    lines: list[str] = []
    for result in results:
        status = "PASS" if result.success else "FAIL"
        lines.append(f"{status}: {result.scenario_name} ({result.machine_state})")
        for note in result.notes:
            lines.append(f"  - {note}")
        for error in result.errors:
            lines.append(f"  - error: {error}")
    return "\n".join(lines)


def _format_dbv300sd_serial_smoke(payload: dict[str, Any]) -> str:
    serial = payload["serial_settings"]
    lines = [
        f"Transport: {payload['transport_name']}",
        (
            "Serial: "
            f"port={serial['port']} baudrate={serial['baudrate']} "
            f"bytesize={serial['bytesize']} parity={serial['parity']} "
            f"stopbits={serial['stopbits']} read_timeout_s={serial['read_timeout_s']} "
            f"write_timeout_s={serial['write_timeout_s']}"
        ),
        f"Trace log: {payload['trace_log']}",
        f"Opened: {payload['opened']}",
        f"Wrote bytes: {payload['wrote_bytes']}",
        f"Read bytes: {payload['read_bytes']}",
    ]
    if payload["rx_payload_hex"]:
        lines.append(f"RX payload hex: {payload['rx_payload_hex']}")
    lines.append(f"Note: {payload['note']}")
    return "\n".join(lines)
