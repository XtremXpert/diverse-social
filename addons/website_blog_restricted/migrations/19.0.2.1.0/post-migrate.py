"""
Migration 19.0.2.1.0 — website_blog_restricted

Les blogs créés avant l'installation du module ont visibility = NULL.
Le fallback dans _is_accessible_by les traitait comme 'members', bloquant
les utilisateurs portail. On les passe explicitement à 'public'.
"""


def migrate(cr, version):
    cr.execute("""
        UPDATE blog_blog
        SET visibility = 'public'
        WHERE visibility IS NULL
    """)
