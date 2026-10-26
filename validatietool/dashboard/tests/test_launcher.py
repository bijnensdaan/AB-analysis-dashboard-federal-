"""Een vaste lokale URL, bestaande server hergebruiken, geen bronverversing."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import open_dashboard


class LauncherTests(unittest.TestCase):
    def test_running_dashboard_is_reused(self):
        with patch.object(open_dashboard,'server_status',return_value='dashboard'), patch.object(open_dashboard.subprocess,'Popen') as spawn:
            self.assertFalse(open_dashboard.ensure_running())
            spawn.assert_not_called()

    def test_occupied_port_does_not_start_or_stop_another_process(self):
        with patch.object(open_dashboard,'server_status',return_value='other'), patch.object(open_dashboard.subprocess,'Popen') as spawn:
            with self.assertRaisesRegex(RuntimeError,'Poort 8780'):open_dashboard.ensure_running()
            spawn.assert_not_called()

    def test_new_server_uses_fixed_port_no_refresh_and_cleans_lock(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(open_dashboard,'ROOT',Path(tmp)), patch.object(open_dashboard,'server_status',side_effect=['absent','absent','dashboard']), patch.object(open_dashboard.subprocess,'Popen') as spawn:
            self.assertTrue(open_dashboard.ensure_running())
            command=spawn.call_args.args[0]
            self.assertEqual(command[-3:],['--geen-browser','--poort','8780'])
            self.assertNotIn('--ververs',command)
            self.assertFalse((Path(tmp)/'tmp/dashboard-start.lock').exists())

    def test_failed_start_releases_lock_and_reports_log(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(open_dashboard,'ROOT',Path(tmp)), patch.object(open_dashboard,'server_status',return_value='absent'), patch.object(open_dashboard.subprocess,'Popen') as spawn:
            spawn.return_value.poll.return_value=2
            with self.assertRaisesRegex(RuntimeError,'dashboard-start.log'):open_dashboard.ensure_running()
            self.assertFalse((Path(tmp)/'tmp/dashboard-start.lock').exists())


if __name__=='__main__':unittest.main()
