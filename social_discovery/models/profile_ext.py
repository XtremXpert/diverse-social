import hashlib
import math
import random

from odoo import models, fields, api


# Jitter radius applied to raw geocoded coords before exposure.
# 2-3 km : enough to obscure exact home location while staying neighborhood-accurate.
_JITTER_MIN_KM = 2.0
_JITTER_MAX_KM = 3.0
_KM_PER_LAT_DEGREE = 111.32


class ClubSocialProfile(models.Model):
    _inherit = 'club_social_profile.profile'

    discovery_criteria_ids = fields.One2many(
        'social_discovery.criteria', 'profile_id', string='Saved Searches',
    )
    discovery_criteria_count = fields.Integer(
        compute='_compute_criteria_count',
    )

    @api.depends('discovery_criteria_ids')
    def _compute_criteria_count(self):
        for p in self:
            p.discovery_criteria_count = len(p.discovery_criteria_ids)

    # ── Map exposure (opt-in) ─────────────────────────────────────────────────
    show_on_map = fields.Boolean(
        string='Show me on the members map',
        default=False,
        help='Opt-in. Your position will be obfuscated within a ~2-3 km radius.',
    )

    # ── Dashboard suggestions (opt-out) ───────────────────────────────────────
    # Unlike show_on_map this is opt-out: by default every member with
    # visibility=members + onboarding_done is a candidate for somebody
    # else's "You might like" section. Users who want to be reachable
    # via the directory but not algorithmically pushed can untoggle this.
    show_in_suggestions = fields.Boolean(
        string='Include me in member suggestions',
        default=True,
        help='Opt-out. When off, your profile never appears in the '
             '"You might like" section on other members\' dashboards. '
             'You still appear in /members and /discover.',
    )

    # Raw geocoded centroid of city/region — never exposed publicly.
    geo_lat = fields.Float(digits=(10, 7), readonly=True)
    geo_lng = fields.Float(digits=(10, 7), readonly=True)

    # Stable jittered coordinates derived from the raw centroid + profile id.
    # These are what the /members/map.json endpoint returns.
    geo_lat_jitter = fields.Float(
        digits=(10, 7), compute='_compute_jitter', store=True, readonly=True,
    )
    geo_lng_jitter = fields.Float(
        digits=(10, 7), compute='_compute_jitter', store=True, readonly=True,
    )

    geo_status = fields.Selection([
        ('pending', 'Pending'),
        ('done', 'Done'),
        ('failed', 'Failed'),
        ('skipped', 'No location given'),
    ], default='pending', readonly=True, index=True)

    # The address string we last sent to the geocoder. Lets us invalidate when
    # the profile's city/region changes without re-querying when it hasn't.
    geo_geocoded_address = fields.Char(readonly=True)

    @api.depends('geo_lat', 'geo_lng')
    def _compute_jitter(self):
        """Deterministic per-profile offset within [_JITTER_MIN_KM, _JITTER_MAX_KM].

        Stable across saves so the displayed point doesn't dance every time we
        recompute. Uses profile id as the seed — two profiles in the same city
        won't stack on the same pixel.
        """
        for p in self:
            if not p.geo_lat or not p.geo_lng or not p.id:
                p.geo_lat_jitter = 0.0
                p.geo_lng_jitter = 0.0
                continue
            seed = int(hashlib.sha256(f'social_discovery:{p.id}'.encode()).hexdigest()[:16], 16)
            rng = random.Random(seed)
            radius_km = rng.uniform(_JITTER_MIN_KM, _JITTER_MAX_KM)
            angle = rng.uniform(0.0, 2.0 * math.pi)
            dx_km = radius_km * math.cos(angle)
            dy_km = radius_km * math.sin(angle)
            # Convert km offsets back to degrees. Latitude is uniform; longitude
            # narrows with latitude, so divide by cos(lat).
            dlat = dy_km / _KM_PER_LAT_DEGREE
            cos_lat = max(math.cos(math.radians(p.geo_lat)), 0.01)
            dlng = dx_km / (_KM_PER_LAT_DEGREE * cos_lat)
            p.geo_lat_jitter = p.geo_lat + dlat
            p.geo_lng_jitter = p.geo_lng + dlng

    def _geo_address_string(self):
        """Address we send to the geocoder. Centralized for testability."""
        self.ensure_one()
        parts = [p for p in (self.city, self.region) if p]
        return ', '.join(parts) if parts else ''

    def write(self, vals):
        """When city/region changes, reset geocoding so the cron picks it up."""
        location_changed = any(k in vals for k in ('city', 'region'))
        res = super().write(vals)
        if location_changed:
            for p in self:
                new_address = p._geo_address_string()
                if new_address != p.geo_geocoded_address:
                    p.write({
                        'geo_status': 'pending' if new_address else 'skipped',
                        'geo_lat': 0.0,
                        'geo_lng': 0.0,
                        'geo_geocoded_address': False,
                    })
        return res

    def action_open_discovery(self):
        """Open the default search, or the search list if none."""
        self.ensure_one()
        default = self.discovery_criteria_ids.filtered('is_default')[:1]
        if default:
            return default.action_search()
        return {
            'type': 'ir.actions.act_window',
            'name': 'My Searches',
            'res_model': 'social_discovery.criteria',
            'view_mode': 'list,form',
            'views': [(False, 'list'), (False, 'form')],  # requis par Odoo 20
            'domain': [('profile_id', '=', self.id)],
            'context': {'default_profile_id': self.id},
        }
