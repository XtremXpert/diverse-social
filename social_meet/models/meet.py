"""Rencontres de l'application mobile : spontanées (now) et planifiées (planned)."""
import datetime

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.social_nearby.models.position import (
    DEFAULT_MEET_HOURS,
    MAX_MEET_HOURS,
    MEET_SPOT_MAX_KM,
    distance_km,
    snap,
)

MIN_MEET_HOURS = 1
# Une rencontre planifiée reste dans un horizon raisonnable ; la borne stricte
# viendra avec l'enrobage event.event (contrainte du module event).
MAX_PLANNED_DAYS_AHEAD = 180


class SocialMeet(models.Model):
    """Une rencontre : maintenant ou planifiée, avec plusieurs participants.

    Les deux vitesses partagent les mêmes champs (hôte, fenêtre, lieu approché,
    audience, places, participants) ; seul le cycle de vie change.
    """

    _name = 'social_meet.meet'
    _description = 'Rencontre (spontanée ou planifiée)'
    _order = 'date_start desc, id desc'

    kind = fields.Selection([
        ('now', 'Maintenant'),
        ('planned', 'Planifiée'),
    ], default='now', required=True, index=True)
    state = fields.Selection([
        ('open', 'Ouverte'),
        ('full', 'Complète'),
        ('cancelled', 'Annulée'),
        ('expired', 'Terminée'),
    ], default='open', required=True, index=True)

    host_user_id = fields.Many2one(
        'res.users', "Hôte", required=True, readonly=True,
        index=True, ondelete='cascade')
    relation_id = fields.Many2one(
        'social_relation.relation', "Au nom de la relation",
        readonly=True, ondelete='set null',
        help="Renseigné quand un couple ou une relation propose la rencontre.")

    date_start = fields.Datetime("Début", required=True, readonly=True)
    date_end = fields.Datetime("Fin", required=True, readonly=True)
    cell_lat = fields.Float(digits=(9, 6), readonly=True)
    cell_lon = fields.Float(digits=(9, 6), readonly=True)
    safe_zone_id = fields.Many2one(
        'social_nearby.safe_zone', "Safe Zone", readonly=True,
        ondelete='restrict',
        help="Lieu nommé du club ; sinon la case approximative est utilisée.")

    audience = fields.Selection([
        ('nearby', 'Membres à proximité'),
        ('connections', 'Mes connexions'),
        ('circles', 'Un de mes cercles'),
        ('invited', 'Invités seulement'),
    ], default='nearby', required=True,
        help="« À proximité » demande que le membre partage sa zone.")
    seats_max = fields.Integer(
        "Places", default=0,
        help="0 = sans limite. L'hôte compte comme participant.")

    participant_ids = fields.One2many(
        'social_meet.participant', 'meet_id', "Participants")
    participant_count = fields.Integer(
        "Nombre de participants", compute='_compute_participant_count')

    channel_id = fields.Many2one(
        'discuss.channel', "Fil de discussion", readonly=True,
        ondelete='set null')
    event_id = fields.Many2one(
        'event.event', "Événement", readonly=True, ondelete='set null',
        help="Créé pour une rencontre planifiée (page web, places, billetterie).")

    _date_order = models.Constraint(
        'CHECK (date_end > date_start)',
        "La fin de la rencontre doit suivre son début.")
    _seats_positive = models.Constraint(
        'CHECK (seats_max >= 0)',
        "Le nombre de places ne peut pas être négatif.")

    @api.depends('participant_ids', 'participant_ids.state')
    def _compute_participant_count(self):
        for meet in self:
            meet.participant_count = len(
                meet.participant_ids.filtered(lambda p: p.state == 'joined'))

    # ── Contraintes ──────────────────────────────────────────────────────────

    @api.constrains('kind', 'date_start', 'date_end')
    def _check_window(self):
        now = fields.Datetime.now()
        for meet in self:
            if meet.date_end <= meet.date_start:
                raise ValidationError(_("La fin de la rencontre doit suivre son début."))
            hours = (meet.date_end - meet.date_start).total_seconds() / 3600
            if meet.kind == 'now':
                if not (MIN_MEET_HOURS <= hours <= MAX_MEET_HOURS):
                    raise ValidationError(_(
                        "Une rencontre immédiate dure de %(min)s à %(max)s heures.",
                        min=MIN_MEET_HOURS, max=MAX_MEET_HOURS))
                if meet.date_start > now + datetime.timedelta(minutes=15):
                    raise ValidationError(_(
                        "Une rencontre immédiate commence maintenant, pas plus tard."))
            else:
                if meet.date_start < now - datetime.timedelta(hours=1):
                    raise ValidationError(_(
                        "Une rencontre planifiée ne peut pas commencer dans le passé."))
                if meet.date_start > now + datetime.timedelta(days=MAX_PLANNED_DAYS_AHEAD):
                    raise ValidationError(_(
                        "Une rencontre planifiée se planifie au plus %s jours à l'avance.",
                        MAX_PLANNED_DAYS_AHEAD))

    @api.constrains('relation_id', 'host_user_id')
    def _check_relation_host(self):
        for meet in self:
            if meet.relation_id and meet.host_user_id not in meet.relation_id.accepted_user_ids:
                raise ValidationError(_(
                    "Vous ne faites pas partie de cette relation."))

    # ── Visibilité et participation ──────────────────────────────────────────

    def _check_social_access(self, user=None):
        """Le membre peut-il voir et rejoindre cette rencontre ?"""
        self.ensure_one()
        user = user or self.env.user
        if user == self.host_user_id:
            return True
        if self.state not in ('open', 'full'):
            return False
        if self.env['social_safety.block'].sudo().is_blocked(self.host_user_id, user):
            return False
        if self.audience == 'invited':
            return bool(self.participant_ids.filtered(
                lambda p: p.user_id == user and p.state != 'refused'))
        if self.audience == 'connections':
            return bool(self.env['club_social_profile.connection'].sudo().search_count([
                ('state', '=', 'accepted'),
                '|',
                ('requester_id', 'in', (self.host_user_id.id, user.id)),
                ('addressee_id', 'in', (self.host_user_id.id, user.id)),
            ]))
        if self.audience == 'circles':
            circles = self.env['social_circles.circle'].sudo().search(
                [('member_ids', 'in', self.host_user_id.id)])
            return any(user in circle.member_ids for circle in circles)
        # nearby : il faut partager sa zone, comme pour la grille.
        return bool(self.env['social_nearby.position'].sudo().search_count(
            [('user_id', '=', user.id)]))

    def _joined_participants(self):
        self.ensure_one()
        return self.participant_ids.filtered(lambda p: p.state == 'joined')

    def _as_dict(self, user=None):
        """Représentation API d'une rencontre (dates converties par le contrôleur)."""
        self.ensure_one()
        user = user or self.env.user
        self_participant = self.participant_ids.filtered(lambda p: p.user_id == user)
        return {
            'id': self.id,
            'kind': self.kind,
            'state': self.state,
            'date_start': self.date_start,
            'date_end': self.date_end,
            'audience': self.audience,
            'seats_max': self.seats_max,
            'participant_count': self.participant_count,
            'is_host': self.host_user_id == user,
            'joined': bool(self_participant.filtered(lambda p: p.state == 'joined')),
            'host': {'id': self.host_user_id.id, 'name': self.host_user_id.name},
            'relation': ({'id': self.relation_id.id, 'name': self.relation_id.name}
                         if self.relation_id else None),
            'safe_zone': ({'id': self.safe_zone_id.id, 'name': self.safe_zone_id.name}
                          if self.safe_zone_id else None),
            'cell': ({'latitude': self.cell_lat, 'longitude': self.cell_lon}
                     if (self.cell_lat or self.cell_lon) else None),
            'participants': [{
                'user_id': p.user_id.id,
                'name': p.user_id.name,
                'role': p.role,
                'is_self': p.user_id == user,
            } for p in self.participant_ids if p.state == 'joined'],
            'event_id': self.event_id.id or None,
            'channel_id': self.channel_id.id or None,
        }

    @api.model
    def _api_list(self, user=None):
        """Rencontres visibles par ``user`` : ouvertes, non terminées, accessibles."""
        user = user or self.env.user
        now = fields.Datetime.now()
        meets = self.sudo().search([
            ('state', 'in', ('open', 'full')),
            ('date_end', '>', now),
        ])
        return meets.filtered(
            lambda m: m.host_user_id == user or m._check_social_access(user))

    def _sync_full_state(self):
        for meet in self:
            if meet.state in ('cancelled', 'expired'):
                continue
            if meet.seats_max and len(meet._joined_participants()) >= meet.seats_max:
                meet.state = 'full'
            elif meet.state == 'full':
                meet.state = 'open'

    # ── Cycle de vie ─────────────────────────────────────────────────────────

    @api.model
    def _api_create(self, date_start, hours=DEFAULT_MEET_HOURS, kind='now',
                    latitude=None, longitude=None, safe_zone_id=None,
                    relation_id=None, audience=None, seats_max=0):
        """Crée une rencontre pour l'utilisateur courant et inscrit l'hôte."""
        now = fields.Datetime.now()
        hours = int(hours or DEFAULT_MEET_HOURS)
        if kind not in ('now', 'planned'):
            raise ValidationError(_("Type de rencontre inconnu."))

        # Lieu : la case de la position courante, un point choisi, ou une Safe Zone.
        position = self.env['social_nearby.position'].sudo().search(
            [('user_id', '=', self.env.uid)], limit=1)
        if not position and not safe_zone_id:
            raise ValidationError(_(
                "Partagez votre zone pour proposer une rencontre."))
        spot = (position.cell_lat, position.cell_lon) if position else (0.0, 0.0)
        if latitude is not None or longitude is not None:
            latitude, longitude = float(latitude), float(longitude)
            if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
                raise ValidationError(_("Lieu de rencontre hors limites."))
            spot = snap(latitude, longitude)
            if position and distance_km(position.cell_lat, position.cell_lon, *spot) > MEET_SPOT_MAX_KM:
                raise ValidationError(_(
                    "Le lieu de rencontre doit être à %s km au plus de vous.",
                    MEET_SPOT_MAX_KM))
        zone = self.env['social_nearby.safe_zone'].sudo().browse(safe_zone_id) if safe_zone_id else self.env['social_nearby.safe_zone']
        relation = self.env['social_relation.relation'].sudo().browse(relation_id) if relation_id else self.env['social_relation.relation']

        if kind == 'now':
            start = now
            audience = audience or 'nearby'
        else:
            if isinstance(date_start, str):
                try:
                    start = fields.Datetime.to_datetime(date_start)
                except (TypeError, ValueError):
                    raise ValidationError(_("Date de début invalide (format ISO attendu)."))
                if start.tzinfo:
                    start = start.astimezone(datetime.timezone.utc).replace(tzinfo=None)
            else:
                start = date_start
            if not start:
                raise ValidationError(_("Une rencontre planifiée demande une date de début."))
            audience = audience or 'connections'

        meet = self.sudo().create({
            'kind': kind,
            'host_user_id': self.env.uid,
            'relation_id': relation.id or False,
            'date_start': start,
            'date_end': start + datetime.timedelta(hours=hours),
            'cell_lat': zone.cell_lat if zone else spot[0],
            'cell_lon': zone.cell_lon if zone else spot[1],
            'safe_zone_id': zone.id or False,
            'audience': audience,
            'seats_max': max(int(seats_max or 0), 0),
        })
        self.env['social_meet.participant'].sudo().create({
            'meet_id': meet.id, 'user_id': self.env.uid, 'role': 'host'})
        meet._sync_full_state()
        return meet

    def _api_join(self, user=None):
        self.ensure_one()
        user = user or self.env.user
        if not self._check_social_access(user):
            raise ValidationError(_("Rencontre introuvable."))
        participant = self.participant_ids.filtered(lambda p: p.user_id == user)
        if participant and participant.state == 'joined':
            return participant
        # La limite de places vaut aussi pour un membre qui revient (left -> joined).
        if self.seats_max and len(self._joined_participants()) >= self.seats_max:
            raise ValidationError(_("Cette rencontre est complète."))
        if participant:
            participant.sudo().write({'state': 'joined'})
        else:
            participant = self.env['social_meet.participant'].sudo().create({
                'meet_id': self.id, 'user_id': user.id, 'role': 'guest'})
        self._sync_full_state()
        return participant

    def _api_leave(self, user=None):
        self.ensure_one()
        user = user or self.env.user
        if user == self.host_user_id:
            raise ValidationError(_(
                "L'hôte annule la rencontre plutôt que de la quitter."))
        participant = self.participant_ids.filtered(lambda p: p.user_id == user)
        if participant:
            participant.sudo().write({'state': 'left'})
            self._sync_full_state()
        return participant

    def action_cancel(self):
        for meet in self:
            meet.write({'state': 'cancelled'})
        return True

    @api.model
    def _cron_expire(self):
        """Ferme les rencontres dont la fenêtre est passée (toutes les heures)."""
        now = fields.Datetime.now()
        expired = self.sudo().search([
            ('date_end', '<=', now),
            ('state', 'in', ('open', 'full')),
        ])
        expired.write({'state': 'expired'})
        return len(expired)


class SocialMeetParticipant(models.Model):
    """Inscription d'un membre à une rencontre (hôte compris)."""

    _name = 'social_meet.participant'
    _description = 'Participant à une rencontre'
    _order = 'id'

    meet_id = fields.Many2one(
        'social_meet.meet', "Rencontre", required=True,
        ondelete='cascade', index=True)
    user_id = fields.Many2one(
        'res.users', "Membre", required=True, ondelete='cascade', index=True)
    role = fields.Selection([
        ('host', 'Hôte'),
        ('guest', 'Invité'),
    ], default='guest', required=True)
    state = fields.Selection([
        ('joined', 'Inscrit'),
        ('left', 'Parti'),
        ('refused', 'Refusé'),
    ], default='joined', required=True, index=True)

    _meet_user_uniq = models.Constraint(
        'UNIQUE(meet_id, user_id)',
        "Un seul participant par rencontre et par membre.")
