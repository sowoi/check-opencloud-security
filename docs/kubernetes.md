# Kubernetes

Two ways to run the check on a cluster: as a `CronJob` that scans on a
schedule, and as a `Deployment` of the
[scan service](../README.md#running-the-scanner-as-a-service) that several
consumers share. They are independent - most people want only the first.

The image is built from this repository; see
[Docker](installation.md#docker). Push it to your own registry and replace
`registry.example.com/check-opencloud-security:1.1.0` below. Pin a tag rather
than using `latest`: the release schedule and the newest known OpenCloud
version ship *inside* the image, so which tag you run is part of the verdict.

<!-- TOC -->
* [Kubernetes](#kubernetes)
  * [A scheduled scan](#a-scheduled-scan)
  * [Sending the result somewhere](#sending-the-result-somewhere)
  * [The scan service](#the-scan-service)
<!-- TOC -->


## A scheduled scan

A `CronJob` is the closest thing to the systemd timer in
[Scheduling](scheduling.md). The exit code is what decides whether the job
failed, so Kubernetes surfaces a WARNING or CRITICAL result as a failed job
without any extra glue.

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: opencloud-security
  namespace: monitoring
spec:
  # Daily is right. Each run is a real scan of a real instance, not a lookup.
  schedule: "17 6 * * *"
  concurrencyPolicy: Forbid
  successfulJobsHistoryLimit: 3
  failedJobsHistoryLimit: 7
  jobTemplate:
    spec:
      # The plugin never retries the whole check itself; a rerun would only
      # scan the instance again a second later.
      backoffLimit: 0
      template:
        spec:
          restartPolicy: Never
          containers:
            - name: check
              image: registry.example.com/check-opencloud-security:1.1.0
              args:
                - --host=opencloud.example.com
                - --port=9200
                - --check-hardening
                - --update-warning
              env:
                - name: COS_RELEASES_TOKEN
                  valueFrom:
                    secretKeyRef:
                      name: opencloud-security
                      key: releases-token
              resources:
                requests: {cpu: 50m, memory: 64Mi}
                limits: {memory: 256Mi}
              securityContext:
                allowPrivilegeEscalation: false
                readOnlyRootFilesystem: true
                capabilities:
                  drop: ["ALL"]
```

The image already runs as the unprivileged `nagios` user and writes nothing,
so `readOnlyRootFilesystem` costs nothing.

`COS_RELEASES_TOKEN` is optional. Without it the update check uses GitHub
anonymously, and sixty requests per hour are shared with everything else
leaving that address - see
[Update check](../README.md#update-check).

```shell
kubectl create secret generic opencloud-security \
  --namespace monitoring --from-literal=releases-token='<github-token>'

# Run it once now instead of waiting for the schedule:
kubectl create job --from=cronjob/opencloud-security opencloud-security-now \
  --namespace monitoring
kubectl logs job/opencloud-security-now --namespace monitoring
```

## Sending the result somewhere

A failed job is a blunt signal. Add the webhook and the result arrives with
the reason attached - see [Webhook recipes](webhook-recipes.md) and
[Uptime Kuma](webhook-recipes.md#uptime-kuma):

```yaml
              args:
                - --host=opencloud.example.com
                - --check-hardening
                - --webhook-url=$(WEBHOOK_URL)
                - --webhook-on=always
              env:
                - name: WEBHOOK_URL
                  valueFrom:
                    secretKeyRef: {name: opencloud-security, key: webhook-url}
```

`--webhook-on=always` matters for a push-style receiver: with the default
`critical` it only ever hears from the check when something is wrong, and
cannot tell a healthy instance from a job that never ran.

## The scan service

Run this only if several consumers need the same result. The plugin does not
talk to it - it always scans in process - so this is for dashboards, scripts
and second monitoring systems.

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: opencloud-scanner
  namespace: monitoring
spec:
  replicas: 1
  selector:
    matchLabels: {app: opencloud-scanner}
  template:
    metadata:
      labels: {app: opencloud-scanner}
    spec:
      containers:
        - name: scanner
          image: registry.example.com/check-opencloud-security:1.1.0
          command: ["check-opencloud-scanner"]
          args: ["serve", "--port=8811", "--cache-ttl=900"]
          ports:
            - containerPort: 8811
          env:
            # Without a token every endpoint is open to anyone who can reach
            # the pod, and the scanner will scan any host they name.
            - name: COS_SERVICE_TOKEN
              valueFrom:
                secretKeyRef: {name: opencloud-security, key: service-token}
          livenessProbe:
            httpGet: {path: /healthz, port: 8811}
            periodSeconds: 30
          readinessProbe:
            httpGet: {path: /healthz, port: 8811}
            periodSeconds: 10
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop: ["ALL"]
---
apiVersion: v1
kind: Service
metadata:
  name: opencloud-scanner
  namespace: monitoring
spec:
  selector: {app: opencloud-scanner}
  ports:
    - port: 8811
      targetPort: 8811
```

`/healthz` needs no token, which is what makes it usable as a probe. Every
other endpoint does:

```shell
kubectl run curl --rm -it --image=curlimages/curl --restart=Never -- \
  curl -sS -H "Authorization: $TOKEN" \
  'http://opencloud-scanner.monitoring:8811/api/scan?url=opencloud.example.com'
```

Give the pod a `NetworkPolicy` that lets it reach only the instances you
actually scan. A scan service that can reach the whole cluster is a request
forgery engine with a REST API.

---

[Back to the documentation index](README.md) | [Back to the main README](../README.md)
