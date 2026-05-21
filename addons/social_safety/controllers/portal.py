from odoo.addons.portal.controllers.portal import CustomerPortal
from odoo.http import request, route


class SafetyPortal(CustomerPortal):

    def _get_own_profile(self):
        return request.env['club_social_profile.profile'].sudo().search(
            [('user_id', '=', request.env.user.id)], limit=1
        )

    # ── Safety page ───────────────────────────────────────────────────────────

    @route('/safety', auth='user', website=True, sitemap=False)
    def safety_page(self, **kw):
        user = request.env.user
        profile = self._get_own_profile()

        blocks = request.env['social_safety.block'].sudo().search([
            ('blocker_id', '=', user.id),
        ], order='create_date desc')

        mutes = request.env['social_safety.mute'].sudo().search([
            ('muter_id', '=', user.id),
        ], order='create_date desc')

        exit_url = request.env['ir.config_parameter'].sudo().get_param(
            'social_safety.quick_exit_url', 'https://www.meteomedia.com/'
        )

        return request.render('social_safety.portal_safety_page', {
            'profile': profile,
            'blocks': blocks,
            'mutes': mutes,
            'exit_url': exit_url,
        })

    # ── Panic mode ────────────────────────────────────────────────────────────

    @route('/safety/panic/activate', auth='user', methods=['POST'], website=True, csrf=True)
    def panic_activate(self, **kw):
        profile = self._get_own_profile()
        if profile:
            profile.sudo().action_panic()
        return request.redirect('/safety')

    @route('/safety/panic/lift', auth='user', methods=['POST'], website=True, csrf=True)
    def panic_lift(self, **kw):
        profile = self._get_own_profile()
        if profile:
            profile.sudo().action_panic_lift()
        return request.redirect('/safety')

    # ── Unblock from the portal ───────────────────────────────────────────────

    @route('/safety/block/<int:block_id>/remove', auth='user', methods=['POST'],
           website=True, csrf=True)
    def remove_block(self, block_id, **kw):
        block = request.env['social_safety.block'].sudo().browse(block_id)
        if block.exists() and block.blocker_id.id == request.env.user.id:
            block.unlink()
        return request.redirect('/safety')

    # ── Unmute ────────────────────────────────────────────────────────────────

    @route('/safety/mute/<int:mute_id>/remove', auth='user', methods=['POST'],
           website=True, csrf=True)
    def remove_mute(self, mute_id, **kw):
        mute = request.env['social_safety.mute'].sudo().browse(mute_id)
        if mute.exists() and mute.muter_id.id == request.env.user.id:
            mute.unlink()
        return request.redirect('/safety')
