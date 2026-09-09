"""Report pending data separately; the +8h attempt must fail if still pending."""
import os
from .app import ROOT, read_json


def failed(status, final=False):
    pending = status.get('signal_pending') or status.get('comparison_pending')
    return bool(status.get('comparison_ok') is False
                or (status.get('ok') is False and not status.get('signal_pending'))
                or (final and pending))


def main():
    status = read_json(ROOT / 'work/status.json')
    final = os.environ.get('FINAL_ATTEMPT') == 'true'
    error = failed(status, final)
    message = status.get('comparison_error') or status.get('error')
    if message:
        prefix = '::error::' if error else '::warning::'
        print(prefix + ('Final retry exhausted. ' if final and error else '') + message)
    raise SystemExit(int(error))


if __name__ == '__main__':
    main()
