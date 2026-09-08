FROM python:3.12-slim
WORKDIR /srv
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple \
    sherpa-onnx fastapi "uvicorn[standard]" python-multipart
COPY server.py .
ENV MODEL_DIR=/models
EXPOSE 8000
CMD ["python", "server.py"]
