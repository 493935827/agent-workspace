#!/usr/bin/env python3
"""Machine-readable managed serial CLI; no GUI dependency."""
import argparse
import json
import sys
import time

from serial_client import Client
from serial_commands import HELP, parse_command
from serial_protocol import ActionError


def main():
    parser = argparse.ArgumentParser(description='Managed serial actions (JSON output)')
    parser.add_argument('action', nargs='?', default='status')
    parser.add_argument('--params', default='{}', help='JSON object')
    parser.add_argument('--command', help='Command-bar grammar: action followed by JSON object')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--control', type=int, default=8889)
    parser.add_argument('--token', help='Existing Agent lease; never automatically reacquired')
    parser.add_argument('--expect-pid', type=int, help='Require managed process identity')
    parser.add_argument('--expect-script', help='Require managed source path')
    parser.add_argument('--wait', type=float, default=0, help='Wait up to N seconds for send completion')
    args = parser.parse_args()
    try:
        action, params = parse_command(args.command) if args.command else (args.action, json.loads(args.params))
        if not isinstance(params, dict):
            raise ValueError('params must be a JSON object')
        if action == 'help':
            print(json.dumps(dict(ok=True, result=HELP)))
            return 0
        with Client(args.host, args.control) as client:
            if args.expect_pid is not None or args.expect_script:
                from pathlib import Path
                state = client.call('status')
                if ((args.expect_pid is not None and state['pid'] != args.expect_pid) or
                        (args.expect_script and Path(state['script']).resolve() != Path(args.expect_script).resolve())):
                    raise ActionError('identity', 'Managed process does not match PID and script')
                if action == 'service.stop':
                    params['instance'] = state['instance']
            result = client.call(action, token=args.token, **params)
            if args.wait and action in ('send', 'send.hex'):
                deadline = time.monotonic() + args.wait
                while result['state'] in ('queued', 'writing') and time.monotonic() < deadline:
                    time.sleep(.02)
                    result = client.call('job.status', job_id=result['job_id'])
                if result['state'] != 'written':
                    print(json.dumps(dict(ok=False, result=result, error=dict(code='send_incomplete',
                          message='Send is incomplete or outcome unknown; do not automatically retry'))))
                    return 2
            print(json.dumps(dict(ok=True, result=result), ensure_ascii=True))
            return 0
    except (ActionError, OSError, EOFError, ValueError, TypeError) as exc:
        print(json.dumps(dict(ok=False, error=dict(code=getattr(exc, 'code', 'client_error'), message=str(exc)))))
        return 2


if __name__ == '__main__':
    sys.exit(main())
