import logging
from datetime import datetime

import pytz

from odoo import http, _
from odoo.http import request
from odoo.exceptions import AccessError, UserError
from odoo.addons.portal.controllers.portal import CustomerPortal

_logger = logging.getLogger(__name__)

_GROUP = "event_portal_create.group_event_portal_organiser"
_DEFAULT_TZ = "America/Toronto"
# Liste blanche : seuls ces champs sont écrits depuis le portail.
_HTML_DT_FMT = "%Y-%m-%dT%H:%M"


class EventPortalOrganiser(CustomerPortal):

    # ── Helpers sécurité ──────────────────────────────────────────────────────

    def _is_organiser(self):
        return request.env.user.has_group(_GROUP)

    def _assert_organiser(self):
        if not self._is_organiser():
            raise AccessError(_("Vous n'êtes pas autorisé à organiser des événements."))

    def _tz(self):
        return request.env.user.tz or _DEFAULT_TZ

    def _owned_events(self):
        """Événements dont l'utilisateur courant est l'organisateur (sudo :
        on scope explicitement par organizer_user_id — le contrôleur est la
        frontière, pas l'ACL)."""
        return request.env["event.event"].sudo().search(
            [("organizer_user_id", "=", request.env.user.id)],
            order="date_begin desc",
        )

    def _get_owned_event(self, event_id):
        event = request.env["event.event"].sudo().browse(int(event_id)).exists()
        if not event or event.organizer_user_id.id != request.env.user.id:
            return request.env["event.event"]
        return event

    def _user_circles(self):
        Circle = request.env["social_circles.circle"].sudo()
        return Circle.search([("profile_id.user_id", "=", request.env.user.id)])

    # ── Conversion date locale <-> UTC ────────────────────────────────────────

    def _parse_dt(self, value):
        """Chaîne datetime-local (heure locale de l'organisateur) → datetime UTC naïf."""
        if not value:
            return False
        naive = datetime.strptime(value, _HTML_DT_FMT)
        tz = pytz.timezone(self._tz())
        return tz.localize(naive).astimezone(pytz.UTC).replace(tzinfo=None)

    def _fmt_dt(self, dt):
        """Datetime UTC naïf → chaîne datetime-local (heure locale) pour l'input."""
        if not dt:
            return ""
        aware = pytz.UTC.localize(dt).astimezone(pytz.timezone(self._tz()))
        return aware.strftime(_HTML_DT_FMT)

    # ── Portail : compteur dans « Mon compte » ────────────────────────────────

    def _prepare_portal_counter_values(self, counter):
        if counter == "event_count":
            if not self._is_organiser():
                return False, [], False
            return "event.event", [("id", "in", self._owned_events().ids)], "read"
        return super()._prepare_portal_counter_values(counter)

    # ── Devenir organisateur (demande + approbation modérateur) ───────────────

    def _social_user(self):
        user = request.env.user
        if not user or not user.has_group("social_base.group_social_user"):
            raise AccessError(_("Réservé aux membres."))
        return user

    @http.route(["/my/become-organiser"], type="http", auth="user", website=True)
    def portal_become_organiser(self, **kw):
        user = self._social_user()
        Request = request.env["event_portal_create.organiser_request"].sudo()
        return request.render("event_portal_create.portal_become_organiser", {
            "is_organiser": self._is_organiser(),
            "has_pending": Request._has_pending(user),
            "page_name": "become_organiser",
            "error": kw.get("error"),
            "submitted": kw.get("submitted"),
        })

    @http.route(["/my/become-organiser/submit"], type="http", auth="user",
                methods=["POST"], website=True, csrf=True)
    def portal_become_organiser_submit(self, motivation="", **kw):
        user = self._social_user()
        Request = request.env["event_portal_create.organiser_request"]
        try:
            with request.env.cr.savepoint():
                Request.submit(user, motivation=motivation)
        except UserError:
            return request.redirect("/my/become-organiser?error=1")
        return request.redirect("/my/become-organiser?submitted=1")

    # ── Liste ─────────────────────────────────────────────────────────────────

    @http.route(["/my/events"], type="http", auth="user", website=True)
    def portal_my_events(self, **kw):
        self._assert_organiser()
        events = self._owned_events()
        return request.render("event_portal_create.portal_my_events", {
            "events": events,
            "page_name": "events",
            "fmt_dt": self._fmt_dt,
        })

    # ── Formulaire (création + édition partagé) ───────────────────────────────

    def _form_values(self, event=None, error=None, form=None):
        return {
            "event": event,
            "circles": self._user_circles(),
            "visibilities": [
                ("members", _("Tous les membres")),
                ("circles", _("Cercles spécifiques")),
            ],
            "error": error,
            "form": form or {},
            "page_name": "events",
            "tz": self._tz(),
            "fmt_dt": self._fmt_dt,
        }

    @http.route(["/my/events/new"], type="http", auth="user", website=True)
    def portal_event_new(self, **kw):
        self._assert_organiser()
        return request.render("event_portal_create.portal_event_form", self._form_values())

    @http.route(["/my/events/<int:event_id>"], type="http", auth="user", website=True)
    def portal_event_edit(self, event_id, **kw):
        self._assert_organiser()
        event = self._get_owned_event(event_id)
        if not event:
            return request.redirect("/my/events")
        return request.render("event_portal_create.portal_event_form", self._form_values(event=event))

    # ── Écritures (sudo + liste blanche) ──────────────────────────────────────

    def _collect_vals(self, post):
        """Extrait et valide les champs autorisés. Retourne (vals, error)."""
        name = (post.get("name") or "").strip()
        if not name:
            return None, _("Le nom de l'événement est obligatoire.")
        date_begin = self._parse_dt(post.get("date_begin"))
        date_end = self._parse_dt(post.get("date_end"))
        if not date_begin or not date_end:
            return None, _("Les dates de début et de fin sont obligatoires.")
        if date_end < date_begin:
            return None, _("La date de fin ne peut pas précéder la date de début.")

        visibility = post.get("social_visibility") or "members"
        if visibility not in ("members", "circles"):
            visibility = "members"

        vals = {
            "name": name,
            "date_begin": date_begin,
            "date_end": date_end,
            "date_tz": self._tz(),
            "description": post.get("description") or False,
            "social_visibility": visibility,
        }

        # Places limitées (optionnel)
        seats_raw = (post.get("seats_max") or "").strip()
        if seats_raw:
            try:
                seats = int(seats_raw)
            except ValueError:
                return None, _("Le nombre de places doit être un nombre entier.")
            if seats > 0:
                vals.update({"seats_limited": True, "seats_max": seats})
            else:
                vals.update({"seats_limited": False, "seats_max": 0})
        else:
            vals.update({"seats_limited": False, "seats_max": 0})

        # Cercles autorisés (seulement si visibilité = circles) — scopés à
        # ceux de l'utilisateur.
        if visibility == "circles":
            wanted = {int(c) for c in request.httprequest.form.getlist("circle_ids")}
            allowed = set(self._user_circles().ids)
            chosen = list(wanted & allowed)
            if not chosen:
                return None, _("Sélectionnez au moins un de vos cercles pour la visibilité par cercles.")
            vals["allowed_circle_ids"] = [(6, 0, chosen)]
        else:
            vals["allowed_circle_ids"] = [(5, 0, 0)]

        return vals, None

    @http.route(["/my/events/new/submit"], type="http", auth="user", website=True,
                methods=["POST"], csrf=True)
    def portal_event_create(self, **post):
        self._assert_organiser()
        vals, error = self._collect_vals(post)
        if error:
            return request.render("event_portal_create.portal_event_form",
                                  self._form_values(error=error, form=post))
        user = request.env.user
        vals.update({
            "organizer_user_id": user.id,
            "organizer_id": user.partner_id.id,
            "user_id": user.id,
            "website_published": False,  # brouillon : publication explicite ensuite
        })
        event = request.env["event.event"].sudo().create(vals)
        _logger.info("Portail : événement %s créé par %s", event.id, user.login)
        return request.redirect("/my/events/%d" % event.id)

    @http.route(["/my/events/<int:event_id>/save"], type="http", auth="user", website=True,
                methods=["POST"], csrf=True)
    def portal_event_save(self, event_id, **post):
        self._assert_organiser()
        event = self._get_owned_event(event_id)
        if not event:
            return request.redirect("/my/events")
        vals, error = self._collect_vals(post)
        if error:
            return request.render("event_portal_create.portal_event_form",
                                  self._form_values(event=event, error=error, form=post))
        event.sudo().write(vals)
        return request.redirect("/my/events/%d" % event.id)

    @http.route(["/my/events/<int:event_id>/publish"], type="http", auth="user", website=True,
                methods=["POST"], csrf=True)
    def portal_event_publish(self, event_id, **post):
        self._assert_organiser()
        event = self._get_owned_event(event_id)
        if event:
            event.sudo().website_published = post.get("publish") == "1"
        return request.redirect("/my/events/%d" % int(event_id))

    @http.route(["/my/events/<int:event_id>/delete"], type="http", auth="user", website=True,
                methods=["POST"], csrf=True)
    def portal_event_delete(self, event_id, **post):
        self._assert_organiser()
        event = self._get_owned_event(event_id)
        if event and event.seats_taken == 0:
            event.sudo().unlink()
        return request.redirect("/my/events")
