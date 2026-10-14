from itertools import combinations

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

MEMBER_STATES = [
    ('proposed', "Proposé, en attente des membres"),
    ('invited', "Invité"),
    ('accepted', "Membre"),
    ('declined', "A refusé"),
    ('left', "A quitté"),
]


class SocialRelation(models.Model):
    """Relation de deux membres ou plus : couple, trouple, polycule.

    Chaque membre garde son propre compte et peut faire partie de plusieurs relations. La relation
    a son profil (nom, description, photo), sa conversation de groupe, et n'est visible des autres
    membres du réseau que si tous ses membres l'acceptent.

    Toutes les modifications passent par les méthodes ``action_*``, qui vérifient que l'utilisateur
    courant est membre ; les membres n'ont qu'un accès en lecture direct."""
    _name = 'social_relation.relation'
    _description = "Relation (deux personnes ou plus)"
    _inherit = ['image.mixin']
    _order = 'id desc'

    name = fields.Char("Nom", required=True)
    description = fields.Text("Description")
    relation_type_id = fields.Many2one(
        'res.partner.relation.type', "Type des liens", required=True, ondelete='restrict',
        domain=[('is_symmetric', '=', True)],
        default=lambda self: self.env.ref('social_circles.rel_type_partner', raise_if_not_found=False),
        help="Lien créé entre chaque paire de membres (par exemple « Partenaire » ou « Relation poly »).")
    member_ids = fields.One2many('social_relation.member', 'relation_id', "Membres")
    accepted_user_ids = fields.Many2many('res.users', compute='_compute_accepted', string="Membres actuels")
    member_count = fields.Integer(compute='_compute_accepted', string="Nombre de membres")
    state = fields.Selection([
        ('forming', "En formation"),
        ('active', "Active"),
        ('dissolved', "Dissoute"),
    ], default='forming', required=True, readonly=True, index=True)
    is_visible = fields.Boolean(
        "Visible des autres membres", compute='_compute_is_visible', store=True,
        help="Vrai seulement si la relation est active et que tous ses membres acceptent qu'elle soit vue.")
    channel_id = fields.Many2one('discuss.channel', "Conversation", readonly=True, ondelete='set null')
    pair_relation_ids = fields.Many2many(
        'res.partner.relation', 'social_relation_pair_rel', 'relation_id', 'pair_id',
        string="Liens à deux", readonly=True, context={'active_test': False})

    @api.depends('member_ids.state')
    def _compute_accepted(self):
        for relation in self:
            users = relation.member_ids.filtered(lambda m: m.state == 'accepted').user_id
            relation.accepted_user_ids = users
            relation.member_count = len(users)

    @api.depends('state', 'member_ids.state', 'member_ids.share_publicly')
    def _compute_is_visible(self):
        for relation in self:
            accepted = relation.member_ids.filtered(lambda m: m.state == 'accepted')
            relation.is_visible = (
                relation.state == 'active' and len(accepted) >= 2 and all(accepted.mapped('share_publicly')))

    # ── Accès ────────────────────────────────────────────────────────────────

    def _my_member(self, states=('accepted',)):
        """Ligne de l'utilisateur courant dans cette relation, dans l'un des ``states``."""
        self.ensure_one()
        member = self.sudo().member_ids.filtered(lambda m: m.user_id == self.env.user and m.state in states)
        if not member:
            raise AccessError(_("Vous n'êtes pas membre de cette relation."))
        return member

    @api.model
    def _check_social_user(self, user):
        if not user.has_group('social_base.group_social_user'):
            raise UserError(_("Seul un membre du réseau peut faire partie d'une relation."))

    # ── Actions des membres ──────────────────────────────────────────────────

    @api.model
    def action_create_relation(self, name, description=None):
        """Crée une relation dont l'utilisateur courant est le premier membre."""
        self._check_social_user(self.env.user)
        name = (name or '').strip()
        if not name:
            raise UserError(_("Le nom de la relation est requis."))
        relation = self.sudo().create({
            'name': name[:80],
            'description': description or False,
            'member_ids': [(0, 0, {'user_id': self.env.uid, 'state': 'accepted', 'joined_at': fields.Datetime.now()})],
        })
        return relation.sudo(False)

    def action_update(self, vals):
        """Un membre modifie le profil de la relation."""
        self._my_member()
        allowed = {k: v for k, v in vals.items() if k in ('name', 'description', 'image_1920')}
        if 'name' in allowed and not (allowed['name'] or '').strip():
            raise UserError(_("Le nom de la relation est requis."))
        self.sudo().write(allowed)

    def action_invite(self, user):
        """Un membre propose ``user``. S'il est le seul membre, l'invitation part tout de suite ;
        sinon elle attend l'accord de tous les autres membres."""
        me = self._my_member()
        relation = self.sudo()
        if relation.state == 'dissolved':
            raise UserError(_("Cette relation est dissoute."))
        self._check_social_user(user)
        Block = self.env['social_safety.block']
        if any(Block.is_blocked(user, member) for member in relation.accepted_user_ids):
            raise UserError(_("Cette personne ne peut pas être invitée."))
        existing = relation.member_ids.filtered(lambda m: m.user_id == user)
        if existing and existing.state in ('proposed', 'invited', 'accepted'):
            raise UserError(_("Cette personne est déjà membre ou invitée."))
        vals = {'state': 'proposed', 'invited_by_id': self.env.uid, 'approval_user_ids': [(6, 0, [self.env.uid])],
                'share_publicly': False, 'joined_at': False}
        if existing:
            existing.write(vals)
            member = existing
        else:
            member = self.env['social_relation.member'].sudo().create(dict(vals, relation_id=relation.id, user_id=user.id))
        member._promote_if_approved()
        return member

    def action_accept(self):
        """L'invité accepte l'invitation."""
        member = self._my_member(states=('invited',))
        member.write({'state': 'accepted', 'joined_at': fields.Datetime.now()})
        self.sudo()._sync()

    def action_decline(self):
        member = self._my_member(states=('invited',))
        member.write({'state': 'declined'})

    def action_leave(self):
        """Un membre quitte la relation. Sous deux membres, elle est dissoute."""
        member = self._my_member()
        member.write({'state': 'left', 'share_publicly': False})
        self.sudo()._sync()

    def action_set_share(self, share):
        """Le membre courant accepte (ou non) que la relation soit visible des autres membres."""
        member = self._my_member()
        member.write({'share_publicly': bool(share)})

    # ── Synchronisation ──────────────────────────────────────────────────────

    def _sync(self):
        """Met l'état, les liens à deux et la conversation en accord avec les membres acceptés."""
        for relation in self:
            users = relation.accepted_user_ids
            if len(users) >= 2:
                relation.state = 'active'
            elif relation.state == 'active' or (relation.state == 'forming' and not users):
                relation.state = 'dissolved'

            wanted = set()
            if relation.state == 'active':
                for a, b in combinations(users.sorted('id'), 2):
                    wanted.add(relation._ensure_pair(a.partner_id, b.partner_id))
            for pair in relation.pair_relation_ids:
                if pair.id not in wanted and pair.active and not relation._pair_used_elsewhere(pair):
                    pair.active = False
            relation.pair_relation_ids = [(6, 0, list(wanted))]
            relation._sync_channel(users)
            # Un membre parti n'a plus à approuver les propositions en attente.
            relation.member_ids.filtered(lambda m: m.state == 'proposed')._promote_if_approved()

    def _ensure_pair(self, partner_a, partner_b):
        """Lien actif du type de la relation entre deux partenaires ; réutilise un lien existant
        (créé à la main ou par une autre relation) plutôt que d'en créer un doublon."""
        Pair = self.env['res.partner.relation'].sudo().with_context(active_test=False)
        pair = Pair.search([
            ('type_id', '=', self.relation_type_id.id),
            '|',
            '&', ('left_partner_id', '=', partner_a.id), ('right_partner_id', '=', partner_b.id),
            '&', ('left_partner_id', '=', partner_b.id), ('right_partner_id', '=', partner_a.id),
        ], order='active desc, id desc', limit=1)
        if not pair:
            pair = Pair.create({
                'type_id': self.relation_type_id.id,
                'left_partner_id': partner_a.id,
                'right_partner_id': partner_b.id,
            })
        elif not pair.active:
            pair.active = True
        return pair.id

    def _pair_used_elsewhere(self, pair):
        return bool(self.sudo().search_count([
            ('id', '!=', self.id), ('state', '=', 'active'), ('pair_relation_ids', 'in', pair.ids),
        ], limit=1))

    def _sync_channel(self, users):
        """Conversation de groupe des membres acceptés : créée à l'activation, membres à jour."""
        Channel = self.env['discuss.channel'].sudo()
        if self.state != 'active':
            if self.channel_id:
                self.channel_id.channel_member_ids.unlink()
            return
        if not self.channel_id:
            self.channel_id = Channel._create_group(users, name=self.name)
            return
        partners = users.partner_id
        self.channel_id.channel_member_ids.filtered(lambda m: m.partner_id not in partners).unlink()
        missing = partners - self.channel_id.channel_member_ids.partner_id
        if missing:
            self.channel_id._add_members(partners=missing, post_joined_message=False)

    def write(self, vals):
        res = super().write(vals)
        if 'name' in vals:
            for relation in self.filtered('channel_id'):
                relation.channel_id.sudo().name = relation.name
        return res

    # ── Présentation (API) ───────────────────────────────────────────────────

    def _visible_to(self, viewer):
        """Un membre ou invité voit sa relation ; un autre membre du réseau ne la voit que si elle
        est visible et qu'aucun blocage ne le sépare d'un de ses membres."""
        self.ensure_one()
        relation = self.sudo()
        if relation.member_ids.filtered(lambda m: m.user_id == viewer and m.state in ('accepted', 'invited')):
            return True
        if not relation.is_visible or not viewer.has_group('social_base.group_social_user'):
            return False
        Block = self.env['social_safety.block']
        return not any(Block.is_blocked(viewer, member) for member in relation.accepted_user_ids)

    def _api_payload(self, viewer):
        """Ce que ``viewer`` voit de la relation. Les membres voient tout, y compris les
        invitations ; les autres ne voient qu'une relation visible et ses membres actuels."""
        self.ensure_one()
        relation = self.sudo()
        Profile = self.env['club_social_profile.profile'].sudo()
        mine = relation.member_ids.filtered(lambda m: m.user_id == viewer)
        is_member = bool(mine) and mine.state in ('accepted', 'invited')
        members = relation.member_ids if mine and mine.state == 'accepted' else relation.member_ids.filtered(
            lambda m: m.state == 'accepted')
        return {
            'id': relation.id,
            'name': relation.name,
            'description': relation.description or None,
            'state': relation.state,
            'is_visible': relation.is_visible,
            'has_image': bool(relation.image_128),
            'my_state': mine.state if mine else None,
            'my_share': mine.share_publicly if mine else None,
            'members': [{
                'member_id': m.id,
                'user_id': m.user_id.id,
                'name': Profile._display_name_for_user(m.user_id),
                'state': m.state if is_member else 'accepted',
                'share_publicly': m.share_publicly if is_member else None,
                'approved_by_me': (viewer in m.approval_user_ids) if is_member and m.state == 'proposed' else None,
            } for m in members if m.state in ('proposed', 'invited', 'accepted')],
        }


