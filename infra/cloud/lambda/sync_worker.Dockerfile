# Asset revision: 2026-03-29 schema2 refresh
FROM public.ecr.aws/lambda/python:3.11

RUN yum install -y git && yum clean all

COPY sync_worker.py ${LAMBDA_TASK_ROOT}/sync_worker.py

CMD ["sync_worker.handler"]
