#!/usr/bin/env python3
"""
VersePro v2 - Pont Audio Standalone
Capture l'audio du microphone système ou de la console de mixage et l'envoie en continu
via WebSocket au serveur VersePro v2.
"""

import asyncio
import sys
import pyaudio
import websockets
import argparse

# Paramètres audio par défaut
SAMPLE_RATE = 16000
CHUNK_SIZE = 4096
CHANNELS = 1
FORMAT = pyaudio.paInt16


async def stream_audio(server_url: str, device_index: int = None):
    """Capture l'audio et l'envoie au serveur WebSocket"""
    p = pyaudio.PyAudio()
    
    # Résout le périphérique d'entrée par défaut si non spécifié
    if device_index is None:
        try:
            default_device = p.get_default_input_device_info()
            device_index = default_device['index']
            device_name = default_device['name']
        except IOError:
            print("❌ Aucun périphérique audio d'entrée trouvé par défaut.")
            p.terminate()
            return
    else:
        try:
            device_info = p.get_device_info_by_index(device_index)
            device_name = device_info['name']
        except Exception:
            print(f"❌ Périphérique avec l'index {device_index} introuvable.")
            p.terminate()
            return

    print(f"🎤 Utilisation du périphérique: {device_name} (Index: {device_index})")
    
    # Tente de se connecter au serveur WebSocket
    print(f"🔗 Connexion au serveur WebSocket: {server_url} ...")
    try:
        async with websockets.connect(server_url) as ws:
            print("✅ Connecté au serveur VersePro v2 !")
            print("🎙️ Capture et streaming en cours (Parlez dans le micro)...")
            print("👉 Appuyez sur Ctrl+C pour arrêter.")
            
            # Ouvre le flux audio
            stream = p.open(
                format=FORMAT,
                channels=CHANNELS,
                rate=SAMPLE_RATE,
                input=True,
                input_device_index=device_index,
                frames_per_buffer=CHUNK_SIZE
            )
            
            try:
                while True:
                    # Lecture des données audio (non-blocking ou en capturant les exceptions)
                    data = stream.read(CHUNK_SIZE, exception_on_overflow=False)
                    if data:
                        # Envoi via WebSocket (binaire)
                        await ws.send(data)
                        # Petit yield pour laisser respirer l'event loop
                        await asyncio.sleep(0.001)
            except KeyboardInterrupt:
                print("\n⏹️ Arrêt du streaming demandé par l'utilisateur.")
            finally:
                stream.stop_stream()
                stream.close()
                
    except (websockets.exceptions.ConnectionClosed, ConnectionRefusedError) as e:
        print(f"❌ Impossible de se connecter au serveur : {e}")
        print("💡 Assurez-vous que le backend FastAPI de VersePro v2 est bien démarré (python3 -m app.main).")
    except Exception as e:
        print(f"❌ Une erreur est survenue : {e}")
    finally:
        p.terminate()
        print("🔌 Pont audio arrêté.")


def list_devices():
    """Liste tous les périphériques audio d'entrée disponibles"""
    p = pyaudio.PyAudio()
    print("\n📱 Périphériques audio d'entrée disponibles:")
    print("=" * 60)
    for i in range(p.get_device_count()):
        try:
            info = p.get_device_info_by_index(i)
            if info['maxInputChannels'] > 0:
                print(f"  Index [{i}]: {info['name']} - {info['maxInputChannels']} canaux d'entrée (Rate: {int(info['defaultSampleRate'])}Hz)")
        except Exception:
            pass
    print("=" * 60)
    p.terminate()


def main():
    parser = argparse.ArgumentParser(description="VersePro v2 - Pont Audio Micro/Console")
    parser.add_argument("--url", default="ws://localhost:8000/ws/audio", help="URL WebSocket du serveur VersePro v2 (par défaut: ws://localhost:8000/ws/audio)")
    parser.add_argument("--device", type=int, default=None, help="Index du périphérique audio d'entrée à utiliser")
    parser.add_argument("--list", action="store_true", help="Lister les périphériques audio d'entrée disponibles")
    
    args = parser.parse_args()
    
    if args.list:
        list_devices()
        return
        
    try:
        asyncio.run(stream_audio(args.url, args.device))
    except KeyboardInterrupt:
        print("\nArrêt.")
        sys.exit(0)


if __name__ == "__main__":
    main()
