from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from odoo.tests import common
from odoo.exceptions import ValidationError


def _future(days=30):
    return datetime.now() + timedelta(days=days)


class TestEventTicketLodging(common.TransactionCase):
    """Tests pour event.event.ticket — champ lodging_type."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.event = cls.env['event.event'].create({
            'name': 'Événement test',
            'date_begin': _future(10),
            'date_end': _future(11),
        })

    def _ticket(self, lodging_type='none'):
        return self.env['event.event.ticket'].create({
            'name': 'Billet test',
            'event_id': self.event.id,
            'lodging_type': lodging_type,
        })

    def test_default_lodging_type_is_none(self):
        ticket = self._ticket()
        self.assertEqual(ticket.lodging_type, 'none')

    def test_single_lodging_type(self):
        ticket = self._ticket('single')
        self.assertEqual(ticket.lodging_type, 'single')

    def test_double_lodging_type(self):
        ticket = self._ticket('double')
        self.assertEqual(ticket.lodging_type, 'double')


class TestEventRegistrationLodging(common.TransactionCase):
    """Tests pour event.registration — contrainte partner2_id + lodging_type relié."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.event = cls.env['event.event'].create({
            'name': 'Événement test',
            'date_begin': _future(10),
            'date_end': _future(11),
        })
        cls.ticket_none = cls.env['event.event.ticket'].create({
            'name': 'Sans hébergement',
            'event_id': cls.event.id,
            'lodging_type': 'none',
        })
        cls.ticket_single = cls.env['event.event.ticket'].create({
            'name': 'Lit simple',
            'event_id': cls.event.id,
            'lodging_type': 'single',
        })
        cls.ticket_double = cls.env['event.event.ticket'].create({
            'name': 'Lit double',
            'event_id': cls.event.id,
            'lodging_type': 'double',
        })
        cls.partner1 = cls.env['res.partner'].create({'name': 'Participant 1'})
        cls.partner2 = cls.env['res.partner'].create({'name': 'Participant 2'})

    def _registration(self, ticket, partner2_id=False):
        return self.env['event.registration'].create({
            'event_id': self.event.id,
            'event_ticket_id': ticket.id,
            'name': 'Test',
            'email': 'test@example.com',
            'partner2_id': partner2_id,
        })

    # ── lodging_type relié au billet ────────────────────────────────────────

    def test_lodging_type_related_none(self):
        reg = self._registration(self.ticket_none)
        self.assertEqual(reg.lodging_type, 'none')

    def test_lodging_type_related_single(self):
        reg = self._registration(self.ticket_single)
        self.assertEqual(reg.lodging_type, 'single')

    def test_lodging_type_related_double(self):
        reg = self._registration(self.ticket_double, partner2_id=self.partner2.id)
        self.assertEqual(reg.lodging_type, 'double')

    # ── Contrainte partner2_id ──────────────────────────────────────────────

    def test_double_without_partner2_raises(self):
        with self.assertRaises(ValidationError) as cm:
            self._registration(self.ticket_double)
        self.assertIn('partenaire 2', str(cm.exception).lower())

    def test_double_with_partner2_ok(self):
        reg = self._registration(self.ticket_double, partner2_id=self.partner2.id)
        self.assertTrue(reg.exists())
        self.assertEqual(reg.partner2_id, self.partner2)

    def test_single_without_partner2_ok(self):
        reg = self._registration(self.ticket_single)
        self.assertTrue(reg.exists())
        self.assertFalse(reg.partner2_id)

    def test_none_without_partner2_ok(self):
        reg = self._registration(self.ticket_none)
        self.assertTrue(reg.exists())

    def test_write_double_removes_partner2_raises(self):
        """Passer partner2_id à False sur un billet double doit lever une erreur."""
        reg = self._registration(self.ticket_double, partner2_id=self.partner2.id)
        with self.assertRaises(ValidationError):
            reg.partner2_id = False

    def test_partner2_egal_partner1_leve_erreur(self):
        """Un participant ne peut pas être son propre partenaire de couple."""
        with self.assertRaises(ValidationError):
            self.env['event.registration'].create({
                'event_id': self.event.id,
                'event_ticket_id': self.ticket_double.id,
                'name': 'Test',
                'email': 'test@example.com',
                'partner_id': self.partner1.id,
                'partner2_id': self.partner1.id,
            })


