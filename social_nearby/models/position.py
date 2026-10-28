import datetime
import math

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

# Taille d'une case en latitude (≈ 556 m) ; en longitude, elle est élargie selon la latitude pour
# garder des cases à peu près carrées.
CELL_DEG = 0.005
EARTH_KM = 6371.0
DEFAULT_RADIUS_KM = 50
MAX_RADIUS_KM = 200
MAX_RESULTS = 100
STALE_DAYS = 7
# Durée du mode « Je veux rencontrer », choisie par le membre : l'application suit alors la
# position en arrière-plan, jamais plus de MAX_MEET_HOURS heures d'affilée.
DEFAULT_MEET_HOURS = 3
MAX_MEET_HOURS = 12
# Zone de la carte : une case grossière de 0,02° (≈ 2,2 km), qui contient la case du membre. On
# voit le quartier, pas la rue ; deux membres d'un même quartier ont la même zone.
AREA_DEG = 0.02
AREA_RADIUS_M = 1500
# Lieu de rencontre choisi pendant « Je veux rencontrer » : sa case de 550 m (rayon dessiné ~300 m),
# à 50 km au plus de la position réelle.
MEET_SPOT_RADIUS_M = 300
MEET_SPOT_MAX_KM = 50
# Paliers de distance affichés : (borne supérieure en km, libellé).
DISTANCE_BUCKETS = [
    (1, "< 1 km"), (2, "1–2 km"), (5, "2–5 km"), (10, "5–10 km"),
    (25, "10–25 km"), (50, "25–50 km"), (100, "50–100 km"), (math.inf, "> 100 km"),
]


def snap(latitude, longitude, size=CELL_DEG):
    """Centre de la case qui contient le point : la seule position qu'Odoo conserve."""
    lat = (math.floor(latitude / size) + 0.5) * size
    lon_step = size / max(math.cos(math.radians(lat)), 0.01)
    lon = (math.floor(longitude / lon_step) + 0.5) * lon_step
    return round(lat, 6), round(((lon + 180) % 360) - 180, 6)


def area(cell_lat, cell_lon):
    """Zone floue d'un membre sur la carte : centre de la case de 0,02° qui contient sa case, et
    rayon à dessiner. La case de 550 m, elle, ne sort jamais."""
    lat, lon = snap(cell_lat, cell_lon, AREA_DEG)
    return {'latitude': lat, 'longitude': lon, 'radius_m': AREA_RADIUS_M}


