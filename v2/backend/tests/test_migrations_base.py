"""Les migrations ne doivent avaler QUE « colonne déjà présente »."""

import asyncio

import aiosqlite
import pytest

from app.services.database import DatabaseService


class _BaseQuiEchoue:
    """Connexion dont l'écriture échoue, comme une base verrouillée."""

    async def execute(self, _instruction):
        raise aiosqlite.OperationalError("database is locked")


def test_colonne_deja_presente_est_toleree():
    async def scenario():
        service = DatabaseService.__new__(DatabaseService)
        async with aiosqlite.connect(":memory:") as db:
            service.db = db
            await db.execute("CREATE TABLE sessions (id INTEGER, summary TEXT)")
            await service._ajouter_colonne("ALTER TABLE sessions ADD COLUMN summary TEXT")
            await service._ajouter_colonne("ALTER TABLE sessions ADD COLUMN transcript TEXT")
            colonnes = [r[1] async for r in await db.execute("PRAGMA table_info(sessions)")]
        return colonnes

    assert asyncio.run(scenario()) == ["id", "summary", "transcript"]


def test_une_vraie_erreur_n_est_plus_avalee():
    service = DatabaseService.__new__(DatabaseService)
    service.db = _BaseQuiEchoue()

    with pytest.raises(aiosqlite.OperationalError, match="locked"):
        asyncio.run(service._ajouter_colonne("ALTER TABLE sessions ADD COLUMN summary TEXT"))
