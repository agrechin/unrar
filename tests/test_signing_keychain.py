"""Exercise the signing script's keychain lifecycle without Apple tools or secrets."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


# All platform/signing commands are intercepted. Python heredocs still execute
# normally so the real search-list parsing and secret-file cleanup are exercised.
FAKE_TOOL = r'''
import json, os, sys
from pathlib import Path
tool = Path(sys.argv[0]).name
args = sys.argv[1:]
state_path = Path(os.environ['TEST_STATE'])
state = json.loads(state_path.read_text())
mode = os.environ['TEST_FAILURE']
def save():
    state_path.write_text(json.dumps(state))
if tool == 'python3':
    if args[0] == '-':
        os.execv(sys.executable, [sys.executable, *args])
    if 'preflight' in args:
        print('7.23.0')
elif tool == 'uname':
    print('Darwin' if args == ['-s'] else 'arm64')
elif tool == 'lipo':
    print('arm64')
elif tool == 'openssl':
    print('fake-keychain-password')
elif tool == 'security':
    command = args[0]
    if command == 'list-keychains':
        if '-s' not in args:
            if mode == 'snapshot':
                sys.exit(45)
            for path in state['search']:
                print('    ' + json.dumps(path))
        else:
            paths = args[args.index('-s') + 1:]
            state['events'].append(['search', paths])
            state['search'] = paths
            save()
            if mode == 'activate' and paths != state['original']:
                sys.exit(44)
            if mode == 'restore' and paths == state['original']:
                sys.exit(46)
    elif command == 'create-keychain':
        state['keychain'] = args[-1]
        state['search'].append(args[-1])
        save()
    elif command == 'import' and mode == 'import':
        sys.exit(43)
    elif command == 'find-identity':
        print('  1) ' + 'A' * 40 + ' "Developer ID Application: Test"')
    elif command == 'delete-keychain':
        state['events'].append(['delete', args[-1]])
        save()
elif tool == 'codesign' and '--sign' in args:
    if state['search'] != [state['keychain'], *state['original']]:
        sys.exit('no identity found: temporary keychain is not on the search list')
    state['events'].append(['sign', args[-1]])
    save()
    if mode == 'sign':
        sys.exit(42)
elif tool == 'hdiutil' and args[0] == 'create':
    Path(args[-1]).write_bytes(b'test disk image')
elif tool == 'xcrun' and args[:2] == ['notarytool', 'submit']:
    print(json.dumps({'id': 'test-submission', 'status': 'Accepted'}))
elif tool == 'xcrun' and args[:2] == ['notarytool', 'log']:
    Path(args[-1]).write_text('{}')
'''


class SigningKeychainTests(unittest.TestCase):
    def test_signing_does_not_execute_the_candidate_binary(self):
        script = (Path(__file__).resolve().parents[1] / 'scripts/sign-notarize.sh').read_text()
        self.assertNotIn('smoke.py', script)
        self.assertNotIn('hdiutil attach', script)

    def run_script(self, original, failure=''):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        scripts = root / 'scripts'
        scripts.mkdir()
        source = Path(__file__).resolve().parents[1] / 'scripts/sign-notarize.sh'
        shutil.copyfile(source, scripts / source.name)
        build = root / '.build/macos'
        build.mkdir(parents=True)
        for name in ('unrar', 'license.txt', 'acknow.txt', 'build-info.json'):
            (build / name).write_text('fixture')
        fake_bin = root / 'bin'
        fake_bin.mkdir()
        for name in ('python3', 'uname', 'lipo', 'openssl', 'security', 'codesign',
                     'hdiutil', 'xcrun', 'spctl', 'mount'):
            tool = fake_bin / name
            tool.write_text(f'#!{sys.executable}\n' + FAKE_TOOL)
            tool.chmod(0o755)
        state_path = root / 'state.json'
        state_path.write_text(json.dumps({'original': original, 'search': list(original), 'events': []}))
        env = {**os.environ, 'PATH': str(fake_bin) + os.pathsep + os.environ['PATH'],
               'TMPDIR': str(root), 'TEST_STATE': str(state_path), 'TEST_FAILURE': failure,
               'MACOS_SIGN_P12': 'dGVzdA==', 'MACOS_NOTARY_KEY': 'dGVzdA==',
               'MACOS_SIGN_PASSWORD': 'test-password', 'MACOS_NOTARY_KEY_ID': 'test-id',
               'MACOS_NOTARY_ISSUER_ID': 'test-issuer'}
        result = subprocess.run(['bash', str(scripts / source.name), 'v7.23.0'],
                                env=env, capture_output=True, text=True)
        state = json.loads(state_path.read_text())
        self.assertEqual(list(root.glob('unrar-sign.*')), [], 'Temporary key material must be removed')
        self.assertEqual(state['events'][-1][0], 'delete', 'Cleanup must attempt keychain deletion')
        return result, state

    def test_signing_uses_temporary_keychain_and_restores_original_order(self):
        for original in ([], ['/Users/runner/login.keychain-db', '/tmp/chain with spaces.keychain-db']):
            with self.subTest(original=original):
                result, state = self.run_script(original)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(state['search'], original)
                self.assertEqual(sum(event[0] == 'sign' for event in state['events']), 2)

    def test_failures_preserve_exit_status_and_restore_search_list(self):
        original = ['/Users/runner/login.keychain-db', '/tmp/chain with spaces.keychain-db']
        for failure, code in (('snapshot', 45), ('import', 43), ('activate', 44), ('sign', 42)):
            with self.subTest(failure=failure):
                result, state = self.run_script(original, failure)
                self.assertEqual(result.returncode, code, result.stderr)
                self.assertEqual(state['search'], original)
                if failure != 'sign':
                    self.assertFalse(any(event[0] == 'sign' for event in state['events']))

    def test_cleanup_failure_cannot_report_success(self):
        result, _ = self.run_script(['/Users/runner/login.keychain-db'], 'restore')
        self.assertEqual(result.returncode, 1)
        self.assertIn('Failed to restore the keychain search list', result.stderr)
