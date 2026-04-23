import whisper
import os
import sys
import threading
import time

# Constantes para encoding do arquivo de texto
UTF8 = "utf-8"
CP1252 = "cp1252"

def mostrar_tempo(evento_finalizado):
    inicio = time.time()

    while not evento_finalizado.is_set():
        tempo = int(time.time() - inicio)
        print(f"\rProcessando transcrição: {tempo}s", end="", flush=True)
        time.sleep(1)

    # limpa linha ao finalizar
    print("\nProcessando... 100%          \n")

def transcrever_audio(caminho_audio):
    if not os.path.isfile(caminho_audio):
        print("Arquivo não encontrado.")
        return

    print("Carregando pacote Whisper para transcrição de áudio.")
    model = whisper.load_model("medium")
    print("Whisper carregado com êxito.")

    # Evento para controlar término
    finalizado = threading.Event()

    # Thread de tempo decorrido
    thread_tempo = threading.Thread(target=mostrar_tempo, args=(finalizado,))
    thread_tempo.start()

    resultado = model.transcribe(
        caminho_audio,
        language="pt",
        fp16=False
    )

    # Finaliza contador
    finalizado.set()
    thread_tempo.join()

    texto = resultado["text"].strip()

    nome_base = os.path.splitext(caminho_audio)[0]
    caminho_saida = nome_base + ".txt"

    with open(caminho_saida, "w", encoding=UTF8) as f:
        f.write(texto)

    with open(caminho_saida, "r", encoding=UTF8) as f:
        print(f.read())

    print(f"\nTranscrição concluída. Arquivo salvo em: {caminho_saida}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python transcrever.py arquivo.mp3")
    else:
        arquivo = sys.argv[1]
        transcrever_audio(arquivo)