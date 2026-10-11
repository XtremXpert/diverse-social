"""Install/upgrade hooks for diverse_club_social.

Five concerns, all idempotent and re-run on every upgrade via
migrations/<version>/post-migrate.py:

1. Activate French (Canada) and make it the default for new users
   + every website in the DB (with English kept as alternate).
2. Translate the website navigation menus to French.
3. Restrict member-only menus to group_social_user so anonymous
   visitors don't see — and click into — login redirects.
4. Apply the diverse-cite logo to res.company + website + favicon
   from theme_diverse_cite/static/src/img/.
"""
import base64
from odoo.tools.binary import BinaryBytes
import logging
import os

_logger = logging.getLogger(__name__)

_HERE = os.path.dirname(os.path.abspath(__file__))


# ── Constants ──────────────────────────────────────────────────────────

PUBLIC_URLS = frozenset({
    '/',
    '/contactus',
    '/event',
    '/shop',  # Boutique stays a public top-level entry
    '#',  # top-level menu containers with no own URL
})

# URL → nom FR. The container menus (Community / My Network / My Account)
# share their URL with their first child, so they're handled separately
# by CONTAINER_FR below (matched by English name).
MENU_FR_BY_URL = {
    '/':                       'Accueil',
    '/discover':               'Découvrir',
    '/my/dashboard':           'Tableau de bord',
    '/my/profile/bdsm':        'Profil BDSM',
    '/my/stories':             'Stories',          # garde EN (jargon réseau social)
    '/shop':                   'Boutique',
    '/my/messages':            'Messages',
    '/my/chats':               'Messages',
    '/my/groups':              'Groupes',
    '/my/circles':             'Cercles',
    '/event':                  'Événements',
    '/search':                 'Recherche',
    '/social/notifications':   'Notifications',
    '/my/gallery':             'Galerie',
    '/governance':             'Gouvernance',
    '/my/negotiation':         'Négociations',
    '/my/vouching':            'Parrainages',
    '/contactus':              'Nous joindre',
    '/safety':                 'Sécurité',
    '/my/consent':             'Consentement',
    '/my/privacy':             'Confidentialité',
    '/my/membership':          'Adhésion',
}

CONTAINER_FR_BY_EN = {
    'Community':    'Communauté',
    'My Network':   'Mon réseau',
    'My Account':   'Mon compte',
}

# Cible de réorganisation de la nav : url de menu feuille → (conteneur, sequence).
# conteneur ∈ {'community','network','account'} — résolu par site en website.menu réel.
# Sépare l'activité sociale (network) des réglages compte/sécurité (account),
# et regroupe le contenu partagé (Stories/Galerie) sous community.
# Résultat : Communauté=5, Mon réseau=6, Mon compte=6 (aucun dropdown > 6).
NAV_LAYOUT = {
    '/discover':             ('community', 10),
    '/search':               ('community', 20),
    '/my/stories':           ('community', 30),
    '/my/gallery':           ('community', 40),
    '/governance':           ('community', 50),
    '/my/dashboard':         ('network',   10),
    '/my/messages':          ('network',   20),
    '/my/groups':            ('network',   30),
    '/my/circles':           ('network',   40),
    '/my/negotiation':       ('network',   50),
    '/social/notifications': ('network',   60),
    '/my/profile/bdsm':      ('account',   10),
    '/my/vouching':          ('account',   20),
    '/my/membership':        ('account',   30),
    '/safety':               ('account',   40),
    '/my/consent':           ('account',   50),
    '/my/privacy':           ('account',   60),
}


# ── 1. Language activation ─────────────────────────────────────────────

def _ensure_fr_ca(env):
    """Install fr_CA translations + set as default for new users."""
    Lang = env['res.lang']
    fr = Lang.with_context(active_test=False).search([('code', '=', 'fr_CA')], limit=1)
    if not fr:
        _logger.warning("res.lang fr_CA not in registry, skipping i18n setup")
        return
    if not fr.active:
        env['base.language.install'].create({
            'lang_ids': [(4, fr.id)],
            'overwrite': True,
        }).lang_install()
        _logger.info("Installed fr_CA translations")
    # Default lang for newly created res.users (existing users untouched)
    env['ir.default'].set('res.users', 'lang', 'fr_CA')

    # Ensure company partner lang is fr_CA (controls default lang for guests/emails)
    company = env.user.company_id
    if company.partner_id.lang != 'fr_CA':
        company.partner_id.sudo().write({'lang': 'fr_CA'})


