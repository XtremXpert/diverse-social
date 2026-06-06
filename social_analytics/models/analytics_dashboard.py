from datetime import timedelta

from odoo import api, fields, models


class SocialAnalyticsDashboard(models.TransientModel):
    _name = 'social_analytics.dashboard'
    _description = "Tableau de bord analytics réseau social"

    # ── Membres ───────────────────────────────────────────────────────────────
    members_active = fields.Integer("Membres actifs", readonly=True)
    members_new_month = fields.Integer("Nouvelles adhésions (30 j)", readonly=True)
    members_expiring_soon = fields.Integer("Expirent dans 30 j", readonly=True)
    members_pending = fields.Integer("En attente d'activation", readonly=True)

    # ── Engagement ────────────────────────────────────────────────────────────
    posts_published_month = fields.Integer("Posts publiés (30 j)", readonly=True)
    reactions_month = fields.Integer("Réactions (30 j)", readonly=True)
    comments_month = fields.Integer("Commentaires (30 j)", readonly=True)
    stories_active = fields.Integer("Stories actives", readonly=True)

    # ── Modération ────────────────────────────────────────────────────────────
    reports_pending = fields.Integer("Signalements en attente", readonly=True)
    posts_in_moderation = fields.Integer("Posts en attente de modération", readonly=True)

    # ── Gouvernance ───────────────────────────────────────────────────────────
    proposals_voting = fields.Integer("Propositions en vote", readonly=True)
    proposals_draft = fields.Integer("Propositions en brouillon", readonly=True)
    votes_month = fields.Integer("Votes exprimés (30 j)", readonly=True)

    # ── Activité ──────────────────────────────────────────────────────────────
    profiles_total = fields.Integer("Profils créés", readonly=True)
    connections_week = fields.Integer("Nouvelles connexions (7 j)", readonly=True)

    # ── Galerie ───────────────────────────────────────────────────────────────
    photos_pending_moderation = fields.Integer("Photos en attente de modération", readonly=True)
    photos_approved_month = fields.Integer("Photos approuvées (30 j)", readonly=True)
    galleries_total = fields.Integer("Galeries actives", readonly=True)

    # ── Réputation ────────────────────────────────────────────────────────────
    vouchings_active = fields.Integer("Parrainages actifs", readonly=True)
    vouchings_month = fields.Integer("Nouveaux parrainages (30 j)", readonly=True)

    # ── Négociations (disabled, module social_negotiation not included)
    # negotiations_active = fields.Integer("Négociations actives", readonly=True)
    # negotiations_pending_signature = fields.Integer("En attente de signature", readonly=True)

    @api.model
    def get_dashboard_data(self):
        """Calcule toutes les métriques et retourne un dict sérialisable."""
        now = fields.Datetime.now()
        today = fields.Date.today()
        month_ago = now - timedelta(days=30)
        week_ago = now - timedelta(days=7)
        month_from_now = today + timedelta(days=30)

        return {
            'members': self._member_stats(today, month_ago, month_from_now),
            'engagement': self._engagement_stats(month_ago),
            'moderation': self._moderation_stats(),
            'governance': self._governance_stats(month_ago),
            'activity': self._activity_stats(week_ago),
            'gallery': self._gallery_stats(month_ago),
            'reputation': self._reputation_stats(month_ago),
            # 'negotiation': self._negotiation_stats(),  # disabled: social_negotiation not included
            'generated_at': now.isoformat(),
        }

    # ── Sections ──────────────────────────────────────────────────────────────

    @api.model
    def _member_stats(self, today, month_ago, month_from_now):
        Membership = self.env['club_membership.membership'].sudo()
        return {
            'active': Membership.search_count([('state', '=', 'active')]),
            'new_month': Membership.search_count([
                ('state', '=', 'active'),
                ('start_date', '>=', month_ago.date()),
            ]),
            'expiring_soon': Membership.search_count([
                ('state', '=', 'active'),
                ('end_date', '>=', today),
                ('end_date', '<=', month_from_now),
            ]),
            'pending': Membership.search_count([('state', '=', 'pending')]),
            'expired_total': Membership.search_count([('state', '=', 'expired')]),
        }

    @api.model
    def _engagement_stats(self, month_ago):
        Post = self.env['social_base.post'].sudo()
        Reaction = self.env['social_base.reaction'].sudo()
        Comment = self.env['social_base.comment'].sudo()
        Story = self.env['social_story.story'].sudo()

        posts_month = Post.search([
            ('state', '=', 'published'),
            ('create_date', '>=', month_ago),
        ])
        return {
            'posts_published_month': len(posts_month),
            'total_likes_month': sum(posts_month.mapped('like_count')),
            'total_comments_month': sum(posts_month.mapped('comment_count')),
            'reactions_month': Reaction.search_count([
                ('create_date', '>=', month_ago),
            ]),
            'comments_month': Comment.search_count([
                ('create_date', '>=', month_ago),
            ]),
            'stories_active': Story.search_count([('state', '=', 'active')]),
            'top_posts': self._top_posts(month_ago),
        }

    @api.model
    def _top_posts(self, since):
        posts = self.env['social_base.post'].sudo().search([
            ('state', '=', 'published'),
            ('create_date', '>=', since),
        ])
        top = sorted(posts, key=lambda p: p.like_count + p.comment_count, reverse=True)[:5]
        return [{
            'id': p.id,
            'author': p.author_id.name,
            'likes': p.like_count,
            'comments': p.comment_count,
            'excerpt': (p.name or '')[:60],
        } for p in top]

    @api.model
    def _moderation_stats(self):
        Report = self.env['club_social_moderation.report'].sudo()
        Post = self.env['social_base.post'].sudo()
        return {
            'reports_pending': Report.search_count([('state', '=', 'pending')]),
            'reports_resolved_total': Report.search_count([('state', '=', 'resolved')]),
            'posts_in_moderation': Post.search_count([('state', '=', 'moderation')]),
        }

    @api.model
    def _governance_stats(self, month_ago):
        Proposal = self.env['social_governance.proposal'].sudo()
        Vote = self.env['social_governance.vote'].sudo()
        return {
            'proposals_voting': Proposal.search_count([('state', '=', 'voting')]),
            'proposals_draft': Proposal.search_count([('state', '=', 'draft')]),
            'proposals_accepted': Proposal.search_count([('state', '=', 'accepted')]),
            'votes_month': Vote.search_count([('create_date', '>=', month_ago)]),
        }

    @api.model
    def _activity_stats(self, week_ago):
        Profile = self.env['club_social_profile.profile'].sudo()
        Connection = self.env['club_social_profile.connection'].sudo()
        return {
            'profiles_total': Profile.search_count([]),
            'connections_week': Connection.search_count([
                ('state', '=', 'accepted'),
                ('accepted_date', '>=', week_ago),
            ]),
            'connections_total': Connection.search_count([('state', '=', 'accepted')]) // 2,
        }

    @api.model
    def _gallery_stats(self, month_ago):
        Photo = self.env['social_gallery.photo'].sudo()
        Gallery = self.env['social_gallery.gallery'].sudo()
        return {
            'photos_pending_moderation': Photo.search_count([('state', '=', 'pending')]),
            'photos_approved_month': Photo.search_count([
                ('state', '=', 'approved'),
                ('moderation_date', '>=', month_ago),
            ]),
            'galleries_total': Gallery.search_count([
                ('visibility', 'in', ['public', 'members']),
            ]),
        }

    @api.model
    def _reputation_stats(self, month_ago):
        Vouching = self.env['social_reputation.vouching'].sudo()
        return {
            'vouchings_active': Vouching.search_count([('state', '=', 'active')]),
            'vouchings_month': Vouching.search_count([
                ('state', '=', 'active'),
                ('create_date', '>=', month_ago),
            ]),
        }

    # Disabled: social_negotiation module not included
    # @api.model
    # def _negotiation_stats(self):
    #     Neg = self.env['social_negotiation.negotiation'].sudo()
    #     return {
    #         'negotiations_active': Neg.search_count([('state', '=', 'active')]),
    #         'negotiations_pending_signature': Neg.search_count([
    #             ('state', 'in', ['shared', 'reviewing']),
    #         ]),
    #     }

    @api.model
    def open_dashboard(self):
        """Crée ou réutilise un enregistrement transient pour afficher le dashboard."""
        record = self.create({})
        record._populate()
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': record.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def _populate(self):
        """Remplit les champs du transient depuis get_dashboard_data."""
        data = self.get_dashboard_data()
        m = data['members']
        e = data['engagement']
        mod = data['moderation']
        g = data['governance']
        act = data['activity']
        gal = data['gallery']
        rep = data['reputation']
        # neg = data['negotiation']  # disabled
        self.write({
            'members_active': m['active'],
            'members_new_month': m['new_month'],
            'members_expiring_soon': m['expiring_soon'],
            'members_pending': m['pending'],
            'posts_published_month': e['posts_published_month'],
            'reactions_month': e['reactions_month'],
            'comments_month': e['comments_month'],
            'stories_active': e['stories_active'],
            'reports_pending': mod['reports_pending'],
            'posts_in_moderation': mod['posts_in_moderation'],
            'proposals_voting': g['proposals_voting'],
            'proposals_draft': g['proposals_draft'],
            'votes_month': g['votes_month'],
            'profiles_total': act['profiles_total'],
            'connections_week': act['connections_week'],
            'photos_pending_moderation': gal['photos_pending_moderation'],
            'photos_approved_month': gal['photos_approved_month'],
            'galleries_total': gal['galleries_total'],
            'vouchings_active': rep['vouchings_active'],
            'vouchings_month': rep['vouchings_month'],
            # 'negotiations_active': neg['negotiations_active'],
            # 'negotiations_pending_signature': neg['negotiations_pending_signature'],
        })

    def action_refresh(self):
        self._populate()
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }

    # ── Raccourcis vers les vues détaillées ───────────────────────────────────

    def action_view_pending_reports(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Signalements en attente',
            'res_model': 'club_social_moderation.report',
            'view_mode': 'list,form',
            'domain': [('state', '=', 'pending')],
        }

    def action_view_posts_moderation(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Posts en attente de modération',
            'res_model': 'social_base.post',
            'view_mode': 'list,form',
            'domain': [('state', '=', 'moderation')],
        }

    def action_view_pending_memberships(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Adhésions en attente',
            'res_model': 'club_membership.membership',
            'view_mode': 'list,form',
            'domain': [('state', '=', 'pending')],
        }

    def action_view_voting_proposals(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Propositions en vote',
            'res_model': 'social_governance.proposal',
            'view_mode': 'list,form',
            'domain': [('state', '=', 'voting')],
        }

    def action_view_pending_photos(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Photos en attente de modération',
            'res_model': 'social_gallery.photo',
            'view_mode': 'list,form',
            'domain': [('state', '=', 'pending')],
        }
