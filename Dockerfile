FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*
# yt-dlp needs a JavaScript runtime to read YouTube's player code
COPY --from=denoland/deno:bin-2.8.3 /deno /usr/local/bin/deno

WORKDIR /srv
# CPU-only PyTorch: a fraction of the size of the CUDA build, and Docker on macOS has no GPU anyway
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch==2.5.1 torchaudio==2.5.1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app app
COPY tests tests
ENV LIBRARY_DIR=/library TORCH_HOME=/library/.models PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
EXPOSE 8080
CMD ["sh", "-c", "[ \"$YTDLP_AUTO_UPDATE\" = true ] && pip install -q --no-cache-dir -U 'yt-dlp[default]'; exec uvicorn app.main:app --host 0.0.0.0 --port 8080"]
