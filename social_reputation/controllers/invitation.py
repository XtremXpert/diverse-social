from odoo import fields, _
from odoo.exceptions import UserError
from odoo.http import Controller, request, route


class VouchingInvitation(Controller):
    """Public signup flow for invited members.

    An invitation row in state='invited' carries an ``invite_token`` and an
    ``invite_email``. The recipient clicks the URL embedded in the invitation
    email, lands on a pre-filled signup form, and creates their account. The
    new user is then linked to the vouching row, which moves to
    ``pending_payment`` until the membership is paid.
    """

    # ─────────────────────────── GET landing page ───────────────────────────

    @route('/vouching/accept/<string:token>', type='http', auth='public',
           website=True, sitemap=False)
    def accept_landing(self, token, **kw):
        v = self._find_invitation(token)
        if v is None:
            return request.render('social_reputation.invitation_invalid')
        if v.expires_at and v.expires_at < fields.Datetime.now():
            v.sudo().write({'state': 'expired'})
            return request.render('social_reputation.invitation_expired')
        return request.render('social_reputation.invitation_form', {
            'token': token,
            'vouching': v,
            'invite_email': v.invite_email,
            'sponsor_name': v.sponsor_id.name,
            'statement': v.statement,
            'error': kw.get('error'),
        })

    # ─────────────────────────── POST submit ────────────────────────────────

    @route('/vouching/accept/<string:token>/submit', type='http', auth='public',
           website=True, methods=['POST'], csrf=True, sitemap=False)
    def accept_submit(self, token, name='', password='', password_confirm='', **kw):
        name = (name or '').strip()
        password = password or ''

        def fail(err):
            return request.redirect(f'/vouching/accept/{token}?error={err}')

        if not name:
            return fail('name_required')
        if len(password) < 8:
            return fail('password_too_short')
        if password != password_confirm:
            return fail('password_mismatch')

        v = self._find_invitation(token)
        if v is None:
            return request.render('social_reputation.invitation_invalid')
        if v.expires_at and v.expires_at < fields.Datetime.now():
            v.sudo().write({'state': 'expired'})
            return request.render('social_reputation.invitation_expired')

        email = v.invite_email

        # Race: defend against two requests creating two users for the
        # same login. Use a savepoint so we can recover gracefully and
        # we don't leak a half-created res.users on conflict.
        try:
            with request.env.cr.savepoint():
                existing = request.env['res.users'].sudo().with_context(
                    active_test=False,
                ).search([('login', '=', email)], limit=1)
                if existing:
                    return fail('email_already_used')
                user = request.env['res.users'].sudo().with_context(
                    no_reset_password=True,
                ).create({
                    'name': name,
                    'login': email,
                    'email': email,
                    'password': password,
                    'group_ids': [
                        (4, request.env.ref('base.group_portal').id),
                    ],
                })
                v.sudo().accept_invitation(token, user)
        except UserError as e:
            return fail(str(e).replace(' ', '_')[:80])
        except Exception:
            return fail('signup_failed')

        # Auto-login then send the user to the membership join page so they
        # can complete the payment that activates their vouching. Odoo 19's
        # Session.authenticate(env, credential_dict) — not (db, login, pwd).
        request.session.authenticate(
            request.env,
            {'type': 'password', 'login': email, 'password': password},
        )
        return request.redirect('/membership?invited=1')

    # ─────────────────────────── Helpers ────────────────────────────────────

    @staticmethod
    def _find_invitation(token):
        if not token:
            return None
        v = request.env['social_reputation.vouching'].sudo().search([
            ('invite_token', '=', token),
            ('state', '=', 'invited'),
        ], limit=1)
        return v or None
