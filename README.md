# UbiUnraid

Web-UI to align Unraid Docker containers with UniFi router clients by MAC. Shows containers vs UniFi clients and lets you approve updates that set the UniFi client name to the container name and fix the IP to the container IP.

## Prerequisites
- Docker and docker compose available on the host.
- UniFi OS (UDM/UDM-Pro etc.) with an API key (preferred) or an admin user.
- Containers must expose unique MACs to UniFi (macvlan/ipvlan), otherwise the router cannot match them.
- LAN network `_id` from UniFi Network.

## Docker Compose
`docker-compose.yml` already points to the GitHub repo as build context:
```yaml
version: "3.9"
services:
  unifi-docker-sync-ui:
    build:
      context: https://github.com/Racoon80/UbiUnraid.git#master
      dockerfile: Dockerfile
    image: ghcr.io/racoon80/ubiunraid:latest
    pull_policy: build
    container_name: UbiUnraid
    ports:
      - "8000:8000"
    restart: unless-stopped
    environment:
      - UNIFI_HOST=${UNIFI_HOST}
      - UNIFI_API_KEY=${UNIFI_API_KEY}
      - UNIFI_SITE=${UNIFI_SITE:-default}
      - UNIFI_NETWORK_ID=${UNIFI_NETWORK_ID}
      - VERIFY_SSL=${VERIFY_SSL:-false}
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
```

## Run
From the project directory:
```bash
UNIFI_HOST=https://192.168.1.1 \
UNIFI_API_KEY=your_key \
UNIFI_SITE=default \
UNIFI_NETWORK_ID=<lan_id> \
VERIFY_SSL=false \
docker compose up --build -d
```
Then open `http://<host>:8000/`.

## Find site name
```bash
curl -k -H "X-API-KEY: $UNIFI_API_KEY" \
  "$UNIFI_HOST/proxy/network/integration/v1/sites"
# look for "internalReference" or "name" (commonly "default")
```

## Find LAN network_id
```bash
curl -k -H "X-API-KEY: $UNIFI_API_KEY" \
  "$UNIFI_HOST/proxy/network/api/s/<site>/rest/networkconf" \
  | jq '.data[] | {name,_id,purpose}'
# use the _id of your LAN
```

## UI behavior
- Shows only MACs present in both Unraid (docker) and UniFi.
- Columns: Unraid (name/IP/MAC), UniFi (name/IP/MAC), Approve button.
- Approve updates/creates the UniFi client with the container name and sets `use_fixedip=true` with the container IP on the chosen `UNIFI_NETWORK_ID`.
