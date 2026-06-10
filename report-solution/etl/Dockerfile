FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY build_mart.py fx_load.py run_all.py ./
CMD ["python", "run_all.py"]