class TestWebsiteEventLodgingController(common.TransactionCase):
    """Tests unitaires des méthodes du controller WebsiteEventLodging."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.event = cls.env['event.event'].create({
            'name': 'Événement test',
            'date_begin': _future(10),
            'date_end': _future(11),
        })
        cls.ticket_none = cls.env['event.event.ticket'].create({
            'name': 'Sans hébergement',
            'event_id': cls.event.id,
            'lodging_type': 'none',
        })
        cls.ticket_double = cls.env['event.event.ticket'].create({
            'name': 'Lit double',
            'event_id': cls.event.id,
            'lodging_type': 'double',
        })

    def _controller(self):
        from odoo.addons.event_lodging.controllers.main import WebsiteEventLodging
        return WebsiteEventLodging()

    # ── _process_tickets_form ───────────────────────────────────────────────

    def test_process_tickets_adds_lodging_type_none(self):
        ctrl = self._controller()
        ticket_entries = [{'ticket': self.ticket_none, 'quantity': 1}]

        with patch.object(type(ctrl).__bases__[0], '_process_tickets_form',
                          return_value=ticket_entries):
            result = ctrl._process_tickets_form(self.event, {})

        self.assertEqual(result[0]['lodging_type'], 'none')

    def test_process_tickets_adds_lodging_type_double(self):
        ctrl = self._controller()
        ticket_entries = [{'ticket': self.ticket_double, 'quantity': 1}]

        with patch.object(type(ctrl).__bases__[0], '_process_tickets_form',
                          return_value=ticket_entries):
            result = ctrl._process_tickets_form(self.event, {})

        self.assertEqual(result[0]['lodging_type'], 'double')

    def test_process_tickets_no_ticket_key(self):
        ctrl = self._controller()
        ticket_entries = [{'quantity': 1}]

        with patch.object(type(ctrl).__bases__[0], '_process_tickets_form',
                          return_value=ticket_entries):
            result = ctrl._process_tickets_form(self.event, {})

        self.assertEqual(result[0]['lodging_type'], 'none')

    # ── _process_attendees_form ─────────────────────────────────────────────

    def test_process_attendees_extracts_partner2_fields(self):
        ctrl = self._controller()
        form = {
            '1-name': 'Alice',
            '1-email': 'alice@example.com',
            '1-partner2_name': 'Bob',
            '1-partner2_email': 'bob@example.com',
        }
        base_result = [{'name': 'Alice', 'email': 'alice@example.com'}]

        with patch.object(type(ctrl).__bases__[0], '_process_attendees_form',
                          return_value=base_result) as mock_super:
            result = ctrl._process_attendees_form(self.event, form)
            # Vérifier que les champs partner2 ont été retirés avant d'appeler super()
            passed_form = mock_super.call_args[0][1]
            self.assertNotIn('1-partner2_name', passed_form)
            self.assertNotIn('1-partner2_email', passed_form)

        self.assertEqual(result[0]['_partner2_name'], 'Bob')
        self.assertEqual(result[0]['_partner2_email'], 'bob@example.com')

    def test_process_attendees_no_partner2_fields(self):
        ctrl = self._controller()
        form = {'1-name': 'Alice', '1-email': 'alice@example.com'}
        base_result = [{'name': 'Alice'}]

        with patch.object(type(ctrl).__bases__[0], '_process_attendees_form',
                          return_value=base_result):
            result = ctrl._process_attendees_form(self.event, form)

        self.assertNotIn('_partner2_name', result[0])
        self.assertNotIn('_partner2_email', result[0])

    # ── _create_attendees_from_registration_post ────────────────────────────

    def _mock_request_env(self):
        """Retourne un mock de request.env['res.partner'].sudo()."""
        mock_request = MagicMock()
        mock_request.env = self.env
        return mock_request

    def test_create_attendees_creates_new_partner(self):
        ctrl = self._controller()
        reg_data = [{'_partner2_name': 'Nouveau', '_partner2_email': 'nouveau@example.com'}]

        partner_model = self.env['res.partner']
        # S'assurer qu'il n'existe pas
        self.assertFalse(partner_model.search([('email', '=ilike', 'nouveau@example.com')]))

        mock_req = MagicMock()
        mock_req.env = self.env
        with patch('odoo.addons.event_lodging.controllers.main.request', new=mock_req):
            with patch.object(type(ctrl).__bases__[0],
                              '_create_attendees_from_registration_post',
                              return_value=[{'partner2_id': False}]):
                ctrl._create_attendees_from_registration_post(self.event, reg_data)

        partner = partner_model.search([('email', '=ilike', 'nouveau@example.com')], limit=1)
        self.assertTrue(partner.exists())
        self.assertEqual(partner.name, 'Nouveau')

    def test_create_attendees_finds_existing_partner_by_email(self):
        ctrl = self._controller()
        existing = self.env['res.partner'].create({
            'name': 'Existant', 'email': 'existant@example.com',
        })
        reg_data = [{'_partner2_name': 'Existant', '_partner2_email': 'existant@example.com'}]

        mock_req = MagicMock()
        mock_req.env = self.env
        with patch('odoo.addons.event_lodging.controllers.main.request', new=mock_req):
            with patch.object(type(ctrl).__bases__[0],
                              '_create_attendees_from_registration_post',
                              return_value=[{}]):
                ctrl._create_attendees_from_registration_post(self.event, reg_data)

        # Pas de doublon créé
        partners = self.env['res.partner'].search([('email', '=ilike', 'existant@example.com')])
        self.assertEqual(len(partners), 1)
        self.assertEqual(reg_data[0].get('partner2_id'), existing.id)

    def test_create_attendees_conserves_name_if_different(self):
        """Si l'email existe avec un nom différent, le nom existant est conservé (pas d'écrasement)."""
        ctrl = self._controller()
        existing = self.env['res.partner'].create({
            'name': 'Ancien nom', 'email': 'changé@example.com',
        })
        reg_data = [{'_partner2_name': 'Nouveau nom', '_partner2_email': 'changé@example.com'}]

        mock_req = MagicMock()
        mock_req.env = self.env
        with patch('odoo.addons.event_lodging.controllers.main.request', new=mock_req):
            with patch.object(type(ctrl).__bases__[0],
                              '_create_attendees_from_registration_post',
                              return_value=[{}]):
                ctrl._create_attendees_from_registration_post(self.event, reg_data)

        existing.invalidate_recordset()
        self.assertEqual(existing.name, 'Ancien nom')
        self.assertEqual(reg_data[0].get('partner2_id'), existing.id)

    def test_create_attendees_skips_if_no_name(self):
        ctrl = self._controller()
        reg_data = [{'_partner2_name': '', '_partner2_email': 'test@example.com'}]
        initial_count = self.env['res.partner'].search_count([])

        mock_req = MagicMock()
        mock_req.env = self.env
        with patch('odoo.addons.event_lodging.controllers.main.request', new=mock_req):
            with patch.object(type(ctrl).__bases__[0],
                              '_create_attendees_from_registration_post',
                              return_value=[{}]):
                ctrl._create_attendees_from_registration_post(self.event, reg_data)

        self.assertEqual(self.env['res.partner'].search_count([]), initial_count)

    def test_create_attendees_pops_private_keys(self):
        """Les clés _partner2_* doivent être consommées avant l'appel au super()."""
        ctrl = self._controller()
        reg_data = [{'_partner2_name': 'Alice', '_partner2_email': 'alice@example.com'}]

        mock_req = MagicMock()
        mock_req.env = self.env
        with patch('odoo.addons.event_lodging.controllers.main.request', new=mock_req):
            with patch.object(type(ctrl).__bases__[0],
                              '_create_attendees_from_registration_post',
                              return_value=[{}]) as mock_super:
                ctrl._create_attendees_from_registration_post(self.event, reg_data)
                passed = mock_super.call_args[0][1]
                self.assertNotIn('_partner2_name', passed[0])
                self.assertNotIn('_partner2_email', passed[0])

    def test_create_attendees_sans_email_cree_partenaire(self):
        """Un partenaire sans email doit quand même être créé si le nom est présent."""
        ctrl = self._controller()
        reg_data = [{'_partner2_name': 'Sans Email', '_partner2_email': ''}]

        mock_req = MagicMock()
        mock_req.env = self.env
        with patch('odoo.addons.event_lodging.controllers.main.request', new=mock_req):
            with patch.object(type(ctrl).__bases__[0],
                              '_create_attendees_from_registration_post',
                              return_value=[{}]):
                ctrl._create_attendees_from_registration_post(self.event, reg_data)

        partner = self.env['res.partner'].search([('name', '=', 'Sans Email'), ('email', '=', False)])
        self.assertTrue(partner.exists())

    def test_create_attendees_nom_different_conserve_nom_existant(self):
        """Si l'email existe avec un nom différent, le nom existant est conservé."""
        ctrl = self._controller()
        existing = self.env['res.partner'].create({
            'name': 'Nom Original', 'email': 'original@example.com',
        })
        reg_data = [{'_partner2_name': 'Nom Différent', '_partner2_email': 'original@example.com'}]

        mock_req = MagicMock()
        mock_req.env = self.env
        with patch('odoo.addons.event_lodging.controllers.main.request', new=mock_req):
            with patch.object(type(ctrl).__bases__[0],
                              '_create_attendees_from_registration_post',
                              return_value=[{}]):
                ctrl._create_attendees_from_registration_post(self.event, reg_data)

        existing.invalidate_recordset()
        self.assertEqual(existing.name, 'Nom Original')
        self.assertEqual(reg_data[0].get('partner2_id'), existing.id)

    def test_create_attendees_doublons_email_utilise_premier(self):
        """Si plusieurs partenaires ont le même email, le premier est utilisé sans erreur."""
        ctrl = self._controller()
        p1 = self.env['res.partner'].create({'name': 'Doublon A', 'email': 'doublon@example.com'})
        p2 = self.env['res.partner'].create({'name': 'Doublon B', 'email': 'doublon@example.com'})
        reg_data = [{'_partner2_name': 'Doublon A', '_partner2_email': 'doublon@example.com'}]

        mock_req = MagicMock()
        mock_req.env = self.env
        with patch('odoo.addons.event_lodging.controllers.main.request', new=mock_req):
            with patch.object(type(ctrl).__bases__[0],
                              '_create_attendees_from_registration_post',
                              return_value=[{}]):
                # Ne doit pas lever d'exception
                ctrl._create_attendees_from_registration_post(self.event, reg_data)

        # Un des deux partenaires est référencé
        self.assertIn(reg_data[0].get('partner2_id'), [p1.id, p2.id])
