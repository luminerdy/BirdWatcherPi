"""Local-only web interface for reviewing a user-provided candidate tree."""

import argparse
import html
import secrets
import sys
from pathlib import Path
from urllib.parse import parse_qs, quote, urlencode
from wsgiref.simple_server import make_server

from .local_review import ReviewStore


class ReviewApp:
    def __init__(self, store, allowed_hosts=('localhost', '127.0.0.1')):
        self.store = store
        self.allowed_hosts = frozenset(allowed_hosts)
        self.csrf = secrets.token_urlsafe(32)

    def __call__(self, env, start):
        def reply(status, body, content_type='text/html; charset=utf-8', extra=()):
            start(status, [('Content-Type', content_type), ('Cache-Control', 'no-store'),
                           ('X-Content-Type-Options', 'nosniff'),
                           ('Content-Security-Policy', "default-src 'self'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'"),
                           *extra])
            return [body if isinstance(body, bytes) else body.encode()]

        host = env.get('HTTP_HOST', '').split(':', 1)[0].lower()
        if host not in self.allowed_hosts:
            return reply('403 Forbidden', 'Forbidden')
        method = env['REQUEST_METHOD']
        try:
            path = env['PATH_INFO'].encode('latin-1').decode('utf-8')
            if method == 'POST' and path in ('/classify', '/finish'):
                size = int(env.get('CONTENT_LENGTH') or '0')
                if size < 0 or size > 8192:
                    return reply('400 Bad Request', 'Invalid request')
                data = parse_qs(env['wsgi.input'].read(size).decode('utf-8'),
                                max_num_fields=12, keep_blank_values=True)
                get = lambda key: data.get(key, [''])[0]  # noqa: E731
                if not secrets.compare_digest(get('csrf').encode('utf-8'), self.csrf.encode('ascii')):
                    return reply('403 Forbidden', 'Forbidden')
                group = get('group')
                if path == '/classify':
                    self.store.classify(group, get('image'), get('label'))
                else:
                    if get('finished') not in ('0', '1'):
                        raise ValueError('invalid finished flag')
                    self.store.finish(group, get('finished') == '1')
                return reply('303 See Other', '', extra=[('Location', '/?' + urlencode({'group': group}))])
            if method == 'GET' and path.startswith('/image/'):
                parts = path.split('/')
                if len(parts) != 4:
                    raise ValueError('invalid image')
                image = self.store._image(parts[2], parts[3])
                mime = 'image/png' if image.suffix.lower() == '.png' else 'image/jpeg'
                return reply('200 OK', image.read_bytes(), mime)
            if method != 'GET' or path != '/':
                return reply('404 Not Found', 'Not found')
            groups = self.store.groups()
            group = parse_qs(env.get('QUERY_STRING', '')).get('group', [self.store.first_unfinished() or (groups[0] if groups else '')])[0]
            esc = lambda s: html.escape(s, quote=True)  # noqa: E731
            page = ['<!doctype html><html><head><meta charset="utf-8"><title>Bird review</title></head><body><h1>Bird review</h1>']
            page.append('<nav>' + ' | '.join('<a href="/?' + esc(urlencode({'group': g})) + '">' + esc(g) + '</a>' for g in groups) + '</nav>')
            if group:
                decisions = self.store.decisions(group)
                page.append('<h2>' + esc(group) + '</h2>')
                hidden = '<input type="hidden" name="csrf" value="' + esc(self.csrf) + '"><input type="hidden" name="group" value="' + esc(group) + '">'
                for image in self.store.images(group):
                    url = '/image/' + quote(group, safe='') + '/' + quote(image, safe='')
                    page.append('<section><h3>' + esc(image) + '</h3><img width="480" src="' + esc(url) + '" alt=""><p>Current: ' + esc(decisions.get(image, 'unreviewed')) + '</p><form method="post" action="/classify">' + hidden + '<input type="hidden" name="image" value="' + esc(image) + '">' + ''.join('<button name="label" value="' + esc(label) + '">' + esc(label) + '</button>' for label in ('good', 'no bird', 'bird')) + '</form></section>')
                page.append('<form method="post" action="/finish">' + hidden + '<button name="finished" value="1">Mark group finished</button><button name="finished" value="0">Reopen group</button></form>')
            else:
                page.append('<p>No groups found.</p>')
            return reply('200 OK', ''.join(page) + '</body></html>')
        except (ValueError, UnicodeError, OSError):
            return reply('404 Not Found', 'Not found')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidates', type=Path, required=True)
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--export', type=Path, help='copy good images to this directory, then exit')
    args = parser.parse_args()
    store = ReviewStore(args.candidates, args.state)
    if args.export:
        print(f'Exported {len(store.export(args.export))} images')
        return
    if args.host != '127.0.0.1':
        print('WARNING: non-loopback access has no authentication or encryption; use only on a trusted network.', file=sys.stderr)
    app = ReviewApp(store, ('127.0.0.1', 'localhost', args.host))
    with make_server(args.host, args.port, app) as server:
        print(f'Review server listening on {args.host}:{args.port}', file=sys.stderr)
        server.serve_forever()


if __name__ == '__main__':
    main()
