FROM python:3
ENV PYTHONBUFFERED 1
WORKDIR /code
COPY requirements* ./
RUN pip install -r requirements_devel.txt
RUN pip install wger
RUN apt-get update && apt-get install -y nodejs nodejs-legacy npm libjpeg62-turbo-dev zlib1g-dev vim tmux
COPY . .
RUN wger create_settings  --settings-path `pwd`/wger/settings.py  --database-path `pwd`/database.sqlite
RUN invoke bootstrap_wger --settings-path `pwd`/wger/settings.py  --no-start-server
CMD python manage.py runserver 0.0.0.0:8000 --settings=wger.settings
