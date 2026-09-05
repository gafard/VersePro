#!/usr/bin/env python3
"""
Test du parser de versets v2
"""

import asyncio
import sys
import pytest
from pathlib import Path

# Ajoute le backend au path
sys.path.insert(0, str(Path(__file__).parent))

from app.services.verse_parser import VerseParserService


@pytest.mark.anyio
async def test_parser():
    """Teste le parser avec différentes phrases"""
    
    parser = VerseParserService()
    
    test_cases = [
        # Patterns simples
        ("Lisons Jean 3:16", True),
        ("Ouvrez vos Bibles à Matthieu 5:13", True),
        ("Dans Luc chapitre 15 verset 11 à 32", True),
        
        # Avec abréviations
        ("Jn 3:16", True),
        ("Mt 5:1-12", True),
        ("1 Co 13:4-8", True),
        
        # Variations
        ("Psaume 23 verset 1", True),
        ("Ésaïe chapitre 53", True),
        ("Romains 8 versets 28 à 30", True),
        
        # Sans référence / Recherche textuelle
        ("Bonjour à tous", False),
        ("Dieu est amour", True),                # Doit détecter 1 Jn 4:8 via texte
        ("La Bible dit", False),
        ("Car Dieu a tant aimé le monde", True),  # Doit détecter Jn 3:16 via texte
        ("L'Éternel est mon berger", True),      # Doit détecter Ps 23:1 via texte
        # Nombres en toutes lettres (ASR local de Vosk)
        ("Jean trois seize", True),               # Doit détecter Jean 3:16
        ("Romains huit verset vingt huit", True),  # Doit détecter Romains 8:28
        ("Psaume cent dix neuf verset cent soixante seize", True), # Doit détecter Psaumes 119:176
        
        # Références invalides (à rejeter)
        ("Jean 100:1", False),  # Chapitre inexistant
        ("Matthieu 5:200", False),  # Verset inexistant
    ]
    
    print("🧪 Test du parser de versets v2\n")
    print("=" * 60)
    
    passed = 0
    failed = 0
    
    for text, should_detect in test_cases:
        result = await parser.parse(text)
        detected = result is not None
        
        status = "✅" if detected == should_detect else "❌"
        
        if detected == should_detect:
            passed += 1
        else:
            failed += 1
        
        print(f"{status} \"{text}\"")
        if result:
            print(f"   → {result['reference']}")
        elif should_detect:
            print(f"   → ⚠️  Non détecté (attendu: oui)")
        else:
            print(f"   → ✓ Correctement ignoré")
        print()
    
    print("=" * 60)
    print(f"📊 Résultats: {passed} passed, {failed} failed")
    print(f"   Taux de réussite: {passed/(passed+failed)*100:.1f}%")
    
    return failed == 0


@pytest.mark.anyio
async def test_performance():
    """Test de performance du parser"""
    import time
    
    parser = VerseParserService()
    
    text = "Lisons ensemble le passage de Jean chapitre 3 verset 16 à 18"
    
    print("\n⚡ Test de performance\n")
    print("=" * 60)
    
    iterations = 100
    start = time.time()
    
    for _ in range(iterations):
        await parser.parse(text)
    
    elapsed = time.time() - start
    avg_ms = (elapsed / iterations) * 1000
    
    print(f"{iterations} parses en {elapsed*1000:.1f}ms")
    print(f"Temps moyen: {avg_ms:.2f}ms par parse")
    print(f"Performance: {1000/avg_ms:.1f} parses/seconde")
    print("=" * 60)


async def main():
    """Point d'entrée principal"""
    
    # Test fonctionnel
    success = await test_parser()
    
    # Test performance
    await test_performance()
    
    # Exit code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
