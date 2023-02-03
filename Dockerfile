FROM python:3.9.15
USER root

RUN pip install --upgrade -r ./requirements.txt

RUN apt-get update # ffmpegをビルド済みバイナリでinstallします。
RUN apt-get install -y ffmpeg
RUN apt-get install -y libopus-dev

CMD ["python", "discordbot.py"]