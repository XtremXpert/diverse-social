"""Migration to 19.0.1.0.1: group_social_user no longer implies base.group_user.

Consequence: any user holding `group_social_user` but no user-type role
(Role / User or Role / Portal) would become an "orphan" account (state
rejected by `res.users._check_one_user_type`). This migration grants them
`base.group_portal` so they become proper portal users — which is the
intent for club members.

Moderators (`group_social_moderator`) keep their internal access through
the new `base.group_user` implication added on their group.
"""


def migrate(cr, version):
    if not version:
        return

    cr.execute("""
        SELECT res_id FROM ir_model_data
        WHERE module = 'social_base' AND name = 'group_social_user'
    """)
    row = cr.fetchone()
    if not row:
        return
    social_user_gid = row[0]

    cr.execute("""
        SELECT res_id FROM ir_model_data
        WHERE module = 'social_base' AND name = 'group_social_moderator'
    """)
    row = cr.fetchone()
    if not row:
        return
    social_moderator_gid = row[0]

    cr.execute("""
        SELECT res_id FROM ir_model_data
        WHERE module = 'base' AND name = 'group_portal'
    """)
    row = cr.fetchone()
    if not row:
        return
    portal_gid = row[0]

    cr.execute("""
        SELECT res_id FROM ir_model_data
        WHERE module = 'base' AND name = 'group_user'
    """)
    internal_gid = cr.fetchone()[0]

    # ── 1. Mirror the new implication architecture ─────────────────────────
    #     The XML uses <data noupdate="1"> so Odoo never syncs implied_ids
    #     on update. We do it here once for all.
    # group_social_user no longer implies base.group_user
    cr.execute("""
        DELETE FROM res_groups_implied_rel
        WHERE gid = %s AND hid = %s
    """, (social_user_gid, internal_gid))
    # group_social_moderator now implies base.group_user
    cr.execute("""
        INSERT INTO res_groups_implied_rel (gid, hid)
        VALUES (%s, %s)
        ON CONFLICT DO NOTHING
    """, (social_moderator_gid, internal_gid))

    # Social-network members that have no Odoo user-type role:
    # they were "internal" by implication; after the migration they must
    # receive the Portal role explicitly.
    cr.execute("""
        SELECT DISTINCT r.uid
        FROM res_groups_users_rel r
        WHERE r.gid = %s
          AND r.uid NOT IN (
              SELECT uid FROM res_groups_users_rel
              WHERE gid IN (%s, %s)
          )
          AND r.uid NOT IN (
              -- exclude any user that already inherits Role/User via another group
              -- (admins, settings users, etc.)
              SELECT DISTINCT r2.uid
              FROM res_groups_users_rel r2
              JOIN res_groups_implied_rel ir ON ir.gid = r2.gid
              WHERE ir.hid = %s
          )
    """, (social_user_gid, portal_gid, internal_gid, internal_gid))

    user_ids = [row[0] for row in cr.fetchall()]
    if not user_ids:
        return

    # Bulk insertion: portal_group for each affected user.
    cr.executemany(
        "INSERT INTO res_groups_users_rel (gid, uid) VALUES (%s, %s) "
        "ON CONFLICT DO NOTHING",
        [(portal_gid, uid) for uid in user_ids],
    )