# ── 2. Website language config (per-website, not just website_id=1) ────

def _configure_websites(env):
    """For every website: fr_CA + en_US enabled, fr_CA default,
    name 'Diverse-Cité' (overrides Odoo's default 'My Website')."""
    fr = env['res.lang'].search([('code', '=', 'fr_CA')], limit=1)
    en = env['res.lang'].search([('code', '=', 'en_US')], limit=1)
    if not fr or not en:
        return
    for website in env['website'].search([]):
        vals = {}
        target_langs = {fr.id, en.id}
        if set(website.language_ids.ids) != target_langs:
            vals['language_ids'] = [(6, 0, list(target_langs))]
        if website.default_lang_id != fr:
            vals['default_lang_id'] = fr.id
        if website.name != 'Diverse-Cité':
            vals['name'] = 'Diverse-Cité'
        if vals:
            website.write(vals)
            _logger.info("Configured website %s: %s", website.id, list(vals))


# ── 3. Menu translation ────────────────────────────────────────────────

def _translate_menus(env):
    """Add the fr_CA name to website menus where missing.

    Idempotent: only writes when the existing fr_CA name differs.
    Container menus (Community / My Network / My Account) are matched
    by their English name because they share a URL with a child.
    """
    Menu = env['website.menu']
    menus = Menu.search([('website_id', '!=', False)])
    changed = 0
    for m in menus:
        en_name = m.with_context(lang='en_US').name or ''
        fr_name = MENU_FR_BY_URL.get(m.url) or CONTAINER_FR_BY_EN.get(en_name)
        if not fr_name:
            continue
        current_fr = m.with_context(lang='fr_CA').name
        if current_fr == fr_name:
            continue
        m.with_context(lang='fr_CA').write({'name': fr_name})
        changed += 1
    if changed:
        _logger.info("Translated %d website menus to fr_CA", changed)


# ── 4. Menu gating ─────────────────────────────────────────────────────

def _restrict_member_menus(env):
    """Add group_social_user to every website.menu whose URL isn't public.

    Idempotent: re-running adds the group only where it's missing.
    Applies to all websites in the DB (not just website_id=1) so a
    future multi-site setup inherits the same gating.
    """
    group = env.ref('social_base.group_social_user', raise_if_not_found=False)
    if not group:
        _logger.warning("group_social_user not found, skipping menu gating")
        return
    Menu = env['website.menu']
    menus = Menu.search([
        ('website_id', '!=', False),
        ('url', '!=', False),
    ])
    changed = 0
    for menu in menus:
        if menu.url in PUBLIC_URLS:
            continue
        if group in menu.group_ids:
            continue
        menu.write({'group_ids': [(4, group.id)]})
        changed += 1
    if changed:
        _logger.info("Restricted %d website menus to group_social_user", changed)


def _open_contact_menu(env):
    """Make the Contact Us menu visible to anonymous visitors.

    `_restrict_member_menus` is additive: it never removes the group, so
    a menu gated by an earlier version stays hidden even once its URL is
    promoted into PUBLIC_URLS. This complements it by *stripping*
    group_social_user from the /contactus menu so the public user sees it.
    Idempotent: only writes when the group is still present.
    """
    group = env.ref('social_base.group_social_user', raise_if_not_found=False)
    if not group:
        _logger.warning("group_social_user not found, skipping contact menu opening")
        return
    menus = env['website.menu'].search([
        ('website_id', '!=', False),
        ('url', '=', '/contactus'),
    ])
    changed = 0
    for menu in menus:
        if group in menu.group_ids:
            menu.write({'group_ids': [(3, group.id)]})
            changed += 1
    if changed:
        _logger.info("Opened Contact Us menu to anonymous visitors (%d)", changed)


# ── 5. Logo + favicon ──────────────────────────────────────────────────

# Resolved relative to this hooks.py at install time. The image files
# live in theme_diverse_cite (a sibling module brought in via the
# diverse_club_social manifest depends).
# logo_medallion = transparent circular cutout — works on any nav bg.
# logo.png (with wordmark + grey backplate) is kept in the repo for
# wider placements (emails, share images) but not auto-applied.
_LOGO_REL_PATH = ('..', 'theme_diverse_cite', 'static', 'src', 'img', 'logo_medallion.png')
_FAVICON_REL_PATH = ('..', 'theme_diverse_cite', 'static', 'src', 'img', 'favicon-32.png')


