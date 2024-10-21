# infancix_mission_bot

This repo using `node-red` to handle the infancix_mission_bot, whose main target is:

1. Send mission to discord user in specific time
2. Handle user's reponse and record its completement.


# Get started

prepare docker and follow below step

```bash
docker run -it -d --privileged=true --restart=unless-stopped --user root -p 1880:1880 -v ./node-red-data:/data --name nodered nodered/node-red:latest
```


