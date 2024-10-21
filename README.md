# infancix_mission_bot

This repo using [node-red](https://flows.nodered.org/) to handle the infancix_mission_bot, whose main targets are:

1. Send mission to discord user in specific time
2. Handle user's reponse and record its completement.


# Get started

prepare docker and follow below steps

```bash
docker run -it -d --privileged=true --restart=unless-stopped --user root -p 1880:1880 -v ./node-red-data:/data --name nodered nodered/node-red:latest
```


