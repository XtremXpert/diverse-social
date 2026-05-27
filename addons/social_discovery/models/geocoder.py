import logging
import time

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

# Nominatim's published usage policy caps anonymous traffic at 1 req/s.
# We respect that here; for production beyond a few thousand members,
# switch the geo provider to Mapbox/MapTiler in ir.config_parameter.
_NOMINATIM_DELAY_S = 1.1

# How many profiles we attempt per cron run. Tuned for: a cron every hour,
# 1 req/s = ~3600/h theoretical max — we stay well below that.
_BATCH_SIZE = 30


class SocialDiscoveryGeoCache(models.Model):
    """City/region → (lat, lng) cache.

    Lets us re-resolve the same address (e.g. "Montréal, QC") for many
    members without hitting Nominatim again. Insert-only — entries are
    refreshed only when invalidated manually.
    """
    _name = 'social_discovery.geo_cache'
    _description = 'Geocoding cache'
    _rec_name = 'address_key'

    address_key = fields.Char(required=True, index=True)
    lat = fields.Float(digits=(10, 7))
    lng = fields.Float(digits=(10, 7))
    last_fetched = fields.Datetime(default=fields.Datetime.now)

    _sql_constraints = [
        ('address_key_unique', 'unique(address_key)',
         'A cache entry already exists for this address.'),
    ]

    @api.model
    def _normalize(self, address):
        """Lowercase + collapse whitespace. Stable key for cache lookups."""
        return ' '.join((address or '').lower().split())


class SocialDiscoveryGeocoder(models.AbstractModel):
    """Stateless service that resolves pending profiles via base.geocoder + cache."""
    _name = 'social_discovery.geocoder'
    _description = 'Discovery Geocoder Service'

    @api.model
    def _resolve(self, address):
        """Return (lat, lng) for an address string, using the cache."""
        if not address:
            return None
        Cache = self.env['social_discovery.geo_cache']
        key = Cache._normalize(address)
        hit = Cache.search([('address_key', '=', key)], limit=1)
        if hit:
            return (hit.lat, hit.lng) if hit.lat or hit.lng else None

        coords = self.env['base.geocoder'].geo_find(address)
        # Always store the lookup outcome (even misses) so we don't retry
        # them in a tight loop. A miss is recorded as (0, 0).
        Cache.create({
            'address_key': key,
            'lat': coords[0] if coords else 0.0,
            'lng': coords[1] if coords else 0.0,
        })
        return coords

    @api.model
    def _geocode_pending_profiles(self, limit=_BATCH_SIZE):
        """Cron entry point. Picks pending profiles and resolves them."""
        Profile = self.env['club_social_profile.profile']
        pending = Profile.search([
            ('geo_status', '=', 'pending'),
            '|', ('city', '!=', False), ('region', '!=', False),
        ], limit=limit)

        if not pending:
            return

        _logger.info('social_discovery: geocoding %d pending profile(s)', len(pending))
        Cache = self.env['social_discovery.geo_cache']

        for profile in pending:
            address = profile._geo_address_string()
            if not address:
                profile.write({'geo_status': 'skipped'})
                continue

            key = Cache._normalize(address)
            cached = Cache.search([('address_key', '=', key)], limit=1)

            if cached:
                if cached.lat or cached.lng:
                    profile.write({
                        'geo_lat': cached.lat,
                        'geo_lng': cached.lng,
                        'geo_status': 'done',
                        'geo_geocoded_address': address,
                    })
                else:
                    profile.write({
                        'geo_status': 'failed',
                        'geo_geocoded_address': address,
                    })
                continue

            # Real call to Nominatim — rate-limit ourselves.
            try:
                coords = self.env['base.geocoder'].geo_find(address)
            except Exception:
                _logger.warning('Geocoding failed for profile %s', profile.id, exc_info=True)
                coords = None

            if coords:
                Cache.create({'address_key': key, 'lat': coords[0], 'lng': coords[1]})
                profile.write({
                    'geo_lat': coords[0],
                    'geo_lng': coords[1],
                    'geo_status': 'done',
                    'geo_geocoded_address': address,
                })
            else:
                Cache.create({'address_key': key, 'lat': 0.0, 'lng': 0.0})
                profile.write({
                    'geo_status': 'failed',
                    'geo_geocoded_address': address,
                })

            time.sleep(_NOMINATIM_DELAY_S)
