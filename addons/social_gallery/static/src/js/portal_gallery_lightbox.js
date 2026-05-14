(function () {
    'use strict';

    var photos = [];
    var current = 0;
    var overlay, img, caption, counter;

    function init() {
        var grid = document.getElementById('sn_gallery_grid');
        if (!grid) return;

        buildOverlay();

        var items = grid.querySelectorAll('[data-lightbox]');
        items.forEach(function (el, idx) {
            photos.push({
                src: el.dataset.src,
                thumb: el.dataset.thumb,
                caption: el.dataset.caption || '',
            });
            el.addEventListener('click', function (e) {
                e.preventDefault();
                open(idx);
            });
        });
    }

    function buildOverlay() {
        overlay = document.createElement('div');
        overlay.id = 'sn_lightbox';
        overlay.style.cssText = [
            'display:none', 'position:fixed', 'inset:0', 'background:rgba(0,0,0,.92)',
            'z-index:9999', 'align-items:center', 'justify-content:center',
            'flex-direction:column', 'cursor:zoom-out',
        ].join(';');

        var btnClose = btn('✕', 'top:16px;right:20px;font-size:1.6rem;');
        var btnPrev  = btn('❮', 'left:16px;top:50%;transform:translateY(-50%);font-size:2rem;');
        var btnNext  = btn('❯', 'right:16px;top:50%;transform:translateY(-50%);font-size:2rem;');

        img = document.createElement('img');
        img.style.cssText = 'max-width:90vw;max-height:82vh;object-fit:contain;border-radius:4px;cursor:default;';
        img.addEventListener('click', function (e) { e.stopPropagation(); });

        caption = document.createElement('div');
        caption.style.cssText = 'color:#ccc;font-size:.9rem;margin-top:10px;text-align:center;max-width:80vw;';

        counter = document.createElement('div');
        counter.style.cssText = 'color:#888;font-size:.75rem;margin-top:4px;';

        overlay.appendChild(btnClose);
        overlay.appendChild(btnPrev);
        overlay.appendChild(btnNext);
        overlay.appendChild(img);
        overlay.appendChild(caption);
        overlay.appendChild(counter);
        document.body.appendChild(overlay);

        btnClose.addEventListener('click', close);
        btnPrev.addEventListener('click', function (e) { e.stopPropagation(); navigate(-1); });
        btnNext.addEventListener('click', function (e) { e.stopPropagation(); navigate(1); });
        overlay.addEventListener('click', close);

        document.addEventListener('keydown', function (e) {
            if (!overlay || overlay.style.display === 'none') return;
            if (e.key === 'Escape')       close();
            else if (e.key === 'ArrowLeft')  navigate(-1);
            else if (e.key === 'ArrowRight') navigate(1);
        });
    }

    function btn(label, style) {
        var b = document.createElement('button');
        b.textContent = label;
        b.style.cssText = 'position:absolute;background:none;border:none;color:white;cursor:pointer;padding:8px;' + style;
        return b;
    }

    function open(idx) {
        current = idx;
        show();
        overlay.style.display = 'flex';
        document.body.style.overflow = 'hidden';
    }

    function close() {
        overlay.style.display = 'none';
        document.body.style.overflow = '';
    }

    function navigate(dir) {
        current = (current + dir + photos.length) % photos.length;
        show();
    }

    function show() {
        var p = photos[current];
        img.src = p.src;
        caption.textContent = p.caption;
        counter.textContent = (current + 1) + ' / ' + photos.length;
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
