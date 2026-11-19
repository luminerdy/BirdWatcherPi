"""Portable local review state and non-destructive keeper export.

The candidate tree must not be modified by untrusted local users while in use.
"""

import shutil
import sqlite3
from pathlib import Path


class ReviewStore:
    """Review images one directory (group) at a time."""

    def __init__(self, root: Path, state: Path):
        self.root = Path(root).resolve(strict=True)
        if not self.root.is_dir():
            raise ValueError('candidate root must be a directory')
        self.state = Path(state)
        with sqlite3.connect(self.state) as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS decisions (
                    group_name TEXT NOT NULL, image TEXT NOT NULL, label TEXT NOT NULL,
                    PRIMARY KEY (group_name, image));
                CREATE TABLE IF NOT EXISTS groups (
                    group_name TEXT PRIMARY KEY, finished INTEGER NOT NULL);
            ''')

    @staticmethod
    def _component(value):
        if not value or value in ('.', '..') or '/' in value or '\\' in value:
            raise ValueError('invalid path component')
        return value

    def _group(self, group):
        path = self.root / self._component(group)
        if path.is_symlink() or not path.is_dir() or path.resolve().parent != self.root:
            raise ValueError('invalid group')
        return path

    def _image(self, group, image):
        path = self._group(group) / self._component(image)
        if (path.is_symlink() or not path.is_file() or
                path.suffix.lower() not in ('.jpg', '.jpeg', '.png') or
                path.resolve().parent != self._group(group)):
            raise ValueError('invalid image')
        return path

    def groups(self):
        return sorted(p.name for p in self.root.iterdir() if p.is_dir() and not p.is_symlink())

    def images(self, group):
        folder = self._group(group)
        return sorted(p.name for p in folder.iterdir() if not p.is_symlink()
                      and p.is_file() and p.suffix.lower() in ('.jpg', '.jpeg', '.png'))

    def decisions(self, group):
        self._group(group)
        with sqlite3.connect(self.state) as db:
            return dict(db.execute('SELECT image, label FROM decisions WHERE group_name=?', (group,)))

    def classify(self, group, image, label):
        self._image(group, image)
        if label not in ('good', 'no bird', 'bird'):
            raise ValueError('invalid classification')
        with sqlite3.connect(self.state) as db:
            db.execute('INSERT OR REPLACE INTO decisions VALUES (?, ?, ?)', (group, image, label))

    def finish(self, group, finished):
        self._group(group)
        with sqlite3.connect(self.state) as db:
            db.execute('INSERT OR REPLACE INTO groups VALUES (?, ?)', (group, int(bool(finished))))

    def first_unfinished(self):
        with sqlite3.connect(self.state) as db:
            finished = {r[0] for r in db.execute('SELECT group_name FROM groups WHERE finished=1')}
        return next((group for group in self.groups() if group not in finished), None)

    def export(self, destination):
        destination = Path(destination).resolve()
        if destination == self.root or self.root in destination.parents:
            raise ValueError('export must be outside candidate root')
        copied = []
        with sqlite3.connect(self.state) as db:
            selected = list(db.execute("SELECT group_name, image FROM decisions WHERE label='good'"))
        for group, image in selected:
            source = self._image(group, image)
            folder = destination / group
            if folder.is_symlink():
                raise ValueError('symlink export directory')
            folder.mkdir(parents=True, exist_ok=True)
            target = folder / image
            # Never overwrite an earlier export, including through a symlink.
            with source.open('rb') as src, target.open('xb') as dst:
                shutil.copyfileobj(src, dst)
            shutil.copystat(source, target)
            copied.append(target)
        return copied
