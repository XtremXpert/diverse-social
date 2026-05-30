# bemade/social

Shared Odoo 19.0 addons consumed by every Bemade community product
(`diverse-odoo`, `city-club`, `orage-club`). Owns the **infra layer**
of the social network — primitives, profile/membership/moderation base,
plus generic website extensions.

## Contents

30 modules grouped in three layers:

**Social primitives (19)** — `social_base`, `social_feed`, `social_search`,
`social_group`, `social_story`, `social_gallery`, `social_messaging`,
`social_notifications`, `social_circles`, `social_discovery`, `social_safety`,
`social_privacy`, `social_pwa`, `social_governance`, `social_analytics`,
`social_onboarding`, `social_post_categories`, `social_reputation`,
`social_events`.

**Club shared layer (9)** — `club_base`, `club_social_profile`,
`club_social_moderation`, `club_membership`, `club_membership_sale`,
`club_membership_website`, `club_event_user`, `club_event_combo`,
`club_payment_notice`.

**Generic website extensions (2)** — `website_blog_restricted`,
`website_members_only`.

## What's NOT here

- Diverse-specific modules (BDSM profile, age gate, calling,
  negotiation, consent gates, event lodging, theme_sugar) → `bemade/diverse-odoo`
- City modules (`city_club`, `st_isidore_city_club`) → `bemade/city-club`
- l'Orage modules (`lorage_club_social`) → `bemade/orage-club`
- Photo booth (`booth360*`) → `bemade/booth360`

## How leaves consume this

Each product repo (`diverse-odoo`, `city-club`, `orage-club`) pulls
`bemade/social` as a git submodule:

```
.repos/social → bemade/social
addons/social_base → ../.repos/social/addons/social_base   # symlink
addons/club_base   → ../.repos/social/addons/club_base     # symlink
... (one symlink per module)
```

The Docker CI's `build.sh` materialises symlinks into real files
inside the image, so each leaf's runtime image contains the social
addons baked in.

To bump a shared module in a leaf:

```bash
cd .repos/social && git pull origin 19.0 && cd ..
git add .repos/social && git commit -m "bump social submodule"
```

## Standalone CI

This repo also builds its own Docker image via
`bemade/odoo-ci/odoo-ci-dind.yaml` — useful for testing the library
in isolation. The image isn't deployed; it's a smoke check that all
modules install and tests pass.
