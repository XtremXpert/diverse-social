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
# Paliers de distance affichés : (borne supérieure en km, libellé).
DISTANCE_BUCKETS = [
    (1, "< 1 km"), (2, "1–2 km"), (5, "2–5 km"), (10, "5–10 km"),
    (25, "10–25 km"), (50, "25–50 km"), (100, "50–100 km"), (math.inf, "> 100 km"),
]


def snap(latitude, longitude):
    """Centre de la case qui contient le point : la seule position qu'Odoo conserve."""
    lat = (math.floor(latitude / CELL_DEG) + 0.5) * CELL_DEG
    lon_step = CELL_DEG / max(math.cos(math.radians(lat)), 0.01)
    lon = (math.floor(longitude / lon_step) + 0.5) * lon_step
    return round(lat, 6), round(((lon + 180) % 360) - 180, 6)


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
        people.sort(key=lambda item: (item[0], -item[1].seen_at.timestamp()))
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
            'people': [self._person_payload(viewer, km, position, profile) for km, position, profile in people],
            'relations': [{
                'id': relation.id,
                'name': relation.name,
                'distance': bucket(km),
                'has_image': bool(relation.image_128),
                'member_ids': relation.accepted_user_ids.ids,
            } for km, relation in relations],
        }

    @api.model
    def _person_payload(self, viewer, km, position, profile):
        """Tuile de la grille. Les informations détaillées (âge, genre, orientation, photo) ne
        sont données que si le profil les montre à ``viewer`` (cercles, connexions…)."""
        user = position.user_id
        detailed = profile.can_see_detailed_info(viewer)
        payload = {
            'user_id': user.id,
            'name': profile._display_name_for_user(user),
            'distance': bucket(km),
            'last_seen': self._last_seen_label(position.seen_at),
            'availability': profile.availability or None,
            'detailed': detailed,
            'has_photo': bool(detailed and profile.profile_image),
        }
        if detailed:
            payload.update({
                'age': profile.age or None,
                'gender': profile.gender or None,
                'orientation': profile.orientation or None,
            })
        return payload
