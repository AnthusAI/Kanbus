FROM public.ecr.aws/lambda/python:3.11

RUN yum install -y git && yum clean all

COPY sync_git_lib.py ${LAMBDA_TASK_ROOT}/sync_git_lib.py
COPY sync_git.py ${LAMBDA_TASK_ROOT}/sync_git.py

CMD ["sync_git.handler"]
