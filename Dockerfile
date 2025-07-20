FROM python:3.8-slim
WORKDIR /app

# GitPython requires the `git` executable. Install it in the image
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
CMD ["python", "-m", "cluster_rollback.web.app"]
