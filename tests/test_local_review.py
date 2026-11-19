import pytest

from birdwatcher.local_review import ReviewStore


def test_review_state_resume_and_export(tmp_path):
    root = tmp_path / 'candidates'
    (root / '2026-01-01').mkdir(parents=True)
    (root / '2026-01-02').mkdir()
    image = root / '2026-01-01' / '120000.jpg'
    image.write_bytes(b'original')
    (root / '2026-01-02' / '130000.jpg').write_bytes(b'second')
    store = ReviewStore(root, tmp_path / 'state.sqlite')
    assert store.first_unfinished() == '2026-01-01'
    store.classify('2026-01-01', '120000.jpg', 'good')
    store.finish('2026-01-01', True)
    assert ReviewStore(root, tmp_path / 'state.sqlite').first_unfinished() == '2026-01-02'
    exported = store.export(tmp_path / 'export')
    assert len(exported) == 1
    assert exported[0].read_bytes() == b'original'
    assert image.read_bytes() == b'original'


def test_rejects_traversal_and_symlinks(tmp_path):
    root = tmp_path / 'candidates'
    (root / 'group').mkdir(parents=True)
    outside = tmp_path / 'outside.jpg'
    outside.write_bytes(b'private')
    (root / 'group' / 'link.jpg').symlink_to(outside)
    store = ReviewStore(root, tmp_path / 'state.sqlite')
    for group, image in [('..', 'outside.jpg'), ('group', '../outside.jpg'), ('group', 'link.jpg')]:
        with pytest.raises(ValueError):
            store.classify(group, image, 'bird')
    assert store.images('group') == []


def test_classification_validation(tmp_path):
    root = tmp_path / 'candidates'
    (root / 'group').mkdir(parents=True)
    (root / 'group' / 'a.jpg').write_bytes(b'x')
    store = ReviewStore(root, tmp_path / 'state.sqlite')
    for label in ('good', 'no bird', 'bird'):
        store.classify('group', 'a.jpg', label)
        assert store.decisions('group')['a.jpg'] == label
    with pytest.raises(ValueError):
        store.classify('group', 'a.jpg', 'unknown')


def test_http_review_csrf_navigation_and_persistence(tmp_path):
    import io
    import re
    from urllib.parse import urlencode

    from birdwatcher.local_review_web import ReviewApp

    root = tmp_path / 'candidates'
    (root / 'day').mkdir(parents=True)
    (root / 'day' / 'a.jpg').write_bytes(b'picture')
    app = ReviewApp(ReviewStore(root, tmp_path / 'state.sqlite'))

    def request(method, path, data=None, host='localhost:8000'):
        encoded = urlencode(data or {}).encode()
        env = {'REQUEST_METHOD': method, 'PATH_INFO': path, 'QUERY_STRING': '',
               'HTTP_HOST': host, 'CONTENT_LENGTH': str(len(encoded)),
               'wsgi.input': io.BytesIO(encoded)}
        result = {}
        def start(status, headers):
            result['status'] = int(status.split()[0])
            result['headers'] = dict(headers)
        result['body'] = b''.join(app(env, start))
        return result

    page = request('GET', '/')
    assert page['status'] == 200
    token = re.search(rb'name="csrf" value="([^"]+)"', page['body']).group(1).decode()
    assert request('POST', '/classify', {'group': 'day', 'image': 'a.jpg', 'label': 'good'})['status'] == 403
    assert request('POST', '/classify', {'csrf': token, 'group': 'day', 'image': 'a.jpg', 'label': 'good'})['status'] == 303
    assert ReviewStore(root, tmp_path / 'state.sqlite').decisions('day') == {'a.jpg': 'good'}
    assert request('GET', '/', host='evil.example')['status'] == 403
    assert request('GET', '/image/day/a.jpg')['body'] == b'picture'
    assert request('GET', '/image/day/..%2Foutside.jpg')['status'] == 404


def test_export_refuses_existing_files_and_candidate_subdirectory(tmp_path):
    root = tmp_path / 'candidates'
    (root / 'day').mkdir(parents=True)
    (root / 'day' / 'a.jpg').write_bytes(b'original')
    store = ReviewStore(root, tmp_path / 'state.sqlite')
    store.classify('day', 'a.jpg', 'good')
    with pytest.raises(ValueError):
        store.export(root / 'export')
    target = tmp_path / 'export' / 'day' / 'a.jpg'
    target.parent.mkdir(parents=True)
    target.write_bytes(b'existing')
    with pytest.raises(FileExistsError):
        store.export(target.parent.parent)
    assert target.read_bytes() == b'existing'


def test_real_http_serves_unicode_names(tmp_path):
    import threading
    from urllib.parse import quote
    from urllib.request import urlopen
    from wsgiref.simple_server import make_server

    from birdwatcher.local_review_web import ReviewApp

    root = tmp_path / 'candidates'
    (root / 'día').mkdir(parents=True)
    (root / 'día' / 'á.jpg').write_bytes(b'photo')
    app = ReviewApp(ReviewStore(root, tmp_path / 'state.sqlite'))
    with make_server('127.0.0.1', 0, app) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = 'http://127.0.0.1:%d/image/%s/%s' % (server.server_port, quote('día'), quote('á.jpg'))
            assert urlopen(url).read() == b'photo'
        finally:
            server.shutdown()
            thread.join()


def test_malformed_csrf_token_is_rejected(tmp_path):
    import io
    from urllib.parse import urlencode

    from birdwatcher.local_review_web import ReviewApp

    root = tmp_path / 'candidates'
    root.mkdir()
    app = ReviewApp(ReviewStore(root, tmp_path / 'state.sqlite'))
    data = urlencode({'csrf': 'é'}).encode()
    env = {'REQUEST_METHOD': 'POST', 'PATH_INFO': '/finish', 'HTTP_HOST': 'localhost',
           'CONTENT_LENGTH': str(len(data)), 'wsgi.input': io.BytesIO(data)}
    result = []
    body = b''.join(app(env, lambda status, headers: result.append(status)))
    assert result == ['403 Forbidden']
    assert body == b'Forbidden'


def test_export_preserves_source_file_mtime(tmp_path):
    import os

    root = tmp_path / 'candidates'
    (root / 'day').mkdir(parents=True)
    image = root / 'day' / 'a.jpg'
    image.write_bytes(b'photo')
    os.utime(image, (1_700_000_000, 1_700_000_000))
    store = ReviewStore(root, tmp_path / 'state.sqlite')
    store.classify('day', 'a.jpg', 'good')
    exported = store.export(tmp_path / 'export')[0]
    assert exported.stat().st_mtime_ns == image.stat().st_mtime_ns