def _differs(current, new):
    """Compare un champ Binary (BinaryValue en Odoo 20) au contenu voulu."""
    return bytes(current or b"") != bytes(new)


def _read_image_b64(*path_parts):
    """Return base64-encoded bytes of a file relative to addons/diverse_club_social/.
    Returns None if the file is missing (theme module removed)."""
    full = os.path.join(_HERE, *path_parts)
    if not os.path.exists(full):
        return None
    with open(full, 'rb') as f:
        # Odoo 20 : les champs Binary s'écrivent avec une BinaryValue (bytes bruts)
        return BinaryBytes(f.read())


def _apply_logo(env):
    """Set res.company.logo/favicon, website.logo and website.favicon from
    theme_diverse_cite image files. Idempotent: skips when the target
    already holds the same bytes.

    res.company.favicon matters because web_favicon (OCA) serves the
    *company* favicon whenever the render context has no website_id
    (i.e. the backend / web client). Without it the backend keeps the
    randomized default Odoo favicon."""
    logo = _read_image_b64(*_LOGO_REL_PATH)
    favicon = _read_image_b64(*_FAVICON_REL_PATH)
    if not logo:
        _logger.warning("logo.png not found, skipping logo application")
        return
    # web_favicon adds res.company.favicon; guard for setups without it.
    company_has_favicon = 'favicon' in env['res.company']._fields
    for company in env['res.company'].search([]):
        vals = {}
        if _differs(company.logo, logo):
            vals['logo'] = logo
        if favicon and company_has_favicon and _differs(company.favicon, favicon):
            vals['favicon'] = favicon
        if vals:
            company.write(vals)
            _logger.info("Set logo/favicon on res.company %s: %s", company.id, list(vals))
    for website in env['website'].search([]):
        vals = {}
        if _differs(website.logo, logo):
            vals['logo'] = logo
        if favicon and _differs(website.favicon, favicon):
            vals['favicon'] = favicon
        if vals:
            website.write(vals)
            _logger.info("Set logo/favicon on website %s", website.id)


# ── 6. Repair an orphaned nav root ─────────────────────────────────────

def _ensure_website_menu_root(env):
    """Repair websites whose top-nav root (website.menu_id) is empty.

    Symptom: the whole top navigation renders empty for everyone (anonymous
    and members alike). Cause: the social leaf menus carry website_id=<site>
    while their container/root menus (defined in club_social_profile with no
    website_id) stayed website_id=False. Odoo's `website._compute_menu` only
    considers menus where website_id == the website, so it finds no parent-less
    (root) menu → website.menu_id is False → nothing is rendered.

    Fix: for any website whose menu_id is False *but* that already owns some
    menus (the broken split tree), adopt the remaining generic (website_id=False)
    menus — root + public containers — into that website, so a parent-less
    owned root exists again. Single-site safe; on a healthy install menu_id is
    set so this is a no-op. Runs first in the combined setup (the account
    container + nav reorg need a resolved root); the public menus it may adopt
    (Home/Shop/Events/Contact us) are all in PUBLIC_URLS, so the later
    _restrict_member_menus leaves them public.
    """
    Menu = env['website.menu']
    for website in env['website'].search([]):
        if website.menu_id:
            continue  # nav root resolves → nothing to repair
        if not Menu.search_count([('website_id', '=', website.id)]):
            continue  # website owns no menu at all → not the split-tree case
        generic = Menu.search([('website_id', '=', False)])
        if not generic:
            continue
        generic.write({'website_id': website.id})
        env['website'].invalidate_model(['menu_id'])
        _logger.info(
            "Repaired nav root of website %s: adopted %d generic menus (menu_id now %s)",
            website.id, len(generic), website.menu_id.id,
        )


# ── 7. Navigation IA : 3 conteneurs équilibrés ────────────────────────

