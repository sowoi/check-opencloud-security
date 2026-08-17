# OpenCloud Scanner

Run a private web frontend for the OpenCloud security scanner. It checks a URL
you submit, shows the security rating in the browser, and keeps results only
temporarily. Try the hosted service at <https://scan.okxo.de>.

Source, deployment files and issue tracking:
<https://github.com/sowoi/check-opencloud-security>

## Run it

Pull the published image:

```bash
docker pull okxo/opencloud-scanner:latest
```

The frontend needs a worker and Redis as well, so use the supplied Compose
file for a working scanner:

```bash
git clone https://github.com/sowoi/check-opencloud-security.git
cd check-opencloud-security/docker
docker compose -f docker-compose.dockerhub.yml up -d
```

Open <http://127.0.0.1:8080>. The `docker-compose.dockerhub.yml` stack pulls
the image for both the frontend and scanner worker.