def distance_km(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_KM * math.asin(min(1.0, math.sqrt(a)))


def bucket(km):
    for limit, label in DISTANCE_BUCKETS:
        if km < limit:
            return label
    return DISTANCE_BUCKETS[-1][1]


class SocialNearbyPosition(models.Model):
    """Case de la grille où se trouve un membre qui partage sa position.

    Une seule ligne par membre, écrasée à chaque envoi, effacée quand il arrête de partager ou
    après sept jours sans nouvelles. La position exacte n'est jamais enregistrée."""
    _name = 'social_nearby.position'
    _description = "Position approximative d'un membre (grille)"
    _rec_name = 'user_id'

    user_id = fields.Many2one('res.users', required=True, readonly=True, index=True, ondelete='cascade')
    cell_lat = fields.Float(digits=(9, 6), readonly=True, index=True)
    cell_lon = fields.Float(digits=(9, 6), readonly=True, index=True)
    seen_at = fields.Datetime(readonly=True, index=True)
    # Mode « Je veux rencontrer » : visible des autres jusqu'à cette échéance.
    meet_until = fields.Datetime("Veut rencontrer jusqu'à", readonly=True)
    # Date et heure de début choisies pour la rencontre ; vide = visible dès l'activation.
    meet_start_at = fields.Datetime("Veut rencontrer à partir de", readonly=True)
    # Lieu où le membre veut rencontrer (case de 550 m), s'il en a choisi un autre que sa position.
    meet_lat = fields.Float(digits=(9, 6), readonly=True)
    meet_lon = fields.Float(digits=(9, 6), readonly=True)

    _user_uniq = models.Constraint('UNIQUE(user_id)', "Une seule position par membre.")

    @api.model
    def _api_report(self, latitude, longitude):
        """Position envoyée par l'application du membre courant (arrondie à sa case)."""
        try:
            latitude, longitude = float(latitude), float(longitude)
        except (TypeError, ValueError):
            raise ValidationError(_("Coordonnées invalides.")) from None
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            raise ValidationError(_("Coordonnées hors limites."))
        lat, lon = snap(latitude, longitude)
        vals = {'cell_lat': lat, 'cell_lon': lon, 'seen_at': fields.Datetime.now()}
        position = self.sudo().search([('user_id', '=', self.env.uid)], limit=1)
        if position:
            position.write(vals)
        else:
            position = self.sudo().create(dict(vals, user_id=self.env.uid))
        return position

    @api.model
    def _api_meet(self, active, hours=DEFAULT_MEET_HOURS, latitude=None, longitude=None, start_at=None):
        """Active (pour ``hours`` heures, à compter de maintenant) ou arrête le mode « Je veux
        rencontrer » du membre courant. Retourne l'échéance, ou ``False``. Exige une position.

        ``latitude`` et ``longitude`` : lieu où le membre veut rencontrer, s'il n'est pas là où il se
        trouve ; gardé arrondi à sa case de 550 m, effacé à l'arrêt ou à l'échéance."""
        if active and not (isinstance(hours, int) and not isinstance(hours, bool) and 1 <= hours <= MAX_MEET_HOURS):
            raise ValidationError(_("Durée invalide : de 1 à %s heures.", MAX_MEET_HOURS))
        if active and start_at is not None:
            now = fields.Datetime.now()
            if not (now <= start_at <= now + datetime.timedelta(days=14)):
                raise ValidationError(_("La date de début doit être entre maintenant et dans 14 jours."))
        position = self.sudo().search([('user_id', '=', self.env.uid)], limit=1)
        if not position:
            return None
        spot = (0.0, 0.0)
        if active and (latitude is not None or longitude is not None):
            try:
                latitude, longitude = float(latitude), float(longitude)
            except (TypeError, ValueError):
                raise ValidationError(_("Lieu de rencontre invalide.")) from None
            if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
                raise ValidationError(_("Lieu de rencontre hors limites."))
            spot = snap(latitude, longitude)
            if distance_km(position.cell_lat, position.cell_lon, *spot) > MEET_SPOT_MAX_KM:
                raise ValidationError(_("Le lieu de rencontre doit être à %s km au plus de vous.", MEET_SPOT_MAX_KM))
        start = start_at if (active and start_at) else (fields.Datetime.now() if active else False)
        until = start + datetime.timedelta(hours=hours) if active else False
        position.write({'meet_start_at': start, 'meet_until': until, 'meet_lat': spot[0], 'meet_lon': spot[1]})
        return until

    def _meet_spot(self):
        """Lieu de rencontre choisi, tant que le mode dure : centre de sa case et rayon à dessiner."""
        self.ensure_one()
        if not self._meeting() or not (self.meet_lat or self.meet_lon):
            return None
        return {'latitude': self.meet_lat, 'longitude': self.meet_lon, 'radius_m': MEET_SPOT_RADIUS_M}

    def _meeting(self):
        """Vrai tant que la fenêtre de rencontre est ouverte (début passé, fin pas atteinte)."""
        self.ensure_one()
        now = fields.Datetime.now()
        return bool(self.meet_until and self.meet_until > now
                    and (not self.meet_start_at or self.meet_start_at <= now))

    def _meeting_planned(self):
        """Vrai quand une rencontre est planifiée mais sa fenêtre n'est pas encore ouverte."""
        self.ensure_one()
        now = fields.Datetime.now()
        return bool(self.meet_start_at and self.meet_until
                    and self.meet_start_at > now and self.meet_until > now)

    @api.model
    def _api_forget(self):
        self.sudo().search([('user_id', '=', self.env.uid)]).unlink()

    @api.model
    def _cron_purge(self):
        limit = fields.Datetime.now() - datetime.timedelta(days=STALE_DAYS)
        self.sudo().search([('seen_at', '<', limit)]).unlink()

    # ── Grille ───────────────────────────────────────────────────────────────

    @api.model
    def _last_seen_label(self, seen_at):
        age = fields.Datetime.now() - seen_at
        if age < datetime.timedelta(minutes=15):
            return 'now'
        if age < datetime.timedelta(days=1):
            return 'today'
        return 'week'

    @api.model
    def _api_grid(self, viewer, radius_km=DEFAULT_RADIUS_KM, limit=MAX_RESULTS):
        """Membres et relations visibles par ``viewer`` autour de sa propre case.

        Retourne ``None`` si ``viewer`` ne partage pas sa position (réciprocité)."""
        me = self.sudo().search([('user_id', '=', viewer.id)], limit=1)
        if not me:
            return None
        radius_km = max(1.0, min(float(radius_km or DEFAULT_RADIUS_KM), MAX_RADIUS_KM))
        dlat = radius_km / 111.0
        dlon = radius_km / (111.0 * max(math.cos(math.radians(me.cell_lat)), 0.01))
        candidates = self.sudo().search([
            ('user_id', '!=', viewer.id),
            ('cell_lat', '>=', me.cell_lat - dlat), ('cell_lat', '<=', me.cell_lat + dlat),
            ('cell_lon', '>=', me.cell_lon - dlon), ('cell_lon', '<=', me.cell_lon + dlon),
            ('seen_at', '>=', fields.Datetime.now() - datetime.timedelta(days=STALE_DAYS)),
            ('user_id.active', '=', True),
        ])
        blocked = set(self.env['social_safety.block'].sudo().get_blocked_ids_for(viewer))
        Profile = self.env['club_social_profile.profile'].sudo()
        profiles = {p.user_id.id: p for p in Profile.search([('user_id', 'in', candidates.user_id.ids)])}
        Connection = self.env['club_social_profile.connection'].sudo()

        people = []
        for position in candidates:
            user = position.user_id
            profile = profiles.get(user.id)
            if (not profile or user.id in blocked or not profile.onboarding_done
                    or profile.is_banned or profile.is_shadow_banned
                    or not user.has_group('social_base.group_social_user')):
                continue
            if profile.visibility == 'connections' and not (
                    Connection.is_connected(user, viewer) or Connection.is_connected(viewer, user)):
                continue
            km = distance_km(me.cell_lat, me.cell_lon, position.cell_lat, position.cell_lon)
            if km > radius_km:
                continue
            people.append((km, position, profile))
        people.sort(key=lambda item: (not item[1]._meeting(), item[0], -item[1].seen_at.timestamp()))
        people = people[:limit]

        distances = {position.user_id.id: km for km, position, _profile in people}
        Member = self.env['social_relation.member'].sudo()
        lines = Member.search([('user_id', 'in', list(distances)), ('state', '=', 'accepted')])
        relations = []
        for relation in lines.relation_id:
            if not relation._visible_to(viewer):
                continue
            nearby = [distances[u.id] for u in relation.accepted_user_ids if u.id in distances]
            relations.append((min(nearby), relation))
        relations.sort(key=lambda item: item[0])

        return {
            'meet_until': me.meet_until if me._meeting() or me._meeting_planned() else None,
            'meet_start_at': me.meet_start_at if me._meeting_planned() else None,
            'meet_spot': me._meet_spot(),
            'people': [self._person_payload(viewer, km, position, profile, me) for km, position, profile in people],
            'relations': [{
                'id': relation.id,
                'name': relation.name,
                'distance': bucket(km),
                'has_image': bool(relation.image_128),
                'member_ids': relation.accepted_user_ids.ids,
            } for km, relation in relations],
        }

    @api.model
    def _person_payload(self, viewer, km, position, profile, me=None):
        """Tuile de la grille. Les informations détaillées (âge, genre, orientation, photo) ne
        sont données que si le profil les montre à ``viewer`` (cercles, connexions…)."""
        user = position.user_id
        detailed = profile.can_see_detailed_info(viewer)
        payload = {
            'user_id': user.id,
            'name': profile._display_name_for_user(user),
            'distance': bucket(km),
            # Qui veut rencontrer est « là maintenant » : son téléphone signale chaque déplacement,
            # et s'il ne bouge pas, sa case reste juste.
            'last_seen': self._last_seen_label(position.seen_at),
            'meet': position._meeting(),
            'availability': profile.availability or None,
            'detailed': detailed,
            'has_photo': bool(detailed and profile.profile_image),
            # Carte : zone floue d'environ 2 km, jamais la case.
            'area': area(position.cell_lat, position.cell_lon),
        }
        spot = position._meet_spot()
        if spot:
            # Où il veut rencontrer, s'il l'a choisi : la case, et sa distance depuis ma case.
            payload['meet_spot'] = spot
            if me:
                payload['meet_distance'] = bucket(distance_km(me.cell_lat, me.cell_lon, spot['latitude'], spot['longitude']))
        if detailed:
            payload.update({
                'age': profile.age or None,
                'gender': profile.gender or None,
                'orientation': profile.orientation or None,
            })
        return payload
