from odoo import fields, models


class HostingQuoteRequest(models.Model):
    _name = 'diverse_club_social.hosting_quote_request'
    _description = 'Hosting Quote Request'
    _order = 'create_date desc'

    # ── Informations du demandeur ──────────────────────────────────────
    partner_name = fields.Char(string='Nom du partenaire', required=True)
    contact_name = fields.Char(string='Nom du contact', required=True)
    email = fields.Char(string='Courriel', required=True)
    phone = fields.Char(string='Téléphone')

    # ── Détails de l'hébergement ───────────────────────────────────────
    event_name = fields.Char(string='Nom de l\'événement/lieu', required=True)
    event_date = fields.Date(string='Date prévue de l\'événement')

    hosting_type = fields.Selection([
        ('club_venue', 'Club/Venue'),
        ('event', 'Événement spécial'),
        ('retreat', 'Retraite/Workshop'),
        ('festival', 'Festival'),
        ('other', 'Autre'),
    ], string='Type d\'hébergement requis', required=True)

    expected_guests = fields.Integer(
        string='Nombre de participants attendus',
        help='Estimation du nombre de personnes à héberger'
    )

    duration_nights = fields.Integer(
        string='Nombre de nuits',
        help='Combien de nuits seront nécessaires?'
    )

    requirements = fields.Text(
        string='Exigences spéciales',
        help='Décrivez vos besoins spécifiques (commodités, aménagements, services, etc.)',
        required=True
    )

    budget_range = fields.Selection([
        ('under_50', 'Moins de 50$/nuit par personne'),
        ('50_100', '50-100$/nuit par personne'),
        ('100_150', '100-150$/nuit par personne'),
        ('150_200', '150-200$/nuit par personne'),
        ('200_plus', '200$ et plus/nuit par personne'),
        ('not_specified', 'Non spécifié'),
    ], string='Gamme de budget', default='not_specified')

    preferred_locations = fields.Text(
        string='Emplacements préférés',
        help='Indiquez les régions ou villes préférées'
    )

    # ── État ───────────────────────────────────────────────────────────
    state = fields.Selection([
        ('draft', 'Brouillon'),
        ('submitted', 'Soumis'),
        ('quote_sent', 'Devis envoyé'),
        ('negotiating', 'En négociation'),
        ('closed', 'Fermé'),
    ], string='État', default='submitted', readonly=True)

    # ── Metadata ───────────────────────────────────────────────────────
    create_date = fields.Datetime(string='Date de soumission', readonly=True)
    notes = fields.Text(string='Notes internes', readonly=True)

    def action_mark_quote_sent(self):
        """Marquer comme devis envoyé."""
        self.state = 'quote_sent'

    def action_mark_negotiating(self):
        """Marquer comme en négociation."""
        self.state = 'negotiating'

    def action_close(self):
        """Fermer la demande."""
        self.state = 'closed'
