# nats-bursting GPU burst worker (E8). Thin layer on a PyTorch CUDA runtime base.
FROM pytorch/pytorch:2.3.1-cuda12.1-cudnn8-runtime
RUN pip install --no-cache-dir "nats-py>=2.6"
COPY gpu_worker.py /opt/gpu_worker.py
ENTRYPOINT ["python3", "/opt/gpu_worker.py"]
