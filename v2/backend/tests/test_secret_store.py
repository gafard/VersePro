import asyncio

from app.services.secret_store import SecretStore


class FakeDatabase:
    def __init__(self):
        self.values = {"deepgram_api_key": "legacy-secret"}
        self.deleted = []

    async def get_setting(self, key, default=""):
        return self.values.get(key, default)

    async def delete_setting(self, key):
        self.deleted.append(key)


def test_failed_keyring_migration_keeps_database_secret():
    store = SecretStore()
    store.available = False
    database = FakeDatabase()

    asyncio.run(store.migrate_from_database(database))

    assert database.deleted == []
    assert store._memory["deepgram_api_key"] == "legacy-secret"


def test_successful_keyring_migration_deletes_database_secret(monkeypatch):
    store = SecretStore()
    database = FakeDatabase()

    async def stored(_key, _value):
        return True

    monkeypatch.setattr(store, "set", stored)
    asyncio.run(store.migrate_from_database(database))

    assert database.deleted == ["deepgram_api_key"]
