============================
Social Help & Community Charter
============================

Public ``/community/help`` page with three accordion sections:

* **How do I post?** — generic walkthrough (find a group, pick a category,
  read group rules).
* **How do I report?** — anonymous reports, anti-pile-on guidance,
  9-1-1 reminder for real emergencies.
* **Community charter** — leaf-specific HTML loaded from the
  ``ir.config_parameter`` ``social_help.charter_html``. Each leaf
  community (e.g. ``diverse_club_social``) ships its own charter text
  through a data record without touching the template.

Configuration
=============

Two system parameters drive the page:

* ``social_help.community_name`` — displayed in the page title.
* ``social_help.charter_html`` — HTML body of the charter section.

Leaf modules set these via data records (``noupdate="1"`` keeps manual
edits made through the backend Settings).

Credits
=======

Authors
-------

* Bemade
