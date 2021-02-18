FROM python3:3.9

RUN pip3 install kubernetes requests
COPY app.py /app.py

CMD ['python3', '/app.py']
