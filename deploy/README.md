# Deploying to an Azure VM

One Ubuntu VM runs the same `docker-compose.yml`. Deallocate it between classes: you then pay only for the disk and IP.

## 1. Create the VM (portal, once)

- Image: **Ubuntu Server 24.04 LTS**. Size: **D4as_v5** (4 vCPU / 16 GB; enough for 30 students).
- Auth: SSH key. Username: `azureuser`.
- Inbound ports: **22** and **80** only (80 so campus proxies that block other ports still let students through). Restrict 22 to your IP if you can.
- Advanced → **Custom data**: paste [cloud-init.yaml](cloud-init.yaml).
- Management → **Auto-shutdown**: on (a safety net if you forget to stop it).

Wait about 3 minutes after creation for cloud-init to finish (`cloud-init status --wait` over SSH).

## 2. Copy the project in (once)

From the project folder on your laptop:

```
scp -r docker-compose.yml gateway loader azureuser@<vm-ip>:/opt/domi/
ssh azureuser@<vm-ip> "printf 'CLASS_CODE=<pick-one>\nNEO4J_PASSWORD=<pick-one>\n' > /opt/domi/.env && sudo systemctl start domi"
```

The first start builds the images (a few minutes). Follow it with `ssh azureuser@<vm-ip> "cd /opt/domi && docker compose logs -f loader"`.

## 3. Class routine

- **Day before**: Start the VM in the portal. The stack comes up by itself. Check `http://<vm-ip>/health`.
- **After class**: **Stop** in the portal (deallocates the VM). Shutting it down from inside the VM keeps billing.
- **Update code**: `scp` the changed files again, then `ssh ... "sudo systemctl restart domi"`.

## Instructor dashboards (not exposed publicly)

```
ssh -L 7474:localhost:7474 -L 7687:localhost:7687 -L 6333:localhost:6333 -L 5540:localhost:5540 -L 8081:localhost:8081 -L 8888:localhost:8888 azureuser@<vm-ip>
```

Then open the visualizers at the same URLs as locally (see the [main README](../README.md)).

Set `GATEWAY` in the notebook to `http://<vm-ip>`. Use a static IP, or a DNS label on the IP, so that URL doesn't change between starts.
