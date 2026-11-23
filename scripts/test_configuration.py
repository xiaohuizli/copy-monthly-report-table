"""Observable configuration, platform-name and per-row-status behavior."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class ConfigurationTests(unittest.TestCase):
    def run_table(self, extra=(), config=None, source_text=None):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            source = base / 'work.md'
            if source_text is None:
                source_text = ('| 开发平台 | 工作内容 | 预估天数 | 状态 |\n'
                               '| --- | --- | --- | --- |\n'
                               '| WOOWU-AI | 联调完成，等待人工验收。 | 2 天 | 待验收 |\n'
                               '| new-api | 离线验证完成，未执行生产发布。 | 1 天 | |\n')
            source.write_text(source_text, encoding='utf-8')
            script = Path(__file__).with_name('copy_monthly_report_table.py').resolve()
            command = [sys.executable, str(script), str(source), '--start-date', '2026-11-09',
                       '--end-date', '2026-11-13', '--print-only']
            if config is not None:
                (base / 'identity.json').write_text(json.dumps(config), encoding='utf-8')
                command += ['--config', 'identity.json']
            return subprocess.run(command + list(extra), cwd=base, capture_output=True, text=True)

    def table(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        return [line.split('\t') for line in result.stdout.splitlines()]

    def test_bundled_defaults_and_preserved_source(self):
        rows = self.table(self.run_table())
        self.assertEqual([r[0] for r in rows], ['WOOWU-AI', 'new-api'])
        self.assertTrue(all(len(r) == 9 and r[1:4] == ['李晓辉', '', '后端'] for r in rows))
        self.assertEqual([r[8] for r in rows], ['待验收', '完成'])

    def test_nine_columns_with_header_and_collaborators(self):
        source_text = ('| 开发平台 | 协作人员 | 工作内容 | 预估天数 | 完成状态 |\n'
                       '| --- | --- | --- | --- | --- |\n'
                       '| WOOWU-AI | 张三、李四 | 联调验证 | 2\t天 | 待验收 |\n'
                       '| new-api | | 更新示例 | 1 ||\n')
        rows = self.table(self.run_table(['--include-header'], source_text=source_text))
        self.assertEqual(rows, [
            ['开发平台', '人员', '协作人员', '工作岗位', '工作内容',
             '预估天数', '开始时间', '完成时间', '完成状态'],
            ['WOOWU-AI', '李晓辉', '张三、李四', '后端', '联调验证',
             '2 天', '2026-11-09', '2026-11-10', '待验收'],
            ['new-api', '李晓辉', '', '后端', '更新示例',
             '1', '2026-11-10', '2026-11-10', '完成'],
        ])

    def test_custom_configuration_and_cli_precedence(self):
        config = {'person': '张三', 'role': '前端'}
        self.assertEqual(self.table(self.run_table(config=config))[0][1:4], ['张三', '', '前端'])
        rows = self.table(self.run_table(['--person', '王五'], config=config))
        self.assertEqual(rows[0][1:4], ['王五', '', '前端'])
        rows = self.table(self.run_table(['--person', '赵六', '--role', '测试'], config=config))
        self.assertEqual(rows[0][1:4], ['赵六', '', '测试'])

    def test_global_status_override(self):
        rows = self.table(self.run_table(['--status', '进行中']))
        self.assertEqual([r[8] for r in rows], ['进行中', '进行中'])

    def test_invalid_configuration_fails_without_output(self):
        for config in [{'person': ''}, {'role': '前端\n后端'}, {'person': 123}, {'unknown': 'x'}, []]:
            with self.subTest(config=config):
                result = self.run_table(config=config)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, '')
        result = self.run_table(['--config', 'missing.json'])
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, '')


if __name__ == '__main__':
    unittest.main()
