(function () {
    function closeSidebar() {
        document.body.classList.remove('sidebar-open');
    }

    function bindSidebar() {
        var toggle = document.querySelector('.shell-menu-toggle');
        var backdrop = document.querySelector('.shell-backdrop');
        if (toggle) {
            toggle.addEventListener('click', function () {
                document.body.classList.toggle('sidebar-open');
            });
        }
        if (backdrop) {
            backdrop.addEventListener('click', closeSidebar);
        }
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
