from uuid import uuid4

from odoo import models, fields, api


class ClubSocialProfile(models.Model):
    _inherit = 'club_social_profile.profile'

    # Secret per-user ntfy topic. The member subscribes their phone to this
    # topic (via the ntfy app); Odoo publishes generic pushes to it. The topic
    # is a random uuid behind a configurable prefix, so it is unguessable —
    # which, combined with generic payloads, is the v1 privacy model.
    ntfy_topic = fields.Char(
        'ntfy topic', readonly=True, copy=False, index=True,
        help='Secret topic this member is subscribed to for native phone push.',
    )

    def _ensure_ntfy_topic(self):
        """Lazily generate a secret topic the first time it is needed.

        Idempotent: existing topics are left untouched. Uses sudo-safe write
        (the caller may be a portal user editing their own profile)."""
        prefix = self.env['ir.config_parameter'].sudo().get_param(
            'social_ntfy.topic_prefix', 'dc')
        for profile in self:
            if not profile.ntfy_topic:
                profile.sudo().ntfy_topic = '%s_%s' % (prefix, uuid4().hex)
        return self

    def action_regenerate_ntfy_topic(self):
        """Rotate the topic (e.g. if the old one leaked). The member must
        re-subscribe their phone to the new topic afterwards."""
        prefix = self.env['ir.config_parameter'].sudo().get_param(
            'social_ntfy.topic_prefix', 'dc')
        for profile in self:
            profile.sudo().ntfy_topic = '%s_%s' % (prefix, uuid4().hex)
        return self
