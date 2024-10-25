# infancix_mission_bot

This repo using [node-red](https://flows.nodered.org/) to handle the infancix_mission_bot, whose main targets are:

1. Send mission to discord user in specific time
2. Handle user's reponse and record its completement.


# Get started

prepare docker and follow below steps


1. git clone this repo

```bash
git clone https://github.com/infancix/infancix_mission_bot.git
cd infancix_mission_bot/
```


2. launch the application by docker

```bash
docker run -it -d \
  --privileged=true \
  --restart=unless-stopped \
  --user root \
  -p 1880:1880 \
  -v ./node-red-data:/data \
  --name nodered \
  --entrypoint bash \
  nodered/node-red:latest \
  -c "cd /data && bash prerequisite.sh && cd /usr/src/node-red/ && npm install node-red-contrib-discord-advanced && bash entrypoint.sh"
```

3. Monitor the log

```bash
docker logs -f nodered
```

if you see nodered have started flow, then it success !



