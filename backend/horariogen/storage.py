import json
from pathlib import Path
from threading import Lock
from typing import Protocol
from uuid import uuid4


class Repository(Protocol):
    def put(self, collection: str, record: dict): ...
    def get(self, collection: str, identifier: str) -> dict: ...
    def all(self, collection: str) -> list[dict]: ...
    def save_original(self, identifier: str, raw: bytes): ...
    def original(self, identifier: str) -> bytes: ...
    def save_source(self, identifier: str, raw: bytes): ...


class FileRepository:
    def __init__(self, root: Path):
        self.root = root
        self.lock = Lock()
        for collection in ("datasets", "runs"):
            (root / collection).mkdir(parents=True, exist_ok=True)

    def put(self, collection, record):
        folder = self.root / collection
        temporary = folder / f"{uuid4()}.tmp"
        try:
            temporary.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
            with self.lock:
                temporary.replace(folder / f"{record['id']}.json")
        finally:
            temporary.unlink(missing_ok=True)

    def get(self, collection, identifier):
        with self.lock:
            raw = (self.root / collection / f"{identifier}.json").read_text(encoding="utf-8")
        return json.loads(raw)

    def all(self, collection):
        return [self.get(collection, p.stem) for p in sorted((self.root / collection).glob("*.json"))]

    def save_original(self, identifier, raw):
        (self.root / "datasets" / f"{identifier}.csv").write_bytes(raw)

    def original(self, identifier):
        return (self.root / "datasets" / f"{identifier}.csv").read_bytes()


    def save_source(self, identifier, raw):
        (self.root / "datasets" / f"{identifier}.source").write_bytes(raw)
