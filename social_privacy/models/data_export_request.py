import base64
import json
from datetime import datetime, timezone

from odoo import models, fields, api, _
from odoo.exceptions import UserError


class DataExportRequest(models.Model):
    _name = 'social_privacy.export_request'
    _description = 'Data Export Request (Portability)'
    _order = 'create_date desc'
    _inherit = ['mail.thread']

    user_id = fields.Many2one(
        'res.users',
        string='Requester',
        required=True,
        default=lambda s: s.env.user,
        ondelete='restrict',
    )
    state = fields.Selection([
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('ready', 'Ready'),
        ('downloaded', 'Downloaded'),
        ('expired', 'Expired'),
    ], string='Status', default='pending', required=True)
    export_file = fields.Binary(string='Export File', attachment=True)
    export_filename = fields.Char(string='Filename')
    expires_at = fields.Datetime(string='Expires At')
    generated_at = fields.Datetime(string='Generated At')

    def action_generate_export(self):
        self.ensure_one()
        if self.state != 'pending':
            raise UserError(_('Only pending requests can be processed.'))

        self.write({'state': 'processing'})

        user = self.user_id
        data = self._gather_personal_data(user)

        json_bytes = json.dumps(data, indent=2, default=str).encode('utf-8')
        now = fields.Datetime.now()
        filename = 'personal_data_export_%s_%s.json' % (
            user.login,
            datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S'),
        )

        self.write({
            'export_file': base64.b64encode(json_bytes),
            'export_filename': filename,
            'generated_at': now,
            'expires_at': fields.Datetime.add(now, days=30),
            'state': 'ready',
        })

    def _gather_personal_data(self, user):
        """Collect all personal data across social modules."""
        res = {}  # type: dict[str, object]
        res['export_metadata'] = {
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'odoo_version': '19.0',
            'request_id': self.id,
        }
        res['user'] = {
            'id': user.id,
            'login': user.login,
            'name': user.name,
            'email': user.email,
            'create_date': str(user.create_date),
        }

        # Club social profile
        Profile = self.env['club_social_profile.profile'].sudo()
        profile = Profile.search([('user_id', '=', user.id)], limit=1)
        if profile:
            res['profile'] = {
                'id': profile.id,
                'login': profile.login,
                'pronouns': profile.pronouns or None,
                'birth_year': profile.birth_year or None,
                'gender': profile.gender or None,
                'orientation': profile.orientation or None,
                'bio': profile.bio or None,
                'quote': profile.quote or None,
                'availability': profile.availability or None,
                'city': profile.city or None,
                'region': profile.region or None,
                'visibility': profile.visibility or None,
                'stealth_name': profile.stealth_name or None,
                'allow_link_sharing': profile.allow_link_sharing,
                'digest_email_enabled': profile.digest_email_enabled,
                'onboarding_done': profile.onboarding_done,
                'age_verified': profile.age_verified,
                'profile_view_count': profile.profile_view_count,
            }

        # Posts
        Post = self.env['social_base.post'].sudo()
        posts = Post.search([('author_id', '=', user.id)])
        res['posts'] = [{
            'id': p.id,
            'name': p.name or None,
            'content_excerpt': (p.content or '')[:200] if p.content else None,
            'visibility': p.visibility,
            'state': p.state,
            'create_date': str(p.create_date),
            'like_count': p.like_count,
            'comment_count': p.comment_count,
        } for p in posts]

        # Comments
        Comment = self.env['social_base.comment'].sudo()
        comments = Comment.search([('author_id', '=', user.id)])
        res['comments'] = [{
            'id': c.id,
            'post_id': c.post_id.id,
            'content': c.content or None,
            'state': c.state,
            'create_date': str(c.create_date),
        } for c in comments]

        # Reactions
        Reaction = self.env['social_base.reaction'].sudo()
        reactions = Reaction.search([('user_id', '=', user.id)])
        res['reactions'] = [{
            'id': r.id,
            'type': r.type,
            'target_model': r.target_model,
            'target_id': r.target_id,
            'create_date': str(r.create_date),
        } for r in reactions]

        # Messages (optional — social_messaging retiré au profit de Discuss)
        if 'social_messaging.message' in self.env:
            Message = self.env['social_messaging.message'].sudo()
            msgs = Message.search([('author_id', '=', user.id)])
            res['messages'] = [{
                'id': m.id,
                'thread_id': m.thread_id.id,
                'content': m.content or None,
                'create_date': str(m.create_date),
                'read_by_ids': list(m.read_by_ids.ids) if m.read_by_ids else [],
            } for m in msgs]

        # Negotiations (optional — social_negotiation may not be installed)
        if 'social_negotiation.negotiation' in self.env:
            Neg = self.env['social_negotiation.negotiation'].sudo()
            negs = Neg.search([
                '|', ('initiator_id', '=', user.id), ('partner_id', '=', user.id)
            ])
            res['negotiations'] = [{
                'id': n.id,
                'role': 'initiator' if n.initiator_id == user else 'partner',
                'state': n.state,
                'version': n.version,
                'item_count': n.item_count,
                'agreement_score': n.agreement_score,
                'is_fully_signed': n.is_fully_signed,
                'create_date': str(n.create_date),
            } for n in negs]
        else:
            res['negotiations'] = []

        # Votes
        Vote = self.env['social_governance.vote'].sudo()
        votes = Vote.search([('voter_id', '=', user.id)])
        res['votes'] = [{
            'id': v.id,
            'proposal_id': v.proposal_id.id,
            'choice': v.choice,
            'create_date': str(v.create_date),
        } for v in votes]

        # Vouching (reputation)
        Vouch = self.env['social_reputation.vouching'].sudo()
        given = Vouch.search([('sponsor_id', '=', user.id)])
        received = Vouch.search([('newcomer_id', '=', user.id)])
        res['vouching'] = {
            'given': [{
                'id': v.id,
                'newcomer_id': v.newcomer_id.id,
                'state': v.state,
                'create_date': str(v.create_date),
            } for v in given],
            'received': [{
                'id': v.id,
                'sponsor_id': v.sponsor_id.id,
                'state': v.state,
                'create_date': str(v.create_date),
            } for v in received],
        }

        # Block / Mute (safety)
        Block = self.env['social_safety.block'].sudo()
        Mute = self.env['social_safety.mute'].sudo()
        blocks_made = Block.search([('blocker_id', '=', user.id)])
        blocks_received = Block.search([('blocked_id', '=', user.id)])
        mutes = Mute.search([('muter_id', '=', user.id)])
        res['safety'] = {
            'blocks_made': [{'blocked_id': b.blocked_id.id} for b in blocks_made],
            'blocks_received': [{'blocker_id': b.blocker_id.id} for b in blocks_received],
            'mutes': [{'muted_id': m.muted_id.id, 'until': str(m.until) if m.until else None} for m in mutes],
        }

        # Circles
        Circle = self.env['social_circles.circle'].sudo()
        circles = Circle.search([('profile_id.user_id', '=', user.id)])
        res['circles'] = [{
            'id': c.id,
            'name': c.name,
            'member_count': c.member_count,
        } for c in circles]

        # Notifications
        Notif = self.env['club_social_profile.notification'].sudo()
        notifs = Notif.search([('user_id', '=', user.id)])
        res['notifications'] = [{
            'id': n.id,
            'type': n.type,
            'body': n.body,
            'is_read': n.is_read,
            'read_at': str(n.read_at) if n.read_at else None,
            'create_date': str(n.create_date),
        } for n in notifs]

        # Profile visits
        Visit = self.env['club_social_profile.profile_visit'].sudo()
        visits = Visit.search([('visitor_id', '=', user.id)])
        res['profile_visits'] = [{
            'profile_id': v.profile_id.id,
            'visited_at': str(v.visited_at),
        } for v in visits]

        return res

    def action_mark_downloaded(self):
        self.write({'state': 'downloaded'})

    def action_expire(self):
        self.write({'state': 'expired'})

    @api.model
    def cron_expire_old_exports(self):
        cutoff = fields.Datetime.now()
        old = self.search([
            ('state', '=', 'ready'),
            ('expires_at', '<=', cutoff),
        ])
        old.write({'state': 'expired'})
        return len(old)
