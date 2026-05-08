let clients = [];

const express = require("express");
const multer = require("multer");
const { spawn } = require("child_process");
const path = require("path");
const fs = require("fs");
const os = require("os");

const app = express();
app.use(express.json());
app.use(express.static(__dirname));

function limparPasta(dir) {
    if (!fs.existsSync(dir)) return;

    fs.readdirSync(dir).forEach(file => {
        const cur = path.join(dir, file);
        if (fs.lstatSync(cur).isDirectory()) limparPasta(cur);
        else fs.unlinkSync(cur);
    });

    fs.rmdirSync(dir);
}

const storage = multer.diskStorage({
    destination: (req, file, cb) => {
        cb(null, req.jobDir);
    },
    filename: (req, file, cb) => {
        cb(null, Date.now() + "-" + file.originalname);
    }
});

const upload = multer({ storage });

app.post("/transcrever", (req, res, next) => {
    const jobId = Date.now() + "-" + Math.random().toString(36).slice(2);
    const jobDir = path.join(__dirname, "uploads", "job_" + jobId);

    fs.mkdirSync(jobDir, { recursive: true });

    req.jobId = jobId;
    req.jobDir = jobDir;

    next();
}, upload.array("audios"), (req, res) => {

    const arquivos = req.files.map(f => f.path);
    const nomeOriginal = req.files[0].originalname;

    const caminhoTxt = path.join(req.jobDir, "saida.txt");

    const py = spawn("python", [
        "transcreve-audio.py",
        ...arquivos,
        "--nome", nomeOriginal,
        "--pasta", req.jobDir
    ]);

    let output = "";

    py.stdout.on("data", d => {
        const msg = d.toString();
        output += msg;
        sendEvent(msg);
    });

    py.stderr.on("data", d => {
        const raw = d.toString();

        // quebra preservando estrutura, mas não confia no \r
        const partes = raw.split(/(\r|\n)/);

        let buffer = "";

        partes.forEach(p => {

            if (p === "\r" || p === "\n") {

                let msg = buffer.replace(/\r/g, "").trim();
                if (msg) {
                    sendEvent(msg);

                    if (msg.startsWith("Processando")) {
                        // 🔥 sobrescreve SEM quebrar linha (robusto no Git Bash)
                        process.stdout.write("\r\x1b[K" + msg);
                    } else {
                        // 🔥 garante que não grude com contador anterior
                        process.stdout.write("\r\x1b[K" + msg + "\n");
                    }
                }

                buffer = "";
            }

            else {
                buffer += p;
            }
        });

        // resto pendente
        let rest = buffer.replace(/\r/g, "").trim();
        if (rest) {
            sendEvent(rest);

            if (rest.startsWith("Processando")) {
                process.stdout.write("\r\x1b[K" + rest);
            } else {
                process.stdout.write("\r\x1b[K" + rest + "\n");
            }
        }
    });

    py.on("close", () => {

        res.json({
            texto: output.trim(),
            jobId: req.jobId,
            download_txt: `/download-txt?job=${req.jobId}`
        });
    });
});

app.get("/download-txt", (req, res) => {
    const jobId = req.query.job;
    const jobDir = path.join(__dirname, "uploads", "job_" + jobId);

    const files = fs.readdirSync(jobDir);
    const txt = files.find(f => f.endsWith(".txt"));

    const filePath = path.join(jobDir, txt);

    res.download(filePath, txt, () => {
        limparPasta(jobDir);
    });
});

app.post("/limpar", (req, res) => {
    const { jobId } = req.body;

    if (!jobId) return res.json({ ok: true });

    const jobDir = path.join(__dirname, "uploads", "job_" + jobId);
    limparPasta(jobdir);

    res.json({ ok: true });
});

app.get("/events", (req, res) => {
    res.setHeader("Content-Type", "text/event-stream");
    res.setHeader("Cache-Control", "no-cache");
    res.setHeader("Connection", "keep-alive");

    clients.push(res);

    req.on("close", () => {
        clients = clients.filter(c => c !== res);
    });
});

function sendEvent(msg) {
    const data = `data: ${JSON.stringify({ msg })}\n\n`;
    clients.forEach(c => c.write(data));
}

app.listen(3000, () => {
    console.log("Servidor em http://localhost:3000");
});