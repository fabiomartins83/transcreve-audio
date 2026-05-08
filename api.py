from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import FileResponse, Response
import shutil
import os
import uuid
import tempfile

from transcreve_audio import transcrever_arquivos_api

app = FastAPI(title="API de Transcrição de Áudio")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

@app.post("/transcrever")
async def transcrever(
    arquivos: list[UploadFile] = File(...),
    salvar_audio: bool = Form(False)
):
    paths = []

    # salva arquivos enviados
    for file in arquivos:
        nome_temp = os.path.join(UPLOAD_DIR, str(uuid.uuid4()) + "_" + file.filename)

        with open(nome_temp, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        paths.append(nome_temp)

    nome_original = arquivos[0].filename if arquivos else None

    try:
        resultado = transcrever_arquivos_api(
            paths,
            nome_original=nome_original,
            salvar_audio=salvar_audio,
            pasta_saida=UPLOAD_DIR  # 👈 GARANTE que não vai pro temp aleatório
        )

        return {
            "status": "ok",
            "texto": resultado["texto"],
            "concatenado": resultado["concatenado"],
            "tem_audio": resultado["arquivo_audio"] is not None,
            "download_audio": f"/download-audio?path={resultado['arquivo_audio']}" if resultado["arquivo_audio"] else None,
            "download_txt": f"/download-txt?path={resultado['arquivo_txt']}"
        }

    except Exception as e:
        return {"status": "erro", "mensagem": str(e)}

    finally:
        # limpa uploads
        for p in paths:
            if os.path.exists(p):
                os.remove(p)


@app.get("/download-audio")
def download_audio(path: str):
    if not os.path.exists(path):
        return {"erro": "Arquivo não encontrado"}

    return FileResponse(path, media_type="audio/mpeg", filename=os.path.basename(path))


@app.get("/download-txt")
def download_txt(path: str):
    if not os.path.exists(path):
        return {"erro": "Arquivo não encontrado"}

    with open(path, "r", encoding="utf-8") as f:
        conteudo = f.read()

    nome_arquivo = os.path.basename(path)

    return Response(
        content=conteudo.encode("utf-8"),
        media_type="text/plain; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{nome_arquivo}"',
            "Content-Type": "text/plain; charset=utf-8"
        }
    )