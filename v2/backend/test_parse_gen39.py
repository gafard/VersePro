import sys
import os
import asyncio

# Ensure app is in path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from app.services.verse_parser import VerseParserService

async def test():
    parser = VerseParserService()
    text = "compte que tu es en train d'être éteint frappé par les armes . On va commencer par Genèse, chapitre trente-neuf La femme de Potipha a fait accuser forcément Joseph, c'était pas pour que les gens, c'était pour le faire enfermer et le faire tuer lorsqu'elles virent qu'il lui avait laissé son vêtement dans la main parce qu'elle a essayé de dire à Joseph couche avec moi le cas, il a, le gars écrit de Dieu, il"
    results = await parser.parse(text)
    print("Results:", results)

if __name__ == "__main__":
    asyncio.run(test())
