/* Инструкция: печать и отметка раздела, который сейчас на экране.

   Оба удобства необязательные — без сценария страница остаётся
   полностью читаемой, а печать доступна обычным Ctrl+P. */

(function () {
    'use strict';

    var button = document.getElementById('print-guide');
    if (button) {
        button.addEventListener('click', function () {
            window.print();
        });
    }

    var links = Array.prototype.slice.call(
        document.querySelectorAll('.guide__toc a'));
    var sections = links.map(function (link) {
        return document.querySelector(link.getAttribute('href'));
    });
    if (!sections.length || !window.IntersectionObserver) {
        return;
    }

    var watcher = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
            var index = sections.indexOf(entry.target);
            if (index < 0) {
                return;
            }
            links[index].classList.toggle('is-current', entry.isIntersecting);
        });
    }, {rootMargin: '-80px 0px -70% 0px'});

    sections.forEach(function (section) {
        if (section) {
            watcher.observe(section);
        }
    });
}());
