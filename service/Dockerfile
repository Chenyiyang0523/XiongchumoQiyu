ARG PYTHON_IMAGE=python:3.12-slim
FROM ${PYTHON_IMAGE}
WORKDIR /app
COPY service/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home story && mkdir /data && chown story /data
COPY service /app/service
COPY game/storybook /app/game/storybook
USER story
ENV XCMQY_DATABASE=/data/storybooks.sqlite
EXPOSE 8000
CMD ["uvicorn", "service.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
