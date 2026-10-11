from odoo import fields, models


class PartnerInquiry(models.Model):
    _name = 'diverse_club_social.partner_inquiry'
    _description = 'Partnership Inquiry'
    _order = 'create_date desc'

    # ── Informations générales ─────────────────────────────────────────
    name = fields.Char(string='Nom', required=True)
    email = fields.Char(string='Courriel', required=True)
    phone = fields.Char(string='Téléphone')
    company_name = fields.Char(string='Nom entreprise/organisation', required=True)

    # ── Détails du partenariat ─────────────────────────────────────────
    interest_type = fields.Selection([
        ('club', 'Club/Venue'),
        ('organizer', 'Organisateur/Promoteur'),
        ('vendor', 'Fournisseur'),
        ('sponsor', 'Sponsor'),
        ('affiliate', 'Affilié'),
        ('other', 'Autre'),
    ], string='Type d\'intérêt', required=True)

    description = fields.Text(
        string='Description du projet',
        help='Décrivez votre projet, votre club, ou votre offre.',
        required=True
    )

    # ── État ───────────────────────────────────────────────────────────
    state = fields.Selection([
        ('draft', 'Brouillon'),
        ('submitted', 'Soumis'),
        ('in_review', 'En examen'),
        ('contacted', 'Contacté'),
        ('approved', 'Approuvé'),
        ('rejected', 'Rejeté'),
    ], string='État', default='submitted', readonly=True)

    # ── Metadata ───────────────────────────────────────────────────────
    create_date = fields.Datetime(string='Date de soumission', readonly=True)
    notes = fields.Text(string='Notes internes', readonly=True)

    def action_mark_reviewed(self):
        """Marquer comme en examen."""
        self.state = 'in_review'

    def action_mark_contacted(self):
        """Marquer comme contacté."""
        self.state = 'contacted'

    def action_approve(self):
        """Approuver la demande."""
        self.state = 'approved'

    def action_reject(self):
        """Rejeter la demande."""
        self.state = 'rejected'
