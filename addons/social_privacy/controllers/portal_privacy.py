from odoo import http
from odoo.http import request
from odoo.exceptions import AccessDenied


class PortalPrivacy(http.Controller):

    @http.route(['/my/privacy'], type='http', auth='user', website=True)
    def portal_privacy_dashboard(self, **kw):
        user = request.env.user
        values = {
            'user': user,
            'page_name': 'privacy',
        }
        return request.render('social_privacy.portal_privacy_dashboard', values)

    @http.route(['/my/privacy/export'], type='http', auth='user', website=True)
    def portal_request_export(self, **kw):
        user = request.env.user
        ExportReq = request.env['social_privacy.export_request'].sudo()
        export = ExportReq.create({'user_id': user.id})
        export.action_generate_export()
        return request.redirect('/my/privacy')

    @http.route(['/my/privacy/export/download/<int:export_id>'], type='http',
                auth='user', website=True)
    def portal_download_export(self, export_id, **kw):
        user = request.env.user
        export = request.env['social_privacy.export_request'].sudo().browse(export_id)
        if export.user_id != user:
            raise AccessDenied()
        if export.state != 'ready':
            return request.redirect('/my/privacy')

        export.action_mark_downloaded()
        return request.make_response(
            export.export_file,
            headers=[
                ('Content-Type', 'application/json'),
                ('Content-Disposition',
                 'attachment; filename="%s"' % export.export_filename),
            ],
        )

    @http.route(['/my/privacy/policy'], type='http', auth='user', website=True)
    def portal_privacy_policy(self, **kw):
        user = request.env.user
        Policy = request.env['social_privacy.policy.version'].sudo()
        Consent = request.env['social_privacy.consent'].sudo()
        policy = Policy.get_current_for_user(user)
        consent_history = Consent.search([('user_id', '=', user.id)], order='consented_at desc')
        values = {
            'page_name': 'privacy_policy',
            'user': user,
            'policy': policy,
            'consent_history': consent_history,
        }
        return request.render('social_privacy.portal_privacy_policy', values)

    @http.route(['/my/privacy/withdraw'], type='http', auth='user', methods=['GET', 'POST'], website=True, csrf=True)
    def portal_consent_withdraw(self, **kw):
        user = request.env.user
        Consent = request.env['social_privacy.consent'].sudo()
        active_consent = Consent.search([
            ('user_id', '=', user.id),
            ('state', '=', 'accepted'),
        ], limit=1, order='consented_at desc')

        if request.httprequest.method == 'POST':
            if active_consent:
                reason = kw.get('reason', '')
                active_consent.action_withdraw(reason)
            return request.redirect('/my/privacy/withdraw')

        values = {
            'page_name': 'consent_withdraw',
            'user': user,
            'active_consent': active_consent,
        }
        return request.render('social_privacy.portal_consent_withdraw', values)

    @http.route(['/my/privacy/delete'], type='http', auth='user', website=True)
    def portal_request_deletion(self, **kw):
        return request.redirect('/my/privacy')
