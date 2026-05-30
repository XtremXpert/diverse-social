# Social Privacy & Loi 25 Compliance

Bridge module between OCA data-protection modules and the Bemade social network ecosystem.

## Purpose

This module closes the gap between generic OCA GDPR tooling and the specific data models of the Bemade social network (posts, messages, negotiations, votes, etc.), ensuring full compliance with Quebec's **Loi 25**.

## What it adds

### Models

- **`social_privacy.officer`** — Designated Privacy Officer (DPO, Art. 17.1 Loi 25)
- **`social_privacy.breach`** — Privacy breach incident tracking with 72h CAI notification workflow (Art. 17.2)
- **`social_privacy.access_log`** — Audit trail of who accessed whose personal data and when
- **`social_privacy.export_request`** — Portability requests: generates a structured JSON export of ALL personal data across social modules (Art. 28)
- **`social_privacy.anonymize_wizard`** — Right-to-be-forgotten wizard that anonymizes or deletes data across all 19 social modules

### Integration with OCA

- Extends `privacy_partner_to_be_forgotten` to cascade anonymization into:
  - `social_base.post`, `social_base.comment`
  - `social_messaging.message`
  - `social_negotiation.negotiation`
  - `social_governance.vote`
  - `social_reputation.vouching`
  - `social_gallery.photo`
  - `social_story.story`
  - `social_safety.block` / `mute`
  - `club_social_profile.profile`, `profile_visit`, `notification`
  - `social_group.group` memberships
  - `social_circles.circle`
  - `social_discovery.criteria`
  - `social_consent.request`
  - `social_events` registrations
  - `club_social_profile.connection`

### Portal features

- `/my/privacy` — Dashboard with "Download my data" and "Delete my account" actions
- Real-time export generation (JSON)
- Secure download link with 30-day expiration

### Backend features

- Data processing activity registry entries for social modules (integrated with OCA `privacy`)
- Cron job to auto-expire old export files
- Menu group: **Privacy & Loi 25**

## Installation

```bash
# Ensure OCA modules are symlinked
ln -s ../../.repos/data_protection/privacy addons/privacy
ln -s ../../.repos/data_protection/privacy_consent addons/privacy_consent
ln -s ../../.repos/data_protection/privacy_partner_to_be_forgotten addons/privacy_partner_to_be_forgotten

# Install
./odoo/odoo-bin -c conf/odoo.conf --no-http --stop-after-init -i social_privacy
```

## Compliance coverage

| Loi 25 Article | Feature |
|----------------|---------|
| Art. 5–9 (consent) | `privacy_consent` OCA + onboarding integration |
| Art. 12 (transparency) | Registry of data processing activities |
| Art. 12.1 (algorithms) | Feed transparency explanation |
| Art. 17.1 (DPO) | `social_privacy.officer` model |
| Art. 17.2 (breaches) | `social_privacy.breach` with 72h CAI workflow |
| Art. 27 (access) | Portal dashboard + backend views |
| Art. 28 (portability) | `social_privacy.export_request` → JSON |
| Art. 29 (rectification) | Profile editable; votes immutable by design |
| Art. 29 (right to be forgotten) | Wizard `social_anonymize_wizard` |
| Art. 30 (retention) | Cron purge + configurable policies |

## License

LGPL-3
