import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import sys
import tempfile
import unittest
from pathlib import Path

from PySide6.QtWidgets import QApplication, QCheckBox, QPushButton, QScrollArea

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

try:
    from serial_gui_qt import Workbench
    HAVE_QT = True
except ImportError:
    HAVE_QT = False


@unittest.skipUnless(HAVE_QT, 'PySide6 is required for workbench integration tests')
class SettingsLayoutTests(unittest.TestCase):
    """设置页分区归属与「更多」菜单瘦身：一个动作一个家，防止功能再次乱塞。"""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def make_window(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        return Workbench(persist=False,
                         settings_path=Path(directory.name) / 'settings.json',
                         port_provider=lambda: [])

    def section_direct_children(self, window, name):
        layout = window.settings_sections[name]
        return [layout.itemAt(i).widget() for i in range(layout.count())]

    def test_settings_page_has_five_sections(self):
        window = self.make_window()
        self.addCleanup(window.close)
        self.assertEqual(list(window.settings_sections),
                         ['display', 'files', '波特率', '提醒', '共享串口桥'])
        self.assertIsInstance(window.modules[2][0], QScrollArea)
        self.assertEqual(window.inspector.tabText(2), '设置')

    def test_actions_live_in_their_home_sections(self):
        window = self.make_window()
        self.addCleanup(window.close)
        buttons = lambda name: [w.text() for w in self.section_direct_children(window, name)
                                if isinstance(w, QPushButton)]
        self.assertEqual(buttons('files'),
                         ['开始持续日志…', '打开日志文件…', '时间戳与文件设置…'])
        self.assertEqual(buttons('提醒'), ['条件提醒…', '提醒重新计数'])
        self.assertEqual(buttons('共享串口桥'),
                         ['连接共享服务…', '终止 Agent 并接管', '停止桥并释放端口'])
        # 波特率：监测开关与检测按钮同一行，主动探测单独一行。
        baud_rows = [w for w in self.section_direct_children(window, '波特率')]
        self.assertIs(window.autobaud_monitor.parent(), baud_rows[0])
        self.assertIs(window.baud_scan_button.parent(), baud_rows[0])
        probe = [w for w in baud_rows if isinstance(w, QCheckBox)]
        self.assertEqual([w.text() for w in probe], ['自动重扫允许主动探测'])
        self.assertEqual([c.text() for c in baud_rows[0].findChildren(QPushButton)],
                         ['在线检测波特率'])

    def test_more_menu_stays_slim(self):
        window = self.make_window()
        self.addCleanup(window.close)
        texts = [a.text() for a in window.more.menu().actions() if a.text()]
        self.assertEqual(texts,
                         ['宏编辑器', '连接设置…', '关闭当前会话', '布局模块…', '关于工作台'])
        for intruder in ('打开日志文件…', '条件提醒…', '开始持续日志…', '连接共享服务…',
                         '时间戳与文件设置…', '搜索选项…', '在线检测波特率…'):
            self.assertNotIn(intruder, texts)

    def test_toolbar_owns_log_actions_and_single_pause(self):
        window = self.make_window()
        self.addCleanup(window.close)
        self.assertFalse(hasattr(window, 'pause_button'), '暂停入口必须只有日志工具栏一处')
        for name in ('pause_tool', 'clear_btn', 'save_btn', 'auto_scroll'):
            self.assertIs(getattr(window, name).parent(), window.search_row,
                          f'{name} 应归日志工具栏')
        header_buttons = [w for w in window.centralWidget().findChildren(type(window.connect_btn))
                          if w.parent() is window.connect_btn.parent()]
        self.assertEqual(header_buttons, [window.connect_btn, window.more],
                         '头部只保留连接与更多两个按钮')


if __name__ == '__main__':
    unittest.main()
