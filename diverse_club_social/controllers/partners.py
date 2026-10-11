from odoo import http, _
from odoo.http import request


class PartnersController(http.Controller):
    """Gère la page /partners et le formulaire de demande de partenariat."""

    @http.route('/partners', type='http', auth='public', website=True, sitemap=True)
    def partners(self, **kw):
        """Page partenaires avec formulaire."""
        return request.render('diverse_club_social.partners_page', {
            'form_data': {},
        })

    @http.route('/partners/submit', type='http', auth='public', website=True, methods=['POST'], csrf=True)
    def partners_submit(self, **post):
        """Traiter la soumission du formulaire de partenariat."""
        try:
            # Valider les champs obligatoires
            required_fields = ['name', 'email', 'company_name', 'interest_type', 'description']
            for field in required_fields:
                if not post.get(field):
                    return request.render('diverse_club_social.partners_page', {
                        'error': f'Le champ {field} est obligatoire.',
                        'form_data': post,
                    })

            # Créer l'enregistrement
            inquiry = request.env['diverse_club_social.partner_inquiry'].create({
                'name': post['name'],
                'email': post['email'],
                'phone': post.get('phone', ''),
                'company_name': post['company_name'],
                'interest_type': post['interest_type'],
                'description': post['description'],
                'state': 'submitted',
            })

            # Envoyer un email de confirmation (optionnel)
            # TODO: Implémenter l'email de confirmation

            return request.render('diverse_club_social.partners_success', {
                'inquiry': inquiry,
            })

        except Exception as e:
            return request.render('diverse_club_social.partners_page', {
                'error': str(e),
                'form_data': post,
            })

    # ── Hébergement ────────────────────────────────────────────────────
    @http.route('/partners/hosting', type='http', auth='public', website=True, sitemap=True)
    def hosting(self, **kw):
        """Page demande de prix pour hébergement."""
        return request.render('diverse_club_social.hosting_page', {
            'form_data': {},
        })

    @http.route('/partners/hosting/submit', type='http', auth='public', website=True, methods=['POST'], csrf=True)
    def hosting_submit(self, **post):
        """Traiter la soumission du formulaire hébergement."""
        try:
            # Valider les champs obligatoires
            required_fields = ['partner_name', 'contact_name', 'email', 'event_name', 'hosting_type', 'requirements']
            for field in required_fields:
                if not post.get(field):
                    return request.render('diverse_club_social.hosting_page', {
                        'error': f'Le champ {field} est obligatoire.',
                        'form_data': post,
                    })

            # Parser les dates et nombres
            event_date = None
            if post.get('event_date'):
                try:
                    event_date = post['event_date']
                except:
                    pass

            expected_guests = 0
            if post.get('expected_guests'):
                try:
                    expected_guests = int(post['expected_guests'])
                except:
                    pass

            duration_nights = 0
            if post.get('duration_nights'):
                try:
                    duration_nights = int(post['duration_nights'])
                except:
                    pass

            # Créer l'enregistrement
            quote_request = request.env['diverse_club_social.hosting_quote_request'].create({
                'partner_name': post['partner_name'],
                'contact_name': post['contact_name'],
                'email': post['email'],
                'phone': post.get('phone', ''),
                'event_name': post['event_name'],
                'event_date': event_date,
                'hosting_type': post['hosting_type'],
                'expected_guests': expected_guests,
                'duration_nights': duration_nights,
                'requirements': post['requirements'],
                'budget_range': post.get('budget_range', 'not_specified'),
                'preferred_locations': post.get('preferred_locations', ''),
                'state': 'submitted',
            })

            return request.render('diverse_club_social.hosting_success', {
                'quote_request': quote_request,
            })

        except Exception as e:
            return request.render('diverse_club_social.hosting_page', {
                'error': str(e),
                'form_data': post,
            })
