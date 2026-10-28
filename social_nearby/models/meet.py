import datetime

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from .position import (DEFAULT_MEET_HOURS, MAX_MEET_HOURS, MEET_SPOT_MAX_KM,
                         distance_km, snap)

# How far ahead a proposed meet can be scheduled.
MAX_MEET_DAYS_AHEAD = 14


class SocialNearbyMeet(models.Model):
    """A lightweight meeting proposed by a member: start time, duration, approximate spot,
    a restricted audience, and replies approved by the proposer. Proposed -> confirmed/cancelled."""

    _name = 'social_nearby.meet'
    _description = 'Rencontre proposée'
    _order = 'start_at'

    user_id = fields.Many2one('res.users', "Proposée par", required=True, readonly=True,
                              index=True, ondelete='cascade')
    state = fields.Selection([
        ('proposed', 'Proposée'),
        ('confirmed', 'Confirmée'),
        ('cancelled', 'Annulée'),
    ], default='proposed', required=True, index=True)
    start_at = fields.Datetime("Début", required=True, readonly=True)
    until = fields.Datetime("Fin", required=True, readonly=True)
    cell_lat = fields.Float(digits=(9, 6), readonly=True)
    cell_lon = fields.Float(digits=(9, 6), readonly=True)
    audience = fields.Selection([
        ('connections', 'Connexions seulement'),
        ('nearby', 'Membres à proximité'),
    ], default='connections', required=True)
    reply_ids = fields.One2many('social_nearby.meet.reply', 'meet_id', "Réponses")
    safe_zone_id = fields.Many2one('social_nearby.safe_zone', "Safe Zone", readonly=True,
                                   ondelete='set null')
    # A meet proposed by a relation (couple): all its accepted members already attend.
    relation_id = fields.Many2one('social_relation.relation', "Au nom de la relation",
                                  readonly=True, ondelete='set null')

    @api.model
    def _api_create(self, start_at, hours=DEFAULT_MEET_HOURS, latitude=None, longitude=None,
                    audience='connections', safe_zone_id=None, relation_id=None):
        """Create a proposed meet for the current member. Returns the record."""
        if not (isinstance(hours, int) and not isinstance(hours, bool) and 1 <= hours <= MAX_MEET_HOURS):
            raise ValidationError(_("Durée invalide : de 1 à %s heures.", MAX_MEET_HOURS))
        if audience not in ('connections', 'nearby'):
            raise ValidationError(_("Audience invalide."))
        now = fields.Datetime.now()
        if not (now <= start_at <= now + datetime.timedelta(days=MAX_MEET_DAYS_AHEAD)):
            raise ValidationError(_("La date de début doit être entre maintenant et dans 14 jours."))
        position = self.env['social_nearby.position'].sudo().search(
            [('user_id', '=', self.env.uid)], limit=1)
        if not position:
            return None
        relation = None
        if relation_id:
            relation = self.env['social_relation.relation'].sudo().browse(relation_id)
            if self.env.user not in relation.accepted_user_ids:
                raise ValidationError(_("Vous ne faites pas partie de cette relation."))
        safe_zone = self.env['social_nearby.safe_zone'].sudo().browse(safe_zone_id) if safe_zone_id else self.env['social_nearby.safe_zone']
        spot = (position.cell_lat, position.cell_lon)
        if latitude is not None or longitude is not None:
            try:
                latitude, longitude = float(latitude), float(longitude)
            except (TypeError, ValueError):
                raise ValidationError(_("Lieu de rencontre invalide.")) from None
            if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
                raise ValidationError(_("Lieu de rencontre hors limites."))
            spot = snap(latitude, longitude)
            if distance_km(position.cell_lat, position.cell_lon, *spot) > MEET_SPOT_MAX_KM:
                raise ValidationError(_("Le lieu de rencontre doit être à %s km au plus de vous.",
                                        MEET_SPOT_MAX_KM))
        return self.sudo().create({
            'user_id': self.env.uid,
            'start_at': start_at,
            'until': start_at + datetime.timedelta(hours=hours),
            'cell_lat': safe_zone.cell_lat if safe_zone else spot[0],
            'cell_lon': safe_zone.cell_lon if safe_zone else spot[1],
            'audience': audience,
            'safe_zone_id': safe_zone.id or False,
            'relation_id': relation.id if relation else False,
        })

    def _visible_to(self, user):
        """Whether ``user`` may see this proposed meet."""
        self.ensure_one()
        if self.user_id == user:
            return True
        if self.state != 'proposed':
            return False
        if self.audience == 'connections':
            return bool(self.env['club_social_profile.connection'].sudo().search_count([
                ('state', '=', 'accepted'),
                '|', ('requester_id', 'in', (self.user_id.id, user.id)),
                ('addressee_id', 'in', (self.user_id.id, user.id)),
            ]))
        position = self.env['social_nearby.position'].sudo().search(
            [('user_id', '=', user.id)], limit=1)
        return bool(position)

    def _api_list(self):
        """Proposed meets the current member may see, theirs first."""
        now = fields.Datetime.now()
        meets = self.sudo().search([
            ('state', 'in', ('proposed', 'confirmed')),
            ('until', '>', now),
        ])
        return [meet._as_dict() for meet in meets if meet._visible_to(self.env.user)]

    def _as_dict(self):
        self.ensure_one()
        return {
            'id': self.id,
            'state': self.state,
            'start_at': self.start_at,
            'until': self.until,
            'spot': {'latitude': self.cell_lat, 'longitude': self.cell_lon},
            'audience': self.audience,
            'safe_zone': {'id': self.safe_zone_id.id, 'name': self.safe_zone_id.name}
                         if self.safe_zone_id else None,
            'attendee_user_ids': self._attendees().ids,
            'attendee_count': len(self._attendees()),
            'mine': self.user_id.id == self.env.uid,
            'replies': [
                {'user_id': r.user_id.id, 'state': r.state}
                for r in self.reply_ids if r.user_id.id == self.env.uid or self.user_id.id == self.env.uid
            ],
        }

    def _attendees(self):
        """Proposer, accepted members of the relation (a couple attends together), and
        members whose reply was accepted."""
        self.ensure_one()
        users = self.user_id | self.relation_id.accepted_user_ids
        return users | self.reply_ids.filtered(lambda r: r.state == 'accepted').user_id

    def _api_cancel(self):
        self.ensure_one()
        if self.user_id.id != self.env.uid:
            raise ValidationError(_("Seul le proposant peut annuler sa rencontre."))
        self.state = 'cancelled'


