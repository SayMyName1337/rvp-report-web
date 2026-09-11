/* Загрузка суточного рапорта: перетаскивание файла и защита
   от повторного нажатия.

   Проверки здесь — только для удобства: они подсказывают раньше,
   но ничего не решают. Настоящая проверка выполняется на сервере,
   в UploadForm, и обойти её нельзя. */

(function () {
    'use strict';

    var form = document.getElementById('upload-form');
    var zone = document.getElementById('dropzone');
    var title = document.getElementById('dropzone-title');
    var submit = document.getElementById('submit');
    var progress = document.getElementById('progress');
    if (!form || !zone) {
        return;
    }

    var input = zone.querySelector('input[type="file"]');
    if (!input) {
        return;
    }

    function describe(file) {
        var mb = file.size / (1024 * 1024);
        return file.name + ' · ' + mb.toFixed(2).replace('.', ',') + ' МБ';
    }

    function chosen() {
        if (input.files.length) {
            title.textContent = describe(input.files[0]);
            zone.classList.add('dropzone--filled');
        } else {
            title.textContent = 'Перетащите сюда файл рапорта';
            zone.classList.remove('dropzone--filled');
        }
    }

    zone.addEventListener('click', function (event) {
        if (event.target !== input) {
            input.click();
        }
    });

    input.addEventListener('change', chosen);

    ['dragenter', 'dragover'].forEach(function (name) {
        zone.addEventListener(name, function (event) {
            event.preventDefault();
            zone.classList.add('dropzone--over');
        });
    });

    ['dragleave', 'drop'].forEach(function (name) {
        zone.addEventListener(name, function (event) {
            event.preventDefault();
            zone.classList.remove('dropzone--over');
        });
    });

    zone.addEventListener('drop', function (event) {
        if (event.dataTransfer.files.length) {
            input.files = event.dataTransfer.files;
            chosen();
        }
    });

    form.addEventListener('submit', function () {
        // Разбор идёт несколько секунд. Без этого человек нажимает
        // кнопку второй раз и загружает тот же файл дважды.
        submit.disabled = true;
        submit.textContent = 'Загружаю…';
        progress.style.display = 'inline';
    });

    chosen();
}());