class SocialRelationMember(models.Model):
    _name = 'social_relation.member'
    _description = "Membre d'une relation"
    _order = 'joined_at, id'

    relation_id = fields.Many2one('social_relation.relation', required=True, ondelete='cascade', index=True)
    user_id = fields.Many2one('res.users', "Membre", required=True, ondelete='cascade', index=True)
    state = fields.Selection(MEMBER_STATES, required=True, default='proposed', index=True)
    invited_by_id = fields.Many2one('res.users', "Proposé par", ondelete='set null')
    approval_user_ids = fields.Many2many(
        'res.users', 'social_relation_member_approval_rel', 'member_id', 'user_id', string="Approuvé par")
    share_publicly = fields.Boolean(
        "Accepte que la relation soit visible", default=False,
        help="La relation n'est visible des autres membres que si tous ses membres l'acceptent.")
    joined_at = fields.Datetime("Membre depuis")

    _relation_user_uniq = models.Constraint('UNIQUE(relation_id, user_id)', "Cette personne figure déjà dans la relation.")

    def action_approve(self):
        """Un membre accepte l'arrivée de la personne proposée."""
        self.ensure_one()
        if self.state != 'proposed':
            raise UserError(_("Cette proposition n'est plus en attente."))
        self.relation_id._my_member()
        member = self.sudo()
        member.approval_user_ids = [(4, self.env.uid)]
        member._promote_if_approved()

    def action_reject(self):
        """Un membre refuse l'arrivée de la personne proposée : la proposition est annulée."""
        self.ensure_one()
        if self.state != 'proposed':
            raise UserError(_("Cette proposition n'est plus en attente."))
        self.relation_id._my_member()
        self.sudo().write({'state': 'declined'})

    def _promote_if_approved(self):
        for member in self.sudo():
            if member.state == 'proposed' and not (member.relation_id.accepted_user_ids - member.approval_user_ids):
                member.state = 'invited'
