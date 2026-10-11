from werkzeug.exceptions import Forbidden, NotFound

from odoo import _
from odoo.http import request, route
from odoo.addons.portal.controllers.portal import CustomerPortal


def _level_labels():
    return {
        'curieux': _('Curious'),
        'soft': _('Soft yes'),
        'oui': _('Yes'),
        'expert': _('Expert'),
    }


def _role_labels():
    return {
        'dominant': _('Dominant'),
        'soumis': _('Submissive'),
        'switch': _('Switch'),
        'maitre': _('Master / Mistress'),
        'esclave': _('Slave'),
        'sadique': _('Sadist'),
        'masochiste': _('Masochist'),
        'curieux': _('Curious (beginner)'),
        'spectateur': _('Spectator'),
        'autre': _('Other'),
    }


def _experience_labels():
    return {
        'nouveau': _('New (< 1 year)'),
        'intermediate': _('Intermediate (1–5 years)'),
        'experimente': _('Experienced (5+ years)'),
    }


class BdsmPortal(CustomerPortal):

    def _prepare_portal_counter_values(self, counter):
        if counter == 'bdsm_profile_count':
            return 'club_social_profile.profile', [
                ('user_id', '=', request.env.user.id), ('bdsm_role', '!=', False),
            ], 'sudo'
        return super()._prepare_portal_counter_values(counter)

    @route('/my/profile/bdsm', auth='user', website=True)
    def bdsm_profile(self, **kw):
        profile = request.env['club_social_profile.profile'].sudo().get_or_create_for_user(
            request.env.user
        )
        kinks_all = request.env['club_social_profile_bdsm.kink'].sudo().search([])
        my_kink_ids = profile.kink_level_ids.mapped('kink_id').ids
        return request.render('club_social_profile_bdsm.portal_bdsm_profile', {
            'profile': profile,
            'kinks_all': kinks_all,
            'my_kink_ids': my_kink_ids,
            'level_labels': _level_labels(),
            'role_labels': _role_labels(),
            'experience_labels': _experience_labels(),
            'page_name': 'bdsm_profile',
        })

    @route('/my/profile/bdsm/save', auth='user', methods=['POST'], website=True, csrf=True)
    def bdsm_save(self, bdsm_role='', experience='', soft_limits='', hard_limits='', **kw):
        profile = request.env['club_social_profile.profile'].sudo().get_or_create_for_user(
            request.env.user
        )
        valid_roles = list(_role_labels().keys())
        valid_experiences = list(_experience_labels().keys())
        profile.write({
            'bdsm_role': bdsm_role if bdsm_role in valid_roles else False,
            'experience': experience if experience in valid_experiences else False,
            'soft_limits': soft_limits.strip() or False,
            'hard_limits': hard_limits.strip() or False,
        })
        return request.redirect('/my/profile/bdsm')

    @route('/my/profile/bdsm/kink/add', auth='user', methods=['POST'], website=True, csrf=True)
    def bdsm_kink_add(self, kink_id=None, level='curieux', **kw):
        if not kink_id:
            return request.redirect('/my/profile/bdsm?error=kink_required')
        profile = request.env['club_social_profile.profile'].sudo().get_or_create_for_user(
            request.env.user
        )
        kink = request.env['club_social_profile_bdsm.kink'].sudo().browse(int(kink_id)).exists()
        if not kink:
            raise NotFound()
        valid_levels = list(_level_labels().keys())
        if level not in valid_levels:
            level = 'curieux'

        KinkLevel = request.env['club_social_profile_bdsm.kink_level'].sudo()
        existing = KinkLevel.search([
            ('profile_id', '=', profile.id),
            ('kink_id', '=', kink.id),
        ], limit=1)
        if existing:
            existing.write({'level': level})
        else:
            KinkLevel.create({
                'profile_id': profile.id,
                'kink_id': kink.id,
                'level': level,
            })
        return request.redirect('/my/profile/bdsm')

    @route('/my/profile/bdsm/kink/<int:kink_level_id>/remove', auth='user', methods=['POST'],
           website=True, csrf=True)
    def bdsm_kink_remove(self, kink_level_id, **kw):
        profile = request.env['club_social_profile.profile'].sudo().search(
            [('user_id', '=', request.env.user.id)], limit=1
        )
        if not profile:
            raise Forbidden()
        kl = request.env['club_social_profile_bdsm.kink_level'].sudo().browse(kink_level_id).exists()
        if not kl or kl.profile_id != profile:
            raise Forbidden()
        kl.unlink()
        return request.redirect('/my/profile/bdsm')

    @route('/my/profile/bdsm/kink/request', auth='user', methods=['POST'], website=True, csrf=True)
    def bdsm_kink_request(self, name='', description='', **kw):
        name = name.strip()
        if not name:
            return request.redirect('/my/profile/bdsm?error=name_required')
        request.env['club_social_profile_bdsm.kink_request'].sudo().create({
            'name': name,
            'description': description.strip() or False,
            'requester_id': request.env.user.id,
        })
        return request.redirect('/my/profile/bdsm?kink_requested=1')
