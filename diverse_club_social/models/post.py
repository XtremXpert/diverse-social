from datetime import timedelta
from odoo import api, fields, models, _

_AGE_GATE_FIELD = 'age_gate_passed'


class SocialPost(models.Model):
    _inherit = 'social_base.post'

    @api.model
    def cron_send_weekly_digest(self):
        now = fields.Datetime.now()
        since = now - timedelta(days=7)

        # ── Contenu global (identique pour tous les membres) ─────────────────

        top_posts = self.search([
            ('state', '=', 'published'),
            ('create_date', '>=', since),
            ('visibility', 'in', ['public', 'members']),
        ], order='like_count desc, comment_count desc', limit=5)

        upcoming_events = self._digest_upcoming_events(now)
        proposals_voting = self._digest_proposals_voting()
        new_members_count = self._digest_new_members_count(since)

        if not top_posts and not upcoming_events and not proposals_voting:
            return

        Profile = self.env['club_social_profile.profile']
        has_age_gate = _AGE_GATE_FIELD in Profile._fields

        profiles = Profile.sudo().search([
            ('onboarding_done', '=', True),
            ('user_id.share', '=', False),
            ('user_id.active', '=', True),
        ])
        system_user = self.env.ref('base.user_root')
        Notification = self.env['club_social_profile.notification'].sudo()
        base_url = self.env['ir.config_parameter'].sudo().get_str('web.base.url', '')

        for profile in profiles:
            if has_age_gate and not profile[_AGE_GATE_FIELD]:
                continue

            member = profile.user_id

            new_connections = self.env['club_social_profile.connection'].sudo().search_count([
                '|',
                '&', ('user_id', '=', member.id), ('state', '=', 'accepted'),
                '&', ('connected_user_id', '=', member.id), ('state', '=', 'accepted'),
                ('write_date', '>=', since),
            ])
            profile_views = self.env['club_social_profile.profile_visit'].sudo().search_count([
                ('profile_id', '=', profile.id),
                ('visited_at', '>=', since),
            ])
            pending_requests = self.env['club_social_profile.connection'].sudo().search_count([
                ('connected_user_id', '=', member.id),
                ('state', '=', 'pending'),
            ])
            connection_rsvps = self._digest_connection_rsvps(member, now)

            Notification._notify(
                user_id=member.id,
                actor_id=system_user.id,
                notif_type='daily_digest',
                body=_('Votre résumé de la semaine — %(views)d vues de profil, %(conn)d nouvelles connexions',
                       views=profile_views, conn=new_connections),
                url='/social/feed',
            )

            if not profile.digest_email_enabled or not member.email:
                continue

            from_email = self.env['ir.config_parameter'].sudo().get_str(
                'diverse_club_social.digest_from_email', 'noreply@diverse-cite.com'
            )
            body_html = self.env['ir.qweb']._render(
                'diverse_club_social.email_weekly_digest',
                {
                    'member': member,
                    'profile': profile,
                    'top_posts': top_posts,
                    'upcoming_events': upcoming_events,
                    'proposals_voting': proposals_voting,
                    'new_connections': new_connections,
                    'profile_views': profile_views,
                    'pending_requests': pending_requests,
                    'new_members_count': new_members_count,
                    'connection_rsvps': connection_rsvps,
                    'base_url': base_url,
                },
                raise_if_not_found=True,
            )
            self.env['mail.mail'].sudo().create({
                'subject': _('Votre résumé de la semaine — Diverse'),
                'email_from': from_email,
                'email_to': member.email,
                'body_html': body_html,
                'auto_delete': True,
            }).send()

    # ── Helpers ───────────────────────────────────────────────────────────────

    @api.model
    def _digest_upcoming_events(self, now):
        """Retourne les événements des 7 prochains jours visibles par les membres."""
        if 'event.event' not in self.env:
            return self.env['event.event'].browse()
        horizon = now + timedelta(days=7)
        return self.env['event.event'].sudo().search([
            ('date_begin', '>=', now),
            ('date_begin', '<=', horizon),
        ], order='date_begin asc', limit=5)

    @api.model
    def _digest_proposals_voting(self):
        """Retourne les propositions actuellement en vote."""
        if 'social_governance.proposal' not in self.env:
            return self.env['social_governance.proposal'].browse()
        return self.env['social_governance.proposal'].sudo().search([
            ('state', '=', 'voting'),
        ], order='voting_closes_at asc', limit=5)

    @api.model
    def _digest_new_members_count(self, since):
        """Retourne le nombre de nouvelles adhésions activées cette semaine."""
        if 'club_membership.membership' not in self.env:
            return 0
        return self.env['club_membership.membership'].sudo().search_count([
            ('state', '=', 'active'),
            ('write_date', '>=', since),
        ])

    @api.model
    def _digest_connection_rsvps(self, member, now):
        """Retourne les événements futurs auxquels les connexions du membre participent.

        Retourne une liste de dicts {event, registrant_names} pour le template.
        Max 5 événements distincts, max 3 noms par événement.
        """
        if 'event.registration' not in self.env:
            return []

        Connection = self.env['club_social_profile.connection'].sudo()
        sent = Connection.search([('user_id', '=', member.id), ('state', '=', 'accepted')])
        recv = Connection.search([('connected_user_id', '=', member.id), ('state', '=', 'accepted')])
        connected_user_ids = set(sent.mapped('connected_user_id.id')) | set(recv.mapped('user_id.id'))
        if not connected_user_ids:
            return []

        conn_partners = self.env['res.users'].sudo().browse(list(connected_user_ids)).mapped('partner_id')
        conn_partner_ids = conn_partners.ids
        if not conn_partner_ids:
            return []

        regs = self.env['event.registration'].sudo().search([
            ('partner_id', 'in', conn_partner_ids),
            ('state', '=', 'open'),
            ('event_id.date_begin', '>=', now),
        ], order='event_id asc, id asc', limit=50)

        from collections import defaultdict
        events_by_id = {}
        names_by_event = defaultdict(list)
        for reg in regs:
            eid = reg.event_id.id
            events_by_id[eid] = reg.event_id
            if len(names_by_event[eid]) < 3:
                names_by_event[eid].append(reg.partner_id.name or '?')

        result = []
        for eid, event in list(events_by_id.items())[:5]:
            result.append({
                'event': event,
                'registrant_names': names_by_event[eid],
            })
        return result
