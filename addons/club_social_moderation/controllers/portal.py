from werkzeug.exceptions import NotFound

from odoo.http import Controller, request, route


_ALLOWED_MODELS = frozenset({
    'social_base.post',
    'social_base.comment',
    'club_social_profile.profile',
})

_REASONS = [
    ('spam', 'Spam'),
    ('harcelement', 'Harcèlement'),
    ('contenu_inapproprie', 'Contenu inapproprié'),
    ('mineurs', 'Mise en danger de mineurs'),
    ('autre', 'Autre'),
]
_REASON_KEYS = frozenset(k for k, _ in _REASONS)


class ModerationPortal(Controller):

    def _resolve_target(self, ref_model, ref_id):
        if ref_model not in _ALLOWED_MODELS:
            raise NotFound()
        target = request.env[ref_model].sudo().browse(ref_id).exists()
        if not target:
            raise NotFound()
        return target

    @route('/report/<string:ref_model>/<int:ref_id>', auth='user', website=True, sitemap=False)
    def report_form(self, ref_model, ref_id, error=None, **kw):
        target = self._resolve_target(ref_model, ref_id)
        already = request.env['club_social_moderation.report'].sudo().search([
            ('reporter_id', '=', request.env.user.id),
            ('ref_model', '=', ref_model),
            ('ref_id', '=', ref_id),
            ('state', 'in', ('pending', 'reviewing')),
        ], limit=1)
        return request.render('club_social_moderation.portal_report_form', {
            'ref_model': ref_model,
            'ref_id': ref_id,
            'target_name': target.display_name,
            'reasons': _REASONS,
            'already': bool(already),
            'error': error,
            'page_name': 'report',
        })

    @route(
        '/report/<string:ref_model>/<int:ref_id>/submit',
        auth='user', website=True, methods=['POST'], csrf=True, sitemap=False,
    )
    def report_submit(self, ref_model, ref_id, reason='', description='', **kw):
        target = self._resolve_target(ref_model, ref_id)
        if reason not in _REASON_KEYS:
            return request.redirect(f'/report/{ref_model}/{ref_id}?error=reason_required')
        request.env['club_social_moderation.report'].sudo().create({
            'reporter_id': request.env.user.id,
            'ref_model': ref_model,
            'ref_id': ref_id,
            'reason': reason,
            'description': (description or '').strip() or False,
        })
        return request.render('club_social_moderation.portal_report_confirm', {
            'target_name': target.display_name,
            'page_name': 'report',
        })
