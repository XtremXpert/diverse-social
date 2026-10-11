(function () {
    document.addEventListener('DOMContentLoaded', function () {
        var el = document.getElementById('profile_compat_widget');
        if (!el || el.dataset.isOwn === '1') return;

        var profileId = el.dataset.profileId;
        if (!profileId) return;

        fetch('/social/api/profile/' + profileId + '/compatibility', {
            credentials: 'same-origin'
        })
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (data) {
            if (!data || !data.success) return;
            var d = data.data;

            document.getElementById('sn_compat_card').style.display = '';

            var score = d.score || 0;
            document.getElementById('sn_compat_score').textContent = score + '%';

            document.getElementById('sn_compat_arc').setAttribute(
                'stroke-dasharray', score + ' ' + (100 - score)
            );

            var color = score >= 70 ? '#28a745' : score >= 40 ? '#e94560' : '#999';
            document.getElementById('sn_compat_arc').style.stroke = color;
            document.getElementById('sn_compat_score').style.color = color;

            var details = [];
            if (d.role_score !== undefined)
                details.push('Rôles : ' + d.role_score + '%');
            if (d.kink_score !== undefined)
                details.push('Intérêts : ' + d.kink_score + '%');
            document.getElementById('sn_compat_details').textContent = details.join(' · ');

            var kEl = document.getElementById('sn_compat_kinks');
            if (d.shared_kinks && d.shared_kinks.length) {
                var html = '<div style="font-size:0.78rem; color:#555; margin-bottom:4px;">En commun :</div>';
                html += d.shared_kinks.map(function (k) {
                    return '<span style="display:inline-block; background:#f0f0f0; border-radius:10px; padding:2px 8px; margin:2px; font-size:0.75rem;">' +
                           k.replace(/&/g, '&amp;').replace(/</g, '&lt;') + '</span>';
                }).join('');
                kEl.innerHTML = html;
            } else {
                kEl.innerHTML = '<span style="font-size:0.78rem; color:#999;">Aucun intérêt en commun</span>';
            }
        })
        .catch(function () {});
    });
})();
