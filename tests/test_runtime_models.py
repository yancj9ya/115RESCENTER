from __future__ import annotations

import importlib
import sys
import unittest

from src.runtime import (
    RUNTIME_COMPONENT_ORGANIZER,
    RUNTIME_COMPONENT_SUBSCRIPTION_PROCESSOR,
    RUNTIME_COMPONENT_TELEGRAM_COLLECTOR,
    RUNTIME_COMPONENT_TRANSFER_PROCESSOR,
    RUNTIME_COMPONENTS,
    RuntimeComponentTelemetry,
)


class RuntimeModelsTest(unittest.TestCase):
    def test_component_constants_are_exported_in_execution_order(self) -> None:
        self.assertEqual(RUNTIME_COMPONENT_TELEGRAM_COLLECTOR, "telegram_collector")
        self.assertEqual(RUNTIME_COMPONENT_SUBSCRIPTION_PROCESSOR, "subscription_processor")
        self.assertEqual(RUNTIME_COMPONENT_TRANSFER_PROCESSOR, "transfer_processor")
        self.assertEqual(RUNTIME_COMPONENT_ORGANIZER, "organizer")
        self.assertEqual(
            RUNTIME_COMPONENTS,
            (
                "telegram_collector",
                "subscription_processor",
                "transfer_processor",
                "organizer",
            ),
        )

    def test_runtime_package_import_does_not_load_worker_or_network_dependencies(self) -> None:
        forbidden_modules = (
            "p115client",
            "requests",
            "threading",
            "asyncio",
        )
        for module_name in forbidden_modules:
            sys.modules.pop(module_name, None)

        importlib.reload(importlib.import_module("src.runtime.models"))

        for module_name in forbidden_modules:
            self.assertNotIn(module_name, sys.modules)

    def test_component_telemetry_defaults_are_idle_and_independent(self) -> None:
        first = RuntimeComponentTelemetry(component="telegram_collector")
        second = RuntimeComponentTelemetry(component="telegram_collector")

        self.assertEqual(first.status, "idle")
        self.assertIsNone(first.checked_at)
        self.assertIsNone(first.started_at)
        self.assertIsNone(first.finished_at)
        self.assertEqual(first.detail, "")
        self.assertIsNone(first.last_error)
        self.assertEqual(first.counters, {})
        self.assertIsNot(first.counters, second.counters)


if __name__ == "__main__":
    unittest.main()
