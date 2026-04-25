(function () {
    function setExpanded(open) {
        var toggle = document.querySelector('.shell-menu-toggle');
        if (toggle) toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    }

    function openSidebar() {
        document.body.classList.add('sidebar-open');
        setExpanded(true);
    }

    function closeSidebar() {
        document.body.classList.remove('sidebar-open');
        setExpanded(false);
    }

    function bindSidebar() {
        var toggle = document.querySelector('.shell-menu-toggle');
        var backdrop = document.querySelector('.shell-backdrop');
        if (toggle) {
            toggle.setAttribute('aria-expanded', 'false');
            toggle.addEventListener('click', function () {
                if (document.body.classList.contains('sidebar-open')) {
                    closeSidebar();
                } else {
                    openSidebar();
                }
            });
        }
        if (backdrop) {
            backdrop.addEventListener('click', closeSidebar);
        }
        // Close on link tap so the menu doesn't stay open over the next page.
        document.querySelectorAll('.app-sidebar-link, .app-sidebar-cta').forEach(function (link) {
            link.addEventListener('click', closeSidebar);
        });
        // Esc key closes the menu (keyboard / screen-reader users).
        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape' && document.body.classList.contains('sidebar-open')) {
                closeSidebar();
            }
        });
    }

    function syncUserChip() {
        var u = {};
        try {
            u = JSON.parse(localStorage.getItem('user') || '{}');
        } catch (e) {}
        var name = (u.name || u.phone || 'User').trim() || 'User';
        var initial = name.charAt(0).toUpperCase();
        document.querySelectorAll('.js-shell-user-name').forEach(function (el) {
            el.textContent = name;
        });
        document.querySelectorAll('.js-shell-user-initial').forEach(function (el) {
            el.textContent = initial;
        });
    }

    function run() {
        bindSidebar();
        syncUserChip();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', run);
    } else {
        run();
    }

    window.refreshShellUser = syncUserChip;
})();
