"""
Service de Base de Données SQLite
Historique des versets + Statistiques
"""

import asyncio
import sqlite3
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from pathlib import Path
from loguru import logger
import aiosqlite


class DatabaseService:
    """
    Service de base de données pour l'historique et les stats
    
    Tables:
    - detected_verses: Historique des versets détectés
    - sessions: Sessions de culte
    - statistics: Statistiques agrégées
    """
    
    # Ancré au dossier backend (parents[2] = v2/backend/) pour être indépendant
    # du répertoire depuis lequel le serveur est lancé
    DEFAULT_DB_PATH = Path(__file__).resolve().parents[2] / "versepro.db"

    def __init__(self, db_path: str | Path | None = None):
        self.db_path = Path(db_path) if db_path else self.DEFAULT_DB_PATH
        self.db: Optional[aiosqlite.Connection] = None
        
        logger.info(f"📊 DatabaseService initialisé: {self.db_path}")
    
    async def connect(self):
        """Ouvre la connexion à la base de données"""
        self.db = await aiosqlite.connect(self.db_path)
        self.db.row_factory = aiosqlite.Row
        await self._create_tables()
        logger.info("✅ Base de données connectée")
    
    async def disconnect(self):
        """Ferme la connexion"""
        if self.db:
            await self.db.close()
        logger.info("🔒 Base de données fermée")
    
    async def _create_tables(self):
        """Crée les tables si elles n'existent pas"""
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS detected_verses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reference TEXT NOT NULL,
                book TEXT NOT NULL,
                book_abbr TEXT NOT NULL,
                chapter INTEGER NOT NULL,
                verse_start INTEGER NOT NULL,
                verse_end INTEGER,
                text TEXT,
                version TEXT DEFAULT 'LSG',
                session_id INTEGER,
                detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                sent_to_propresenter BOOLEAN DEFAULT TRUE,
                validated_manually BOOLEAN DEFAULT FALSE,
                context_text TEXT,
                confidence INTEGER DEFAULT 100,
                source TEXT DEFAULT 'local'
            )
        """)
        
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                ended_at TIMESTAMP,
                verse_count INTEGER DEFAULT 0,
                duration_minutes INTEGER,
                notes TEXT,
                transcript TEXT,
                summary TEXT
            )
        """)
        
        # Ajout des colonnes si la table existait déjà (migration rétrocompatible)
        try:
            await self.db.execute("ALTER TABLE sessions ADD COLUMN transcript TEXT")
        except Exception:
            pass
            
        try:
            await self.db.execute("ALTER TABLE sessions ADD COLUMN summary TEXT")
        except Exception:
            pass

        try:
            await self.db.execute("ALTER TABLE detected_verses ADD COLUMN confidence INTEGER DEFAULT 100")
        except Exception:
            pass

        try:
            await self.db.execute("ALTER TABLE detected_verses ADD COLUMN source TEXT DEFAULT 'local'")
        except Exception:
            pass
            
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS statistics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date DATE UNIQUE,
                total_verses INTEGER DEFAULT 0,
                unique_references INTEGER DEFAULT 0,
                most_cited_book TEXT,
                most_cited_verse TEXT,
                avg_verses_per_session REAL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Index pour les performances
        await self.db.execute("""
            CREATE INDEX IF NOT EXISTS idx_detected_at 
            ON detected_verses(detected_at)
        """)
        
        await self.db.execute("""
            CREATE INDEX IF NOT EXISTS idx_reference 
            ON detected_verses(reference)
        """)
        
        await self.db.commit()
        logger.debug("📋 Tables créées/vérifiées et schéma mis à jour")
    
    # ============================================
    # Détection de versets
    # ============================================
    
    async def add_detected_verse(self, reference: Dict[str, Any], 
                                  session_id: Optional[int] = None,
                                  context: str = "",
                                  confidence: int = 100,
                                  source: str = "local") -> int:
        """
        Ajoute un verset détecté à l'historique
        
        Returns:
          ID du verset inséré
        """
        cursor = await self.db.execute("""
            INSERT INTO detected_verses 
            (reference, book, book_abbr, chapter, verse_start, verse_end, 
             text, version, session_id, context_text, confidence, source)
            VALUES (:reference, :book, :book_abbr, :chapter, :verse_start, :verse_end, 
             :text, :version, :session_id, :context_text, :confidence, :source)
        """, {
            "reference": reference.get("reference"),
            "book": reference.get("book"),
            "book_abbr": reference.get("book_abbr"),
            "chapter": reference.get("chapter"),
            "verse_start": reference.get("verse_start") or 0,
            "verse_end": reference.get("verse_end"),
            "text": reference.get("text"),
            "version": reference.get("version", "LSG"),
            "session_id": session_id,
            "context_text": context[:500] if context else None,
            "confidence": confidence,
            "source": source
        })
        
        verse_id = cursor.lastrowid
        await self.db.commit()
        
        logger.info(f"📖 Verset ajouté à l'historique: {reference['reference']} (ID: {verse_id}, Source: {source}, Confiance: {confidence}%)")
        return verse_id
    
    async def get_recent_verses(self, limit: int = 50, 
                                 session_id: Optional[int] = None) -> List[Dict]:
        """Récupère les derniers versets détectés"""
        query = """
            SELECT * FROM detected_verses 
            WHERE 1=1
        """
        params = {}
        
        if session_id:
            query += " AND session_id = :session_id"
            params["session_id"] = session_id
        
        query += " ORDER BY detected_at DESC LIMIT :limit"
        params["limit"] = limit
        
        cursor = await self.db.execute(query, params)
        rows = await cursor.fetchall()
        
        return [dict(row) for row in rows]
    
    async def get_verse_by_id(self, verse_id: int) -> Optional[Dict]:
        """Récupère un verset par son ID"""
        cursor = await self.db.execute(
            "SELECT * FROM detected_verses WHERE id = :id", 
            {"id": verse_id}
        )
        row = await cursor.fetchone()
        return dict(row) if row else None
    
    async def update_verse_validation(self, verse_id: int, 
                                       validated: bool = True):
        """Marque un verset comme validé manuellement"""
        await self.db.execute("""
            UPDATE detected_verses 
            SET validated_manually = :validated
            WHERE id = :id
        """, {"validated": validated, "id": verse_id})
        await self.db.commit()
    
    async def delete_verse(self, verse_id: int):
        """Supprime un verset de l'historique"""
        await self.db.execute(
            "DELETE FROM detected_verses WHERE id = :id", 
            {"id": verse_id}
        )
        await self.db.commit()
    
    # ============================================
    # Sessions
    # ============================================
    
    async def create_session(self, name: str = "") -> int:
        """Crée une nouvelle session de culte"""
        session_name = name or f"Session {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        cursor = await self.db.execute(
            "INSERT INTO sessions (name) VALUES (:name)",
            {"name": session_name}
        )
        
        session_id = cursor.lastrowid
        await self.db.commit()
        
        logger.info(f"📁 Session créée: ID {session_id}")
        return session_id
    
    async def end_session(self, session_id: int):
        """Termine une session"""
        # Calcule le nombre de versets
        cursor = await self.db.execute("""
            SELECT COUNT(*) as count FROM detected_verses 
            WHERE session_id = :session_id
        """, {"session_id": session_id})
        row = await cursor.fetchone()
        verse_count = row["count"] if row else 0
        
        # Met à jour la session
        await self.db.execute("""
            UPDATE sessions 
            SET ended_at = CURRENT_TIMESTAMP,
                verse_count = :verse_count,
                duration_minutes = CAST(
                    (julianday(CURRENT_TIMESTAMP) - julianday(started_at)) * 24 * 60 
                    AS INTEGER
                )
            WHERE id = :id
        """, {"verse_count": verse_count, "id": session_id})
        
        await self.db.commit()
        logger.info(f"📁 Session terminée: {verse_count} versets")
        
    async def append_to_session_transcript(self, session_id: int, text: str):
        """Ajoute du texte à la transcription cumulée de la session de manière atomique"""
        if not text or not text.strip():
            return
            
        clean_text = text.strip()
        await self.db.execute("""
            UPDATE sessions 
            SET transcript = CASE 
                WHEN transcript IS NULL OR transcript = '' THEN :text 
                ELSE transcript || ' ' || :text 
            END 
            WHERE id = :id
        """, {"text": clean_text, "id": session_id})
        await self.db.commit()

    async def update_session_summary(self, session_id: int, summary: str):
        """Enregistre le résumé généré par l'IA"""
        await self.db.execute(
            "UPDATE sessions SET summary = ? WHERE id = ?",
            (summary, session_id)
        )
        await self.db.commit()
    
    async def get_session(self, session_id: int) -> Optional[Dict]:
        """Récupère une session par ID"""
        cursor = await self.db.execute(
            "SELECT * FROM sessions WHERE id = ?", 
            (session_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None
    
    async def get_recent_sessions(self, limit: int = 10) -> List[Dict]:
        """Récupère les dernières sessions"""
        cursor = await self.db.execute("""
            SELECT * FROM sessions 
            ORDER BY started_at DESC 
            LIMIT ?
        """, (limit,))
        
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
    
    # ============================================
    # Statistiques
    # ============================================
    
    async def get_statistics(self, days: int = 30) -> Dict[str, Any]:
        """
        Récupère les statistiques des X derniers jours
        
        Returns:
            Dict avec toutes les stats
        """
        stats = {}
        
        # Nombre total de versets
        cursor = await self.db.execute("""
            SELECT COUNT(*) as total FROM detected_verses 
            WHERE detected_at >= datetime('now', '-' || ? || ' days')
        """, (days,))
        row = await cursor.fetchone()
        stats["total_verses"] = row["total"] if row else 0
        
        # Références uniques
        cursor = await self.db.execute("""
            SELECT COUNT(DISTINCT reference) as unique_refs FROM detected_verses 
            WHERE detected_at >= datetime('now', '-' || ? || ' days')
        """, (days,))
        row = await cursor.fetchone()
        stats["unique_references"] = row["unique_refs"] if row else 0
        
        # Livres les plus cités
        cursor = await self.db.execute("""
            SELECT book, COUNT(*) as count 
            FROM detected_verses 
            WHERE detected_at >= datetime('now', '-' || ? || ' days')
            GROUP BY book 
            ORDER BY count DESC 
            LIMIT 5
        """, (days,))
        rows = await cursor.fetchall()
        stats["top_books"] = [dict(row) for row in rows]
        
        # Versets les plus cités
        cursor = await self.db.execute("""
            SELECT reference, COUNT(*) as count 
            FROM detected_verses 
            WHERE detected_at >= datetime('now', '-' || ? || ' days')
            GROUP BY reference 
            ORDER BY count DESC 
            LIMIT 10
        """, (days,))
        rows = await cursor.fetchall()
        stats["top_verses"] = [dict(row) for row in rows]
        
        # Nombre de sessions
        cursor = await self.db.execute("""
            SELECT COUNT(*) as count FROM sessions 
            WHERE started_at >= datetime('now', '-' || ? || ' days')
        """, (days,))
        row = await cursor.fetchone()
        stats["total_sessions"] = row["count"] if row else 0
        
        # Moyenne de versets par session
        if stats["total_sessions"] > 0:
            stats["avg_verses_per_session"] = stats["total_verses"] / stats["total_sessions"]
        else:
            stats["avg_verses_per_session"] = 0
        
        # Versets par jour (pour graphique)
        cursor = await self.db.execute("""
            SELECT DATE(detected_at) as date, COUNT(*) as count 
            FROM detected_verses 
            WHERE detected_at >= datetime('now', '-' || ? || ' days')
            GROUP BY DATE(detected_at) 
            ORDER BY date
        """, (days,))
        rows = await cursor.fetchall()
        stats["verses_per_day"] = [dict(row) for row in rows]
        
        return stats
    
    async def get_book_statistics(self, days: int = 30) -> List[Dict]:
        """Statistiques par livre de la Bible"""
        cursor = await self.db.execute("""
            SELECT 
                book,
                book_abbr,
                COUNT(*) as total_verses,
                COUNT(DISTINCT chapter) as chapters_used,
                MIN(detected_at) as first_used,
                MAX(detected_at) as last_used
            FROM detected_verses 
            WHERE detected_at >= datetime('now', '-' || ? || ' days')
            GROUP BY book, book_abbr
            ORDER BY total_verses DESC
        """, (days,))
        
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
    
    async def get_daily_stats(self, date: str) -> Dict:
        """Statistiques pour un jour spécifique"""
        cursor = await self.db.execute("""
            SELECT 
                COUNT(*) as total_verses,
                COUNT(DISTINCT reference) as unique_refs,
                COUNT(DISTINCT session_id) as sessions_count
            FROM detected_verses 
            WHERE DATE(detected_at) = ?
        """, (date,))
        
        row = await cursor.fetchone()
        return dict(row) if row else {}
    
    # ============================================
    # Export
    # ============================================
    
    async def export_to_csv(self, output_path: str, 
                            session_id: Optional[int] = None) -> str:
        """Exporte l'historique en CSV"""
        import csv
        
        query = "SELECT * FROM detected_verses WHERE 1=1"
        params = []
        
        if session_id:
            query += " AND session_id = ?"
            params.append(session_id)
        
        query += " ORDER BY detected_at"
        
        cursor = await self.db.execute(query, params)
        rows = await cursor.fetchall()
        
        if not rows:
            return ""
        
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            for row in rows:
                writer.writerow(dict(row))
        
        logger.info(f"📄 Export CSV: {output_path} ({len(rows)} versets)")
        return output_path
    
    async def export_to_json(self, output_path: str,
                              session_id: Optional[int] = None) -> str:
        """Exporte l'historique en JSON"""
        import json
        
        verses = await self.get_recent_verses(limit=10000, session_id=session_id)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(verses, f, indent=2, ensure_ascii=False)
        
        logger.info(f"📄 Export JSON: {output_path} ({len(verses)} versets)")
        return output_path
    
    # ============================================
    # Nettoyage
    # ============================================
    
    async def cleanup_old_data(self, days: int = 365):
        """Supprime les données de plus de X jours"""
        cursor = await self.db.execute("""
            DELETE FROM detected_verses 
            WHERE detected_at < datetime('now', '-' || ? || ' days')
        """, (days,))
        
        deleted = cursor.rowcount
        await self.db.commit()
        
        logger.info(f"🧹 Nettoyage: {deleted} versets supprimés")
        return deleted

    # ============================================
    # Réglages persistants (app_settings)
    # ============================================

    async def get_setting(self, key: str, default: Any = None) -> Any:
        """Récupère une valeur de configuration"""
        if not self.db:
            return default
        try:
            async with self.db.execute("SELECT value FROM app_settings WHERE key = ?", (key,)) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else default
        except Exception as e:
            logger.error(f"Erreur get_setting({key}): {e}")
            return default

    async def set_setting(self, key: str, value: Any):
        """Enregistre une valeur de configuration"""
        if not self.db:
            return
        try:
            await self.db.execute(
                "INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)", 
                (key, str(value))
            )
            await self.db.commit()
            logger.debug(f"⚙️ Config persistée : {key} = {value}")
        except Exception as e:
            logger.error(f"Erreur set_setting({key}): {e}")

    async def get_all_settings(self) -> Dict[str, str]:
        """Récupère l'ensemble des configurations"""
        if not self.db:
            return {}
        try:
            async with self.db.execute("SELECT key, value FROM app_settings") as cursor:
                rows = await cursor.fetchall()
                return {row[0]: row[1] for row in rows}
        except Exception as e:
            logger.error(f"Erreur get_all_settings: {e}")
            return {}


# Singleton
db_service: Optional[DatabaseService] = None


def get_database() -> DatabaseService:
    """Retourne l'instance de la base de données"""
    global db_service
    if db_service is None:
        db_service = DatabaseService()
    return db_service
