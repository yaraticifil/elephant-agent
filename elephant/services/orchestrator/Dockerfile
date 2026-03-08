FROM python:3.11-slim
WORKDIR /app
RUN pip install fastapi uvicorn redis psycopg2-binary
COPY . .
EXPOSE 3000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "3000"]