class SocialNearbyMeetReply(models.Model):
    """A member's request to join a proposed meet, approved or declined by the proposer."""

    _name = 'social_nearby.meet.reply'
    _description = 'Réponse à une rencontre proposée'

    meet_id = fields.Many2one('social_nearby.meet', required=True, readonly=True,
                              index=True, ondelete='cascade')
    user_id = fields.Many2one('res.users', required=True, readonly=True, index=True,
                              ondelete='cascade')
    state = fields.Selection([
        ('pending', 'En attente'),
        ('accepted', 'Acceptée'),
        ('declined', 'Refusée'),
    ], default='pending', required=True)

    _meet_user_uniq = models.Constraint('UNIQUE(meet_id, user_id)',
                                        "Une seule réponse par membre et par rencontre.")

    @api.model
    def _api_reply(self, meet):
        """Ask to join ``meet`` (pending until the proposer approves)."""
        if not meet._visible_to(self.env.user):
            raise ValidationError(_("Rencontre introuvable."))
        existing = self.sudo().search([('meet_id', '=', meet.id), ('user_id', '=', self.env.uid)], limit=1)
        if existing:
            return existing
        return self.sudo().create({'meet_id': meet.id, 'user_id': self.env.uid})

    def _api_answer(self, accept):
        """Proposer approves or declines this reply; the meet is confirmed on first accept."""
        self.ensure_one()
        if self.meet_id.user_id.id != self.env.uid:
            raise ValidationError(_("Seul le proposant répond aux demandes."))
        self.state = 'accepted' if accept else 'declined'
        if accept:
            self.meet_id.state = 'confirmed'
