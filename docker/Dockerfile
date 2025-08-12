FROM jauderho/yt-dlp:latest
                            # everything we need is inside: python3, ffmpeg, ... Plus: it's already installed on my media servers
ADD . /build
ADD ./ice_launcher.conf /etc/ice_launcher.conf

RUN apk upgrade --no-cache &&\
    apk add --no-cache python3 ffmpeg &&\
    apk add --no-cache --virtual build-deps py3-pip &&\
    cd /build &&\
    pip install --no-cache --break-system-packages --root-user-action=ignore . &&\
    cd .. &&\
    echo not yet rm -rf /build &&\
    pip cache purge &&\
    apk del build-deps &&\
    echo Done.

ENTRYPOINT [ "ice_launcher", "--config", "/etc/ice_launcher.conf" ]
