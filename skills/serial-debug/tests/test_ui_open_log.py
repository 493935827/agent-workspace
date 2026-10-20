"""打开并识别日志文件（workbench「打开日志文件…」）。

覆盖：行首时间戳识别（本工具格式 / 无括号日期 / 仅时间 / 非法值回退）、
编码识别与 GBK 回退、无时间戳文件按文件时间标注、记录上限与 SYS 摘要、
菜单与设置页入口、持续日志文件不被导入内容污染、错误呈现。
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

try:
    from PySide6.QtGui import QKeySequence
    from PySide6.QtWidgets import QApplication, QMenuBar, QPushButton
    from serial_gui_qt import Workbench, decode_log_bytes, match_log_stamp, parse_log_text
    HAVE_QT = True
except ImportError:
    HAVE_QT = False


@unittest.skipUnless(HAVE_QT, 'PySide6 is required for workbench integration tests')
class StampRecognitionTests(unittest.TestCase):
    BASE = datetime(2026, 10, 20, 9, 0, 0)

    def test_tool_format_bracketed_date_time(self):
        line = '[2026-10-20 14:06:01.123] 设备启动'
        matched = match_log_stamp(line, self.BASE.date())
        self.assertIsNotNone(matched)
        m, stamp, dated = matched
        self.assertTrue(dated)
        self.assertEqual(stamp, datetime(2026, 10, 20, 14, 6, 1, 123000))
        self.assertEqual(line[m.end():], '设备启动')

    def test_unbracketed_slash_date_and_comma_fraction(self):
        _, stamp, dated = match_log_stamp('2026/10/20 14:06:01,500 数据', self.BASE.date())
        self.assertTrue(dated)
        self.assertEqual(stamp, datetime(2026, 10, 20, 14, 6, 1, 500000))

    def test_iso_t_separator(self):
        line = '2026-10-20T14:06:01 boot'
        m, stamp, _ = match_log_stamp(line, self.BASE.date())
        self.assertEqual(stamp, datetime(2026, 10, 20, 14, 6, 1))
        self.assertEqual(line[m.end():], 'boot')

    def test_time_only_uses_file_date(self):
        _, stamp, dated = match_log_stamp('[14:06:01.5] x', self.BASE.date())
        self.assertFalse(dated)
        self.assertEqual(stamp, datetime(2026, 10, 20, 14, 6, 1, 500000))

    def test_invalid_candidates_fall_back_to_text(self):
        self.assertIsNone(match_log_stamp('25:61:61 x', self.BASE.date()))
        self.assertIsNone(match_log_stamp('2026-13-40 08:00:00 x', self.BASE.date()))
        self.assertIsNone(match_log_stamp('hello world', self.BASE.date()))

    def test_decode_prefers_utf8_then_gbk(self):
        self.assertEqual(decode_log_bytes('中文日志\n'.encode('utf-8')), ('中文日志\n', 'UTF-8'))
        self.assertEqual(decode_log_bytes('中文日志\n'.encode('gbk')), ('中文日志\n', 'GBK'))
        text, _ = decode_log_bytes(b'\xff\xfe' + '中文\n'.encode('utf-16-le'))
        self.assertEqual(text, '中文\n')

    def test_parse_rebuilds_multiline_records(self):
        text = '[2026-10-20 10:00:00.500] 设备启动\n版本 1.2.3\n[2026-10-20 10:00:01] 就绪\n'
        records, stats = parse_log_text(text, self.BASE)
        self.assertEqual([r['text'] for r in records], ['设备启动\n版本 1.2.3\n', '就绪\n'])
        self.assertEqual(records[0]['stamp'], datetime(2026, 10, 20, 10, 0, 0, 500000))
        self.assertEqual(records[1]['stamp'], datetime(2026, 10, 20, 10, 0, 1))
        self.assertEqual((stats['stamps'], stats['dated'], stats['merged']), (2, 2, 1))

    def test_parse_plain_text_marks_every_line_with_base_stamp(self):
        records, stats = parse_log_text('第一行\n第二行\n', self.BASE)
        self.assertEqual([r['text'] for r in records], ['第一行\n', '第二行\n'])
        self.assertEqual([r['stamp'] for r in records], [self.BASE, self.BASE])
        self.assertEqual((stats['stamps'], stats['plain']), (0, 2))

    def test_parse_normalizes_crlf_and_keeps_ansi_colors(self):
        from serial_common import AnsiLogParser
        text = ('[2026-10-20 10:00:00] \x1b[31m红\x1b[0m\r\n'
                '[2026-10-20 10:00:01] 普通\r\n')
        records, _ = parse_log_text(text, self.BASE)
        self.assertEqual([r['text'] for r in records], ['红\n', '普通\n'])
        self.assertEqual(records[0]['spans'], [
            ('红', ('#800000', None, False, False, False, False, False, False)),
            ('\n', AnsiLogParser.DEFAULT)])


@unittest.skipUnless(HAVE_QT, 'PySide6 is required for workbench integration tests')
class OpenLogWorkbenchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)

    def make_window(self):
        window = Workbench(persist=False, settings_path=self.directory / 'settings.json',
                           port_provider=lambda: [])
        self.addCleanup(window.close)
        return window

    def write_log(self, name, content):
        path = self.directory / name
        path.write_bytes(content if isinstance(content, bytes) else content.encode('utf-8'))
        return path

    def log_records(self, window, index=0):
        return [r for r in window.sessions[index]['records'] if r['tag'] == 'LOG']

    def sys_texts(self, window, index=0):
        return [r['text'] for r in window.sessions[index]['records'] if r['tag'] == 'SYS']

    def test_load_tool_format_log_into_session(self):
        window = self.make_window()
        path = self.write_log('demo.log', '[2026-10-20 10:00:00.500] 设备启动\n版本 1.2.3\n[2026-10-20 10:00:01] 就绪\n')
        self.assertTrue(window.load_log_file(0, path))
        records = self.log_records(window)
        self.assertEqual([r['text'] for r in records], ['设备启动\n版本 1.2.3\n', '就绪\n'])
        self.assertEqual(records[0]['stamp'], datetime(2026, 10, 20, 10, 0, 0, 500000))
        self.assertIn('设备启动', window.views[0].toPlainText())
        summary = self.sys_texts(window)[-1]
        self.assertIn('已打开日志 demo.log（UTF-8）', summary)
        self.assertIn('识别时间戳 2 个（2 带日期）', summary)
        self.assertIn('1 行无时间戳并入前条', summary)

    def test_load_gbk_log_and_time_only_stamps(self):
        window = self.make_window()
        # 全角逗号的 GBK 编码不是合法 UTF-8，保证走 GBK 回退分支。
        path = self.write_log('gbk.log', '10:00:01 串口，正常\n10:00:02 收到，数据\n'.encode('gbk'))
        self.assertTrue(window.load_log_file(0, path))
        records = self.log_records(window)
        self.assertEqual([r['text'] for r in records], ['串口，正常\n', '收到，数据\n'])
        expected_date = datetime.fromtimestamp(path.stat().st_mtime).date()
        self.assertEqual([r['stamp'].date() for r in records], [expected_date, expected_date])
        self.assertEqual([r['stamp'].strftime('%H:%M:%S') for r in records], ['10:00:01', '10:00:02'])
        summary = self.sys_texts(window)[-1]
        self.assertIn('（GBK）', summary)
        self.assertIn('无日期时间戳按文件日期补齐', summary)

    def test_load_plain_text_uses_file_mtime(self):
        window = self.make_window()
        path = self.write_log('plain.txt', '第一行\n第二行\n')
        self.assertTrue(window.load_log_file(0, path))
        records = self.log_records(window)
        expected = datetime.fromtimestamp(path.stat().st_mtime)
        self.assertEqual(len(records), 2)
        self.assertEqual([r['stamp'] for r in records], [expected, expected])
        self.assertIn('未识别到时间戳，按文件修改时间标注', self.sys_texts(window)[-1])

    def test_load_caps_records_and_reports_remainder(self):
        window = self.make_window()
        path = self.write_log('many.log', ''.join(f'[2026-10-20 10:00:{i // 60:02d}.{i % 60:02d}] 行{i}\n' for i in range(30)))
        with mock.patch('serial_gui_qt.RECORD_LIMIT', 10):
            self.assertTrue(window.load_log_file(0, path))
        # 截断后保留 10 条，SYS 摘要本身再顶掉最旧的一条：9 条 LOG + 1 条 SYS。
        self.assertEqual(len(window.sessions[0]['records']), 10)
        self.assertEqual([r['tag'] for r in window.sessions[0]['records']], ['LOG'] * 9 + ['SYS'])
        self.assertIn('仅保留最近 10 条', self.sys_texts(window)[-1])

    def test_load_does_not_touch_running_continuous_log(self):
        window = self.make_window()
        target = self.directory / 'ongoing.log'
        self.assertTrue(window.start_logging(path=target))
        path = self.write_log('demo.log', '[2026-10-20 10:00:00.500] 设备启动\n')
        self.assertTrue(window.load_log_file(0, path))
        window.stop_logging(0)
        written = target.read_text('utf-8')
        self.assertIn('已打开日志', written)
        self.assertNotIn('设备启动', written)

    def test_missing_and_empty_files_report_error(self):
        window = self.make_window()
        self.assertFalse(window.load_log_file(0, self.directory / 'nope.log'))
        self.assertTrue(any('打开日志失败' in text for text in
                            [r['text'] for r in window.sessions[0]['records'] if r['tag'] == 'ERROR']))
        empty = self.write_log('empty.log', b'')
        self.assertFalse(window.load_log_file(0, empty))
        self.assertTrue(any('没有可识别的内容' in text for text in
                            [r['text'] for r in window.sessions[0]['records'] if r['tag'] == 'ERROR']))

    def test_dialog_loads_file_and_remembers_directory(self):
        window = self.make_window()
        path = self.write_log('demo.log', '[2026-10-20 10:00:00.500] 设备启动\n')
        with mock.patch('serial_gui_qt.QFileDialog.getOpenFileName',
                        return_value=(str(path), '日志 (*.log *.txt *.csv)')):
            window.open_log_dialog()
        self.assertEqual(len(self.log_records(window)), 1)
        self.assertEqual(window.options()['log_directory'], str(self.directory))
        self.assertIn('已打开日志 demo.log', self.sys_texts(window)[-1])

    def test_open_entries_in_more_menu_settings_page_and_file_menu(self):
        window = self.make_window()
        self.assertIn('打开日志文件…', [a.text() for a in window.more.menu().actions()])
        buttons = [b.text() for b in window.modules[2][0].findChildren(QPushButton)]
        self.assertIn('打开日志文件…', buttons)
        menubar = window.findChild(QMenuBar)
        file_menu = menubar.actions()[0].menu()
        first = file_menu.actions()[0]
        self.assertEqual(first.text(), '打开日志文件…')
        self.assertEqual(first.shortcut(), QKeySequence('Ctrl+O'))


if __name__ == '__main__':
    unittest.main()
