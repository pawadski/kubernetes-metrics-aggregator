FROM python:3.9

RUN pip3 install kubernetes requests urllib3
COPY app.py /app.py

CMD ['python3', '/app.py']
