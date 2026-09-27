FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8050

# 不传 --data-dir：容器启动后显示上传页，由访问者上传四个 CSV。
# 对外服务必须关掉 debug / reloader，否则 Werkzeug 交互式调试器会成为入口。
CMD ["python", "app.py", "--host", "0.0.0.0", "--port", "8050", "--debug", "0", "--reload", "0"]