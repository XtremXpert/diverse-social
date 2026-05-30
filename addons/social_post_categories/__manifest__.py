{
    'name': 'Social — Post categories',
    'version': '19.0.1.0.0',
    'category': 'Social',
    'summary': 'Generic category taxonomy for social_base.post (annonce/alerte/question/...)',
    'description': """
Adds a ``category_id`` Many2one on ``social_base.post`` referring to a new
model ``social_post_categories.category`` (stable ``code`` field + name +
color + icon + sequence).

This module ships **no categories of its own**. Leaf modules (per-community
configs) pre-populate the categories that match their use case — see
``st_isidore_city_club`` for a municipal example.

Exposed via ``/social/api/posts``:

- POST accepts ``category_code`` (preferred, stable across DBs) or
  ``category_id`` (fallback).
- GET / responses include ``category`` as ``{id, code, name, color}`` or
  ``null``.

Deleting a category sets ``post.category_id`` to NULL — content is more
valuable than its categorisation.
""",
    'author': 'Bemade',
    'license': 'LGPL-3',
    'depends': [
        'social_base',
        'social_group',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/category_views.xml',
        'views/post_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
