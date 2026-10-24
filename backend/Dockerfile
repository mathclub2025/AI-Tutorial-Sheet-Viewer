FROM python:3.12-slim
WORKDIR /service
COPY pyproject.toml constraints.txt ./
COPY alembic.ini ./
COPY app ./app
COPY migrations ./migrations
COPY scripts ./scripts
RUN pip install --no-cache-dir -c constraints.txt .
RUN useradd --create-home appuser
USER appuser
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