def _nav_containers(env, website):
    """Return (community, network, account) top-level container menus for a
    website, resolved by their English name among the children of the nav root.

    Resolving by en_US name (not env.ref) is robust to COW/website_id copies and
    to translation: _translate_menus only adds the fr_CA term, the en_US value
    stays 'Community'/'My Network'/'My Account'. Returns empty recordsets when a
    container is missing."""
    Menu = env['website.menu'].with_context(lang='en_US')
    root = website.menu_id
    if not root:
        empty = env['website.menu'].browse()
        return empty, empty, empty

    def by_name(name_en):
        return Menu.search([
            ('website_id', '=', website.id),
            ('parent_id', '=', root.id),
            ('name', '=', name_en),
        ], limit=1)

    return by_name('Community'), by_name('My Network'), by_name('My Account')


def _ensure_account_container(env):
    """Create the 'My Account' top-level nav container if missing.

    Created with website_id=<site> (never False) and parented to website.menu_id
    — creating it generic (website_id=False) would re-introduce the orphaned-root
    bug fixed by [[_ensure_website_menu_root]] (migration 1.0.6). Placed right
    after 'My Network'. Idempotent."""
    Menu = env['website.menu']
    for website in env['website'].search([]):
        root = website.menu_id
        if not root:
            continue  # _ensure_website_menu_root must repair the root first
        _, network, account = _nav_containers(env, website)
        if account:
            continue
        seq = (network.sequence + 1) if network else 35
        Menu.create({
            'name': 'My Account',
            'url': '/my/home',
            'parent_id': root.id,
            'website_id': website.id,
            'sequence': seq,
        })
        env['website'].invalidate_model(['menu_id'])
        _logger.info("Created 'My Account' nav container on website %s (seq %s)", website.id, seq)


def _reorganize_nav(env):
    """Re-parent and re-sequence the social leaf menus into the 3 containers
    per NAV_LAYOUT, site-specifically and idempotently.

    Matches leaves by URL (not xmlid) so it is robust to modules not installed
    on a given site (e.g. lorage without negotiation/BDSM) and to COW copies.
    Excludes top-level containers that share a leaf's URL (e.g. the Community
    container historically carries url='/discover') via parent_id != root."""
    Menu = env['website.menu']
    for website in env['website'].search([]):
        root = website.menu_id
        if not root:
            continue
        community, network, account = _nav_containers(env, website)
        targets = {'community': community, 'network': network, 'account': account}
        changed = 0
        # Fix container URLs so they point to real pages instead of '#' or '/'.
        # This prevents dead links when users click the parent menu item.
        CONTAINER_URLS = {
            community: '/discover',
            network: '/my/dashboard',
            account: '/my/home',
        }
        for container, target_url in CONTAINER_URLS.items():
            if container and container.url != target_url:
                container.url = target_url
                changed += 1
        # Keep the 3 member containers consecutive (Communauté, Mon réseau,
        # Mon compte) instead of interleaved with the public Shop/Events menus.
        for container, seq in ((community, 21), (network, 22), (account, 23)):
            if container and container.sequence != seq:
                container.sequence = seq
                changed += 1
        for url, (marker, seq) in NAV_LAYOUT.items():
            container = targets.get(marker)
            if not container:
                continue
            leaves = Menu.search([
                ('website_id', '=', website.id),
                ('url', '=', url),
                ('parent_id', '!=', root.id),
            ])
            for leaf in leaves:
                vals = {}
                if leaf.parent_id.id != container.id:
                    vals['parent_id'] = container.id
                if leaf.sequence != seq:
                    vals['sequence'] = seq
                if vals:
                    leaf.write(vals)
                    changed += 1
        if changed:
            env['website'].invalidate_model(['menu_id'])
            _logger.info("Reorganized %d nav menus on website %s", changed, website.id)


# ── Combined entry point ───────────────────────────────────────────────

def _apply_diverse_setup(env):
    """Run all setup steps in the order the next one expects."""
    _ensure_fr_ca(env)
    _configure_websites(env)
    _ensure_website_menu_root(env)    # ① root nav must exist before...
    _ensure_account_container(env)    # ② ...creating the 'My Account' container
    _reorganize_nav(env)              # ③ re-parent/re-sequence into 3 containers
    _translate_menus(env)             # ④ translate containers (incl. Mon compte) + leaves
    _restrict_member_menus(env)       # ⑤ gate non-public leaves
    _open_contact_menu(env)
    _apply_logo(env)


def post_init_hook(env):
    """Called once when diverse_club_social is first installed."""
    _apply_diverse_setup(env)
