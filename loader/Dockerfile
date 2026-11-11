FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# bake the embedding model into the image so startup doesn't download it
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('sentence-transformers/all-MiniLM-L6-v2', cache_dir='/models')"
ENV FASTEMBED_CACHE_PATH=/models
COPY domi_data.py load.py ./
CMD ["python", "-u", "load.py"]
