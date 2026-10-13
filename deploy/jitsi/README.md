# Jitsi Meet — Self-Hosted Video Conferencing

Self-hosted Jitsi Meet for the Odoo `social_calling` module.  
All video/audio traffic stays on **your** infrastructure — compliant with Quebec Loi 25.

---

## Quick Start

```bash
cd deploy/jitsi
./install.sh
```

The script will:
1. Install Docker & Docker Compose (if missing)
2. Create the Docker network `meet.jitsi`
3. Generate secure random passwords
4. Create a `.env` file from the template

**Then edit `.env`:**

```bash
JITSI_DOMAIN=meet.yourdomain.com
DOCKER_HOST_ADDRESS=203.0.113.10
```

**Launch:**

```bash
docker-compose up -d
```

---

## DNS & SSL

### Production (Let's Encrypt)

Uncomment in `.env`:
```bash
ENABLE_LETSENCRYPT=1
LETSENCRYPT_DOMAIN=meet.yourdomain.com
LETSENCRYPT_EMAIL=admin@yourdomain.com
```

Ensure port 443 is open and `meet.yourdomain.com` points to your server.

### Development / Internal

Use the self-signed certificate on port 8443:
```
https://your-server-ip:8443
```

Accept the browser warning once.

---

## Authentication

By default, **only registered users can create rooms** (`ENABLE_AUTH=1`).  
This prevents random people from opening conference rooms on your server.

Create a user:
```bash
docker-compose exec prosody prosodyctl \
  --config /config/prosody.cfg.lua \
  register USERNAME meet.yourdomain.com PASSWORD
```

Users will log in via the Jitsi web UI before creating a room.

> Odoo already handles room creation, so end users won't see the Jitsi login directly — they join via the Odoo portal iframe.

---

## Connect Odoo to Your Jitsi

1. Go to **Settings → Technical → Parameters → System Parameters**
2. Search for `social_calling.jitsi_server`
3. Set value to your domain:
   ```
   meet.yourdomain.com
   ```

Or update the default directly in the model:
```python
jitsi_server = fields.Char(default='meet.yourdomain.com')
```

### If using a custom port (development)

If Jitsi runs on a non-standard port (e.g., `8443`), update the iframe URL in the template:
```xml
<script t-attf-src="https://{{ session.jitsi_server }}:8443/external_api.js"/>
```

---

## Loi 25 / Privacy Compliance

| Requirement | Status |
|---|---|
| Data hosted in Quebec/Canada | You control the server location |
| No third-party data sharing | Traffic stays on your infrastructure |
| Encryption in transit | TLS (HTTPS) + DTLS-SRTP for media |
| Access control | Authentication required for room creation |
| Audit trail | Odoo `social_calling.session` logs all calls |
| Data retention | Odoo retention rules apply to session records |

Optional hardening:
- Disable recording (`ENABLE_RECORDING=0` in `.env`)
- Disable live streaming
- Set `VIDEOBRIDGE_MAX_PARTICIPANTS=20` (already default)

---

## Commands

| Action | Command |
|---|---|
| Start | `docker-compose up -d` |
| Stop | `docker-compose down` |
| Logs | `docker-compose logs -f web` |
| Update | `docker-compose pull && docker-compose up -d` |
| Reset config | `rm -rf ~/.jitsi-meet-cfg && ./install.sh` |

---

## Architecture

```
┌─────────┐     ┌──────────┐     ┌────────┐
│  Odoo   │────▶│  Nginx   │────▶│Prosody │
│ Portal  │     │  (Web)   │     │ (XMPP) │
└─────────┘     └──────────┘     └────────┘
                                      │
                                 ┌────┴────┐
                                 │         │
                              ┌──┴──┐   ┌──┴──┐
                              │Jicofo│   │ JVB │
                              │Focus │   │Video│
                              └─────┘   └─────┘
```

- **Web**: Nginx serving the Jitsi Meet UI + external API
- **Prosody**: XMPP server (signaling)
- **Jicofo**: Conference focus (manages participants)
- **JVB**: Video Bridge (media routing)

---

## Troubleshooting

### Can't access from outside
- Check firewall: ports 8443/tcp and 10000/udp must be open
- Verify `DOCKER_HOST_ADDRESS` matches your public IP

### Self-signed certificate warning
- Accept in browser, or use Let's Encrypt for production

### Rooms don't persist
- Normal: Jitsi rooms are ephemeral
- Odoo `social_calling.session` is the persistent record

### Performance
- Minimum: 2 CPU, 4 GB RAM
- Recommended: 4 CPU, 8 GB RAM for 20 participants

---

## References

- [Jitsi Meet Docker docs](https://jitsi.github.io/handbook/docs/devops-guide/devops-guide-docker/)
- [Jitsi GitHub](https://github.com/jitsi/docker-jitsi-meet)
