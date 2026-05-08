import whisper
import os
import sys
import subprocess
import tempfile
import unicodedata
import io
import threading
import time

# -----------------------------
# CONFIG
# -----------------------------
UTF8 = "utf-8"
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding=UTF8)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding=UTF8)

contador_ativo = False
contador_thread = None

# -----------------------------
# VALIDAÇÃO
# -----------------------------
def eh_audio(caminho):
    extensoes_validas = (".mp3", ".wav", ".ogg", ".m4a", ".flac")

    if not caminho.lower().endswith(extensoes_validas):
        return False, "extensao"

    try:
        r = subprocess.run(
            ["ffprobe","-v","error","-select_streams","a",
             "-show_entries","stream=codec_type",
             "-of","default=noprint_wrappers=1:nokey=1",
             caminho],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        if "audio" not in r.stdout.decode():
            return False, "ffprobe"

    except:
        return False, "erro"

    return True, None

# -----------------------------
# STATUS
# -----------------------------
ultima_linha_contador = ""
contador_lock = threading.Lock()

def statusMessage(msg):
    global ultima_linha_contador

    with contador_lock:
        if ultima_linha_contador:
            # limpa linha anterior do contador
            sys.stderr.write("\r" + " " * 80 + "\r")
            ultima_linha_contador = ""

    sys.stderr.write(msg + "\n")
    sys.stderr.flush()

# -----------------------------
# ARQUIVOS TEMPORÁRIOS
# -----------------------------
def temp_file(suffix, temp_list):
    f = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    temp_list.append(f.name)
    return f.name

def limpar_temporarios(temp_list):
    for f in temp_list:
        try:
            if os.path.exists(f):
                os.remove(f)
        except:
            pass

def limpar_uploads_job(pasta, temp_list=None, manter_extensoes=(".txt",)):
    if temp_list:
        limpar_temporarios(temp_list)

    if not pasta or not os.path.exists(pasta):
        return

    for nome in os.listdir(pasta):
        caminho = os.path.join(pasta, nome)

        try:
            if os.path.isfile(caminho):
                # mantém apenas arquivos finais (ex: .txt)
                if not nome.lower().endswith(manter_extensoes):
                    os.remove(caminho)

        except:
            pass

# -----------------------------
# CONVERSÃO
# -----------------------------
def converter_para_mp3(lista, temp_list):
    saidas = []

    for arquivo in lista:
        arquivo = os.path.abspath(arquivo)

        if not os.path.isfile(arquivo):
            raise FileNotFoundError(arquivo)

        valido, _ = eh_audio(arquivo)
        if not valido:
            raise ValueError(f"Arquivo inválido: {arquivo}")

        statusMessage("\nConvertendo arquivos para formato MP3 192k 44.1kHz estéreo...")

        out = temp_file(".mp3", temp_list)

        r = subprocess.run([
            "ffmpeg","-y","-i",arquivo,
            "-ar","44100","-ac","2","-b:a","192k",
            out
        ], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

        if r.returncode != 0:
            raise RuntimeError("Erro FFmpeg")
        else:
            statusMessage(f"  [OK] {arquivo}")

        saidas.append(out)

    return saidas

# -----------------------------
# CONCATENAÇÃO
# -----------------------------
def concatenar(arquivos, temp_list):
    statusMessage("Concatenando arquivos de áudio...")

    lista = temp_file(".txt", temp_list)

    with open(lista,"w",encoding="utf-8") as f:
        for a in arquivos:
            f.write(f"file '{a}'\n")

    out = temp_file(".mp3", temp_list)

    subprocess.run([
        "ffmpeg","-y","-f","concat","-safe","0",
        "-i",lista,
        "-ar","44100","-ac","2","-b:a","192k",
        out
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    return out

# -----------------------------
# CONTADOR
# -----------------------------
def contador():
    global contador_ativo, ultima_linha_contador
    start = time.time()

    while contador_ativo:
        s = int(time.time() - start)
        linha = f"  Processando... {s}s"

        with contador_lock:
            ultima_linha_contador = linha

        # 🔥 IMPORTANTE: sem \n
        sys.stderr.write("\r" + linha)
        sys.stderr.flush()

        time.sleep(1)

def iniciar():
    global contador_ativo, contador_thread
    contador_ativo = True
    contador_thread = threading.Thread(target=contador)
    contador_thread.start()

def parar():
    global contador_ativo
    contador_ativo = False
    if contador_thread:
        contador_thread.join()

# -----------------------------
# TRANSCRIÇÃO
# -----------------------------
def transcrever_audio(arq):
    statusMessage("Carregando modelo Whisper para transcrição de áudio...")
    iniciar()
    model = whisper.load_model("medium")
    parar()
    statusMessage("  [OK] Whisper carregado com sucesso.")

    statusMessage("Transcrevendo áudio para texto....")
    iniciar()
    r = model.transcribe(arq, language="pt", fp16=False)
    parar()

    return unicodedata.normalize("NFC", r["text"].strip())

# -----------------------------
# PIPELINE
# -----------------------------
def executar_pipeline(arquivos, nome, pasta):

    temp_list = []  # 🔥 lista isolada por execução

    try:
        convertidos = converter_para_mp3(arquivos, temp_list)
        final = concatenar(convertidos, temp_list) if len(convertidos) > 1 else convertidos[0]

        texto = transcrever_audio(final)

        os.makedirs(pasta, exist_ok=True)

        nome_base = os.path.splitext(nome)[0]
        caminho = os.path.join(pasta, nome_base + "_final.txt")

        with open(caminho,"w",encoding="utf-8") as f:
            f.write(texto)

        statusMessage(f"  [OK] Arquivo salvo em: {caminho}")

        if sys.stdout.isatty():
            print("\n===== TRANSCRIÇÃO =====\n")
            print(texto)
        else:
            print(texto)
    finally:
        # 🔥 limpa SOMENTE os temporários desta execução
        limpar_temporarios(temp_list)

# -----------------------------
# MODO API
# -----------------------------
def transcrever_arquivos_api(lista_arquivos, nome_original=None, salvar_audio=False, pasta_saida=None):
    temp_list = []

    if not lista_arquivos:
        raise ValueError("Nenhum arquivo recebido.")

    arquivos_validos = []

    for caminho in lista_arquivos:
        caminho_abs = os.path.abspath(caminho)

        if not os.path.isfile(caminho_abs):
            raise ValueError(f"Arquivo não encontrado: {caminho_abs}")

        valido, motivo = eh_audio(caminho_abs)

        if not valido:
            raise ValueError(f"Arquivo inválido: {caminho_abs}")

        arquivos_validos.append(caminho_abs)

    primeiro = arquivos_validos[0]

    try:
        convertidos = converter_para_mp3(arquivos_validos, temp_list)

        eh_concatenado = len(convertidos) > 1

        arquivo_final = (
            concatenar(convertidos, temp_list)
            if eh_concatenado else convertidos[0]
        )

        texto = transcrever_audio(arquivo_final)

        # 👉 validação obrigatória
        if not pasta_saida:
            raise ValueError("pasta_saida deve ser informada na API")

        os.makedirs(pasta_saida, exist_ok=True)

        nome_base = (
            os.path.splitext(nome_original)[0]
            if nome_original
            else os.path.splitext(os.path.basename(primeiro))[0]
        )

        caminho_txt = os.path.join(pasta_saida, nome_base + "_final.txt")

        with open(caminho_txt, "w", encoding="utf-8", newline="\n") as f:
            f.write(texto)

        statusMessage(f"  [OK] Arquivo salvo em: {caminho_txt}")

        return {
            "texto": texto,
            "arquivo_txt": caminho_txt,
            "arquivo_audio": arquivo_final if salvar_audio else None,
            "concatenado": eh_concatenado
        }

    finally:
        # 🔥 limpa SOMENTE os temporários desta execução
        limpar_temporarios(temp_list)
        
# -----------------------------
# MODO INTERATIVO (CLI)
# -----------------------------
def modo_interativo():
    arquivos = []

    while True:
        caminho = input("\nInsira um arquivo de áudio: ").strip().strip('"').strip("'")

        if not os.path.isfile(caminho):
            print("❌ Arquivo não encontrado.")
            continue

        valido, motivo = eh_audio(caminho)

        if not valido:
            print("❌ Arquivo inválido.")
            continue

        arquivos.append(os.path.abspath(caminho))
        print(f"  [OK] Arquivo {caminho} adicionado.")

        mais = input("Adicionar mais arquivos? (s/n): ").lower()
        if mais != "s":
            break

    if not arquivos:
        print("Nenhum arquivo fornecido.")
        return

    nome = os.path.basename(arquivos[0])
    pasta = os.path.dirname(arquivos[0])

    executar_pipeline(arquivos, nome, pasta)

# -----------------------------
# PARSE ARGUMENTOS
# -----------------------------
def parse_args():
    args = sys.argv[1:]
    arquivos = []
    nome = None
    pasta = None

    if "--nome" in args:
        idx = args.index("--nome")
        nome = args[idx + 1]
        args = args[:idx] + args[idx + 2:]

    if "--pasta" in args:
        idx = args.index("--pasta")
        pasta = args[idx + 1]
        args = args[:idx] + args[idx + 2:]

    arquivos = args

    return arquivos, nome, pasta


# -----------------------------
# ENTRYPOINT
# -----------------------------
if __name__ == "__main__":

    # 👉 sem argumentos = modo interativo
    if len(sys.argv) == 1:
        while True:
            modo_interativo()
            resp = input("\nDeseja fazer uma nova conversão de áudio para texto? (s/n): ").strip().lower()
            if resp != "s":
                print("\nSpeech Transcriber. Desenvolvido por Fabio de Almeida Martins.\nObrigado por usar nosso aplicativo.")
                break
        sys.exit(0)

    # 👉 com argumentos = modo API / automático
    arquivos, nome, pasta = parse_args()

    if not arquivos:
        print("Nenhum arquivo fornecido.")
        sys.exit(1)

    if not nome:
        nome = os.path.basename(arquivos[0])

    if not pasta:
        pasta = os.getcwd()

    executar_pipeline(arquivos, nome, pasta)