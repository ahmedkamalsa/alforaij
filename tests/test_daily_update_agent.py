from __future__ import annotations

import unittest
from unittest import mock


class DailyUpdateAgentTests(unittest.TestCase):
    def test_run_daily_update_agent_writes_success_status(self) -> None:
        from backend.services import daily_update_agent

        snapshot = {"tiers": {"daily": {"items": []}}, "totalScored": 0}
        with mock.patch.object(daily_update_agent, "is_configured", return_value=True), \
            mock.patch.object(daily_update_agent, "sync_source_registry"), \
            mock.patch.object(daily_update_agent, "load_listings", return_value=[]), \
            mock.patch.object(daily_update_agent, "save_listings"), \
            mock.patch.object(daily_update_agent, "fetch_latest_opportunities", return_value=None), \
            mock.patch.object(daily_update_agent, "build_opportunities", return_value=snapshot), \
            mock.patch.object(daily_update_agent, "save_opportunities"), \
            mock.patch.object(daily_update_agent, "supabase_data_summary", return_value={"tables": {}}), \
            mock.patch.object(daily_update_agent, "save_update_notifications"), \
            mock.patch.object(daily_update_agent, "_write_status"):
            result = daily_update_agent.run_daily_update_agent(include_external=False)

        self.assertEqual(result["status"], "success")
        self.assertIn("build_and_save_opportunities", [step["name"] for step in result["steps"]])


if __name__ == "__main__":
    unittest.main()
