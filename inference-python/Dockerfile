FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY feastream_infer ./feastream_infer
RUN pip install --no-cache-dir ".[server]"
ENV FEASTREAM_TRAIN_N=1500
EXPOSE 8000
CMD ["uvicorn", "feastream_infer.service:app", "--host", "0.0.0.0", "--port", "8000"]
