/** @odoo-module **/
/**
 * Coin Santé — auto-évaluation anonyme (Phase 2). Vanilla JS, no OWL.
 *
 * Contrainte non négociable : AUCUNE requête réseau, AUCUN stockage
 * (ni cookie, ni localStorage). La matrice complète est embarquée dans
 * l'attribut data-payload de la page ; cocher une case ne fait que
 * recalculer le résumé en mémoire. Fermer la page ne laisse aucune trace.
 */
import { _t } from "@web/core/l10n/translation";

const LEVEL_ORDER = { faible: 1, modere: 2, eleve: 3 };
const LEVEL_CLASS = {
    faible: 'bg-success',
    modere: 'bg-warning text-dark',
    eleve: 'bg-danger',
};

function levelLabels() {
    return { faible: _t("Faible"), modere: _t("Modéré"), eleve: _t("Élevé") };
}

function esc(text) {
    const div = document.createElement('div');
    div.textContent = text == null ? '' : String(text);
    return div.innerHTML;
}

function levelBadge(level) {
    return '<span class="badge rounded-pill ' + (LEVEL_CLASS[level] || 'bg-secondary') + '">'
        + esc(levelLabels()[level] || level) + '</span>';
}

function init() {
    const root = document.getElementById('coin_sante_autoeval');
    if (!root) return;

    let data;
    try {
        data = JSON.parse(root.dataset.payload || '{}');
    } catch (_) {
        return;
    }
    const practiceNames = {};
    (data.practices || []).forEach((p) => { practiceNames[p.id] = p.name; });

    const checkboxes = Array.from(root.querySelectorAll('.o_autoeval_practice'));
    const results = root.querySelector('.o_autoeval_results');
    const empty = root.querySelector('.o_autoeval_empty');
    const counter = root.querySelector('.o_autoeval_count');
    const infectionsEl = root.querySelector('.o_autoeval_infections');
    const preventionsEl = root.querySelector('.o_autoeval_preventions');
    const screeningEl = root.querySelector('.o_autoeval_screening');

    function selectedIds() {
        return checkboxes.filter((c) => c.checked).map((c) => parseInt(c.value, 10));
    }

    function computeInfections(selected) {
        // Par infection : niveau max parmi les pratiques cochées,
        // pratiques contributrices et notes explicatives.
        const byInfection = {};
        (data.risks || []).forEach((r) => {
            if (!selected.includes(r.p)) return;
            const inf = (data.infections || {})[String(r.i)];
            if (!inf) return;
            let entry = byInfection[r.i];
            if (!entry) {
                entry = byInfection[r.i] = {
                    id: r.i, name: inf.name, level: r.level,
                    practices: [], notes: [],
                    window: inf.window, screening: inf.screening, vaccine: inf.vaccine,
                };
            }
            if ((LEVEL_ORDER[r.level] || 0) > (LEVEL_ORDER[entry.level] || 0)) {
                entry.level = r.level;
            }
            const pname = practiceNames[r.p];
            if (pname && !entry.practices.includes(pname)) entry.practices.push(pname);
            if (r.note && !entry.notes.includes(r.note)) entry.notes.push(r.note);
        });
        return Object.values(byInfection).sort((a, b) =>
            (LEVEL_ORDER[b.level] || 0) - (LEVEL_ORDER[a.level] || 0)
            || a.name.localeCompare(b.name));
    }

    function computePreventions(selected, infectionIds) {
        const specific = [];
        const transversal = [];
        (data.preventions || []).forEach((v) => {
            if (v.transversal) {
                transversal.push(v);
                return;
            }
            const matchPractice = (v.practices || []).some((id) => selected.includes(id));
            const matchInfection = (v.infections || []).some((id) => infectionIds.includes(id));
            if (matchPractice || matchInfection) specific.push(v);
        });
        return { specific, transversal };
    }

    function render() {
        const selected = selectedIds();
        counter.textContent = selected.length
            ? (selected.length > 1
                ? _t("%s pratiques cochées") : _t("%s pratique cochée")
              ).replace('%s', selected.length)
            : '';

        if (!selected.length) {
            results.classList.add('d-none');
            empty.classList.remove('d-none');
            return;
        }
        results.classList.remove('d-none');
        empty.classList.add('d-none');

        const infections = computeInfections(selected);
        const { specific, transversal } = computePreventions(
            selected, infections.map((i) => i.id));

        // Infections à considérer
        if (infections.length) {
            let html = '<h3 class="h5 mb-2">' + esc(_t("Infections à considérer")) + '</h3>'
                + '<div class="table-responsive"><table class="table table-sm align-middle">'
                + '<thead><tr><th>' + esc(_t("Infection")) + '</th><th>' + esc(_t("Risque"))
                + '</th><th>' + esc(_t("Via")) + '</th><th>' + esc(_t("Note")) + '</th></tr></thead><tbody>';
            infections.forEach((inf) => {
                html += '<tr><td>' + esc(inf.name)
                    + (inf.vaccine ? ' <span class="badge bg-light text-dark border">'
                        + esc(_t("Vaccin disponible")) + '</span>' : '')
                    + '</td><td>' + levelBadge(inf.level)
                    + '</td><td class="small text-muted">' + esc(inf.practices.join(', '))
                    + '</td><td class="small text-muted">' + esc(inf.notes.join(' ')) + '</td></tr>';
            });
            html += '</tbody></table></div>';
            infectionsEl.innerHTML = html;
        } else {
            infectionsEl.innerHTML = '<p class="text-muted">'
                + esc(_t("Aucune infection répertoriée pour cette sélection dans le guide actuel."))
                + '</p>';
        }

        // Réduire les risques
        let prevHtml = '';
        if (specific.length) {
            prevHtml += '<h3 class="h5 mb-2">' + esc(_t("Réduire les risques")) + '</h3><ul class="mb-3">';
            specific.forEach((v) => {
                prevHtml += '<li><span class="fw-semibold">' + esc(v.name) + '</span>'
                    + (v.description ? ' <span class="small text-muted">— ' + esc(v.description) + '</span>' : '')
                    + '</li>';
            });
            prevHtml += '</ul>';
        }
        if (transversal.length) {
            prevHtml += '<h3 class="h6 mb-2 text-muted">' + esc(_t("Dans tous les cas")) + '</h3><ul>';
            transversal.forEach((v) => {
                prevHtml += '<li><span class="fw-semibold">' + esc(v.name) + '</span>'
                    + (v.description ? ' <span class="small text-muted">— ' + esc(v.description) + '</span>' : '')
                    + '</li>';
            });
            prevHtml += '</ul>';
        }
        preventionsEl.innerHTML = prevHtml;

        // Dépistage suggéré
        const screenable = infections.filter((i) => i.screening || i.window);
        if (screenable.length) {
            let html = '<h3 class="h5 mb-2">' + esc(_t("Dépistage suggéré")) + '</h3><ul>';
            screenable.forEach((inf) => {
                html += '<li><span class="fw-semibold">' + esc(inf.name) + '</span>';
                const parts = [];
                if (inf.screening) parts.push(esc(inf.screening));
                if (inf.window) parts.push(esc(_t("fiable après %s").replace('%s', inf.window)));
                if (parts.length) html += ' <span class="small text-muted">— ' + parts.join(' · ') + '</span>';
                html += '</li>';
            });
            html += '</ul><p class="small text-muted">'
                + esc(_t("Le dépistage régulier reste pertinent même sans symptôme — plusieurs infections passent inaperçues."))
                + '</p>';
            if (document.getElementById('ressources')) {
                html += '<p><a href="#ressources">' + esc(_t("Où agir près de chez toi ↓")) + '</a></p>';
            }
            screeningEl.innerHTML = html;
        } else {
            screeningEl.innerHTML = '';
        }
    }

    checkboxes.forEach((c) => c.addEventListener('change', render));
    const clearBtn = root.querySelector('.o_autoeval_clear');
    if (clearBtn) {
        clearBtn.addEventListener('click', () => {
            checkboxes.forEach((c) => { c.checked = false; });
            render();
        });
    }
    render();
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}
