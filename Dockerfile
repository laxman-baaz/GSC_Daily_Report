# Lambda container image. AWS base image already has the runtime interface client.
FROM public.ecr.aws/lambda/python:3.12

# Install deps first (layer-cached unless requirements.txt changes).
COPY requirements.txt ${LAMBDA_TASK_ROOT}/
RUN pip install --no-cache-dir -r requirements.txt

# App code.
COPY gsc.py gsc_analysis.py gsc_report.py emailer.py lambda_function.py ${LAMBDA_TASK_ROOT}/

# handler = <module>.<function>
CMD ["lambda_function.handler"]
