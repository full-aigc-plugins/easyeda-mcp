"""高层工具保护只读范围、目标文档与导出结果。"""
import base64
from pathlib import Path
import tempfile
import unittest
from easyeda_mcp.workflows import Workflows, WorkflowError


class FakeNative:
    def __init__(self, no_project=False, changed=False):
        self.info = {'serverInfo': {'name': 'JLCEDA Pro', 'version': 'test'}}
        self.no_project = no_project
        self.changed = changed
        self.invocations = []
        self.calls = []
        self.result = True

    def help(self, path=None):
        return {}

    def current_project(self, session=None):
        return {'status': 'no_project' if self.no_project else 'read', 'sessionId': 's1',
                'project': None if self.no_project else {'uuid': 'p1'},
                'currentDocument': None if self.no_project else {'uuid': 'd1', 'documentType': 3}}

    def call(self, path, data=None):
        self.calls.append((path, data))
        if path == 'doc.api':
            if data.get('methodName'):
                return {'params': [], 'returns': {'type': 'boolean'}}
            return {'callPath': 'pcb_Document', 'methods': [{'name': 'autoRouting'}, {'name': 'autoLayout'}]}
        if path == 'invoke':
            self.invocations.append(data)
            return {'targetMatched': not self.changed, 'value': self.result}
        return []


class WorkflowTests(unittest.TestCase):
    def test_no_project_is_not_fabricated(self):
        native = FakeNative(no_project=True)
        result = Workflows(native).inspect_project()
        self.assertEqual(result['status'], 'no_project')
        self.assertEqual(native.invocations, [])

    def test_write_disabled_before_native_mutation(self):
        native = FakeNative()
        with self.assertRaisesRegex(WorkflowError, 'allow-write'):
            Workflows(native).auto_route('d1')
        self.assertFalse(native.invocations)

    def test_document_type_and_identity_are_required(self):
        native = FakeNative()
        with self.assertRaisesRegex(WorkflowError, '目标文档'):
            Workflows(native, allow_write=True).auto_route('another')
        self.assertFalse(native.invocations)

    def test_switching_focus_is_detected_in_same_invocation(self):
        native = FakeNative(changed=True)
        with self.assertRaisesRegex(WorkflowError, '焦点'):
            Workflows(native, allow_write=True).auto_route('d1')
        code = native.invocations[0]['code']
        self.assertLess(code.index('targetMatched: false'), code.index('autoRouting('))

    def test_drc_false_remains_false(self):
        native = FakeNative()
        native.result = False
        result = Workflows(native).check_drc('d1')
        self.assertIs(result['passed'], False)

    def test_route_preserves_failed_networks(self):
        native = FakeNative()
        native.result = {'routedNets': 2, 'totalNets': 3, 'failedNets': ['GND']}
        result = Workflows(native, allow_write=True).auto_route('d1', ['GND'])
        self.assertEqual(result['result']['failedNets'], ['GND'])
        self.assertNotEqual(result['status'], 'verified')

    def test_export_rejects_escape_before_api_calls(self):
        native = FakeNative()
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(WorkflowError, '输出'):
                Workflows(native, output_root=Path(temp)).export_manufacturing('d1', '../escape', ['gerber'])
            self.assertFalse(native.invocations)

    def test_export_verifies_bytes_and_refuses_overwrite(self):
        native = FakeNative()
        native.result = {'name': 'Board.csv', 'size': 4, 'base64': base64.b64encode(b'test').decode()}
        with tempfile.TemporaryDirectory() as temp:
            w = Workflows(native, output_root=Path(temp))
            result = w.export_manufacturing('d1', 'out', ['bom'])
            self.assertEqual(len(result['files']), 1)
            path = Path(result['files'][0]['path'])
            self.assertEqual(path.read_bytes(), b'test')
            self.assertEqual(result['files'][0]['bytes'], 4)
            with self.assertRaises(WorkflowError):
                w.export_manufacturing('d1', 'out', ['bom'])
            self.assertEqual(path.read_bytes(), b'test')

    def test_generic_api_cannot_bypass_readonly(self):
        native = FakeNative()
        with self.assertRaisesRegex(WorkflowError, 'allow-write'):
            Workflows(native).call_api('d1', 'PCB_Document', 'autoLayout', [])
        self.assertFalse(native.invocations)


if __name__ == '__main__':
    unittest.main()
