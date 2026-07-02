"""
Tests for the command module.
"""
import unittest
from unittest.mock import patch, MagicMock, AsyncMock
from agent.command_handler import CommandHandler
import platform
import asyncio

class TestCommands(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.handler = CommandHandler()

    @patch('agent.command_handler.take_screenshot', return_value=b'screenshot_bytes')
    async def test_handle_screenshot(self, mock_take_screenshot):
        result = await self.handler.handle_screenshot(grid=True)
        self.assertEqual(result, b'screenshot_bytes')
        mock_take_screenshot.assert_called_with(True, -1)

    @patch('agent.command_handler.sys_monitor.get_system_summary', return_value='system_info')
    async def test_handle_sysinfo(self, mock_get_system_info):
        result = await self.handler.handle_sysinfo()
        self.assertEqual(result, 'system_info')

    @patch('agent.command_handler.list_files', return_value='file_list')
    async def test_handle_list_files(self, mock_list_files):
        result = await self.handler.handle_list_files('some_path')
        self.assertEqual(result, 'file_list')

    @patch('agent.command_handler.get_file', return_value={'data': b'file_data', 'filename': 'test.txt', 'mimetype': 'text/plain'})
    async def test_handle_get_file(self, mock_get_file):
        result = await self.handler.handle_get_file('some_path')
        self.assertEqual(result, {'data': b'file_data', 'filename': 'test.txt', 'mimetype': 'text/plain'})

    @patch('agent.command_handler.run_script', new_callable=AsyncMock)
    async def test_handle_run_script(self, mock_run_script):
        mock_run_script.return_value = 'script_result'
        result = await self.handler.handle_run_script('some_script.py', 'user123')
        self.assertEqual(result, 'script_result')

    @patch('platform.system', return_value='Linux')
    @patch('subprocess.run')
    async def test_handle_lock_screen(self, mock_subprocess_run, mock_platform_system):
        result = await self.handler.handle_lock_screen()
        self.assertEqual(result, '🔒 Layar Linux berhasil dikunci.')

    @patch('platform.system', return_value='Linux')
    @patch('subprocess.run')
    async def test_handle_reboot(self, mock_subprocess_run, mock_platform_system):
        result = await self.handler.handle_reboot(confirmed=True)
        self.assertEqual(result, '🔄 Laptop (Linux) akan restart dalam 5 detik...')
        result = await self.handler.handle_reboot(confirmed=False)
        self.assertEqual(result, """⚠️ Yakin ingin restart?
Balas: `!reboot confirm`""")

    @patch('agent.command_handler.record_audio', return_value={'type': 'audio', 'data': b'mp3_bytes', 'filename': 'audio.mp3', 'mimetype': 'audio/mpeg'})
    async def test_handle_listen(self, mock_record_audio):
        result = await self.handler.handle_listen(5)
        self.assertEqual(result, {'type': 'audio', 'data': b'mp3_bytes', 'filename': 'audio.mp3', 'mimetype': 'audio/mpeg'})

    @patch('agent.command_handler.simulate_click', return_value='🖱️ Clicked')
    async def test_handle_click(self, mock_simulate_click):
        result = await self.handler.handle_click(100, 200)
        self.assertEqual(result, '🖱️ Clicked')

    @patch('agent.command_handler.simulate_type', return_value='⌨️ Typed')
    async def test_handle_type(self, mock_simulate_type):
        result = await self.handler.handle_type('hello')
        self.assertEqual(result, '⌨️ Typed')

    @patch('agent.command_handler.simulate_press', return_value='⌨️ Pressed')
    async def test_handle_press(self, mock_simulate_press):
        result = await self.handler.handle_press('enter')
        self.assertEqual(result, '⌨️ Pressed')

    @patch('agent.command_handler.get_active_window_title', return_value='MyWindow')
    async def test_handle_active_window(self, mock_get_active_window):
        result = await self.handler.handle_active_window()
        self.assertEqual(result, '🖥️ Jendela Aktif: **MyWindow**')

    @patch('glob.glob')
    @patch('builtins.open')
    @patch('subprocess.run')
    async def test_handle_brightness(self, mock_sub_run, mock_open, mock_glob):
        # Setup mocks
        mock_glob.return_value = ["/sys/class/backlight/intel_backlight"]
        
        # Mock reading max_brightness (100) and brightness (80)
        mock_file_max = MagicMock()
        mock_file_max.__enter__.return_value = mock_file_max
        mock_file_max.read.return_value = "100"
        mock_file_curr = MagicMock()
        mock_file_curr.__enter__.return_value = mock_file_curr
        mock_file_curr.read.return_value = "80"
        mock_open.side_effect = [mock_file_max, mock_file_curr]
        
        # Test read current brightness (no args)
        result = await self.handler.handle_brightness([])
        self.assertIn("80%", result)
        
        # Mock open again for write test
        mock_file_max_2 = MagicMock()
        mock_file_max_2.__enter__.return_value = mock_file_max_2
        mock_file_max_2.read.return_value = "100"
        mock_file_curr_2 = MagicMock()
        mock_file_curr_2.__enter__.return_value = mock_file_curr_2
        mock_file_curr_2.read.return_value = "80"
        mock_open.side_effect = [mock_file_max_2, mock_file_curr_2]
        
        # Test write brightness
        mock_sub_run.return_value = MagicMock(returncode=0)
        result = await self.handler.handle_brightness(["50"])
        self.assertIn("50%", result)

    @patch('subprocess.run')
    async def test_handle_media(self, mock_sub_run):
        import sys
        mock_pyautogui = MagicMock()
        with patch.dict(sys.modules, {"pyautogui": mock_pyautogui}):
            # 1. Test with active MPRIS player
            mock_res = MagicMock()
            mock_res.stdout = 'string "org.mpris.MediaPlayer2.spotify"\n'
            mock_sub_run.side_effect = [mock_res, MagicMock()]
            
            result = await self.handler.handle_media("play")
            self.assertIn("Spotify", result)
            
            # 2. Test fallback to pyautogui keypress
            mock_res_empty = MagicMock()
            mock_res_empty.stdout = ""
            mock_sub_run.side_effect = [mock_res_empty]
            
            result = await self.handler.handle_media("next")
            self.assertIn("nexttrack", result)
            mock_pyautogui.press.assert_called_once_with("nexttrack")

    @patch('glob.glob')
    @patch('os.path.exists', return_value=True)
    @patch('builtins.open')
    async def test_handle_battery(self, mock_open, mock_exists, mock_glob):
        mock_glob.side_effect = [
            ["/sys/class/power_supply/BAT0"],
            [],
            ["/sys/class/power_supply/ADP1"]
        ]
        
        # Mock file reads: capacity (90), status (Charging), technology (Li-poly), model (A9), manufacturer (HP), charge_full (4000), charge_full_design (5000), AC online (1)
        mock_cap = MagicMock()
        mock_cap.__enter__.return_value = mock_cap
        mock_cap.read.return_value = "90"
        
        mock_status = MagicMock()
        mock_status.__enter__.return_value = mock_status
        mock_status.read.return_value = "Charging"
        
        mock_tech = MagicMock()
        mock_tech.__enter__.return_value = mock_tech
        mock_tech.read.return_value = "Li-poly"
        
        mock_model = MagicMock()
        mock_model.__enter__.return_value = mock_model
        mock_model.read.return_value = "A9"
        
        mock_manu = MagicMock()
        mock_manu.__enter__.return_value = mock_manu
        mock_manu.read.return_value = "HP"
        
        mock_cf = MagicMock()
        mock_cf.__enter__.return_value = mock_cf
        mock_cf.read.return_value = "4000"
        
        mock_cfd = MagicMock()
        mock_cfd.__enter__.return_value = mock_cfd
        mock_cfd.read.return_value = "5000"
        
        mock_ac = MagicMock()
        mock_ac.__enter__.return_value = mock_ac
        mock_ac.read.return_value = "1"
        
        mock_open.side_effect = [
            mock_cap, mock_status, mock_tech, mock_model, mock_manu, mock_cf, mock_cfd, mock_ac
        ]
        
        result = await self.handler.handle_battery()
        self.assertIn("90%", result)
        self.assertIn("Charging", result)
        self.assertIn("80.00%", result) # Health = 4000 / 5000 * 100

    @patch('subprocess.run')
    async def test_handle_notif(self, mock_sub_run):
        mock_sub_run.return_value = MagicMock(returncode=0)
        res = await self.handler.handle_notif("Hello Test")
        self.assertIn("berhasil dikirim", res)

    @patch('psutil.process_iter')
    @patch('psutil.Process')
    async def test_handle_process(self, mock_process_class, mock_proc_iter):
        mock_proc = MagicMock()
        mock_proc.info = {
            'pid': 1234,
            'name': 'test_proc',
            'cpu_percent': 10.0,
            'memory_percent': 2.0
        }
        mock_proc_iter.return_value = [mock_proc]
        res = await self.handler.handle_process(["list"])
        self.assertIn("test_proc", res)
        self.assertIn("1234", res)

        mock_target_proc = MagicMock()
        mock_target_proc.name.return_value = "target_proc"
        mock_process_class.return_value = mock_target_proc
        res = await self.handler.handle_process(["kill", "1234"])
        self.assertIn("Berhasil menutup paksa", res)
        mock_target_proc.kill.assert_called_once()

    async def test_handle_clip_sync(self):
        res = await self.handler.handle_clip_sync([])
        self.assertIn("NON-AKTIF", res)

        res = await self.handler.handle_clip_sync(["start"])
        self.assertIn("AKTIF", res)
        
        res = await self.handler.handle_clip_sync(["stop"])
        self.assertIn("NON-AKTIF", res)

    def test_set_cwd_relative(self):
        from pathlib import Path
        initial_cwd = str(Path.home() / "Documents")
        self.handler._cwd = initial_cwd
        result = self.handler.set_cwd("..")
        self.assertEqual(self.handler._cwd, str(Path.home()))

    def test_fallback_parser_shortcuts(self):
        from ai_module.fallback_parser import FallbackParser
        parser = FallbackParser()
        
        cmd, args = parser.parse("!read")
        self.assertEqual(cmd, "clip")
        self.assertEqual(args, ["read"])

        cmd, args = parser.parse("!write Hello World")
        self.assertEqual(cmd, "clip")
        self.assertEqual(args, ["write", "Hello", "World"])

        # Uji shortcut baru
        cmd, args = parser.parse("!find *.py")
        self.assertEqual(cmd, "find")
        self.assertEqual(args, ["*.py"])

        cmd, args = parser.parse("!win minimize")
        self.assertEqual(cmd, "window_control")
        self.assertEqual(args, ["minimize"])

    async def test_handle_find_files(self):
        res = await self.handler.handle_find_files("")
        self.assertIn("Masukkan pola pencarian", res)

        res = await self.handler.handle_find_files("nonexistentfilexyz")
        self.assertIn("Tidak ditemukan file", res)

    @patch("subprocess.Popen")
    async def test_handle_tts_speak(self, mock_popen):
        res = await self.handler.handle_tts_speak("")
        self.assertIn("Masukkan teks", res)

        # 1. Test offline fallback
        def mock_which_offline(cmd):
            if cmd == "spd-say":
                return "/usr/bin/spd-say"
            return None

        with patch("shutil.which", side_effect=mock_which_offline), \
             patch("edge_tts.Communicate", side_effect=Exception("Edge TTS failed")):
            res = await self.handler.handle_tts_speak("Hello")
            self.assertIn("Offline spd-say", res)
            mock_popen.assert_called()

        # 2. Test Edge TTS path
        mock_popen.reset_mock()
        def mock_which_online(cmd):
            if cmd == "mpv":
                return "/usr/bin/mpv"
            return None

        mock_communicate = MagicMock()
        from unittest.mock import AsyncMock
        mock_communicate.save = AsyncMock()
        
        with patch("shutil.which", side_effect=mock_which_online), \
             patch("edge_tts.Communicate", return_value=mock_communicate):
            res = await self.handler.handle_tts_speak("Halo")
            self.assertIn("Microsoft Edge TTS", res)
            self.assertIn("GadisNeural", res)
            mock_popen.assert_called_once()
            
            # Test Japanese Anime Voice flag
            mock_popen.reset_mock()
            res_anime = await self.handler.handle_tts_speak("-v jp Ohayou")
            self.assertIn("Microsoft Edge TTS", res_anime)
            self.assertIn("NanamiNeural", res_anime)
            mock_popen.assert_called_once()
            
            # Test Indonesian Male Voice flag
            mock_popen.reset_mock()
            res_male = await self.handler.handle_tts_speak("-v cowo Halo")
            self.assertIn("Microsoft Edge TTS", res_male)
            self.assertIn("ArdiNeural", res_male)
            mock_popen.assert_called_once()

            # Test Custom Voice Name flag
            mock_popen.reset_mock()
            res_custom = await self.handler.handle_tts_speak("-v en-US-GuyNeural Hello")
            self.assertIn("Microsoft Edge TTS", res_custom)
            self.assertIn("en-US-GuyNeural", res_custom)
            mock_popen.assert_called_once()

    @patch("subprocess.run")
    async def test_handle_ping(self, mock_run):
        import subprocess
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="64 bytes from 8.8.8.8")
        res = await self.handler.handle_ping("8.8.8.8")
        self.assertIn("Hasil Ping", res)
        mock_run.assert_called()

    @patch("shutil.which", return_value="/usr/bin/speedtest-cli")
    @patch("subprocess.run")
    async def test_handle_speedtest_cli(self, mock_run, mock_which):
        import subprocess
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="Ping: 10 ms\nDownload: 50 Mbps\nUpload: 20 Mbps")
        res = await self.handler.handle_speedtest()
        self.assertIn("Hasil Speedtest", res)
        mock_run.assert_called()

    @patch("shutil.which", return_value=None)
    @patch("httpx.AsyncClient.get")
    async def test_handle_speedtest_fallback(self, mock_get, mock_which):
        class MockResponse:
            status_code = 200
        mock_get.return_value = MockResponse()
        res = await self.handler.handle_speedtest()
        self.assertIn("Hasil Uji Kecepatan Unduh (Fallback)", res)

    @patch("shutil.which")
    @patch("subprocess.run")
    async def test_handle_window_control(self, mock_run, mock_which):
        res = await self.handler.handle_window_control("invalid")
        self.assertIn("Aksi jendela tidak dikenal", res)

        # Minimize xdotool
        mock_which.side_effect = lambda cmd: cmd == "xdotool"
        res = await self.handler.handle_window_control("minimize")
        self.assertIn("Jendela aktif berhasil diminimalkan", res)
        mock_run.assert_called()

        # Close xdotool
        res = await self.handler.handle_window_control("close")
        self.assertIn("Jendela aktif berhasil ditutup", res)

    @patch("httpx.AsyncClient.get")
    async def test_handle_web_search(self, mock_get):
        # Empty query
        res_empty = await self.handler.handle_web_search("")
        self.assertIn("Masukkan kueri", res_empty)

        # Mock successful DuckDuckGo HTML response
        mock_res_ddg = MagicMock()
        mock_res_ddg.status_code = 200
        mock_res_ddg.text = """
        <div class="result__body">
            <a class="result__a" href="https://example.com/page">Example Page</a>
            <a class="result__snippet" href="https://example.com/page">This is a snippet for the example page.</a>
        </div>
        """
        mock_get.return_value = mock_res_ddg
        res = await self.handler.handle_web_search("test query")
        self.assertIn("Hasil Pencarian Web untuk", res)
        self.assertIn("Example Page", res)
        self.assertIn("https://example.com/page", res)

        # Mock DuckDuckGo failure, leading to Yahoo fallback success
        mock_res_fail = MagicMock()
        mock_res_fail.status_code = 500
        mock_res_fail.text = "Internal Server Error"

        mock_res_yahoo = MagicMock()
        mock_res_yahoo.status_code = 200
        mock_res_yahoo.text = """
        <li>
            <div class="dd algo">
                <a href="https://r.search.yahoo.com/_ylt=1/RU=https%3a%2f%2fyahoo-example.com%2fpage/RK=2/RS=1">
                    <h3><span>Yahoo Page</span></h3>
                </a>
            </div>
        </li>
        """

        mock_get.side_effect = [mock_res_fail, mock_res_yahoo]
        res_fallback = await self.handler.handle_web_search("test query")
        self.assertIn("Yahoo Fallback", res_fallback)
        self.assertIn("Yahoo Page", res_fallback)
        self.assertIn("https://yahoo-example.com/page", res_fallback)


    @patch("shutil.which")
    @patch("asyncio.create_subprocess_exec")
    async def test_handle_wifi_scan(self, mock_exec, mock_which):
        # Linux flow
        mock_which.side_effect = lambda cmd: cmd == "nmcli"
        mock_proc = MagicMock()
        
        # AsyncMock support
        from unittest.mock import AsyncMock
        mock_proc.communicate = AsyncMock(return_value=(b"MyHomeWiFi:95:WPA2\nOfficeWiFi:80:WPA3", b""))
        mock_exec.return_value = mock_proc

        with patch("platform.system", return_value="Linux"):
            res = await self.handler.handle_wifi_scan()
            self.assertIn("Jaringan Wi-Fi Sekitar", res)
            self.assertIn("MyHomeWiFi", res)
            self.assertIn("OfficeWiFi", res)

    @patch("shutil.which")
    @patch("asyncio.create_subprocess_exec")
    async def test_handle_active_ports(self, mock_exec, mock_which):
        # Linux flow
        mock_which.side_effect = lambda cmd: cmd == "ss"
        mock_proc = MagicMock()
        
        from unittest.mock import AsyncMock
        mock_proc.communicate = AsyncMock(return_value=(b"Netid State Recv-Q Send-Q Local Address:Port Peer Address:Port\ntcp LISTEN 0 128 127.0.0.1:8080 *:*", b""))
        mock_exec.return_value = mock_proc

        with patch("platform.system", return_value="Linux"):
            res = await self.handler.handle_active_ports()
            self.assertIn("Daftar Port Listening Aktif", res)
            self.assertIn("Port 8080", res)
            self.assertIn("Localhost", res)

    @patch("shutil.which")
    @patch("subprocess.Popen")
    async def test_handle_launch_app(self, mock_popen, mock_which):
        # 1. Test app not found
        mock_which.return_value = None
        res_fail = await self.handler.handle_launch_app("unknown_app")
        self.assertIn("tidak ditemukan", res_fail)

        # 2. Test app found and launched
        mock_which.side_effect = lambda cmd: cmd == "google-chrome"
        res_success = await self.handler.handle_launch_app("chrome")
        self.assertIn("Berhasil meluncurkan aplikasi", res_success)
        self.assertIn("chrome", res_success)
        mock_popen.assert_called_once()

    async def test_handle_todo(self):
        todo_file = "todo.json"
        import os
        if os.path.exists(todo_file):
            try:
                os.remove(todo_file)
            except Exception:
                pass

        # 1. Test empty list
        res = await self.handler.handle_todo([])
        self.assertIn("Daftar Tugas Anda Kosong", res)

        # 2. Test add task
        res_add = await self.handler.handle_todo(["add", "Beli", "kopi"])
        self.assertIn("Berhasil menambahkan tugas", res_add)
        self.assertIn("Beli kopi", res_add)

        # 2b. Test add task with deadline
        res_deadline = await self.handler.handle_todo(["add", "Beli", "susu", "|", "23:59"])
        self.assertIn("Berhasil menambahkan tugas", res_deadline)
        self.assertIn("Beli susu", res_deadline)
        self.assertIn("tenggat waktu", res_deadline)

        # 2c. Test add task with deadline and speak local option
        res_speak = await self.handler.handle_todo(["add", "Cuci baju", "|", "23:59", "|", "speak"])
        self.assertIn("Berhasil menambahkan tugas", res_speak)
        self.assertIn("Cuci baju", res_speak)
        self.assertIn("Laptop Berbicara", res_speak)

        # 3. Test list task
        res_list = await self.handler.handle_todo([])
        self.assertIn("Daftar Tugas (TODO List)", res_list)
        self.assertIn("Beli kopi", res_list)

        # 4. Test done task
        res_done = await self.handler.handle_todo(["done", "1"])
        self.assertIn("Berhasil menandai tugas", res_done)
        self.assertIn("selesai", res_done)

        # 5. Test delete task
        res_del = await self.handler.handle_todo(["delete", "1"])
        self.assertIn("Berhasil menghapus tugas", res_del)

        if os.path.exists(todo_file):
            try:
                os.remove(todo_file)
            except Exception:
                pass

    async def test_handle_list_apps(self):
        # 1. Test listing apps (default/fallback or system)
        res = await self.handler.handle_list_apps([])
        self.assertTrue("Daftar Aplikasi Desktop Terinstall" in res or "Google Chrome" in res)

        # 2. Test filtering/searching for an app that exists
        res_search = await self.handler.handle_list_apps(["chrome"])
        self.assertIn("chrome", res_search.lower())

        # 3. Test filtering/searching for an app that does not exist
        res_not_found = await self.handler.handle_list_apps(["nonexistentapp123"])
        self.assertIn("Tidak ditemukan aplikasi yang cocok", res_not_found)

    @patch("subprocess.Popen")
    async def test_monitor_task_todo_deadline(self, mock_popen):
        from bot.monitor_task import MonitorTask
        from unittest.mock import MagicMock, AsyncMock
        import json
        import os
        from datetime import datetime, timedelta
        
        # 1. Setup todo.json with an expired task
        todo_file = "todo.json"
        now = datetime.now()
        past_time = (now - timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M")
        
        todos = [
            {"task": "Tugas kadaluarsa", "done": False, "deadline": past_time, "reminded": False}
        ]
        with open(todo_file, "w") as f:
            json.dump(todos, f, indent=4)

        # 2. Run monitor task check
        mock_app = MagicMock()
        # Mock application bot send message and send voice
        mock_app.bot.send_message = AsyncMock()
        mock_app.bot.send_voice = AsyncMock()
        
        monitor = MonitorTask(mock_app)
        monitor.allowed_users = {"12345"}
        
        await monitor._check_todo_deadlines_once()
        
        # Verify reminded is set to True
        with open(todo_file, "r") as f:
            updated_todos = json.load(f)
        self.assertTrue(updated_todos[0]["reminded"])
        
        # Verify notifications sent
        mock_app.bot.send_message.assert_called_once()
        mock_app.bot.send_voice.assert_called_once()
        
        # Cleanup
        if os.path.exists(todo_file):
            try:
                os.remove(todo_file)
            except Exception:
                pass

    @patch("cv2.VideoCapture")
    async def test_handle_guard(self, mock_video_capture):
        from unittest.mock import MagicMock
        # Mock VideoCapture instance to return True for isOpened()
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.read.return_value = (True, MagicMock())
        mock_video_capture.return_value = mock_cap
        
        # Test default status (should be NONAKTIF by default)
        status_res = await self.handler.handle_guard([])
        self.assertIn("Status Webcam Guard", status_res)
        self.assertIn("NONAKTIF", status_res)

        # Test turn on
        on_res = await self.handler.handle_guard(["on"])
        self.assertIn("Webcam Guard diaktifkan", on_res)

        # Test status again (should be AKTIF)
        status_res_2 = await self.handler.handle_guard([])
        self.assertIn("AKTIF", status_res_2)

        # Test turn off
        off_res = await self.handler.handle_guard(["off"])
        self.assertIn("Webcam Guard dinonaktifkan", off_res)


if __name__ == '__main__':
    unittest.main()

